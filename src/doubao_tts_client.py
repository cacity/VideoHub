"""Doubao/Volcengine asynchronous text-to-speech client for VideoHub."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests

DEFAULT_API_BASE = "https://openspeech.bytedance.com/api/v1/tts_async"
DEFAULT_RESOURCE_ID = "volc.tts_async.default"
DEFAULT_VOICE_TYPE = "BV701_streaming"


class DoubaoTTSClient:
    """Generate WAV files through the official Doubao async TTS HTTP API."""

    def __init__(
        self,
        app_id: str | None = None,
        access_token: str | None = None,
        resource_id: str | None = None,
        api_base: str | None = None,
        voice_type: str | None = None,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: float = 1.0,
        sample_rate: int = 24000,
        timeout: int | None = None,
        poll_interval: float | None = None,
        request_timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.app_id = (app_id or os.getenv("DOUBAO_TTS_APP_ID") or "").strip()
        self.access_token = (
            access_token or os.getenv("DOUBAO_TTS_ACCESS_TOKEN") or ""
        ).strip()
        self.resource_id = (
            resource_id
            or os.getenv("DOUBAO_TTS_RESOURCE_ID")
            or DEFAULT_RESOURCE_ID
        ).strip()
        self.api_base = (
            api_base or os.getenv("DOUBAO_TTS_API_BASE") or DEFAULT_API_BASE
        ).strip().rstrip("/")
        self.voice_type = (
            voice_type
            or os.getenv("DOUBAO_TTS_VOICE_TYPE")
            or DEFAULT_VOICE_TYPE
        ).strip()
        self.speed = float(speed)
        self.volume = float(volume)
        self.pitch = float(pitch)
        self.sample_rate = int(sample_rate)
        self.timeout = max(
            30,
            int(
                timeout
                if timeout is not None
                else os.getenv("DOUBAO_TTS_TIMEOUT_SECONDS", "900")
            ),
        )
        self.poll_interval = max(
            1.0,
            float(
                poll_interval
                if poll_interval is not None
                else os.getenv("DOUBAO_TTS_POLL_INTERVAL_SECONDS", "5")
            ),
        )
        self.request_timeout = max(10, int(request_timeout))
        self.session = session or requests.Session()

        if not self.app_id:
            raise ValueError("未配置豆包 TTS AppID")
        if not self.access_token:
            raise ValueError("未配置豆包 TTS Access Token")
        if not self.resource_id:
            raise ValueError("豆包 TTS Resource ID 不能为空")
        if not self.voice_type:
            raise ValueError("豆包 TTS voice_type 不能为空")
        if not self.api_base.startswith(("https://", "http://")):
            raise ValueError("豆包 TTS API 地址无效")
        if not 0.2 <= self.speed <= 3.0:
            raise ValueError("豆包 TTS 语速必须在 0.2 到 3.0 之间")
        if not 0.1 <= self.volume <= 3.0:
            raise ValueError("豆包 TTS 音量必须在 0.1 到 3.0 之间")
        if not 0.1 <= self.pitch <= 3.0:
            raise ValueError("豆包 TTS 音调必须在 0.1 到 3.0 之间")

    def synthesize(self, text: str, output_path: str | Path) -> str:
        clean_text = self._clean_text(text)
        if not clean_text:
            raise ValueError("豆包 TTS 文本为空")
        if len(clean_text) >= 100000:
            raise ValueError("豆包异步 TTS 单次文本必须少于 100000 字符")

        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        task_path = target.with_suffix(target.suffix + ".task.json")
        identity = self._identity(clean_text)
        task_id = self._resume_task_id(task_path, identity)
        if not task_id:
            task_id = self._submit(clean_text)
            self._write_task_record(
                task_path,
                {
                    "schema_version": "1.0",
                    "provider": "doubao",
                    "task_id": task_id,
                    "identity": identity,
                    "voice_type": self.voice_type,
                    "resource_id": self.resource_id,
                    "status": "submitted",
                },
            )

        result = self._poll(task_id)
        audio_url = str(result.get("audio_url") or "").strip()
        if not audio_url:
            raise RuntimeError(f"豆包 TTS 任务完成但未返回音频地址: {task_id}")
        self._download_audio(audio_url, target)
        self._write_task_record(
            task_path,
            {
                "schema_version": "1.0",
                "provider": "doubao",
                "task_id": task_id,
                "identity": identity,
                "voice_type": self.voice_type,
                "resource_id": self.resource_id,
                "status": "complete",
                "sentences": result.get("sentences", []),
            },
        )
        return str(target)

    def _submit(self, text: str) -> str:
        payload = {
            "appid": self.app_id,
            "reqid": uuid.uuid4().hex,
            "text": text,
            "format": "wav",
            "voice_type": self.voice_type,
            "language": "zh",
            "sample_rate": self.sample_rate,
            "volume": self.volume,
            "speed": self.speed,
            "pitch": self.pitch,
            "enable_subtitle": 1,
        }
        response = self.session.post(
            f"{self.api_base}/submit",
            json=payload,
            headers=self._headers(),
            timeout=self.request_timeout,
        )
        data = self._response_json(response, "提交")
        task_id = str(data.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError(
                "豆包 TTS 提交失败: "
                f"{self._safe_message(data.get('message') or data)}"
            )
        return task_id

    def _poll(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            response = self.session.get(
                f"{self.api_base}/query",
                params={"appid": self.app_id, "task_id": task_id},
                headers=self._headers(),
                timeout=self.request_timeout,
            )
            data = self._response_json(response, "查询")
            status = int(data.get("task_status", 0) or 0)
            if status == 1:
                return data
            if status == 2 or data.get("code"):
                raise RuntimeError(
                    "豆包 TTS 合成失败: "
                    f"{self._safe_message(data.get('message') or data)} "
                    f"(task_id={task_id})"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "豆包 TTS 任务仍在处理中，已保留 task_id，稍后重试会继续查询: "
                    f"{task_id}"
                )
            time.sleep(self.poll_interval)

    def _download_audio(self, audio_url: str, target: Path) -> None:
        response = self.session.get(audio_url, timeout=self.request_timeout)
        if not response.ok:
            raise RuntimeError(
                f"豆包 TTS 音频下载失败: HTTP {response.status_code}"
            )
        audio = response.content
        if len(audio) < 44 or not audio.startswith(b"RIFF"):
            raise RuntimeError("豆包 TTS 返回的 WAV 文件无效")
        target.write_bytes(audio)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer; {self.access_token}",
            "Resource-Id": self.resource_id,
            "Content-Type": "application/json",
        }

    def _identity(self, text: str) -> str:
        value = (
            f"{self.voice_type}|{self.speed:.3f}|{self.volume:.3f}|"
            f"{self.pitch:.3f}|{self.sample_rate}|{text}"
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _resume_task_id(path: Path, identity: str) -> str:
        if not path.is_file():
            return ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if data.get("identity") != identity:
            return ""
        return str(data.get("task_id") or "").strip()

    @staticmethod
    def _write_task_record(path: Path, data: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _response_json(response: requests.Response, action: str) -> dict[str, Any]:
        if not response.ok:
            raise RuntimeError(
                f"豆包 TTS {action}请求失败: HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"豆包 TTS {action}返回了无效 JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"豆包 TTS {action}返回格式无效")
        return data

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _safe_message(value: Any, max_length: int = 300) -> str:
        text = str(value or "")
        text = re.sub(r"(?:Bearer;?\s*)?[A-Za-z0-9_-]{24,}", "[REDACTED]", text)
        return text[:max_length]
