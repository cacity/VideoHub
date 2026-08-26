from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@dataclass(slots=True)
class DesktopSettings:
    workspace_dir: str
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    proxy: str = ""
    whisper_model: str = "small"
    target_language: str = "zh-CN"
    translation_method: str = "google"
    translation_polish: bool = False
    tts_backend: str = "minimax"
    cosyvoice_url: str = "http://127.0.0.1:8877"
    cosyvoice_mode: str = "sft"
    cosyvoice_speaker: str = "中文女"
    cosyvoice_instruction: str = ""
    minimax_api_url: str = "https://api.minimaxi.com/v1/t2a_v2"
    minimax_model: str = "speech-2.8-turbo"
    minimax_voice_id: str = "Chinese (Mandarin)_Male_Announcer"
    minimax_language_boost: str = "Chinese"
    subtitle_font_zh: str = "Microsoft YaHei"
    subtitle_font_zh_size: int = 48
    subtitle_font_en: str = "Arial"
    subtitle_font_en_size: int = 38
    ytdlp_mode: str = "python"
    ytdlp_exe_path: str = ""
    koushare_username: str = ""
    idle_start: str = "23:00"
    idle_end: str = "07:00"

    @classmethod
    def defaults(cls, data_dir: Path) -> DesktopSettings:
        workspace = Path(os.environ.get("VIDEOHUB_WORKSPACE_DIR", data_dir / "workspace"))
        return cls(workspace_dir=str(workspace.expanduser().resolve()))

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class SettingsStore:
    _ALLOWED_FIELDS = set(DesktopSettings.__dataclass_fields__)

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.expanduser().resolve()
        self.path = self.data_dir / "settings.json"
        self.settings = self._load()

    def _load(self) -> DesktopSettings:
        defaults = DesktopSettings.defaults(self.data_dir)
        if not self.path.is_file():
            return defaults
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        values = defaults.public_dict()
        values.update({key: value for key, value in payload.items() if key in self._ALLOWED_FIELDS})
        return DesktopSettings(**values)

    def update(self, changes: dict[str, Any]) -> DesktopSettings:
        unknown = sorted(set(changes) - self._ALLOWED_FIELDS)
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(unknown)}")
        values = self.settings.public_dict()
        values.update(changes)
        for name in ("idle_start", "idle_end"):
            try:
                datetime.strptime(str(values[name]), "%H:%M")
            except ValueError as exc:
                raise ValueError(f"{name} must use HH:MM format") from exc
        for name in ("subtitle_font_zh_size", "subtitle_font_en_size"):
            size = int(values[name])
            if size < 12 or size > 160:
                raise ValueError(f"{name} must be between 12 and 160")
            values[name] = size
        if values["tts_backend"] not in {"minimax", "cosyvoice", "kokoro", "doubao"}:
            raise ValueError("Unsupported TTS backend")
        if values["cosyvoice_mode"] not in {"sft", "zero_shot", "instruct"}:
            raise ValueError("Unsupported CosyVoice mode")
        if values["ytdlp_mode"] not in {"python", "local"}:
            raise ValueError("Unsupported yt-dlp mode")
        if not str(values["workspace_dir"]).strip():
            raise ValueError("workspace_dir must not be empty")
        values["workspace_dir"] = str(Path(values["workspace_dir"]).expanduser().resolve())
        self.settings = DesktopSettings(**values)
        _atomic_json_write(self.path, self.settings.public_dict())
        return self.settings

    def apply_environment(self) -> None:
        values = self.settings
        environment = {
            "OPENAI_MODEL": values.openai_model,
            "OPENAI_BASE_URL": values.openai_base_url,
            "DEEPSEEK_MODEL": values.deepseek_model,
            "DEEPSEEK_BASE_URL": values.deepseek_base_url,
            "PROXY": values.proxy,
            "WHISPER_MODEL": values.whisper_model,
            "TRANSLATION_METHOD": values.translation_method,
            "TRANSLATION_POLISH_DEEPSEEK": "true" if values.translation_polish else "false",
            "TTS_BACKEND": values.tts_backend,
            "COSYVOICE_TTS_URL": values.cosyvoice_url,
            "COSYVOICE_TTS_MODE": values.cosyvoice_mode,
            "COSYVOICE_TTS_SPEAKER": values.cosyvoice_speaker,
            "COSYVOICE_TTS_INSTRUCTION": values.cosyvoice_instruction,
            "MINIMAX_TTS_API_URL": values.minimax_api_url,
            "MINIMAX_TTS_MODEL": values.minimax_model,
            "MINIMAX_TTS_VOICE_ID": values.minimax_voice_id,
            "MINIMAX_TTS_LANGUAGE_BOOST": values.minimax_language_boost,
            "SUBTITLE_FONT_ZH": values.subtitle_font_zh,
            "SUBTITLE_FONT_ZH_SIZE": str(values.subtitle_font_zh_size),
            "SUBTITLE_FONT_EN": values.subtitle_font_en,
            "SUBTITLE_FONT_EN_SIZE": str(values.subtitle_font_en_size),
            "YT_DLP_MODE": values.ytdlp_mode,
            "YT_DLP_EXE_PATH": values.ytdlp_exe_path,
            "KOUSHARE_USERNAME": values.koushare_username,
        }
        for name, value in environment.items():
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)


