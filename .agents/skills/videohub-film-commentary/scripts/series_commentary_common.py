#!/usr/bin/env python3
"""Shared configuration and media helpers for episodic commentary projects."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SeriesConfigError(ValueError):
    """Raised when a series production configuration is incomplete or unsafe."""


@dataclass(frozen=True)
class SeriesProject:
    root: Path
    config_path: Path
    episode_specs_path: Path
    config: dict[str, Any]
    episodes: dict[int, dict[str, Any]]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run(
    args: list[str],
    *,
    capture: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("$", subprocess.list2cmdline(args))
    return subprocess.run(
        args,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        cwd=str(cwd) if cwd else None,
    )


def probe(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    result = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def media_duration(path: Path, ffprobe: str = "ffprobe") -> float:
    return float(probe(path, ffprobe)["format"]["duration"])


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SeriesConfigError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SeriesConfigError(f"{label} must not be empty")
    return text


def _positive_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SeriesConfigError(f"{label} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise SeriesConfigError(f"{label} must be greater than zero")
    return number


def resolve_project_path(root: Path, value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def load_series_project(
    project_dir: str | Path,
    config_path: str | Path | None = None,
) -> SeriesProject:
    root = Path(project_dir).expanduser().resolve()
    if not root.is_dir():
        raise SeriesConfigError(f"project directory does not exist: {root}")
    resolved_config = (
        resolve_project_path(root, config_path)
        if config_path
        else root / "data" / "series_spec.json"
    )
    if not resolved_config.is_file():
        raise SeriesConfigError(f"series configuration not found: {resolved_config}")
    config = _mapping(read_json(resolved_config), "series_spec")
    if str(config.get("schema_version")) != "1.0":
        raise SeriesConfigError("series_spec.schema_version must be '1.0'")

    series = _mapping(config.get("series"), "series")
    _text(series.get("title"), "series.title")
    _text(series.get("slug"), "series.slug")
    production = _mapping(config.get("production"), "production")
    paths = _mapping(config.get("paths", {}), "paths")

    resolution = production.get("resolution", [1080, 1920])
    if (
        not isinstance(resolution, list)
        or len(resolution) != 2
        or any(int(item) <= 0 for item in resolution)
    ):
        raise SeriesConfigError("production.resolution must be [width, height]")
    production["resolution"] = [int(resolution[0]), int(resolution[1])]

    narration = _mapping(production.get("narration"), "production.narration")
    _text(narration.get("provider"), "production.narration.provider")
    _text(narration.get("model"), "production.narration.model")
    _text(narration.get("voice_id"), "production.narration.voice_id")
    _positive_number(narration.get("speed"), "production.narration.speed")
    _positive_number(
        narration.get("max_audio_speedup", 1.25),
        "production.narration.max_audio_speedup",
    )
    max_gap = float(narration.get("max_block_tail_gap_sec", 0.75))
    if not 0 <= max_gap <= 3:
        raise SeriesConfigError(
            "production.narration.max_block_tail_gap_sec must be between 0 and 3"
        )

    audio = _mapping(production.get("audio", {}), "production.audio")
    for name in ("original_audio_volume", "source_audio_volume"):
        value = float(audio.get(name, 0.0))
        if not 0 <= value <= 1:
            raise SeriesConfigError(f"production.audio.{name} must be between 0 and 1")

    episode_specs_value = paths.get("episode_specs", "data/episode_specs.json")
    episode_specs_path = resolve_project_path(root, episode_specs_value)
    if not episode_specs_path.is_file():
        raise SeriesConfigError(f"episode specs not found: {episode_specs_path}")
    raw_episodes = _mapping(read_json(episode_specs_path), "episode_specs")
    episodes: dict[int, dict[str, Any]] = {}
    for raw_number, raw_spec in raw_episodes.items():
        try:
            number = int(raw_number)
        except (TypeError, ValueError) as exc:
            raise SeriesConfigError(f"invalid episode number: {raw_number}") from exc
        if number <= 0:
            raise SeriesConfigError(f"episode number must be positive: {number}")
        spec = _mapping(raw_spec, f"episode_specs.{number}")
        _positive_number(spec.get("duration"), f"episode_specs.{number}.duration")
        _text(spec.get("summary"), f"episode_specs.{number}.summary")
        texts = spec.get("texts") or spec.get("narration_blocks")
        if not isinstance(texts, list) or not texts:
            raise SeriesConfigError(
                f"episode_specs.{number}.texts must contain narration blocks"
            )
        if any(not str(item if not isinstance(item, dict) else item.get("text", "")).strip() for item in texts):
            raise SeriesConfigError(
                f"episode_specs.{number}.texts contains an empty narration block"
            )
        starts = spec.get("source_starts")
        if starts is not None and (
            not isinstance(starts, list) or len(starts) != len(texts)
        ):
            raise SeriesConfigError(
                f"episode_specs.{number}.source_starts must match narration block count"
            )
        episodes[number] = spec
    if not episodes:
        raise SeriesConfigError("episode_specs must contain at least one episode")
    return SeriesProject(
        root=root,
        config_path=resolved_config,
        episode_specs_path=episode_specs_path,
        config=config,
        episodes=episodes,
    )


def parse_episode_selector(value: str | None, available: set[int]) -> list[int]:
    if not value:
        return sorted(available)
    selected: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if match:
            start, end = (int(match.group(1)), int(match.group(2)))
            if end < start:
                raise SeriesConfigError(f"invalid episode range: {token}")
            selected.update(range(start, end + 1))
        elif token.isdigit():
            selected.add(int(token))
        else:
            raise SeriesConfigError(f"invalid episode selector: {token}")
    unknown = sorted(selected - available)
    if unknown:
        raise SeriesConfigError(f"unknown episodes: {unknown}")
    if not selected:
        raise SeriesConfigError("episode selector is empty")
    return sorted(selected)


def configured_path(project: SeriesProject, key: str, default: str) -> Path:
    paths = project.config.get("paths", {})
    return resolve_project_path(project.root, paths.get(key, default))


def episode_input_path(
    project: SeriesProject,
    episode: int,
    kind: str,
) -> Path:
    spec = project.episodes[episode]
    explicit = spec.get(kind)
    if explicit:
        return resolve_project_path(project.root, explicit)
    paths = project.config.get("paths", {})
    if kind == "video":
        base = configured_path(project, "source_dir", "data/source_episodes")
        pattern = str(paths.get("video_pattern", "episode_{episode:02d}.mp4"))
    elif kind == "subtitle":
        base = configured_path(project, "subtitle_dir", "data/subtitles")
        pattern = str(paths.get("subtitle_pattern", "episode_{episode:02d}.srt"))
    else:
        raise SeriesConfigError(f"unsupported input kind: {kind}")
    return base / pattern.format(episode=episode)


def narration_texts(spec: dict[str, Any]) -> list[str]:
    values = spec.get("texts") or spec.get("narration_blocks") or []
    return [
        str(value if not isinstance(value, dict) else value.get("text", "")).strip()
        for value in values
    ]


def slot_duration(spec: dict[str, Any]) -> float:
    texts = narration_texts(spec)
    return float(spec.get("slot_duration") or float(spec["duration"]) / len(texts))


def source_starts(
    spec: dict[str, Any],
    source_duration: float,
) -> list[float]:
    texts = narration_texts(spec)
    configured = spec.get("source_starts")
    if configured is not None:
        return [float(value) for value in configured]
    if len(texts) == 1:
        return [0.0]
    slot = slot_duration(spec)
    if source_duration < slot:
        raise SeriesConfigError(
            f"source duration {source_duration:.3f}s is shorter than one "
            f"narration slot {slot:.3f}s"
        )
    span = max(0.0, source_duration - slot)
    return [round(index * span / (len(texts) - 1), 3) for index in range(len(texts))]


def episode_signature(project: SeriesProject, episode: int) -> str:
    production = project.config["production"]
    relevant = {
        "series": project.config["series"],
        "production": production,
        "episode": project.episodes[episode],
    }
    return payload_hash(relevant)
