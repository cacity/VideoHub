"""Central path configuration for VideoHub.

Runtime output belongs under ``workspace/``. Repository-owned source,
configuration, and static assets stay under the project root.
"""

from __future__ import annotations

import os
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent
SRC_PATH = BASE_PATH / "src"
WORKSPACE_PATH = BASE_PATH / "workspace"

BASE_DIR = str(BASE_PATH)
SRC_DIR = str(SRC_PATH)
WORKSPACE_DIR = str(WORKSPACE_PATH)


def _ensure_dir(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _ensure_workspace_subdir(name: str) -> str:
    return _ensure_dir(WORKSPACE_PATH / name)


# Runtime directories.
YOUTUBE_DIR = _ensure_workspace_subdir("youtube")
YOUTUBE_AUDIO_DIR = _ensure_workspace_subdir("youtube_audio")
TWITTER_DIR = _ensure_workspace_subdir("twitter")
BILIBILI_DIR = _ensure_workspace_subdir("bilibili")
DOUYIN_DIR = _ensure_workspace_subdir("douyin")
LIVE_DIR = _ensure_workspace_subdir("live")
KOUSHARE_DIR = _ensure_workspace_subdir("koushare")

# Backward-compatible constant names used throughout the app.
VIDEOS_DIR = YOUTUBE_DIR
DOWNLOADS_DIR = YOUTUBE_AUDIO_DIR
SUBTITLES_DIR = _ensure_workspace_subdir("subtitles")
TRANSCRIPTS_DIR = _ensure_workspace_subdir("transcripts")
SUMMARIES_DIR = _ensure_workspace_subdir("summaries")
VIDEOS_WITH_SUBTITLES_DIR = _ensure_workspace_subdir("videos_with_subtitles")
NATIVE_SUBTITLES_DIR = _ensure_workspace_subdir("native_subtitles")
TWITTER_DOWNLOADS_DIR = TWITTER_DIR
BILIBILI_DOWNLOADS_DIR = BILIBILI_DIR
DOUYIN_DOWNLOADS_DIR = DOUYIN_DIR
LIVE_DOWNLOADS_DIR = LIVE_DIR
KOUSHARE_DOWNLOADS_DIR = KOUSHARE_DIR
DUBBING_TEMP_DIR = _ensure_workspace_subdir("dubbing_temp")
DUBBING_OUTPUT_DIR = _ensure_workspace_subdir("dubbing_output")
LOGS_DIR = _ensure_workspace_subdir("logs")
TEMPLATES_DIR = _ensure_workspace_subdir("templates")
GLOSSARIES_DIR = _ensure_workspace_subdir("glossaries")
QA_REPORTS_DIR = _ensure_workspace_subdir("qa_reports")
REVIEW_PACKS_DIR = _ensure_workspace_subdir("review_packs")


DIRECTORY_MAP = {
    "youtube": YOUTUBE_DIR,
    "youtube_audio": YOUTUBE_AUDIO_DIR,
    "audio": YOUTUBE_AUDIO_DIR,
    "twitter": TWITTER_DIR,
    "bilibili": BILIBILI_DIR,
    "douyin": DOUYIN_DIR,
    "live": LIVE_DIR,
    "koushare": KOUSHARE_DIR,

    # Legacy logical names kept for older code and saved settings.
    "videos": VIDEOS_DIR,
    "downloads": DOWNLOADS_DIR,
    "subtitles": SUBTITLES_DIR,
    "transcripts": TRANSCRIPTS_DIR,
    "summaries": SUMMARIES_DIR,
    "videos_with_subtitles": VIDEOS_WITH_SUBTITLES_DIR,
    "native_subtitles": NATIVE_SUBTITLES_DIR,
    "twitter_downloads": TWITTER_DOWNLOADS_DIR,
    "bilibili_downloads": BILIBILI_DOWNLOADS_DIR,
    "douyin_downloads": DOUYIN_DOWNLOADS_DIR,
    "live_downloads": LIVE_DOWNLOADS_DIR,
    "koushare_downloads": KOUSHARE_DOWNLOADS_DIR,
    "dubbing_temp": DUBBING_TEMP_DIR,
    "dubbing_output": DUBBING_OUTPUT_DIR,
    "logs": LOGS_DIR,
    "templates": TEMPLATES_DIR,
    "glossaries": GLOSSARIES_DIR,
    "qa_reports": QA_REPORTS_DIR,
    "review_packs": REVIEW_PACKS_DIR,
}


# Repository-root state/config files.
ENV_FILE = str(BASE_PATH / ".env")
IDLE_QUEUE_FILE = str(BASE_PATH / "idle_queue.json")
FFMPEG_CONFIG_FILE = str(BASE_PATH / "ffmpeg_config.json")
YTDLP_CONFIG_FILE = str(BASE_PATH / "ytdlp_config.json")
LOCAL_FFMPEG_DIR = str(BASE_PATH / "ffmpeg")
LOCAL_YTDLP_DIR = str(BASE_PATH / "ytdlp")


DEFAULT_SUMMARY_DIR = SUMMARIES_DIR


def get_directory(name: str) -> str:
    try:
        return DIRECTORY_MAP[name]
    except KeyError as exc:
        available = ", ".join(sorted(DIRECTORY_MAP))
        raise KeyError(f"Unknown directory '{name}'. Available directories: {available}") from exc


def list_all_directories() -> dict[str, str]:
    return DIRECTORY_MAP.copy()


def get_workspace_size() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for name, directory in DIRECTORY_MAP.items():
        total_size = 0
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    pass
        sizes[name] = total_size
    return sizes