class CredentialStore:
    SERVICE_NAME = "VideoHub Desktop"
    ENVIRONMENT_NAMES = {
        "openai_api_key": "OPENAI_API_KEY",
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "claude_api_key": "CLAUDE_API_KEY",
        "minimax_api_key": "MINIMAX_API_KEY",
        "doubao_tts_app_id": "DOUBAO_TTS_APP_ID",
        "doubao_tts_access_token": "DOUBAO_TTS_ACCESS_TOKEN",
        "koushare_access_token": "KOUSHARE_ACCESS_TOKEN",
    }

    def __init__(self, backend: Any | None = None):
        if backend is None:
            try:
                import keyring
            except ImportError:
                keyring = None
            backend = keyring
        self.backend = backend

    def _read(self, name: str) -> str:
        environment_name = self.ENVIRONMENT_NAMES[name]
        if self.backend is not None:
            value = self.backend.get_password(self.SERVICE_NAME, name)
            if value:
                return value
        return os.environ.get(environment_name, "")

    def status(self) -> dict[str, bool]:
        return {name: bool(self._read(name)) for name in self.ENVIRONMENT_NAMES}

    def update(self, changes: dict[str, Any]) -> dict[str, bool]:
        unknown = sorted(set(changes) - set(self.ENVIRONMENT_NAMES))
        if unknown:
            raise ValueError(f"Unknown credentials: {', '.join(unknown)}")
        if self.backend is None:
            raise RuntimeError("The system credential backend is unavailable. Install the 'keyring' package.")
        for name, raw_value in changes.items():
            value = str(raw_value or "").strip()
            if value:
                self.backend.set_password(self.SERVICE_NAME, name, value)
            elif self.backend.get_password(self.SERVICE_NAME, name) is not None:
                self.backend.delete_password(self.SERVICE_NAME, name)
        self.apply_environment()
        return self.status()

    def apply_environment(self) -> None:
        for name, environment_name in self.ENVIRONMENT_NAMES.items():
            value = self._read(name)
            if value:
                os.environ[environment_name] = value
            else:
                os.environ.pop(environment_name, None)


@dataclass(slots=True)
class RuntimeConfig:
    data_dir: Path
    workspace_dir: Path
    session_token: str
    parent_pid: int | None = None

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        data_dir = Path(os.environ.get("VIDEOHUB_DATA_DIR", Path.cwd() / ".videohub-data"))
        settings = SettingsStore(data_dir)
        workspace_dir = Path(os.environ.get("VIDEOHUB_WORKSPACE_DIR", settings.settings.workspace_dir))
        parent = os.environ.get("VIDEOHUB_PARENT_PID", "").strip()
        return cls(
            data_dir=data_dir.expanduser().resolve(),
            workspace_dir=workspace_dir.expanduser().resolve(),
            session_token=os.environ.get("VIDEOHUB_SESSION_TOKEN", ""),
            parent_pid=int(parent) if parent.isdigit() else None,
        )

    def apply_environment(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        os.environ["VIDEOHUB_DATA_DIR"] = str(self.data_dir)
        os.environ["VIDEOHUB_WORKSPACE_DIR"] = str(self.workspace_dir)
