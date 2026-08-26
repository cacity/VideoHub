from __future__ import annotations

import contextlib
import ctypes
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]
YOUTUBE_CLIENT_FALLBACK_ERRORS = (
    "HTTP Error 403",
    "Requested format is not available",
)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    id: str
    title: str
    category: str
    description: str


OPERATION_SPECS = (
    OperationSpec("system.preflight", "System preflight", "system", "Inspect runtime dependencies without modifying the computer."),
    OperationSpec("system.echo", "Diagnostic echo", "system", "Exercise the persisted job and event pipeline."),
    OperationSpec("platform.download", "Platform download", "download", "Download YouTube, Twitter/X, Bilibili or Instagram media with yt-dlp."),
    OperationSpec("douyin.download", "Douyin download", "download", "Download one Douyin video with the native VideoHub adapter."),
    OperationSpec("koushare.download", "Koushare download", "download", "Download one Koushare video with the native VideoHub adapter."),
    OperationSpec("youtube.process", "YouTube processing", "media", "Download, transcribe, translate, summarize and optionally burn subtitles."),
    OperationSpec("youtube.batch", "YouTube batch", "batch", "Process multiple YouTube URLs."),
    OperationSpec("local.audio", "Local audio", "local", "Transcribe, subtitle and summarize a local audio file."),
    OperationSpec("local.video", "Local video", "local", "Process a local video file."),
    OperationSpec("local.video_batch", "Local video batch", "batch", "Process a video directory as a portable series project."),
    OperationSpec("local.text", "Local text", "local", "Summarize a local text document."),
    OperationSpec("audio.extract", "Extract audio", "local", "Extract audio from one video or a directory."),
    OperationSpec("subtitle.translate", "Translate subtitles", "subtitle", "Translate and optionally polish an SRT file."),
    OperationSpec("subtitle.embed", "Burn subtitles", "subtitle", "Burn a subtitle file into a video."),
    OperationSpec("dubbing.run", "AI dubbing", "dubbing", "Run the existing VideoHub dubbing engine."),
    OperationSpec("live.record", "Live recording", "live", "Resolve a supported live URL and record it with FFmpeg until cancelled or the duration limit is reached."),
    OperationSpec("cleanup.preview", "Cleanup preview", "storage", "List files selected by the cleanup policy."),
    OperationSpec("cleanup.execute", "Cleanup", "storage", "Execute an explicitly confirmed cleanup job."),
)

OPERATION_IDS = {item.id for item in OPERATION_SPECS}


def operation_catalog() -> list[dict[str, str]]:
    return [asdict(item) for item in OPERATION_SPECS]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class _LogWriter:
    def __init__(self, callback: LogCallback):
        self.callback = callback
        self._pending = ""

    def write(self, value: str) -> int:
        self._pending += value
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            if line.strip():
                self.callback(line.rstrip())
        return len(value)

    def flush(self) -> None:
        if self._pending.strip():
            self.callback(self._pending.rstrip())
        self._pending = ""


class _YtDlpLogger:
    """Route yt-dlp messages to the job log without relying on stdio streams.

    Frozen worker processes do not always expose the same stdout/stderr object
    shape as a normal Python console. yt-dlp's logger callback is its supported
    integration point and keeps all downloader messages inside the job record.
    """

    def __init__(self, callback: LogCallback):
        self._callback = callback

    def debug(self, message: str) -> None:
        self._callback(str(message))

    def warning(self, message: str) -> None:
        self._callback(f"WARNING: {message}")

    def error(self, message: str) -> None:
        self._callback(f"ERROR: {message}")


def _required(parameters: dict[str, Any], name: str) -> str:
    value = str(parameters.get(name, "")).strip()
    if not value:
        raise ValueError(f"Missing required parameter: {name}")
    return value


def _common_media_options(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": parameters.get("model"),
        "api_key": None,
        "base_url": parameters.get("base_url"),
        "whisper_model_size": parameters.get("whisper_model_size", "small"),
        "stream": bool(parameters.get("stream", True)),
        "summary_dir": parameters.get("summary_dir"),
        "custom_prompt": parameters.get("custom_prompt"),
        "template_path": parameters.get("template_path"),
        "generate_subtitles": bool(parameters.get("generate_subtitles", True)),
        "translate_to_chinese": bool(parameters.get("translate_to_chinese", True)),
        "enable_transcription": bool(parameters.get("enable_transcription", True)),
        "generate_article": bool(parameters.get("generate_article", True)),
        "enable_translation_polish": bool(parameters.get("enable_translation_polish", False)),
        "target_language": parameters.get("target_language", "zh-CN"),
    }


