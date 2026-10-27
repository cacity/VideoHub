"""Probe and explicitly prepare browser previews without changing originals."""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".mpeg", ".mpg"}


def executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    path = Path(__file__).resolve().parents[2] / "ffmpeg" / "bin" / f"{name}.exe"
    if path.is_file():
        return str(path)
    raise ValueError(f"未找到 {name}，请先配置 FFmpeg")


def probe(path: Path) -> dict:
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("请选择存在的本地视频文件")
    try:
        result = subprocess.run(
            [executable("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            timeout=30,
            check=True,
        )
        info = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError):
        raise ValueError("无法读取视频，请检查文件完整性") from None
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("文件中没有视频轨道")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    duration = float(info["format"].get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise ValueError("无法确定视频时长")
    browser = (
        path.suffix.lower() in {".mp4", ".m4v", ".mov", ".webm"}
        and video["codec_name"] in {"h264", "vp8", "vp9", "av1"}
        and audio.get("codec_name") in {None, "aac", "mp3", "opus", "vorbis"}
    )
    stat = path.stat()
    return {
        "duration": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "codec": video["codec_name"],
        "audio_codec": audio.get("codec_name"),
        "browser_ready": browser,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def preview(path: Path, destination: Path, cancelled, on_progress) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial.mp4")
    process = subprocess.Popen(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-y",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-threads",
            "4",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            str(temporary),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        # The monitor thread also terminates the process if encoding stops producing output.
        import threading

        done = threading.Event()

        def monitor():
            while not done.wait(0.2):
                if cancelled.is_set():
                    process.terminate()
                    return

        threading.Thread(target=monitor, daemon=True).start()
        try:
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    on_progress(float(line.split("=", 1)[1].strip() or 0) / 1_000_000)
            result = process.wait()
        finally:
            done.set()
        if cancelled.is_set():
            raise InterruptedError("预览生成已停止")
        if result:
            raise ValueError("浏览器预览转码失败，请检查视频与磁盘空间")
        temporary.replace(destination)
        return destination
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout:
            process.stdout.close()
        temporary.unlink(missing_ok=True)


def mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
