"""Persistent desktop UI preferences that do not belong in the secret .env file."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QSettings


ONLINE_VIDEO_CHECKBOX_DEFAULTS = {
    "online_video/download_video": False,
    "online_video/prefer_native_subtitles": True,
    "online_video/enable_transcription": True,
    "online_video/generate_subtitles": False,
    "online_video/translate_subtitles": True,
    "online_video/embed_subtitles": False,
    "online_video/generate_article": True,
    "online_video/show_translation_logs": True,
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


class UIPreferences:
    """Read and immediately persist non-sensitive desktop UI state."""

    def __init__(self, settings: Optional[QSettings] = None):
        self.settings = settings or QSettings("VideoHub", "VideoHub")

    def get_bool(self, key: str, default: bool = False) -> bool:
        return _as_bool(self.settings.value(key, default), default)

    def set_bool(self, key: str, value: bool) -> None:
        self.settings.setValue(key, bool(value))
        self.settings.sync()