def _preflight() -> dict[str, Any]:
    from paths_config import LOCAL_FFMPEG_DIR, LOCAL_YTDLP_DIR, WORKSPACE_DIR

    ffmpeg_candidates = [
        shutil.which("ffmpeg"),
        str(Path(LOCAL_FFMPEG_DIR) / "ffmpeg.exe"),
    ]
    ffprobe_candidates = [
        shutil.which("ffprobe"),
        str(Path(LOCAL_FFMPEG_DIR) / "ffprobe.exe"),
    ]
    ytdlp_candidates = [
        shutil.which("yt-dlp"),
        str(Path(LOCAL_YTDLP_DIR) / "yt-dlp.exe"),
    ]

    def first_file(candidates: list[str | None]) -> str:
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        return ""

    packages = {
        name: importlib.util.find_spec(module) is not None
        for name, module in {
            "yt_dlp": "yt_dlp",
            "whisper": "whisper",
            "torch": "torch",
            "PyQt6": "PyQt6",
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
        }.items()
    }
    return {
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "workspace": WORKSPACE_DIR,
        "tools": {
            "ffmpeg": first_file(ffmpeg_candidates),
            "ffprobe": first_file(ffprobe_candidates),
            "yt_dlp": first_file(ytdlp_candidates),
        },
        "packages": packages,
    }


def _platform_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "instagram" in host or "instagr.am" in host:
        return "instagram"
    if "twitter" in host or host.endswith("x.com"):
        return "twitter"
    if "bilibili" in host or "b23.tv" in host:
        return "bilibili"
    return "youtube"


_TEMPORARY_MEDIA_SUFFIXES = {".part", ".temp", ".ytdl"}
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_ERROR_NO_MORE_FILES = 18


class _Win32FindData(ctypes.Structure):
    """Unicode directory entry returned by FindFirstFileW on Windows."""

    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("dwReserved0", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("cFileName", wintypes.WCHAR * 260),
        ("cAlternateFileName", wintypes.WCHAR * 14),
    ]


def _completed_media_files(output_dir: Path) -> set[Path]:
    """Return completed media paths without passing Windows names through an ANSI codec."""

    if os.name != "nt":
        return {
            item
            for item in output_dir.iterdir()
            if item.is_file() and item.suffix.lower() not in _TEMPORARY_MEDIA_SUFFIXES
        }

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstFileW
    find_first.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(_Win32FindData))
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextFileW
    find_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Win32FindData))
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = (wintypes.HANDLE,)
    find_close.restype = wintypes.BOOL

    data = _Win32FindData()
    handle = find_first(str(output_dir / "*"), ctypes.byref(data))
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        if error == 2:  # ERROR_FILE_NOT_FOUND: an empty directory.
            return set()
        raise ctypes.WinError(error)

    files: set[Path] = set()
    try:
        while True:
            name = data.cFileName
            is_directory = bool(data.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY)
            if (
                name not in {".", ".."}
                and not is_directory
                and Path(name).suffix.lower() not in _TEMPORARY_MEDIA_SUFFIXES
            ):
                files.add(output_dir / name)

            if find_next(handle, ctypes.byref(data)):
                continue
            error = ctypes.get_last_error()
            if error == _ERROR_NO_MORE_FILES:
                break
            raise ctypes.WinError(error)
    finally:
        find_close(handle)
    return files


