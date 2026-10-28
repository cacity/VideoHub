"""Parse display text without losing source timestamps or stable references."""

from __future__ import annotations

import hashlib
import html
import math
import re
from pathlib import Path

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")


def seconds(value: str) -> float:
    match = TIME.fullmatch(value.strip())
    if not match:
        raise ValueError(f"无效字幕时间码：{value[:40]}")
    hours, minutes, secs, millis = match.groups()
    if int(minutes) > 59 or int(secs) > 59:
        raise ValueError("字幕时间码的分秒必须小于 60")
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs) + int(millis.ljust(3, "0")) / 1000


def plain(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    return html.unescape(text).replace(r"\N", "\n").replace(r"\n", "\n").strip()


def normalize(rows: list[dict]) -> list[dict]:
    result, seen = [], set()
    for row in rows:
        start, end, text = float(row["start"]), float(row["end"]), plain(row["text"])
        if not all(math.isfinite(n) for n in (start, end)) or start < 0 or end <= start:
            raise ValueError("字幕须有有效且递增的开始/结束时间")
        signature = f"{start:.3f}|{end:.3f}|{text}"
        if not text or signature in seen:
            continue
        seen.add(signature)
        result.append(
            {"id": "c" + hashlib.sha256(signature.encode()).hexdigest()[:16], "start": start, "end": end, "text": text}
        )
    result.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    if not result:
        raise ValueError("字幕没有可读取的有效内容")
    if len(result) > 100_000:
        raise ValueError("字幕超过十万条，请拆分视频")
    return result


def parse(content: str, suffix: str = ".srt", role: str = "source") -> list[dict]:
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if suffix.lower() in {".ass", ".ssa"}:
        try:
            from ..subtitle_utils import parse_ass_dialogues, TARGET_STYLE_NAMES
        except ImportError:
            from subtitle_utils import parse_ass_dialogues, TARGET_STYLE_NAMES
        events = parse_ass_dialogues(content)
        translated = [r for r in events if r.style.lower() in TARGET_STYLE_NAMES]
        original = [r for r in events if r.style.lower() not in TARGET_STYLE_NAMES]
        if translated and original:
            events = translated if role == "target" else original
        return normalize([{"start": r.start_seconds, "end": r.end_seconds, "text": r.text} for r in events])
    rows = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            if "-->" not in line:
                continue
            left, right = line.split("-->", 1)
            rows.append(
                {
                    "start": seconds(left.strip()),
                    "end": seconds(right.strip().split()[0]),
                    "text": "\n".join(lines[index + 1 :]),
                }
            )
            break

    # VideoHub's SRT/VTT translations can contain English + Chinese in one cue.
    # Split only when separate language lines recur across the track; mixed words
    # inside a single line and ordinary multiline monolingual text stay intact.
    def languages(text):
        lines = [plain(line) for line in text.splitlines() if plain(line)]
        chinese = [line for line in lines if re.search(r"[\u4e00-\u9fff]", line)]
        original = [line for line in lines if not re.search(r"[\u4e00-\u9fff]", line) and re.search(r"[A-Za-z]", line)]
        return original, chinese

    paired = [languages(row["text"]) for row in rows]
    if paired and sum(bool(a and b) for a, b in paired) >= max(1, len(paired) / 2):
        rows = [
            {**row, "text": "\n".join(parts[1 if role == "target" else 0])}
            for row, parts in zip(rows, paired)
            if parts[1 if role == "target" else 0]
        ]
    return normalize(rows)


def read_track(path: Path, role: str = "source") -> dict:
    if path.suffix.lower() not in {".srt", ".vtt", ".ass", ".ssa"}:
        raise ValueError("支持 SRT、VTT、ASS 字幕")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("字幕文件超过 20MB")
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("gb18030")
    return {"path": str(path), "hash": hashlib.sha256(raw).hexdigest(), "cues": parse(content, path.suffix, role)}


def aligned(source: list[dict], target: list[dict]) -> list[dict]:
    """Sweep time overlaps, allowing many-to-one and one-to-many translations."""
    result, active, index = [], [], 0
    for cue in source:
        active = [t for t in active if t["end"] > cue["start"]]
        while index < len(target) and target[index]["start"] < cue["end"]:
            active.append(target[index])
            index += 1
        matches = [t for t in active if min(t["end"], cue["end"]) > max(t["start"], cue["start"])]
        result.append(
            {
                **cue,
                "translation": "\n".join(dict.fromkeys(t["text"] for t in matches)),
                "translation_ids": [t["id"] for t in matches],
            }
        )
    return result


def timestamp(value: float) -> str:
    value = max(0, int(value))
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


def bound_transcription(cues: list[dict], duration: float) -> tuple[list[dict], int]:
    """Whisper can emit padded/silence timestamps; never ingest those as evidence."""
    rows, changed = [], 0
    for cue in cues:
        if cue["start"] >= duration:
            changed += 1
            continue
        end = min(duration, cue["end"])
        changed += end != cue["end"]
        rows.append({"start": cue["start"], "end": end, "text": cue["text"]})
    return normalize(rows), changed


def write_srt(path: Path, cues: list[dict]):
    def stamp(seconds):
        milliseconds = round(seconds * 1000)
        return timestamp(milliseconds // 1000) + f",{milliseconds % 1000:03d}"

    path.write_text(
        "\n\n".join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i, c in enumerate(cues, 1))
        + "\n",
        encoding="utf-8",
    )
