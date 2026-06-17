"""HTTP client for the local CosyVoice TTS service."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Literal

import requests


CosyVoiceMode = Literal["sft", "instruct"]


class CosyVoiceTTSClient:
    def __init__(
        self,
        base_url: str | None = None,
        mode: CosyVoiceMode = "sft",
        speaker: str = "中文女",
        instruction: str = "",
        timeout: int = 600,
    ) -> None:
        self.base_url = (base_url or os.getenv("COSYVOICE_TTS_URL") or "http://127.0.0.1:8877").rstrip("/")
        self.mode = mode if mode in {"sft", "instruct"} else "sft"
        self.speaker = speaker or os.getenv("COSYVOICE_TTS_SPEAKER", "中文女")
        self.instruction = instruction or os.getenv(
            "COSYVOICE_TTS_INSTRUCTION",
            "用自然、清晰、适合视频讲解的语气朗读，句子之间保留适当停顿。",
        )
        self.timeout = timeout

    def check_health(self) -> dict:
        response = requests.get(f"{self.base_url}/health", timeout=10)
        response.raise_for_status()
        return response.json()

    def synthesize(self, text: str) -> str:
        text = self._clean_text(text)
        if not text:
            raise ValueError("CosyVoice TTS 文本为空")

        if self.mode == "instruct":
            endpoint = f"{self.base_url}/tts/instruct"
            payload = {
                "text": text,
                "speaker": self.speaker,
                "instruction": self.instruction,
            }
        else:
            endpoint = f"{self.base_url}/tts/sft"
            payload = {
                "text": text,
                "speaker": self.speaker,
            }

        response = requests.post(endpoint, json=payload, timeout=self.timeout)
        if not response.ok:
            raise RuntimeError(f"CosyVoice TTS 请求失败: {response.status_code} {response.text}")

        data = response.json()
        file_path = data.get("file_path")
        if not file_path or not Path(file_path).exists():
            raise RuntimeError(f"CosyVoice TTS 未返回有效音频文件: {data}")
        return file_path

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def wait_for_service(base_url: str, timeout_seconds: int = 5) -> bool:
        deadline = time.time() + timeout_seconds
        url = base_url.rstrip("/") + "/health"
        while time.time() < deadline:
            try:
                response = requests.get(url, timeout=2)
                if response.ok:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False
