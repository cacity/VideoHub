"""Learning domain operations, independent of Flask and Qt."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from . import media, subtitles
from .store import Store, encode, new_id, now

try:
    from ..subtitle_tracks import snapshot_track
except ImportError:
    from subtitle_tracks import snapshot_track

DEFAULT_SUBTITLE_STYLE = {
    "font_family": "sans",
    "source_color": "#ffffff",
    "target_color": "#f3f1cd",
    "background": 0,
    "position": "bottom",
    "bold": False,
    "outline": True,
    "line_height": 1.5,
}


def subtitle_style(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - DEFAULT_SUBTITLE_STYLE.keys():
        raise ValueError("字幕样式格式无效")
    style = {**DEFAULT_SUBTITLE_STYLE, **value}
    if (
        not isinstance(style["font_family"], str) or style["font_family"] not in {"sans", "serif", "mono"}
        or not isinstance(style["position"], str) or style["position"] not in {"bottom", "top"}
    ):
        raise ValueError("字幕字体或位置无效")
    for key in ("source_color", "target_color"):
        if not isinstance(style[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", style[key]):
            raise ValueError("字幕颜色须为六位十六进制颜色")
    for key in ("bold", "outline"):
        if not isinstance(style[key], bool):
            raise ValueError("字幕描边/粗体设置无效")
    style["background"] = min(0.9, max(0, finite(style["background"], "字幕背景")))
    style["line_height"] = min(2, max(1.1, finite(style["line_height"], "字幕行距")))
    return style


def finite(value, name: str = "时间") -> float:
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}无效") from None
    if not math.isfinite(result):
        raise ValueError(f"{name}无效")
    return result


class LearningService:
    def __init__(self, root: Path):
        self.store = Store(root)

    def register(
        self, path: str, title: str = "", source_url: str = "", tracks: list | None = None, project: dict | None = None
    ) -> dict:
        source = Path(path.strip().strip('"')).expanduser().resolve()
        info = media.probe(source)
        if source_url and not source_url.startswith(("https://", "http://")):
            raise ValueError("来源链接须为 HTTP/HTTPS")
        existing = next((v for v in self.store.videos() if Path(v["path"]) == source), None)
        if project and not existing and project.get("id"):
            try:
                previous = self.store.video(project["id"])
            except KeyError:
                previous = None
            if previous:
                from .project import signature
                previous_signature = previous.get("media_signature")
                if not previous_signature and Path(previous["path"]).is_file():
                    previous_signature = signature(Path(previous["path"]))
                if previous_signature != project["media_signature"]:
                    raise ValueError("工程编号与另一视频冲突，请检查工程清单")
            existing = previous
        video = {
            **(existing or {}),
            **info,
            "id": existing["id"] if existing else new_id(),
            "path": str(source),
            "title": title.strip()[:300] or source.stem,
            "source_url": source_url[:2000] or (existing or {}).get("source_url", ""),
            "created": (existing or {}).get("created", now()),
        }
        if project:
            video.update(project_root=project["root"], media_signature=project["media_signature"])
            if not existing and project.get("id"):
                video["id"] = project["id"]
        if existing and (existing.get("size"), existing.get("mtime_ns")) != (info["size"], info["mtime_ns"]):
            video.pop("preview", None)
        prepared = {}
        if tracks is not None and (
            not isinstance(tracks, list) or len(tracks) > 80 or any(not isinstance(t, dict) for t in tracks)
        ):
            raise ValueError("字幕清单格式无效，最多80份")
        for track in tracks or []:
            item = self.prepare_track(track)
            self.validate_track(item, video["duration"])
            key = item["role"]
            if key in prepared:
                key = "available-" + hashlib.sha256((item["path"] + item["role"]).encode()).hexdigest()[:20]
            prepared[key] = item
        self.store.save_video(video)
        self.store.save_tracks(video["id"], prepared)
        return self.detail(video["id"])

    def prepare_track(self, track: dict) -> dict:
        role = track.get("role", "source")
        if role not in {"source", "target"}:
            raise ValueError("字幕角色必须是 source 或 target")
        language = str(track.get("language", "en" if role == "source" else "zh-CN"))[:30]
        if track.get("path"):
            data = subtitles.read_track(Path(track["path"]).expanduser().resolve(), role)
        else:
            content = str(track.get("content", ""))
            if len(content.encode("utf-8")) > 20 * 1024 * 1024:
                raise ValueError("字幕文件超过 20MB")
            data = {
                "path": "",
                "hash": hashlib.sha256(content.encode()).hexdigest(),
                "cues": subtitles.parse(content, str(track.get("suffix", ".srt")), role),
            }
        data["hash"] = hashlib.sha256((data["hash"] + encode([role, language, data["cues"]])).encode()).hexdigest()
        return {**data, "role": role, "language": language, "updated": now()}

    def add_track(self, video_id: str, track: dict):
        video = self.store.video(video_id)
        prepared = self.prepare_track(track)
        self.validate_track(prepared, video["duration"])
        self.store.save_tracks(video_id, {prepared["role"]: prepared})
        return self.detail(video_id)

    @staticmethod
    def validate_track(track: dict, duration: float):
        end = max(c["end"] for c in track["cues"])
        if end <= duration:
            return
        # Platform captions can linger briefly after the final video frame.
        # Only shorten cues that actually begin inside the video; a later cue
        # or a substantial overrun still indicates a potentially wrong file.
        if end > duration + 5 or any(c["start"] >= duration for c in track["cues"]):
            name = Path(track["path"]).name or "所选字幕"
            raise ValueError(f"{name}：字幕超出视频时长 {end - duration:.2f} 秒，请检查是否选错文件")
        track["cues"], changed = subtitles.bound_transcription(track["cues"], duration)
        track["hash"] = hashlib.sha256(encode([track["role"], track["language"], track["cues"]]).encode()).hexdigest()
        name = Path(track["path"]).name or "所选字幕"
        track["timing_warning"] = (
            f"{name}：片尾延长 {end - duration:.2f} 秒，已将 {changed} 条字幕的结束时间对齐至片尾；原文件未改动。"
        )

    def detail(self, video_id: str) -> dict:
        video = self.store.video(video_id)
        tracks = self.store.tracks(video_id)
        changed = {}
        for key, track in tracks.items():
            if (
                track.get("separate_file")
                and f".{track['role']}." in Path(track["path"]).name
                and Path(track["path"]).is_file()
            ):
                continue
            original = track.get("original_path", track["path"])
            fallback = self.store.root / "subtitles" / video_id
            folder = Path(video["project_root"]) / "subtitles" / "learning_tracks" if video.get("project_root") else fallback
            name = Path(original).stem or "subtitles"
            try:
                path = snapshot_track(track["cues"], folder, name, track["role"], track["language"])
            except OSError:
                path = snapshot_track(track["cues"], fallback, name, track["role"], track["language"])
            changed[key] = {**track, "path": str(path), "original_path": original, "separate_file": True}
        if changed:
            self.store.save_tracks(video_id, changed)
            tracks.update(changed)
        source = tracks.get("source", {}).get("cues", [])
        target = tracks.get("target", {}).get("cues", [])
        cues = (
            subtitles.aligned(source, target)
            if source
            else [{**cue, "translation": cue["text"], "translation_ids": [cue["id"]]} for cue in target]
        )
        version = hashlib.sha256("|".join(tracks[r]["hash"] for r in sorted(tracks)).encode()).hexdigest()
        progress = self.store.progress(video_id)
        return {
            **video,
            "tracks": {r: {k: v for k, v in t.items() if k != "cues"} for r, t in tracks.items()},
            "available_tracks": [
                {
                    "key": r, "name": Path(t.get("original_path") or t["path"]).name,
                    "path": t["path"], "language": t["language"], "role": t["role"],
                }
                for r, t in tracks.items()
            ],
            "cues": cues,
            # Transcript alignment is many-to-many. Playback must use each
            # selected track's own clock, rather than repeat aligned text.
            "playback_cues": {"source": source, "target": target},
            "subtitle_urls": {
                role: f"/api/learning/videos/{video_id}/subtitle-file?role={role}"
                for role in ("source", "target") if tracks.get(role)
            },
            "subtitle_version": version,
            "subtitle_warnings": list(dict.fromkeys(t["timing_warning"] for t in tracks.values() if t.get("timing_warning"))),
            "progress": {**progress, "style": subtitle_style(progress.get("style", {}))},
            "media_url": f"/api/learning/videos/{video_id}/media",
            "has_source": bool(source),
            "has_target": bool(target),
        }

    def select_track(self, video_id: str, data: dict):
        role, key = data.get("role"), data.get("key")
        if role not in {"source", "target"}:
            raise ValueError("字幕角色无效")
        tracks = self.store.tracks(video_id)
        if key not in tracks:
            raise ValueError("字幕轨道不存在，请刷新工程")
        old = tracks.get(role)
        additions = {role: {**tracks[key], "role": role}}
        if old:
            backup_key = "available-" + hashlib.sha256((old.get("original_path", old["path"]) + old["role"]).encode()).hexdigest()[:20]
            additions[backup_key] = old
        self.store.save_tracks(video_id, additions)
        return self.detail(video_id)

    def media_path(self, video_id: str) -> Path:
        video = self.store.video(video_id)
        path = Path(video.get("preview") or video["path"])
        if not path.is_file():
            raise FileNotFoundError("原视频已移动或被删除，请重新导入")
        if not video.get("preview"):
            stat = path.stat()
            if (stat.st_size, stat.st_mtime_ns) != (video["size"], video["mtime_ns"]):
                raise ValueError("视频已被替换，请重新导入后再播放，避免引用错位")
        return path

    def progress(self, video_id: str, value: dict):
        video = self.store.video(video_id)
        previous = self.store.progress(video_id)
        if "style" in value:
            if not isinstance(value["style"], dict):
                raise ValueError("字幕样式格式无效")
            previous["style"] = subtitle_style({**previous.get("style", {}), **value["style"]})
        previous.update({k: v for k, v in value.items() if k in {"time", "rate", "mode", "overlay", "font"}})
        previous["time"] = min(video["duration"], max(0, finite(previous["time"])))
        previous["rate"] = min(3, max(0.25, finite(previous["rate"], "倍速")))
        previous["font"] = min(36, max(14, finite(previous["font"], "字号")))
        if any(previous[k] not in {"source", "target", "bilingual", "off"} for k in ("mode", "overlay")):
            raise ValueError("字幕显示模式无效")
        self.store.save_progress(video_id, previous)
        return previous
