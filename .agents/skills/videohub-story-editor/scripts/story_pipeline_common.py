#!/usr/bin/env python3
"""Shared helpers for the deterministic VideoHub story-editing pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIMESTAMP_PATTERN = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
SPEAKER_PATTERN = re.compile(
    r"^\s*(?:\[)?(?P<speaker>[\w\u3400-\u9fff][\w\u3400-\u9fff ._-]{0,31})(?:\])?"
    r"\s*[:：]\s*(?P<text>.+)$"
)


@dataclass(frozen=True)
class SubtitleCue:
    start_sec: float
    end_sec: float
    text: str
    speaker: str = ""


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def safe_slug(value: str, fallback: str = "video") -> str:
    slug = re.sub(r"[^0-9A-Za-z\u3400-\u9fff-]+", "_", value or "")
    slug = re.sub(r"_+", "_", slug).strip("._-")
    return slug[:80] or fallback


def normalize_text(value: str) -> str:
    text = re.sub(r"\{[^{}]*\}", "", value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ")
    return re.sub(r"\s+", " ", text).strip()


def timestamp_to_seconds(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _split_speaker(text: str) -> tuple[str, str]:
    match = SPEAKER_PATTERN.match(text)
    if not match:
        return "", text
    speaker = normalize_text(match.group("speaker"))
    body = normalize_text(match.group("text"))
    if not body or any(mark in speaker for mark in "。！？!?;；"):
        return "", text
    return speaker, body


def parse_srt_or_vtt(content: str) -> list[SubtitleCue]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[SubtitleCue] = []
    index = 0

    while index < len(lines):
        match = TIMESTAMP_PATTERN.search(lines[index])
        if not match:
            index += 1
            continue

        start_sec = timestamp_to_seconds(match.group("start"))
        end_sec = timestamp_to_seconds(match.group("end"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            if not TIMESTAMP_PATTERN.search(lines[index]):
                text_lines.append(lines[index].strip())
            index += 1

        text = normalize_text(" ".join(text_lines))
        if text and end_sec > start_sec:
            speaker, body = _split_speaker(text)
            cues.append(SubtitleCue(start_sec, end_sec, body, speaker))

    return cues


def parse_ass(content: str) -> list[SubtitleCue]:
    fields = [
        "layer",
        "start",
        "end",
        "style",
        "name",
        "marginl",
        "marginr",
        "marginv",
        "effect",
        "text",
    ]
    in_events = False
    cues: list[SubtitleCue] = []
    seen: set[tuple[float, float, str]] = set()

    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip().lstrip("\ufeff")
        if line.startswith("[") and line.endswith("]"):
            in_events = line.lower() == "[events]"
            continue
        if not in_events:
            continue
        if line.lower().startswith("format:"):
            candidate = [
                item.strip().lower()
                for item in line.split(":", 1)[1].split(",")
                if item.strip()
            ]
            if {"start", "end", "text"}.issubset(candidate):
                fields = candidate
            continue
        if not line.lower().startswith("dialogue:"):
            continue

        values = line.split(":", 1)[1].lstrip().split(",", max(len(fields) - 1, 0))
        if len(values) != len(fields):
            continue
        row = dict(zip(fields, values))
        try:
            start_sec = timestamp_to_seconds(row["start"])
            end_sec = timestamp_to_seconds(row["end"])
        except (KeyError, ValueError):
            continue

        text = normalize_text(row.get("text", ""))
        if not text or end_sec <= start_sec:
            continue
        speaker = normalize_text(row.get("name", ""))
        if not speaker:
            speaker, text = _split_speaker(text)
        key = (round(start_sec, 3), round(end_sec, 3), text)
        if key in seen:
            continue
        seen.add(key)
        cues.append(SubtitleCue(start_sec, end_sec, text, speaker))

    return cues


def parse_subtitle(path: Path) -> list[SubtitleCue]:
    if not path.is_file():
        raise FileNotFoundError(f"Subtitle file not found: {path}")
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".ass", ".ssa"}:
        cues = parse_ass(content)
    elif suffix in {".srt", ".vtt"}:
        cues = parse_srt_or_vtt(content)
    else:
        raise ValueError(f"Unsupported subtitle format: {path.suffix}")
    if not cues:
        raise ValueError(f"No timed subtitle cues found in: {path}")
    return sorted(cues, key=lambda cue: (cue.start_sec, cue.end_sec))


def overlap_duration(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def pair_translations(
    source_cues: Sequence[SubtitleCue],
    target_cues: Sequence[SubtitleCue],
) -> list[str]:
    results: list[str] = []
    cursor = 0

    for source in source_cues:
        best_index = -1
        best_score = 0.0
        search_start = max(0, cursor - 3)
        for index in range(search_start, len(target_cues)):
            target = target_cues[index]
            if target.start_sec > source.end_sec + 2.0:
                break
            overlap = overlap_duration(
                source.start_sec,
                source.end_sec,
                target.start_sec,
                target.end_sec,
            )
            distance = abs(source.start_sec - target.start_sec) + abs(source.end_sec - target.end_sec)
            score = overlap * 10.0 - distance
            if score > best_score or (
                best_index < 0 and distance <= 0.8 and target.start_sec <= source.end_sec + 0.5
            ):
                best_index = index
                best_score = score
        if best_index >= 0:
            results.append(target_cues[best_index].text)
            cursor = best_index
        else:
            results.append("")
    return results


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_timestamp(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(total_cs, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass_text(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", "")
        .replace("\n", r"\N")
        .strip()
    )


def write_srt(path: Path, cues: Iterable[dict[str, Any]], text_field: str) -> int:
    rows = [cue for cue in cues if normalize_text(str(cue.get(text_field, "")))]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, cue in enumerate(rows, start=1):
            handle.write(f"{index}\n")
            handle.write(
                f"{format_srt_timestamp(float(cue['start_sec']))} --> "
                f"{format_srt_timestamp(float(cue['end_sec']))}\n"
            )
            handle.write(f"{normalize_text(str(cue[text_field]))}\n\n")
    return len(rows)


def write_ass(
    path: Path,
    cues: Iterable[dict[str, Any]],
    mode: str,
    title: str = "VideoHub Story",
    position_percent: float | None = None,
) -> int:
    rows = list(cues)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    if position_percent is None:
        target_margin = 24
        source_margin = 72
    else:
        bounded_position = min(94.0, max(12.0, float(position_percent)))
        target_margin = round((100.0 - bounded_position) * 10.8)
        source_margin = target_margin + 48

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("[Script Info]\n")
        handle.write(f"Title: {title}\n")
        handle.write("ScriptType: v4.00+\n")
        handle.write("WrapStyle: 0\n")
        handle.write("ScaledBorderAndShadow: Yes\n")
        handle.write("PlayResX: 1920\n")
        handle.write("PlayResY: 1080\n\n")
        handle.write("[V4+ Styles]\n")
        handle.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        handle.write(
            "Style: Source,Arial,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,0,2,50,50,72,1\n"
        )
        handle.write(
            "Style: Target,Microsoft YaHei,46,&H0000D7FF,&H000000FF,&H00000000,"
            f"&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,50,50,{target_margin},1\n\n"
        )
        handle.write("[Events]\n")
        handle.write(
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        for cue in rows:
            source = normalize_text(str(cue.get("source_text", "")))
            target = normalize_text(str(cue.get("target_text", "")))
            start = format_ass_timestamp(float(cue["start_sec"]))
            end = format_ass_timestamp(float(cue["end_sec"]))
            if mode in {"source", "bilingual"} and source:
                style = "Source" if mode == "bilingual" else "Target"
                margin = source_margin if mode == "bilingual" else target_margin
                handle.write(
                    f"Dialogue: 0,{start},{end},{style},,0,0,{margin},,"
                    f"{escape_ass_text(source)}\n"
                )
                written += 1
            if mode in {"translated", "bilingual"} and target:
                handle.write(
                    f"Dialogue: 1,{start},{end},Target,,0,0,{target_margin},,"
                    f"{escape_ass_text(target)}\n"
                )
                written += 1
    return written


def resolve_executable(name: str, explicit: str | None = None) -> str:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"{name} executable not found: {candidate}")

    discovered = shutil.which(name)
    if discovered:
        return discovered

    repo_root = find_repo_root()
    suffix = ".exe" if os.name == "nt" else ""
    local_candidates = [
        repo_root / "ffmpeg" / f"{name}{suffix}",
        repo_root / "ffmpeg" / "bin" / f"{name}{suffix}",
    ]
    for candidate in local_candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        f"{name} was not found. Configure VideoHub FFmpeg or pass --{name}."
    )


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "paths_config.py").is_file():
            return parent
    return Path.cwd().resolve()


def run_command(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        rendered = subprocess.list2cmdline(list(command))
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {rendered}\n{detail}")
    return result


def probe_media(video_path: Path, ffprobe: str) -> dict[str, Any]:
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        {},
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        {},
    )
    duration = payload.get("format", {}).get("duration") or video_stream.get("duration")
    if not duration:
        raise ValueError(f"Unable to determine video duration: {video_path}")

    def parse_rate(value: str | None) -> float | None:
        if not value or value in {"0/0", "N/A"}:
            return None
        numerator, denominator = value.split("/", 1)
        if float(denominator) == 0:
            return None
        return round(float(numerator) / float(denominator), 6)

    return {
        "duration_sec": round(float(duration), 3),
        "size_bytes": video_path.stat().st_size,
        "video": {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": parse_rate(video_stream.get("avg_frame_rate")),
            "pixel_format": video_stream.get("pix_fmt"),
        },
        "audio": {
            "present": bool(audio_stream),
            "codec": audio_stream.get("codec_name"),
            "sample_rate": int(audio_stream["sample_rate"])
            if str(audio_stream.get("sample_rate", "")).isdigit()
            else None,
            "channels": audio_stream.get("channels"),
        },
    }


def source_fingerprint(video_path: Path) -> str:
    digest = hashlib.sha256()
    stat = video_path.stat()
    digest.update(str(video_path.resolve()).encode("utf-8", errors="replace"))
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(str(stat.st_mtime_ns).encode("ascii"))
    with video_path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
    return digest.hexdigest()


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def referenced_ids(items: Iterable[dict[str, Any]], key: str = "id") -> set[str]:
    return {
        str(item.get(key, "")).strip()
        for item in items
        if isinstance(item, dict) and str(item.get(key, "")).strip()
    }
