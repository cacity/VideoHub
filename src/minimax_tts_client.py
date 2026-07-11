"""MiniMax text-to-speech HTTP client used by VideoHub dubbing."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

import requests


DEFAULT_API_URL = "https://api.minimaxi.com/v1/t2a_v2"
DEFAULT_MODEL = "speech-2.8-turbo"
DEFAULT_VOICE_ID = "female-shaonv"
SUPPORTED_MODELS = {
    "speech-2.8-turbo",
    "speech-2.8-hd",
    "speech-2.6-turbo",
    "speech-2.6-hd",
    "speech-02-turbo",
    "speech-02-hd",
}


class MiniMaxTTSClient:
    """Generate WAV files through MiniMax's synchronous T2A API."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        model: str | None = None,
        voice_id: str | None = None,
        speed: float = 1.0,
        language_boost: str | None = None,
        timeout: int = 180,
        max_retries: int = 5,
        min_request_interval: float | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("MINIMAX_API_KEY") or "").strip()
        self.api_url = (
            api_url or os.getenv("MINIMAX_TTS_API_URL") or DEFAULT_API_URL
        ).strip()
        self.model = (model or os.getenv("MINIMAX_TTS_MODEL") or DEFAULT_MODEL).strip()
        self.voice_id = (
            voice_id or os.getenv("MINIMAX_TTS_VOICE_ID") or DEFAULT_VOICE_ID
        ).strip()
        self.speed = float(speed)
        self.language_boost = (
            language_boost
            or os.getenv("MINIMAX_TTS_LANGUAGE_BOOST")
            or "Chinese"
        ).strip()
        self.timeout = max(10, int(timeout))
        self.max_retries = max(0, int(max_retries))
        self.min_request_interval = max(
            0.0,
            float(
                min_request_interval
                if min_request_interval is not None
                else os.getenv("MINIMAX_TTS_REQUEST_INTERVAL_SECONDS", "1.5")
            ),
        )
        self.rate_limit_backoff = max(
            1.0,
            float(os.getenv("MINIMAX_TTS_RATE_LIMIT_BACKOFF_SECONDS", "20")),
        )
        self._last_request_started = 0.0

        if not self.api_key:
            raise ValueError("未配置 MiniMax API Key")
        if not self.api_url.startswith(("https://", "http://")):
            raise ValueError("MiniMax TTS API 地址无效")
        if self.model not in SUPPORTED_MODELS:
            raise ValueError(f"不支持的 MiniMax TTS 模型: {self.model}")
        if not self.voice_id:
            raise ValueError("MiniMax Voice ID 不能为空")
        if not 0.5 <= self.speed <= 2.0:
            raise ValueError("MiniMax TTS 语速必须在 0.5 到 2.0 之间")

    def synthesize(self, text: str, output_path: str | Path | None = None) -> str:
        """Synthesize text, save the returned WAV bytes, and return its path."""
        clean_text = self._clean_text(text)
        if not clean_text:
            raise ValueError("MiniMax TTS 文本为空")
        if len(clean_text) >= 10000:
            raise ValueError("MiniMax TTS 单次文本必须少于 10000 字符")

        payload = {
            "model": self.model,
            "text": clean_text,
            "stream": False,
            "language_boost": self.language_boost or "auto",
            "output_format": "hex",
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": self.speed,
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "wav",
                "channel": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = self._post_with_retry(payload, headers)
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg") or "未知错误"
            trace_id = data.get("trace_id") or "unknown"
            raise RuntimeError(
                f"MiniMax TTS 请求失败: {status_msg} "
                f"(status_code={status_code}, trace_id={trace_id})"
            )

        audio_hex = (data.get("data") or {}).get("audio")
        if not audio_hex:
            trace_id = data.get("trace_id") or "unknown"
            raise RuntimeError(f"MiniMax TTS 未返回音频数据 (trace_id={trace_id})")

        try:
            audio_bytes = bytes.fromhex(audio_hex)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("MiniMax TTS 返回的音频编码无效") from exc

        if len(audio_bytes) < 44 or not audio_bytes.startswith(b"RIFF"):
            raise RuntimeError("MiniMax TTS 返回的 WAV 文件无效")

        target = Path(output_path) if output_path else self._default_output_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio_bytes)
        return str(target.resolve())

    def _post_with_retry(self, payload: dict, headers: dict) -> dict:
        retry_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                self._wait_for_rate_slot()
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                self._last_request_started = time.monotonic()
                if response.status_code in retry_statuses and attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                if not response.ok:
                    raise RuntimeError(
                        f"MiniMax TTS HTTP {response.status_code}: "
                        f"{self._safe_error_text(response.text)}"
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise RuntimeError("MiniMax TTS 返回了无效 JSON") from exc

                base_resp = data.get("base_resp") or {}
                status_code = base_resp.get("status_code", 0)
                status_msg = str(base_resp.get("status_msg") or "")
                is_rate_limited = (
                    str(status_code) == "1002"
                    or "rate limit" in status_msg.lower()
                    or "rpm" in status_msg.lower()
                )
                if is_rate_limited and attempt < self.max_retries:
                    delay = min(120.0, self.rate_limit_backoff * (attempt + 1))
                    time.sleep(delay)
                    continue
                return data
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                break

        raise RuntimeError(f"MiniMax TTS 网络请求失败: {last_error}") from last_error

    def _wait_for_rate_slot(self) -> None:
        if self.min_request_interval <= 0 or self._last_request_started <= 0:
            return
        elapsed = time.monotonic() - self._last_request_started
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _safe_error_text(text: str, max_length: int = 300) -> str:
        safe = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", text or "")
        return safe[:max_length]

    @staticmethod
    def _default_output_path() -> Path:
        try:
            from .paths_config import DUBBING_TEMP_DIR
        except ImportError:
            from paths_config import DUBBING_TEMP_DIR

        filename = f"minimax_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.wav"
        return Path(DUBBING_TEMP_DIR) / "minimax" / filename
