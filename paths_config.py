import os

"""
统一管理项目运行时产生的大文件目录（视频、音频、字幕、摘要等）。

所有下载/生成的大体积文件都会放在项目根目录下的 `workspace/` 目录中，
便于本地调试时集中管理，也便于通过 .gitignore 一次性忽略这些文件。
"""

# 项目根目录（当前文件所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 统一的工作目录
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)


def _ensure_subdir(name: str) -> str:
    """
    在工作目录下创建并返回子目录路径，例如:
    _ensure_subdir("videos") -> <项目根>/workspace/videos
    """
    path = os.path.join(WORKSPACE_DIR, name)
    os.makedirs(path, exist_ok=True)
    return path


# 各类运行时目录（统一挂在 workspace/ 下）
VIDEOS_DIR = _ensure_subdir("videos")
DOWNLOADS_DIR = _ensure_subdir("downloads")
SUBTITLES_DIR = _ensure_subdir("subtitles")
TRANSCRIPTS_DIR = _ensure_subdir("transcripts")
SUMMARIES_DIR = _ensure_subdir("summaries")
VIDEOS_WITH_SUBTITLES_DIR = _ensure_subdir("videos_with_subtitles")
NATIVE_SUBTITLES_DIR = _ensure_subdir("native_subtitles")

# 其他平台相关目录
TWITTER_DOWNLOADS_DIR = _ensure_subdir("twitter_downloads")
BILIBILI_DOWNLOADS_DIR = _ensure_subdir("bilibili_downloads")
DOUYIN_DOWNLOADS_DIR = _ensure_subdir("douyin_downloads")
LIVE_DOWNLOADS_DIR = _ensure_subdir("live_downloads")


# 逻辑名称到实际目录路径的映射，供清理/打开目录等功能使用
DIRECTORY_MAP = {
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
}


# 默认摘要目录（供各处作为默认值使用）
DEFAULT_SUMMARY_DIR = SUMMARIES_DIR

