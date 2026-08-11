#!/usr/bin/env python3
"""Run a configuration-driven episodic commentary production pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from series_commentary_common import (
    SeriesConfigError,
    SeriesProject,
    configured_path,
    episode_input_path,
    episode_signature,
    load_series_project,
    media_duration,
    narration_texts,
    parse_episode_selector,
    probe,
    read_json,
    resolve_project_path,
    run,
    sha256,
    slot_duration,
    source_starts,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
STORY_TOOLS = REPO_ROOT / ".agents" / "skills" / "videohub-story-editor" / "scripts"
COVER_TOOL = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "videohub-cover-designer"
    / "scripts"
    / "generate_series_covers.py"
)
AUDIT_TOOL = Path(__file__).with_name("audit_series_episode.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--episodes", help="Episode selector such as 1,3-5")
    parser.add_argument(
        "--stage",
        choices=("preflight", "prepare", "render", "package", "audit", "all"),
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--full-decode", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def evidence_refs(evidence: dict[str, Any], key: str) -> list[str]:
    return [str(item["id"]) for item in evidence.get(key, []) if item.get("id")]


def episode_paths(project: SeriesProject, episode: int) -> dict[str, Path]:
    job_root = configured_path(project, "job_root", "docs/story_jobs") / f"episode_{episode:02d}"
    output = configured_path(project, "episode_output_root", "outputs/episodes") / f"episode_{episode:02d}"
    package = configured_path(project, "package_root", "outputs/publish_packages") / f"episode_{episode:02d}"
    return {
        "video": episode_input_path(project, episode, "video"),
        "subtitle": episode_input_path(project, episode, "subtitle"),
        "job": job_root,
        "evidence_dir": job_root / "evidence",
        "evidence": job_root / "evidence" / "evidence_pack.json",
        "analysis": job_root / "story_analysis.json",
        "plan": job_root / "story_plan.json",
        "narration": job_root / "narration_plan.json",
        "output": output,
        "audio": output / "narration.wav",
        "narration_srt": output / "narration.srt",
        "narration_manifest": output / "narration_manifest.json",
        "final": output / "final.mp4",
        "render_qa": output / "render_qa.md",
        "package": package,
        "publish_manifest": package / "publish_manifest.json",
        "audit": job_root / "series_episode_audit.json",
    }


def preflight_episode(
    project: SeriesProject,
    episode: int,
    ffprobe: str,
) -> dict[str, Any]:
    paths = episode_paths(project, episode)
    missing = [name for name in ("video", "subtitle") if not paths[name].is_file()]
    if missing:
        raise FileNotFoundError(
            f"episode {episode} missing inputs: "
            + ", ".join(str(paths[name]) for name in missing)
        )
    media = probe(paths["video"], ffprobe)
    duration = float(media["format"]["duration"])
    starts = source_starts(project.episodes[episode], duration)
    slot = slot_duration(project.episodes[episode])
    if any(start < 0 or start + slot > duration + 0.1 for start in starts):
        raise SeriesConfigError(
            f"episode {episode} source_starts exceed the source duration"
        )
    return {
        "episode": episode,
        "signature": episode_signature(project, episode),
        "video": str(paths["video"]),
        "subtitle": str(paths["subtitle"]),
        "source_duration_sec": duration,
        "target_duration_sec": float(project.episodes[episode]["duration"]),
        "slot_duration_sec": slot,
        "source_starts_sec": starts,
        "video_streams": [
            item for item in media.get("streams", []) if item.get("codec_type") == "video"
        ],
        "audio_streams": [
            item for item in media.get("streams", []) if item.get("codec_type") == "audio"
        ],
        "status": "PASS",
    }


def build_evidence(
    project: SeriesProject,
    episode: int,
    paths: dict[str, Path],
    force: bool,
) -> dict[str, Any]:
    if force or not paths["evidence"].is_file():
        series = project.config["series"]
        run(
            [
                sys.executable,
                str(STORY_TOOLS / "build_evidence_pack.py"),
                "--video",
                str(paths["video"]),
                "--subtitle",
                str(paths["subtitle"]),
                "--language",
                str(series.get("source_language", "zh-CN")),
                "--target-language",
                str(project.config["production"].get("target_language", "zh-CN")),
                "--job-id",
                f"{series['slug']}_ep{episode:02d}",
                "--output-dir",
                str(paths["evidence_dir"]),
                "--scene-threshold",
                str(project.config["production"].get("scene_threshold", 0.30)),
                "--max-keyframes",
                str(project.config["production"].get("max_keyframes", 24)),
            ]
        )
    return read_json(paths["evidence"])


def make_analysis(
    project: SeriesProject,
    episode: int,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    spec = project.episodes[episode]
    job_id = f"{project.config['series']['slug']}_ep{episode:02d}"
    subtitle_ids = evidence_refs(evidence, "subtitles")
    scene_ids = evidence_refs(evidence, "scenes")
    frame_ids = evidence_refs(evidence, "keyframes")
    chunks = evidence.get("analysis_chunks", [])
    opening = subtitle_ids[:4] or scene_ids[:4]
    closing = subtitle_ids[-4:] or scene_ids[-4:]
    evidence_base = opening or closing
    angle = str(spec.get("angle") or "按因果顺序压缩本集剧情，以旁白保持连续性。")
    entities = spec.get("entities") or []
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "selected_option_id": "option-01",
        "global_summary": spec["summary"],
        "content_profile": {
            "type": str(project.config["series"].get("content_type", "drama")),
            "confidence": 0.9,
            "evidence_refs": evidence_base[:3],
        },
        "chunk_findings": [
            {
                "id": f"finding-{index:03d}",
                "chunk_id": str(chunk["id"]),
                "summary": str(
                    chunk.get("summary")
                    or chunk.get("source_text")
                    or f"第{index}个证据分块用于核对当前集剧情。"
                ),
                "evidence_refs": [str(chunk["id"])],
            }
            for index, chunk in enumerate(chunks, 1)
            if isinstance(chunk, dict) and chunk.get("id")
        ],
        "events": [
            {
                "id": "event-01",
                "label": "本集开端",
                "kind": "event",
                "chronology_index": 1,
                "summary": str(spec.get("opening") or "建立人物处境和本集冲突。"),
                "cause_event_ids": [],
                "evidence_refs": opening[:3],
                "confidence": 0.9,
            },
            {
                "id": "event-02",
                "label": "冲突推进",
                "kind": "event",
                "chronology_index": 2,
                "summary": spec["summary"],
                "cause_event_ids": ["event-01"],
                "evidence_refs": evidence_base[:4],
                "confidence": 0.9,
            },
            {
                "id": "event-03",
                "label": "阶段结果",
                "kind": "result",
                "chronology_index": 3,
                "summary": str(spec.get("closing") or "冲突形成阶段结果或新的悬念。"),
                "cause_event_ids": ["event-02"],
                "evidence_refs": closing[:4],
                "confidence": 0.9,
            },
        ],
        "themes": [
            {
                "id": "theme-main",
                "label": str(spec.get("theme") or "选择与结果"),
                "summary": spec["summary"],
                "evidence_refs": evidence_base[:3],
            }
        ],
        "visual_findings": [
            {
                "id": "visual-main",
                "summary": "当前集画面用于核对人物、动作和叙事阶段。",
                "frame_refs": frame_ids[:8],
                "scene_refs": scene_ids[:8],
                "candidate_refs": [],
                "confidence": 0.9,
            }
        ],
        "continuity_constraints": [
            {
                "id": "constraint-chronology",
                "type": "chronology",
                "description": "保持当前集因果顺序，旁白必须与对应画面阶段一致。",
                "required_before_refs": opening[:2],
                "protected_refs": closing[:2],
            }
        ],
        "story_options": [
            {
                "id": "option-01",
                "premise": spec["summary"],
                "angle": angle,
                "estimated_duration_sec": float(spec["duration"]),
                "target_audience": str(spec.get("target_audience") or "连续剧解说观众"),
                "arc": [
                    {"id": "arc-hook", "role": "hook", "purpose": "建立悬念。", "evidence_refs": opening[:1]},
                    {"id": "arc-context", "role": "context", "purpose": "补齐处境。", "evidence_refs": opening[:2]},
                    {"id": "arc-development", "role": "development", "purpose": "推进冲突。", "evidence_refs": evidence_base[:3]},
                    {"id": "arc-turn", "role": "turn", "purpose": "呈现转折。", "evidence_refs": closing[:2]},
                    {"id": "arc-resolution", "role": "resolution", "purpose": "交代结果。", "evidence_refs": closing[:3]},
                    {"id": "arc-closing", "role": "closing", "purpose": "形成收束或悬念。", "evidence_refs": closing[-1:]},
                ],
                "risks": ["外部剧情资料只用于校验，具体剪辑以本地字幕和画面为准。"],
            }
        ],
        "entities": entities,
        "uncertainties": spec.get("uncertainties") or [],
    }


def make_story_plan(
    project: SeriesProject,
    episode: int,
    paths: dict[str, Path],
    evidence: dict[str, Any],
    source_duration: float,
) -> tuple[dict[str, Any], list[float]]:
    spec = project.episodes[episode]
    production = project.config["production"]
    texts = narration_texts(spec)
    slot = slot_duration(spec)
    starts = source_starts(spec, source_duration)
    roles = ["hook", "context", "development", "development", "turn", "resolution", "resolution", "closing"]
    subtitles = evidence.get("subtitles", [])
    scenes = evidence.get("scenes", [])
    segments: list[dict[str, Any]] = []
    for index, (start, narration) in enumerate(zip(starts, texts), 1):
        end = min(source_duration, start + slot)
        if end - start < slot - 0.05:
            start = max(0.0, source_duration - slot)
            end = source_duration
        subtitle_ids = [
            str(item["id"])
            for item in subtitles
            if float(item.get("start_sec", 0)) < end
            and float(item.get("end_sec", 0)) > start
        ]
        scene_ids = [
            str(item["id"])
            for item in scenes
            if float(item.get("start_sec", 0)) < end
            and float(item.get("end_sec", 0)) > start
        ]
        source_text = " ".join(
            str(item.get("source_text", ""))
            for item in subtitles
            if str(item.get("id", "")) in subtitle_ids
        ).strip()
        segments.append(
            {
                "id": f"seg-{index:03d}",
                "kind": "dialogue" if source_text else "visual",
                "story_role": roles[min(index - 1, len(roles) - 1)],
                "source_start_sec": round(start, 3),
                "source_end_sec": round(end, 3),
                "output_start_sec": round((index - 1) * slot, 3),
                "output_end_sec": round(index * slot, 3),
                "playback_rate": 1.0,
                "source_subtitle_ids": subtitle_ids,
                "source_scene_ids": scene_ids or evidence_refs(evidence, "scenes")[:1],
                "analysis_refs": ["event-01", "event-02", "event-03"],
                "output_order": index,
                "source_text": source_text,
                "audio_mode": "source",
                "narration_text": narration,
                "narration_source": "editorial_bridge",
                "story_reason": f"第{episode}集第{index}个叙事阶段，与本时间窗画面对应。",
                "transition": "cut",
            }
        )
    source = evidence["source"]
    return {
        "schema_version": "1.0",
        "job_id": f"{project.config['series']['slug']}_ep{episode:02d}",
        "selected_option_id": "option-01",
        "source": {
            "video_path": str(paths["video"].resolve()),
            "subtitle_path": str(paths["subtitle"].resolve()),
            "fingerprint": source.get("fingerprint", ""),
            "duration_sec": source.get("duration_sec"),
            "language": str(project.config["series"].get("source_language", "zh-CN")),
        },
        "settings": {
            "target_duration_sec": float(spec["duration"]),
            "duration_tolerance_ratio": float(production.get("duration_tolerance_ratio", 0.003)),
            "target_language": str(production.get("target_language", "zh-CN")),
            "subtitle_mode": str(production.get("subtitle_mode", "source")),
            "translation_stage": str(production.get("translation_stage", "post_edit")),
            "translation_polish": bool(production.get("translation_polish", False)),
            "allow_speed_change": False,
            "original_audio_volume": float(production["audio"].get("original_audio_volume", 0.0)),
            "source_audio_volume": float(production["audio"].get("source_audio_volume", 0.0)),
        },
        "segments": segments,
        "story": {
            "premise": spec["summary"],
            "selected_option_id": "option-01",
            "arc": ["hook", "context", "development", "turn", "resolution", "closing"],
        },
        "classification": {
            "type": str(project.config["series"].get("content_type", "drama")),
            "confidence": 0.9,
            "evidence": [
                "当前集字幕时间线",
                "当前集场景和关键帧",
                "当前集视频时长和音视频流",
            ],
            "evidence_refs": evidence_refs(evidence, "subtitles")[:3]
            or evidence_refs(evidence, "scenes")[:3],
        },
        "output": {
            "video_path": str(paths["final"].resolve()),
            "source_subtitle_path": str((paths["output"] / "story_source.srt").resolve()),
            "qa_report_path": str(paths["render_qa"].resolve()),
        },
    }, starts


def make_narration_plan(
    project: SeriesProject,
    episode: int,
    plan_path: Path,
) -> dict[str, Any]:
    spec = project.episodes[episode]
    production = project.config["production"]
    narration = production["narration"]
    audio = production["audio"]
    slot = slot_duration(spec)
    blocks = [
        {
            "id": f"nar-{index:03d}",
            "start_sec": round((index - 1) * slot, 3),
            "end_sec": round(index * slot, 3),
            "text": text,
            "subtitle_text": text,
            "purpose": "连续第三者旁白，与对应画面阶段保持一致。",
            "evidence_refs": [f"seg-{index:03d}", "event-01", "event-02"],
        }
        for index, text in enumerate(narration_texts(spec), 1)
    ]
    return {
        "schema_version": "1.0",
        "job_id": f"{project.config['series']['slug']}_ep{episode:02d}",
        "story_plan_path": str(plan_path.resolve()),
        "style": str(production.get("style", "film_commentary")),
        "settings": {
            "target_language": str(production.get("target_language", "zh-CN")),
            "audio_strategy": str(audio.get("strategy", "narration_only")),
            "original_audio_volume": float(audio.get("original_audio_volume", 0.0)),
            "source_audio_volume": float(audio.get("source_audio_volume", 0.0)),
            "max_audio_speedup": float(narration.get("max_audio_speedup", 1.25)),
        },
        "tts": {
            "provider": narration["provider"],
            "model": narration["model"],
            "voice_id": narration["voice_id"],
            "speed": float(narration["speed"]),
            "language_boost": str(narration.get("language_boost", "Chinese")),
        },
        "blocks": blocks,
        "source_audio_windows": spec.get("source_audio_windows") or [],
    }


def prepare_episode(
    project: SeriesProject,
    episode: int,
    preflight: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    paths = episode_paths(project, episode)
    evidence = build_evidence(project, episode, paths, force)
    analysis = make_analysis(project, episode, evidence)
    plan, starts = make_story_plan(
        project,
        episode,
        paths,
        evidence,
        float(preflight["source_duration_sec"]),
    )
    narration = make_narration_plan(project, episode, paths["plan"])
    write_json(paths["analysis"], analysis)
    write_json(paths["plan"], plan)
    write_json(paths["narration"], narration)
    run(
        [
            sys.executable,
            str(STORY_TOOLS / "validate_story_analysis.py"),
            str(paths["analysis"]),
            "--evidence",
            str(paths["evidence"]),
        ]
    )
    run(
        [
            sys.executable,
            str(STORY_TOOLS / "validate_story_plan.py"),
            str(paths["plan"]),
            "--evidence",
            str(paths["evidence"]),
            "--analysis",
            str(paths["analysis"]),
        ]
    )
    run(
        [
            sys.executable,
            str(STORY_TOOLS / "validate_narration_plan.py"),
            str(paths["narration"]),
            "--story-plan",
            str(paths["plan"]),
            "--evidence",
            str(paths["evidence"]),
            "--analysis",
            str(paths["analysis"]),
        ]
    )
    return {"episode": episode, "status": "PREPARED", "source_starts_sec": starts}


def validate_continuity(project: SeriesProject, manifest_path: Path) -> dict[str, float]:
    manifest = read_json(manifest_path)
    narration = project.config["production"]["narration"]
    gap_limit = float(narration.get("max_block_tail_gap_sec", 0.75))
    speed_limit = float(narration.get("max_audio_speedup", 1.25))
    max_gap = 0.0
    max_speedup = 1.0
    failures: list[str] = []
    for block in manifest.get("blocks", []):
        slot = float(block["slot_end_sec"]) - float(block["slot_start_sec"])
        gap = slot - float(block["final_duration_sec"])
        speedup = float(
            block.get("audio_speedup")
            or block.get("speedup_ratio")
            or block.get("speedup_applied")
            or 1.0
        )
        max_gap = max(max_gap, gap)
        max_speedup = max(max_speedup, speedup)
        if gap > gap_limit + 0.001:
            failures.append(f"{block['id']} tail_gap={gap:.3f}s")
        if speedup > speed_limit + 0.001:
            failures.append(f"{block['id']} speedup={speedup:.3f}x")
    if failures:
        raise RuntimeError("narration continuity failed: " + ", ".join(failures))
    return {"max_tail_gap_sec": max_gap, "max_speedup": max_speedup}


def exact_audio(path: Path, target: float, ffmpeg: str, ffprobe: str) -> None:
    fixed = path.with_name(path.stem + ".fixed.wav")
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-af",
            "apad",
            "-t",
            f"{target:.3f}",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(fixed),
        ]
    )
    fixed.replace(path)
    actual = media_duration(path, ffprobe)
    if abs(actual - target) > 0.1:
        raise RuntimeError(f"narration duration mismatch: {actual:.3f}s vs {target:.3f}s")


def detection_events(ffmpeg: str, video: Path, kind: str) -> list[str]:
    if kind == "silence":
        command = [ffmpeg, "-hide_banner", "-i", str(video), "-af", "silencedetect=noise=-45dB:d=1.0", "-f", "null", "-"]
        needles = ("silence_start", "silence_end")
    else:
        command = [ffmpeg, "-hide_banner", "-i", str(video), "-vf", "blackdetect=d=1.0:pix_th=0.10", "-an", "-f", "null", "-"]
        needles = ("black_start",)
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    return [line.strip() for line in result.stderr.splitlines() if any(item in line for item in needles)]


def render_episode(
    project: SeriesProject,
    episode: int,
    force: bool,
    ffmpeg: str,
    ffprobe: str,
) -> dict[str, Any]:
    paths = episode_paths(project, episode)
    required = ("evidence", "analysis", "plan", "narration")
    missing = [str(paths[name]) for name in required if not paths[name].is_file()]
    if missing:
        raise FileNotFoundError("prepare stage is incomplete: " + ", ".join(missing))
    if paths["final"].is_file() and not force:
        return {"episode": episode, "status": "REUSED", "video": str(paths["final"])}
    paths["output"].mkdir(parents=True, exist_ok=True)
    provider = str(project.config["production"]["narration"]["provider"])
    run(
        [
            sys.executable,
            str(STORY_TOOLS / "synthesize_story_narration.py"),
            str(paths["narration"]),
            "--story-plan",
            str(paths["plan"]),
            "--evidence",
            str(paths["evidence"]),
            "--analysis",
            str(paths["analysis"]),
            "--provider",
            provider,
            "--output",
            str(paths["audio"]),
            "--subtitle-output",
            str(paths["narration_srt"]),
            "--manifest",
            str(paths["narration_manifest"]),
            "--ffmpeg",
            ffmpeg,
            "--ffprobe",
            ffprobe,
        ]
    )
    continuity = validate_continuity(project, paths["narration_manifest"])
    target = float(project.episodes[episode]["duration"])
    exact_audio(paths["audio"], target, ffmpeg, ffprobe)
    production = project.config["production"]
    command = [
        sys.executable,
        str(STORY_TOOLS / "render_story.py"),
        str(paths["plan"]),
        "--evidence",
        str(paths["evidence"]),
        "--analysis",
        str(paths["analysis"]),
        "--narration-audio",
        str(paths["audio"]),
        "--narration-subtitle",
        str(paths["narration_srt"]),
        "--narration-plan",
        str(paths["narration"]),
        "--background-volume",
        str(production["audio"].get("original_audio_volume", 0.0)),
        "--burn-subtitles",
        str(production.get("burn_subtitles", "none")),
        "--source-audio-stream",
        str(production.get("source_audio_stream", 0)),
        "--segment-cache-dir",
        str(project.root / ".story_editor_cache" / "segments"),
        "--output",
        str(paths["final"]),
        "--qa-report",
        str(paths["render_qa"]),
        "--ffmpeg",
        ffmpeg,
        "--ffprobe",
        ffprobe,
    ]
    run(command)
    actual = media_duration(paths["final"], ffprobe)
    tolerance = float(production.get("duration_tolerance_sec", 0.2))
    if abs(actual - target) > tolerance:
        raise RuntimeError(f"episode {episode} duration failed: {actual:.3f}s")
    silence = detection_events(ffmpeg, paths["final"], "silence")
    black = detection_events(ffmpeg, paths["final"], "black")
    if silence:
        raise RuntimeError(f"episode {episode} contains >=1s silence: {silence}")
    if black:
        raise RuntimeError(f"episode {episode} contains >=1s black frame: {black}")
    return {
        "episode": episode,
        "status": "RENDERED",
        "video": str(paths["final"]),
        **continuity,
    }


def format_timestamp(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def build_chapters(spec: dict[str, Any]) -> tuple[str, str]:
    texts = narration_texts(spec)
    count = int(spec.get("chapter_count") or (4 if len(texts) <= 6 else 5))
    count = max(3, min(7, count))
    markdown = ["| 时间 | 内容 |", "| --- | --- |"]
    plain: list[str] = []
    for index in range(count):
        start = float(spec["duration"]) * index / count
        end = float(spec["duration"]) * (index + 1) / count
        block_start = int(index * len(texts) / count)
        block_end = max(block_start + 1, int((index + 1) * len(texts) / count))
        summary = " ".join(texts[block_start:block_end]).split("。", 1)[0]
        label = f"{format_timestamp(start)}-{format_timestamp(end)}"
        markdown.append(f"| {label} | {summary} |")
        plain.append(f"{format_timestamp(start)} {summary}")
    return "\n".join(markdown) + "\n", "\n".join(plain) + "\n"


def package_episode(
    project: SeriesProject,
    episode: int,
    force: bool,
    ffprobe: str,
) -> dict[str, Any]:
    paths = episode_paths(project, episode)
    if not paths["final"].is_file():
        raise FileNotFoundError(f"rendered video not found: {paths['final']}")
    signature = episode_signature(project, episode)
    if paths["publish_manifest"].is_file() and not force:
        existing = read_json(paths["publish_manifest"])
        if existing.get("production_signature") == signature:
            return existing
    series = project.config["series"]
    spec = project.episodes[episode]
    delivery = project.config.get("delivery", {})
    package = paths["package"]
    package.mkdir(parents=True, exist_ok=True)
    duration_tag = f"{float(spec['duration']):.3f}".rstrip("0").rstrip(".")
    video_name = str(
        spec.get("output_name")
        or f"{series['title']}_第{episode}集_{duration_tag}秒_解说.mp4"
    )
    package_video = package / video_name
    shutil.copy2(paths["final"], package_video)
    for source, name in (
        (paths["narration_srt"], "narration.srt"),
        (paths["plan"], "story_plan.json"),
        (paths["narration_manifest"], "narration_manifest.json"),
    ):
        if source.is_file():
            shutil.copy2(source, package / name)

    cover = project.config.get("cover", {})
    cover_source_value = cover.get("source") or project.config.get("paths", {}).get("cover_source")
    cover_files: list[str] = []
    if cover_source_value:
        cover_source = resolve_project_path(project.root, cover_source_value)
        if not cover_source.is_file():
            raise FileNotFoundError(f"cover source not found: {cover_source}")
        cover_dir = package / "cover_assets"
        formats = list(cover.get("formats") or ["cover_9x16.jpg", "cover_3x4.jpg", "cover_4x3.jpg", "cover_16x9.jpg"])
        command = [
            sys.executable,
            str(COVER_TOOL),
            "--source",
            str(cover_source),
            "--output-dir",
            str(cover_dir),
            "--title",
            str(series["title"]),
            "--episode",
            f"{episode:02d}",
            "--episode-label",
            str(spec.get("episode_label") or f"第{episode}集"),
            "--category",
            str(cover.get("category") or delivery.get("category") or "影视解说"),
            "--focus-x",
            str(cover.get("focus_x", 0.63)),
            "--focus-y",
            str(cover.get("focus_y", 0.48)),
            "--formats",
            *formats,
        ]
        for hook in list(spec.get("hooks") or [])[:2]:
            command.extend(["--hook", str(hook)])
        if cover.get("landscape_source"):
            command.extend(["--landscape-source", str(resolve_project_path(project.root, cover["landscape_source"]))])
        for key in ("landscape_focus_x", "landscape_focus_y", "accent", "badge_color"):
            if key in cover:
                command.extend(["--" + key.replace("_", "-"), str(cover[key])])
        run(command)
        cover_files = [f"cover_assets/{name}" for name in formats]
        preview = cover_dir / "thumbnail_preview.jpg"
        if preview.is_file():
            cover_files.append("cover_assets/thumbnail_preview.jpg")

    hooks = list(spec.get("hooks") or [spec["summary"]])
    titles = list(spec.get("titles") or [])
    if not titles:
        titles = [
            f"《{series['title']}》第{episode}集：{hooks[0]}",
            f"{series['title']} 第{episode}集｜{hooks[-1]}",
            f"第{episode}集剧情解说：{spec['summary']}",
        ]
    caption = str(spec.get("caption") or spec["summary"])
    hashtags = list(spec.get("hashtags") or delivery.get("hashtags") or [series["title"], "影视解说", "剧透社"])
    hashtag_text = " ".join(f"#{item.lstrip('#')}" for item in hashtags)
    (package / "titles.txt").write_text("\n".join(titles) + "\n", encoding="utf-8")
    (package / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    (package / "hashtags.txt").write_text(hashtag_text + "\n", encoding="utf-8")
    chapters_md, chapters_txt = build_chapters(spec)
    (package / "chapters.md").write_text(f"# 《{series['title']}》第{episode}集章节\n\n" + chapters_md, encoding="utf-8")
    (package / "chapters.txt").write_text(chapters_txt, encoding="utf-8")
    narration = project.config["production"]["narration"]
    audio = project.config["production"]["audio"]
    (package / "publish_info.md").write_text(
        f"# 发布信息\n\n## 推荐标题\n\n{titles[0]}\n\n## 文案\n\n{caption}\n\n"
        f"## 话题\n\n{hashtag_text}\n\n## 音频\n\n- {narration['provider']} {narration['voice_id']}\n"
        f"- 语速 {narration['speed']}x\n- 旁白音量 1.0\n- 原声音量 {audio.get('original_audio_volume', 0.0)}\n",
        encoding="utf-8",
    )
    media = probe(package_video, ffprobe)
    video_stream = next(item for item in media["streams"] if item.get("codec_type") == "video")
    audio_stream = next(item for item in media["streams"] if item.get("codec_type") == "audio")
    manifest = {
        "schema_version": "1.0",
        "series": series["title"],
        "episode": episode,
        "production_signature": signature,
        "video_file": package_video.name,
        "assets": [{"name": package_video.name, "kind": "video"}],
        "video_sha256": sha256(package_video),
        "duration_sec": float(media["format"]["duration"]),
        "media": {
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": audio_stream.get("codec_name"),
            "sample_rate": audio_stream.get("sample_rate"),
            "channels": audio_stream.get("channels"),
        },
        "audio": {
            "provider": narration["provider"],
            "voice": narration["voice_id"],
            "speed": narration["speed"],
            "original_audio_volume": audio.get("original_audio_volume", 0.0),
            "source_audio_volume": audio.get("source_audio_volume", 0.0),
        },
        "cover_files": cover_files,
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    write_json(paths["publish_manifest"], manifest)
    checksum_lines = [
        f"{sha256(item)}  {item.relative_to(package).as_posix()}"
        for item in sorted(package.rglob("*"))
        if item.is_file() and item.name != "SHA256SUMS.txt"
    ]
    (package / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return manifest


def audit_episode(
    project: SeriesProject,
    episode: int,
    full_decode: bool,
    ffmpeg: str,
    ffprobe: str,
) -> dict[str, Any]:
    paths = episode_paths(project, episode)
    production = project.config["production"]
    width, height = production["resolution"]
    formats = list(project.config.get("cover", {}).get("formats") or [])
    command = [
        sys.executable,
        str(AUDIT_TOOL),
        str(project.root),
        "--video",
        str(paths["final"]),
        "--package",
        str(paths["package"]),
        "--expected-duration",
        str(project.episodes[episode]["duration"]),
        "--duration-tolerance",
        str(production.get("duration_tolerance_sec", 0.2)),
        "--expected-width",
        str(width),
        "--expected-height",
        str(height),
        "--ffmpeg",
        ffmpeg,
        "--ffprobe",
        ffprobe,
        "--json-out",
        str(paths["audit"]),
    ]
    for name in formats:
        command.extend(["--expected-cover", name])
    coverage = paths["job"] / "source_dialogue_coverage.json"
    if coverage.is_file():
        command.extend(["--coverage-report", str(coverage)])
    if full_decode:
        command.append("--full-decode")
    run(command)
    return read_json(paths["audit"])


def selected_stages(stage: str) -> list[str]:
    if stage == "all":
        return ["preflight", "prepare", "render", "package", "audit"]
    return [stage]


def main() -> int:
    args = parse_args()
    try:
        project = load_series_project(args.project_dir, args.config)
        episodes = parse_episode_selector(args.episodes, set(project.episodes))
        stages = selected_stages(args.stage)
        preflight_results = {
            episode: preflight_episode(project, episode, args.ffprobe)
            for episode in episodes
        }
        report: dict[str, Any] = {
            "schema_version": "1.0",
            "series": project.config["series"]["title"],
            "project": str(project.root),
            "episodes": episodes,
            "stages": stages,
            "results": {},
        }
        preflight_path = configured_path(project, "preflight_report", "docs/series_preflight.json")
        write_json(preflight_path, {"schema_version": "1.0", "episodes": list(preflight_results.values())})
        for episode in episodes:
            result: dict[str, Any] = {"preflight": preflight_results[episode]}
            if "prepare" in stages:
                result["prepare"] = prepare_episode(
                    project, episode, preflight_results[episode], args.force
                )
            if "render" in stages:
                result["render"] = render_episode(
                    project, episode, args.force, args.ffmpeg, args.ffprobe
                )
            if "package" in stages:
                result["package"] = package_episode(
                    project, episode, args.force, args.ffprobe
                )
            if "audit" in stages:
                result["audit"] = audit_episode(
                    project,
                    episode,
                    args.full_decode,
                    args.ffmpeg,
                    args.ffprobe,
                )
            report["results"][str(episode)] = result
        report["status"] = "PASS"
    except (SeriesConfigError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        report = {"schema_version": "1.0", "status": "FAIL", "error": str(exc)}
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.json_out:
            output = resolve_project_path(args.project_dir.resolve(), args.json_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        print(rendered, file=sys.stderr, end="")
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        output = resolve_project_path(project.root, args.json_out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
