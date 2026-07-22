#!/usr/bin/env python3
"""Build a grounded evidence pack from a video and timed subtitles."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from story_pipeline_common import (
    find_repo_root,
    overlap_duration,
    pair_translations,
    parse_subtitle,
    probe_media,
    resolve_executable,
    run_command,
    safe_slug,
    source_fingerprint,
    write_json,
)

PTS_TIME_PATTERN = re.compile(r"pts_time:(?P<time>-?\d+(?:\.\d+)?)")


def detect_scene_boundaries(
    video_path: Path,
    ffmpeg: str,
    duration_sec: float,
    threshold: float,
) -> list[float]:
    expression = f"select=gt(scene\\,{threshold}),showinfo"
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video_path),
            "-an",
            "-vf",
            expression,
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"FFmpeg scene detection failed:\n{detail}")

    boundaries = [0.0]
    for match in PTS_TIME_PATTERN.finditer(result.stderr):
        timestamp = float(match.group("time"))
        if 0.4 < timestamp < duration_sec - 0.4:
            boundaries.append(timestamp)
    boundaries.append(duration_sec)

    deduplicated: list[float] = []
    for timestamp in sorted(boundaries):
        if not deduplicated or timestamp - deduplicated[-1] >= 0.4:
            deduplicated.append(round(timestamp, 3))
    if deduplicated[-1] < duration_sec:
        deduplicated.append(round(duration_sec, 3))
    else:
        deduplicated[-1] = round(duration_sec, 3)
    return deduplicated


def build_scenes(boundaries: list[float]) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        if end <= start:
            continue
        scenes.append(
            {
                "id": f"scene-{index:04d}",
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": round(end - start, 3),
            }
        )
    return scenes


def _split_interval(start: float, end: float, maximum: float = 6.0) -> list[tuple[float, float]]:
    if end <= start:
        return []
    if end - start <= maximum:
        return [(start, end)]
    chunks: list[tuple[float, float]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(end, cursor + maximum)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def build_visual_candidates(
    subtitles: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    duration_sec: float,
    min_gap_sec: float,
) -> list[dict[str, Any]]:
    occupied = sorted(
        (
            max(0.0, float(item["start_sec"])),
            min(duration_sec, float(item["end_sec"])),
        )
        for item in subtitles
    )
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in occupied:
        if start - cursor >= min_gap_sec:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if duration_sec - cursor >= min_gap_sec:
        gaps.append((cursor, duration_sec))

    candidates: list[dict[str, Any]] = []
    for gap_start, gap_end in gaps:
        split_points = [gap_start]
        split_points.extend(
            float(scene["start_sec"])
            for scene in scenes
            if gap_start < float(scene["start_sec"]) < gap_end
        )
        split_points.append(gap_end)

        for section_start, section_end in zip(split_points, split_points[1:]):
            if section_end - section_start < min_gap_sec:
                continue
            for start, end in _split_interval(section_start, section_end):
                if end - start < min_gap_sec:
                    continue
                scene_ids = [
                    str(scene["id"])
                    for scene in scenes
                    if overlap_duration(
                        start,
                        end,
                        float(scene["start_sec"]),
                        float(scene["end_sec"]),
                    )
                    > 0
                ]
                candidates.append(
                    {
                        "id": f"visual-{len(candidates) + 1:04d}",
                        "start_sec": round(start, 3),
                        "end_sec": round(end, 3),
                        "duration_sec": round(end - start, 3),
                        "scene_ids": scene_ids,
                        "reason": "subtitle_gap",
                        "requires_visual_review": True,
                    }
                )
    return candidates


def select_keyframe_times(
    scenes: list[dict[str, Any]],
    visual_candidates: list[dict[str, Any]],
    duration_sec: float,
    maximum: int,
) -> list[float]:
    if maximum <= 0:
        return []

    prioritized: list[float] = []
    prioritized.extend(
        (float(item["start_sec"]) + float(item["end_sec"])) / 2.0
        for item in visual_candidates
    )

    if len(prioritized) < maximum:
        scene_step = max(1, len(scenes) // max(1, maximum - len(prioritized)))
        prioritized.extend(
            (float(scene["start_sec"]) + float(scene["end_sec"])) / 2.0
            for scene in scenes[::scene_step]
        )

    if len(prioritized) < maximum:
        remaining = maximum - len(prioritized)
        prioritized.extend(
            duration_sec * (index + 1) / (remaining + 1)
            for index in range(remaining)
        )

    selected: list[float] = []
    for timestamp in prioritized:
        bounded = min(max(0.0, timestamp), max(0.0, duration_sec - 0.05))
        if all(abs(bounded - existing) >= 0.5 for existing in selected):
            selected.append(round(bounded, 3))
        if len(selected) >= maximum:
            break
    return sorted(selected)


def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    ffmpeg: str,
    timestamps: list[float],
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    keyframes: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        path = output_dir / f"frame-{index:04d}_{timestamp:010.3f}s.jpg"
        result = run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                "-q:v",
                "3",
                "-y",
                str(path),
            ],
            check=False,
        )
        if result.returncode != 0 or not path.is_file():
            print(
                f"WARNING: failed to extract keyframe at {timestamp:.3f}s",
                file=sys.stderr,
            )
            continue
        keyframes.append(
            {
                "id": f"frame-{len(keyframes) + 1:04d}",
                "time_sec": round(timestamp, 3),
                "path": path.resolve().as_posix(),
                "observation": "",
                "requires_visual_review": True,
            }
        )
    return keyframes


def build_analysis_chunks(
    output_dir: Path,
    duration_sec: float,
    chunk_duration_sec: float,
    subtitles: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    keyframes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunk_dir = output_dir / "analysis_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, Any]] = []
    chunk_count = max(1, int((duration_sec + chunk_duration_sec - 0.001) // chunk_duration_sec))

    for index in range(chunk_count):
        start = index * chunk_duration_sec
        end = min(duration_sec, (index + 1) * chunk_duration_sec)
        chunk_id = f"chunk-{index + 1:03d}"
        chunk_subtitles = [
            item
            for item in subtitles
            if overlap_duration(
                start,
                end,
                float(item["start_sec"]),
                float(item["end_sec"]),
            )
            > 0
        ]
        scene_ids = [
            str(item["id"])
            for item in scenes
            if overlap_duration(
                start,
                end,
                float(item["start_sec"]),
                float(item["end_sec"]),
            )
            > 0
        ]
        frame_ids = [
            str(item["id"])
            for item in keyframes
            if start <= float(item["time_sec"]) < end
        ]
        path = chunk_dir / f"{chunk_id}.json"
        payload = {
            "schema_version": "1.0",
            "chunk_id": chunk_id,
            "start_sec": round(start, 3),
            "end_sec": round(end, 3),
            "subtitle_ids": [str(item["id"]) for item in chunk_subtitles],
            "scene_ids": scene_ids,
            "keyframe_ids": frame_ids,
            "subtitles": chunk_subtitles,
        }
        write_json(path, payload)
        chunks.append(
            {
                "id": chunk_id,
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "path": path.resolve().as_posix(),
                "subtitle_count": len(chunk_subtitles),
                "scene_ids": scene_ids,
                "keyframe_ids": frame_ids,
            }
        )
    return chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="Source video path")
    parser.add_argument(
        "--subtitle",
        type=Path,
        required=True,
        help="Timed source subtitle (.srt, .vtt, .ass, or .ssa)",
    )
    parser.add_argument(
        "--translated-subtitle",
        type=Path,
        help="Optional translated timed subtitle",
    )
    parser.add_argument("--language", default="unknown", help="Source language code")
    parser.add_argument("--target-language", default="zh-CN")
    parser.add_argument("--job-id", help="Stable job identifier")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ffmpeg", help="Path to ffmpeg executable")
    parser.add_argument("--ffprobe", help="Path to ffprobe executable")
    parser.add_argument("--scene-threshold", type=float, default=0.35)
    parser.add_argument("--skip-scene-detection", action="store_true")
    parser.add_argument("--min-visual-gap", type=float, default=1.2)
    parser.add_argument("--max-keyframes", type=int, default=24)
    parser.add_argument("--skip-keyframes", action="store_true")
    parser.add_argument("--chunk-duration", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_path = args.video.expanduser().resolve()
    subtitle_path = args.subtitle.expanduser().resolve()
    translated_path = (
        args.translated_subtitle.expanduser().resolve()
        if args.translated_subtitle
        else None
    )
    if not video_path.is_file():
        print(f"ERROR: video file not found: {video_path}", file=sys.stderr)
        return 2
    if not subtitle_path.is_file():
        print(f"ERROR: subtitle file not found: {subtitle_path}", file=sys.stderr)
        return 2
    if translated_path and not translated_path.is_file():
        print(f"ERROR: translated subtitle file not found: {translated_path}", file=sys.stderr)
        return 2
    if not 0.05 <= args.scene_threshold <= 0.95:
        print("ERROR: --scene-threshold must be between 0.05 and 0.95", file=sys.stderr)
        return 2
    if args.min_visual_gap <= 0 or args.chunk_duration <= 0:
        print("ERROR: visual gap and chunk duration must be positive", file=sys.stderr)
        return 2

    job_id = args.job_id or (
        f"{safe_slug(video_path.stem)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else find_repo_root()
        / "workspace"
        / "review_packs"
        / "story_editor"
        / job_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        ffprobe = resolve_executable("ffprobe", args.ffprobe)
        ffmpeg = resolve_executable("ffmpeg", args.ffmpeg)
        media = probe_media(video_path, ffprobe)
        duration_sec = float(media["duration_sec"])
        source_cues = parse_subtitle(subtitle_path)
        target_cues = parse_subtitle(translated_path) if translated_path else []
        translated_texts = (
            pair_translations(source_cues, target_cues)
            if target_cues
            else [""] * len(source_cues)
        )

        subtitles: list[dict[str, Any]] = []
        for index, (cue, target_text) in enumerate(
            zip(source_cues, translated_texts),
            start=1,
        ):
            if cue.start_sec >= duration_sec:
                continue
            subtitles.append(
                {
                    "id": f"sub-{index:05d}",
                    "start_sec": round(max(0.0, cue.start_sec), 3),
                    "end_sec": round(min(duration_sec, cue.end_sec), 3),
                    "speaker": cue.speaker,
                    "source_text": cue.text,
                    "target_text": target_text,
                }
            )
        if not subtitles:
            raise ValueError("No subtitle cue overlaps the source video")

        if args.skip_scene_detection:
            boundaries = [0.0, duration_sec]
        else:
            boundaries = detect_scene_boundaries(
                video_path,
                ffmpeg,
                duration_sec,
                args.scene_threshold,
            )
        scenes = build_scenes(boundaries)
        visual_candidates = build_visual_candidates(
            subtitles,
            scenes,
            duration_sec,
            args.min_visual_gap,
        )

        keyframes: list[dict[str, Any]] = []
        if not args.skip_keyframes and args.max_keyframes > 0:
            keyframe_times = select_keyframe_times(
                scenes,
                visual_candidates,
                duration_sec,
                args.max_keyframes,
            )
            keyframes = extract_keyframes(
                video_path,
                output_dir / "keyframes",
                ffmpeg,
                keyframe_times,
            )

        chunks = build_analysis_chunks(
            output_dir,
            duration_sec,
            args.chunk_duration,
            subtitles,
            scenes,
            keyframes,
        )

        source = {
            "video_path": video_path.as_posix(),
            "fingerprint": source_fingerprint(video_path),
            "duration_sec": duration_sec,
            "language": args.language,
            **media,
        }
        source["duration_sec"] = duration_sec
        evidence_pack = {
            "schema_version": "1.0",
            "job_id": job_id,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": source,
            "inputs": {
                "source_subtitle_path": subtitle_path.as_posix(),
                "translated_subtitle_path": translated_path.as_posix()
                if translated_path
                else None,
                "target_language": args.target_language,
                "transcription_backend": "existing_subtitle_or_videohub_whisper",
            },
            "subtitles": subtitles,
            "scenes": scenes,
            "visual_candidates": visual_candidates,
            "keyframes": keyframes,
            "analysis_chunks": chunks,
            "statistics": {
                "subtitle_count": len(subtitles),
                "scene_count": len(scenes),
                "visual_candidate_count": len(visual_candidates),
                "keyframe_count": len(keyframes),
                "translated_subtitle_count": sum(
                    1 for item in subtitles if item["target_text"]
                ),
            },
        }
        evidence_path = output_dir / "evidence_pack.json"
        write_json(evidence_path, evidence_pack)
        write_json(
            output_dir / "transcript.json",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "subtitles": subtitles,
            },
        )
        write_json(
            output_dir / "scenes.json",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "scenes": scenes,
                "visual_candidates": visual_candidates,
                "keyframes": keyframes,
            },
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Evidence pack: {evidence_path}")
    print(f"Subtitles: {len(subtitles)}")
    print(f"Scenes: {len(scenes)}")
    print(f"Visual candidates: {len(visual_candidates)}")
    print(f"Keyframes: {len(keyframes)}")
    print(f"Analysis chunks: {len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
