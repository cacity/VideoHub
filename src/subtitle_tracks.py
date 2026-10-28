"""Plain, language-separated SRT files shared by downloads and learning."""

from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from pathlib import Path


def srt_content(cues: list[dict]) -> str:
    def stamp(seconds):
        milliseconds = round(float(seconds) * 1000)
        return f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}"

    rows = []
    for cue in cues:
        start, end, text = float(cue["start"]), float(cue["end"]), str(cue["text"]).strip()
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("字幕时间无效")
        if text:
            rows.append(f"{len(rows) + 1}\n{stamp(start)} --> {stamp(end)}\n{text}\n")
    if not rows:
        raise ValueError("没有可保存的字幕内容")
    return "\n".join(rows)


def snapshot_track(cues: list[dict], folder: Path, name: str, role: str, language: str, name_limit: int = 70) -> Path:
    """Immutable snapshots: do not replace a user's subtitle or edited export."""
    content = srt_content(cues).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()[:20]
    stem = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._") or "subtitles"
    if len(stem) > name_limit:
        stem = stem[: name_limit - 25] + "_" + stem[-24:]
    code = re.sub(r"[^A-Za-z0-9-]", "", language)[:20] or "auto"
    if role not in {"source", "target"}:
        raise ValueError("字幕角色无效")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}.{role}.{code}.{digest}.srt"
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"单语言字幕副本已被修改：{path.name}，请先另存或重新导入")
        return path
    temporary = folder / f".{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(content)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("单语言字幕副本内容冲突") from None
    finally:
        temporary.unlink(missing_ok=True)
    return path


def save_language_tracks(
    rows: list[dict], base: str | Path, source_language: str, target_language: str
) -> dict[str, str]:
    """Keep existing bilingual render assets and add portable plain SRT tracks."""
    base = Path(base)
    result = {}
    for role, field, language in [("source", "source", source_language), ("target", "translation", target_language)]:
        cues = [
            {"start": r["start"], "end": r["end"], "text": r.get(field, "")} for r in rows if r.get(field, "").strip()
        ]
        if cues:
            result[role] = str(snapshot_track(cues, base.parent, base.stem, role, language, name_limit=150))
    return result
