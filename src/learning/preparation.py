"""Explicit preview/transcription jobs, preserving originals and cached resources."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import media
from .store import new_id
from .subtitles import bound_transcription, read_track, write_srt


def start_preview(assistant, video_id: str):
    service = assistant.service
    video = service.store.video(video_id)

    def work(cancelled, update):
        destination = service.store.root / "cache" / video_id / f"preview-{video['size']}-{video['mtime_ns']}.mp4"
        if not destination.is_file():
            media.preview(
                Path(video["path"]),
                destination,
                cancelled,
                lambda seconds: update(
                    progress=min(95, round(seconds / video["duration"] * 95)),
                    message="正在生成浏览器预览，原视频保持不变",
                ),
            )
        if cancelled.is_set():
            raise InterruptedError()
        current = service.store.video(video_id)
        if (current["size"], current["mtime_ns"]) != (video["size"], video["mtime_ns"]):
            raise ValueError("原视频已改变，请重新生成预览")
        media.probe(destination)
        service.store.save_video({**current, "preview": str(destination)})
        return {"preview_ready": True}

    return assistant.jobs.start(video_id, "preview", work)


def start_transcription(assistant, video_id: str, data: dict):
    service = assistant.service
    video = service.store.video(video_id)
    subtitle_version = service.detail(video_id)["subtitle_version"]
    if video.get("audio_codec") is None:
        raise ValueError("此视频没有音频轨道，无法转写")
    model = str(data.get("whisper_model", "small"))
    if model not in {"tiny", "base", "small", "medium", "large"}:
        raise ValueError("Whisper 模型无效")
    language = str(data.get("language", ""))
    if language and (len(language) > 12 or not all(c.isalpha() or c == "-" for c in language)):
        raise ValueError("转写语言代码无效")
    if service.detail(video_id)["has_source"] and data.get("replace") is not True:
        raise ValueError("已有原文字幕，请直接使用；如需重新转写，请先明确选择替换")

    def work(cancelled, update):
        destination = service.store.root / "cache" / video_id / ("transcription-" + new_id())
        destination.mkdir(parents=True)
        update(message="Whisper 正在转写；首次运行可能需要下载模型", progress=5)
        repo = Path(__file__).resolve().parents[2]
        with (destination / "worker.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "src.learning.transcribe_worker",
                    "--video",
                    video["path"],
                    "--output",
                    str(destination),
                    "--model",
                    model,
                    "--language",
                    language,
                ],
                cwd=repo,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                while process.poll() is None:
                    if cancelled.wait(0.3):
                        import psutil

                        try:
                            parent = psutil.Process(process.pid)
                            for child in parent.children(recursive=True):
                                try:
                                    child.kill()
                                except psutil.NoSuchProcess:
                                    pass
                            parent.kill()
                        except psutil.NoSuchProcess:
                            pass
                        process.wait(timeout=10)
                        raise InterruptedError()
                if process.returncode:
                    raise ValueError("转写失败，请检查本地 Whisper、FFmpeg 和模型资源；原字幕未被修改")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        result = json.loads((destination / "result.json").read_text(encoding="utf-8"))
        if cancelled.is_set():
            raise InterruptedError()
        if service.detail(video_id)["subtitle_version"] != subtitle_version:
            raise ValueError("字幕在转写期间已改变，请重新选择需要使用的原文字幕")
        cues, changed = bound_transcription(read_track(Path(result["subtitle"]))["cues"], video["duration"])
        validated = destination / "validated.srt"
        write_srt(validated, cues)
        warning = [f"识别结果有 {changed} 条时间越界，已剔除或裁至原片边界；请核对片尾静音段"] if changed else []
        update(warnings=warning)
        service.add_track(
            video_id,
            {"role": "source", "path": str(validated), "language": result.get("language") or language or "auto"},
        )
        return {"transcribed": True, "cues": len(cues), "warnings": warning}

    return assistant.jobs.start(video_id, "transcription", work)