def _platform_download(
    parameters: dict[str, Any],
    progress: ProgressCallback,
    log: LogCallback,
) -> dict[str, Any]:
    import yt_dlp

    try:
        from paths_config import BILIBILI_DIR, INSTAGRAM_DIR, TWITTER_DIR, YOUTUBE_DIR
    except ImportError:
        from src.paths_config import BILIBILI_DIR, INSTAGRAM_DIR, TWITTER_DIR, YOUTUBE_DIR

    url = _required(parameters, "url")
    platform = str(parameters.get("platform") or _platform_name(url)).lower()
    default_dirs = {
        "youtube": YOUTUBE_DIR,
        "twitter": TWITTER_DIR,
        "bilibili": BILIBILI_DIR,
        "instagram": INSTAGRAM_DIR,
    }
    if platform not in default_dirs:
        raise ValueError(f"Unsupported platform: {platform}")
    output_dir = Path(parameters.get("output_dir") or default_dirs[platform]).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_files = _completed_media_files(output_dir)

    def hook(event: dict[str, Any]) -> None:
        if event.get("status") == "downloading":
            total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
            downloaded = event.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            progress(min(max(percent, 1), 95), f"Downloading {platform}: {percent}%")
        elif event.get("status") == "finished":
            progress(96, "Download complete, finalizing media")

    options: dict[str, Any] = {
        "format": parameters.get("format") or "bestvideo+bestaudio/best",
        "outtmpl": str(output_dir / "%(title).180B_%(id)s.%(ext)s"),
        "noplaylist": not bool(parameters.get("playlist", False)),
        "progress_hooks": [hook],
        "logger": _YtDlpLogger(log),
        "quiet": False,
        "no_warnings": False,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "file_access_retries": 3,
        # Keep parity with the established local yt-dlp invocation used by VideoHub.
        "nocheckcertificate": bool(parameters.get("no_check_certificate", True)),
    }
    cookies = str(parameters.get("cookies_file", "")).strip()
    if cookies:
        if not Path(cookies).is_file():
            raise FileNotFoundError(f"Cookies file not found: {cookies}")
        options["cookiefile"] = cookies
    proxy = str(parameters.get("proxy") or os.environ.get("PROXY") or "").strip()
    if proxy:
        options["proxy"] = proxy

    def download(download_options: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
        with yt_dlp.YoutubeDL(download_options) as downloader:
            info = downloader.extract_info(url, download=True)
            requested = info.get("requested_downloads") or []
            candidates = [Path(item["filepath"]) for item in requested if item.get("filepath")]
            candidates.append(Path(downloader.prepare_filename(info)))
        return info, candidates

    try:
        info, candidates = download(options)
    except yt_dlp.utils.DownloadError as exc:
        if platform != "youtube" or not any(
            marker in str(exc) for marker in YOUTUBE_CLIENT_FALLBACK_ERRORS
        ):
            raise
        progress(1, "Retrying YouTube download with web_embedded")
        fallback_options = dict(options)
        fallback_options["extractor_args"] = {
            "youtube": {"player_client": ["web_embedded"]},
        }
        info, candidates = download(fallback_options)
    # yt-dlp's Windows metadata can carry a legacy-codepage filepath in a frozen
    # worker even though the media was written with the correct Unicode filename.
    # The filesystem is the authoritative source for the completed output.
    current_files = _completed_media_files(output_dir)
    new_files = current_files - existing_files
    media_id = str(info.get("id") or "")
    id_matches = {
        path for path in current_files if media_id and f"_{media_id}." in path.name
    }
    selected_files = sorted(new_files or id_matches, key=lambda item: item.name.casefold())
    if not selected_files:
        raise RuntimeError("yt-dlp completed without a discoverable media output")
    files = [str(path) for path in selected_files]
    title = str(info.get("title") or "")
    if selected_files:
        title = selected_files[0].stem
        suffix = f"_{media_id}"
        if media_id and title.endswith(suffix):
            title = title[: -len(suffix)]
    progress(100, "Download finished")
    return {"platform": platform, "title": title, "files": files, "output_dir": str(output_dir)}


def _live_record(
    parameters: dict[str, Any],
    progress: ProgressCallback,
    log: LogCallback,
) -> dict[str, Any]:
    import yt_dlp

    from paths_config import LIVE_DOWNLOADS_DIR, LOCAL_FFMPEG_DIR

    url = _required(parameters, "url")
    output_dir = Path(parameters.get("output_dir") or LIVE_DOWNLOADS_DIR).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = max(0, int(parameters.get("duration_seconds") or 0))
    container = str(parameters.get("container") or "ts").lower()
    if container not in {"ts", "mp4", "mkv"}:
        raise ValueError("Live recording container must be ts, mp4, or mkv")

    options: dict[str, Any] = {
        "format": parameters.get("format") or "best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "logger": _YtDlpLogger(log),
    }
    cookies = str(parameters.get("cookies_file", "")).strip()
    if cookies:
        if not Path(cookies).is_file():
            raise FileNotFoundError(f"Cookies file not found: {cookies}")
        options["cookiefile"] = cookies

    progress(5, "Resolving live stream")
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
    stream_url = str(info.get("url") or "").strip()
    if not stream_url:
        requested = info.get("requested_formats") or info.get("formats") or []
        stream_url = next(
            (str(item.get("url")) for item in reversed(requested) if item.get("url")),
            "",
        )
    if not stream_url:
        raise RuntimeError("yt-dlp did not return a playable live stream URL")

    title = str(info.get("title") or "live")
    safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", title).strip("._") or "live"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{safe_title[:120]}_{timestamp}.{container}"
    ffmpeg = shutil.which("ffmpeg") or str(Path(LOCAL_FFMPEG_DIR) / "ffmpeg.exe")
    if not Path(ffmpeg).is_file():
        raise FileNotFoundError("FFmpeg was not found. Configure or bundle FFmpeg before recording.")

    command = [ffmpeg, "-hide_banner", "-y", "-i", stream_url]
    if duration:
        command.extend(["-t", str(duration)])
    command.extend(["-c", "copy", str(output_path)])
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    progress(10, "Recording live stream")
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )
    assert process.stderr is not None
    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
    for line in process.stderr:
        match = time_pattern.search(line)
        if match:
            elapsed = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
            if duration:
                value = min(98, 10 + int(elapsed * 88 / duration))
                progress(value, f"Recording {elapsed:.0f}s / {duration}s")
            else:
                progress(10, f"Recording {elapsed:.0f}s; cancel the task to stop")
        elif "error" in line.lower():
            log(line.strip())
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg live recording exited with code {return_code}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Live recording completed without a valid output file")
    progress(100, "Live recording finished")
    return {
        "title": title,
        "output": str(output_path),
        "size": output_path.stat().st_size,
        "duration_limit": duration,
    }


def run_operation(
    operation: str,
    parameters: dict[str, Any],
    progress: ProgressCallback,
    log: LogCallback,
) -> Any:
    if operation not in OPERATION_IDS:
        raise ValueError(f"Unsupported operation: {operation}")

    os.environ["TRANSLATION_POLISH_DEEPSEEK"] = (
        "true" if parameters.get("enable_translation_polish") else "false"
    )
    writer = _LogWriter(log)
    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
        if operation == "system.echo":
            delay = max(0.0, min(float(parameters.get("delay", 0.05)), 2.0))
            message = str(parameters.get("message", "VideoHub sidecar is ready"))
            for percent in (10, 35, 70, 100):
                progress(percent, message)
                time.sleep(delay)
            result: Any = {"message": message}
        elif operation == "system.preflight":
            progress(20, "Inspecting runtime")
            result = _preflight()
            progress(100, "Preflight complete")
        elif operation == "platform.download":
            result = _platform_download(parameters, progress, log)
        elif operation == "douyin.download":
            from douyin_cli import download_douyin_video
            from paths_config import DOUYIN_DOWNLOADS_DIR

            progress(5, "Starting Douyin download")
            result = download_douyin_video(
                _required(parameters, "url"),
                output_dir=parameters.get("output_dir") or DOUYIN_DOWNLOADS_DIR,
                cookie=os.environ.get("DOUYIN_COOKIE") or None,
            )
            progress(100, "Douyin download finished")
        elif operation == "koushare.download":
            import koushare_downloader
            from paths_config import KOUSHARE_DOWNLOADS_DIR

            result = koushare_downloader.download(
                _required(parameters, "url"),
                output_dir=parameters.get("output_dir") or KOUSHARE_DOWNLOADS_DIR,
                progress_callback=lambda message, value: progress(int(value), str(message)),
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Koushare download failed"))
        elif operation in {"youtube.process", "youtube.batch", "local.audio", "local.video", "local.video_batch", "local.text", "audio.extract", "subtitle.translate", "subtitle.embed", "cleanup.preview", "cleanup.execute"}:
            import youtube_transcriber as media
            from paths_config import DEFAULT_SUMMARY_DIR, SONGS_DIR, VIDEOS_WITH_SUBTITLES_DIR

            common = _common_media_options(parameters)
            if not common["summary_dir"]:
                common["summary_dir"] = DEFAULT_SUMMARY_DIR
            if operation == "youtube.process":
                progress(2, "Starting YouTube workflow")
                result = media.process_youtube_video(
                    youtube_url=_required(parameters, "url"),
                    download_video=bool(parameters.get("download_video", True)),
                    embed_subtitles=bool(parameters.get("embed_subtitles", False)),
                    cookies_file=parameters.get("cookies_file"),
                    prefer_native_subtitles=bool(parameters.get("prefer_native_subtitles", True)),
                    **common,
                )
            elif operation == "youtube.batch":
                urls = parameters.get("urls") or []
                if not isinstance(urls, list) or not urls:
                    raise ValueError("Parameter 'urls' must be a non-empty list")
                result = media.process_youtube_videos_batch(
                    youtube_urls=urls,
                    download_video=bool(parameters.get("download_video", True)),
                    embed_subtitles=bool(parameters.get("embed_subtitles", False)),
                    cookies_file=parameters.get("cookies_file"),
                    prefer_native_subtitles=bool(parameters.get("prefer_native_subtitles", True)),
                    **common,
                )
            elif operation == "local.audio":
                result = media.process_local_audio(audio_path=_required(parameters, "path"), **common)
            elif operation == "local.video":
                result = media.process_local_video(
                    video_path=_required(parameters, "path"),
                    embed_subtitles=bool(parameters.get("embed_subtitles", False)),
                    source_language=parameters.get("source_language"),
                    project_root=parameters.get("project_root"),
                    **common,
                )
            elif operation == "local.video_batch":
                result = media.process_local_videos_batch(
                    input_path=_required(parameters, "path"),
                    embed_subtitles=bool(parameters.get("embed_subtitles", False)),
                    source_language=parameters.get("source_language"),
                    series_project=bool(parameters.get("series_project", True)),
                    **common,
                )
            elif operation == "local.text":
                result = media.process_local_text(
                    text_path=_required(parameters, "path"),
                    model=common["model"],
                    api_key=None,
                    base_url=common["base_url"],
                    stream=common["stream"],
                    summary_dir=common["summary_dir"],
                    custom_prompt=common["custom_prompt"],
                    template_path=common["template_path"],
                )
            elif operation == "audio.extract":
                result = media.extract_audio_from_local_videos(
                    _required(parameters, "path"),
                    output_dir=parameters.get("output_dir") or SONGS_DIR,
                    recursive=bool(parameters.get("recursive", True)),
                )
            elif operation == "subtitle.translate":
                result = media.translate_subtitle_file(
                    _required(parameters, "path"),
                    target_language=parameters.get("target_language", "zh-CN"),
                    output_dir=parameters.get("output_dir"),
                    enable_translation_polish=bool(parameters.get("enable_translation_polish", False)),
                    progress_callback=lambda value, message: progress(int(value), str(message)),
                )
            elif operation == "subtitle.embed":
                result = media.embed_subtitles_to_video(
                    _required(parameters, "video_path"),
                    _required(parameters, "subtitle_path"),
                    output_dir=parameters.get("output_dir") or VIDEOS_WITH_SUBTITLES_DIR,
                )
            else:
                directories = parameters.get("directories")
                result = media.cleanup_files(directories, dry_run=operation == "cleanup.preview")
            progress(100, "Operation finished")
        elif operation == "dubbing.run":
            from dubbing_engine import DubbingTask, VideoDubbingEngine

            task_values = dict(parameters)
            task_values.pop("api_key", None)
            task_values.pop("minimax_api_key", None)
            if task_values.get("tts_backend") == "minimax":
                task_values["minimax_api_key"] = os.environ.get("MINIMAX_API_KEY", "")
            task = DubbingTask(**task_values)
            engine = VideoDubbingEngine(
                progress_callback=lambda value, message: progress(int(value), str(message)),
                step_callback=lambda name, index: log(f"Step {index + 1}: {name}"),
                log_callback=log,
            )
            result = engine.dub_video(task)
            progress(100, "Dubbing finished")
        elif operation == "live.record":
            result = _live_record(parameters, progress, log)
        else:
            raise AssertionError(f"Operation has no runner: {operation}")
    writer.flush()
    return _json_safe(result)
