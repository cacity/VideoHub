#!/usr/bin/env python3
"""Render a validated VideoHub story plan and rebuild its subtitle timeline."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from story_pipeline_common import (
    SubtitleCue,
    normalize_text,
    pair_translations,
    parse_subtitle,
    probe_media,
    read_json,
    resolve_executable,
    run_command,
    safe_slug,
    write_ass,
    write_srt,
)
from validate_narration_plan import validate_narration_plan
from validate_story_plan import validate_plan

BURN_MODES = {"none", "source", "translated", "bilingual"}


def _atempo_filter(rate: float) -> str:
    if not 0.5 <= rate <= 2.0:
        raise ValueError(f"Unsupported audio playback rate: {rate}")
    return f"atempo={rate:.8f}"


def _concat_quote(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def _subtitle_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    for source, target in (
        ("\\", "\\\\"),
        (":", r"\:"),
        ("'", r"\'"),
        (",", r"\,"),
        ("[", r"\["),
        ("]", r"\]"),
    ):
        value = value.replace(source, target)
    return value


def render_segment(
    *,
    ffmpeg: str,
    source_video: Path,
    segment: dict[str, Any],
    output_path: Path,
    source_has_audio: bool,
) -> None:
    start_sec = float(segment["source_start_sec"])
    source_duration = float(segment["source_end_sec"]) - start_sec
    output_duration = float(segment["output_end_sec"]) - float(
        segment["output_start_sec"]
    )
    playback_rate = float(segment.get("playback_rate", 1.0))
    audio_mode = str(segment.get("audio_mode", "source"))
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_sec:.6f}",
        "-t",
        f"{source_duration:.6f}",
        "-i",
        str(source_video),
    ]

    narration_path: Path | None = None
    if audio_mode == "narration":
        raw_narration_path = str(segment.get("narration_audio_path", "")).strip()
        if not raw_narration_path:
            raise ValueError(
                f"{segment['id']} requires narration_audio_path before rendering"
            )
        narration_path = Path(raw_narration_path).expanduser().resolve()
        if not narration_path.is_file():
            raise FileNotFoundError(
                f"Narration audio not found for {segment['id']}: {narration_path}"
            )
        command.extend(["-i", str(narration_path)])
    elif not source_has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{output_duration:.6f}",
                "-i",
                "anullsrc=r=48000:cl=stereo",
            ]
        )

    video_filter = f"setpts=(PTS-STARTPTS)/{playback_rate:.8f},format=yuv420p"
    command.extend(["-map", "0:v:0"])
    if narration_path:
        command.extend(["-map", "1:a:0"])
        audio_filter = (
            f"atrim=duration={output_duration:.6f},"
            "asetpts=PTS-STARTPTS,"
            f"apad=pad_dur={output_duration:.6f},"
            f"atrim=duration={output_duration:.6f}"
        )
    elif source_has_audio:
        command.extend(["-map", "0:a:0"])
        volume = {"source": 1.0, "mute": 0.0, "duck": 0.25}.get(audio_mode)
        if volume is None:
            raise ValueError(f"Unsupported audio mode for {segment['id']}: {audio_mode}")
        audio_filter = (
            "asetpts=PTS-STARTPTS,"
            f"{_atempo_filter(playback_rate)},"
            f"volume={volume:.3f}"
        )
    else:
        command.extend(["-map", "1:a:0"])
        audio_filter = "asetpts=PTS-STARTPTS"

    command.extend(
        [
            "-vf",
            video_filter,
            "-af",
            audio_filter,
            "-t",
            f"{output_duration:.6f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
    )
    run_command(command)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Rendered segment is missing or empty: {output_path}")


def concat_segments(ffmpeg: str, segment_paths: list[Path], output_path: Path) -> None:
    concat_path = output_path.parent / "segments.concat.txt"
    concat_path.write_text(
        "".join(f"file '{_concat_quote(path)}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
    )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Concatenated video is missing or empty: {output_path}")


def rebuild_subtitle_timeline(
    plan: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    subtitle_by_id = {
        str(item["id"]): item
        for item in evidence.get("subtitles", [])
        if isinstance(item, dict) and item.get("id")
    }
    rebuilt: list[dict[str, Any]] = []

    for segment in plan["segments"]:
        if segment.get("kind") != "dialogue":
            continue
        source_start = float(segment["source_start_sec"])
        source_end = float(segment["source_end_sec"])
        output_start = float(segment["output_start_sec"])
        output_end = float(segment["output_end_sec"])
        rate = float(segment.get("playback_rate", 1.0))
        for subtitle_id in segment.get("source_subtitle_ids", []):
            cue = subtitle_by_id.get(str(subtitle_id))
            if not cue:
                continue
            clipped_start = max(source_start, float(cue["start_sec"]))
            clipped_end = min(source_end, float(cue["end_sec"]))
            if clipped_end - clipped_start < 0.04:
                continue
            new_start = output_start + (clipped_start - source_start) / rate
            new_end = output_start + (clipped_end - source_start) / rate
            new_start = max(output_start, min(output_end, new_start))
            new_end = min(output_end, new_end)
            if new_end - new_start < 0.04:
                continue
            rebuilt.append(
                {
                    "source_subtitle_id": str(subtitle_id),
                    "segment_id": str(segment["id"]),
                    "start_sec": round(new_start, 3),
                    "end_sec": round(new_end, 3),
                    "speaker": str(cue.get("speaker", "")),
                    "source_text": normalize_text(str(cue.get("source_text", ""))),
                    "target_text": normalize_text(str(cue.get("target_text", ""))),
                }
            )

    rebuilt.sort(key=lambda cue: (cue["start_sec"], cue["end_sec"]))
    return rebuilt


def apply_external_translation(
    cues: list[dict[str, Any]],
    translated_subtitle_path: Path,
) -> list[dict[str, Any]]:
    """Attach a post-edit translation to the rebuilt output timeline."""
    target_cues = parse_subtitle(translated_subtitle_path)
    source_cues = [
        SubtitleCue(
            float(cue["start_sec"]),
            float(cue["end_sec"]),
            str(cue.get("source_text", "")),
            str(cue.get("speaker", "")),
        )
        for cue in cues
    ]
    paired = pair_translations(source_cues, target_cues)
    missing = [index + 1 for index, text in enumerate(paired) if not normalize_text(text)]
    if missing:
        preview = ", ".join(str(index) for index in missing[:12])
        raise ValueError(
            "Post-edit translation does not cover every selected subtitle cue: "
            f"missing cue(s) {preview}"
        )
    return [
        {**cue, "target_text": normalize_text(target)}
        for cue, target in zip(cues, paired)
    ]


def narration_subtitle_timeline(path: Path) -> list[dict[str, Any]]:
    """Load Chinese narration captions that already use the output timeline."""
    return [
        {
            "source_subtitle_id": "",
            "segment_id": "narration",
            "start_sec": round(float(cue.start_sec), 3),
            "end_sec": round(float(cue.end_sec), 3),
            "speaker": cue.speaker,
            "source_text": "",
            "target_text": normalize_text(cue.text),
        }
        for cue in parse_subtitle(path)
    ]


def select_subtitle_cues_for_windows(
    cues: list[dict[str, Any]],
    windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Clip source-dialogue subtitles to the final-timeline source-audio windows."""
    selected: list[dict[str, Any]] = []
    for window in windows:
        window_start = float(window["start_sec"])
        window_end = float(window["end_sec"])
        for cue in cues:
            start = max(window_start, float(cue["start_sec"]))
            end = min(window_end, float(cue["end_sec"]))
            if end - start <= 0.01:
                continue
            selected.append(
                {
                    **cue,
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "source_audio_window_id": str(window.get("id", "")),
                }
            )
    return selected


def combine_commentary_subtitles(
    narration_cues: list[dict[str, Any]],
    source_audio_cues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        [*narration_cues, *source_audio_cues],
        key=lambda cue: (float(cue["start_sec"]), float(cue["end_sec"])),
    )


def build_source_volume_expression(
    windows: list[dict[str, Any]],
    *,
    background_volume: float,
    source_audio_volume: float,
) -> str:
    if not windows:
        return f"volume={background_volume:.6f}"
    conditions = "+".join(
        (
            f"between(t,{float(window['start_sec']):.6f},"
            f"{float(window['end_sec']):.6f})"
        )
        for window in windows
    )
    return (
        "volume='if(gt("
        f"{conditions},0),{source_audio_volume:.6f},{background_volume:.6f}"
        ")':eval=frame"
    )


def write_subtitle_outputs(
    plan: dict[str, Any],
    cues: list[dict[str, Any]],
    fallback_dir: Path,
    output_prefix: Path | None = None,
) -> dict[str, Path]:
    output = plan.get("output", {})

    def output_path(key: str, fallback_name: str) -> Path:
        raw = str(output.get(key, "")).strip()
        return Path(raw).expanduser().resolve() if raw else fallback_dir / fallback_name

    if output_prefix:
        prefix = output_prefix.expanduser().resolve()
        paths = {
            "source_srt": prefix.with_name(f"{prefix.name}_source.srt"),
            "translated_srt": prefix.with_name(f"{prefix.name}_zh-CN.srt"),
            "bilingual_ass": prefix.with_name(f"{prefix.name}_bilingual.ass"),
        }
    else:
        paths = {
            "source_srt": output_path("source_subtitle_path", "story_source.srt"),
            "translated_srt": output_path(
                "translated_subtitle_path",
                "story_translated.srt",
            ),
            "bilingual_ass": output_path(
                "bilingual_subtitle_path",
                "story_bilingual.ass",
            ),
        }
    paths["source_ass"] = paths["source_srt"].with_suffix(".ass")
    paths["translated_ass"] = paths["translated_srt"].with_suffix(".ass")

    write_srt(paths["source_srt"], cues, "source_text")
    write_srt(paths["translated_srt"], cues, "target_text")
    write_ass(paths["source_ass"], cues, "source")
    write_ass(paths["translated_ass"], cues, "translated")
    write_ass(paths["bilingual_ass"], cues, "bilingual")
    return paths


def burn_subtitles(
    *,
    ffmpeg: str,
    source_video: Path,
    subtitle_path: Path,
    output_video: Path,
) -> None:
    if not subtitle_path.is_file() or subtitle_path.stat().st_size == 0:
        raise FileNotFoundError(f"Subtitle file cannot be burned: {subtitle_path}")
    subtitle_filter = f"ass='{_subtitle_filter_path(subtitle_path)}'"
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_video),
            "-vf",
            subtitle_filter,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-y",
            str(output_video),
        ]
    )


def mix_narration_audio(
    *,
    ffmpeg: str,
    source_video: Path,
    narration_audio: Path,
    output_video: Path,
    background_volume: float,
    source_audio_windows: list[dict[str, Any]] | None = None,
    source_audio_volume: float = 1.0,
) -> None:
    if not narration_audio.is_file() or narration_audio.stat().st_size == 0:
        raise FileNotFoundError(f"Narration audio not found: {narration_audio}")
    if not 0.0 <= background_volume <= 1.0:
        raise ValueError("background volume must be between 0.0 and 1.0")
    if not 0.0 <= source_audio_volume <= 1.0:
        raise ValueError("source audio volume must be between 0.0 and 1.0")
    source_volume_filter = build_source_volume_expression(
        source_audio_windows or [],
        background_volume=background_volume,
        source_audio_volume=source_audio_volume,
    )
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_video),
            "-i",
            str(narration_audio),
            "-filter_complex",
            (
                f"[0:a]aresample=48000,{source_volume_filter}[background];"
                "[1:a]aresample=48000,apad[narration];"
                "[background][narration]amix=inputs=2:duration=first:"
                "dropout_transition=0:normalize=0,alimiter=limit=0.95[mixed]"
            ),
            "-map",
            "0:v:0",
            "-map",
            "[mixed]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-y",
            str(output_video),
        ]
    )
    if not output_video.is_file() or output_video.stat().st_size == 0:
        raise RuntimeError(f"Narration mix is missing or empty: {output_video}")


def _safe_cleanup_render_work(work_dir: Path, plan_path: Path) -> None:
    resolved_work = work_dir.resolve()
    resolved_parent = plan_path.resolve().parent
    try:
        resolved_work.relative_to(resolved_parent)
    except ValueError as exc:
        raise RuntimeError(
            f"Refusing to clean render work outside plan directory: {resolved_work}"
        ) from exc
    if not resolved_work.name.startswith(".story_render_"):
        raise RuntimeError(f"Refusing to clean unexpected render directory: {resolved_work}")
    shutil.rmtree(resolved_work)


def write_qa_report(
    *,
    path: Path,
    plan: dict[str, Any],
    output_video: Path,
    ffmpeg: str,
    ffprobe: str,
    subtitle_cues: list[dict[str, Any]],
    decode_check: bool,
) -> tuple[bool, list[str]]:
    media = probe_media(output_video, ffprobe)
    actual_duration = float(media["duration_sec"])
    planned_duration = float(plan["segments"][-1]["output_end_sec"])
    checks: list[tuple[str, bool, str]] = []
    duration_ok = abs(actual_duration - planned_duration) <= max(
        0.35,
        planned_duration * 0.01,
    )
    checks.append(
        (
            "Duration",
            duration_ok,
            f"planned={planned_duration:.3f}s, actual={actual_duration:.3f}s",
        )
    )
    subtitle_ok = all(
        0 <= float(cue["start_sec"]) < float(cue["end_sec"]) <= actual_duration + 0.1
        for cue in subtitle_cues
    )
    checks.append(
        (
            "Subtitle timeline",
            subtitle_ok,
            f"{len(subtitle_cues)} cue(s), all within output duration",
        )
    )
    decode_ok = True
    decode_detail = "skipped"
    if decode_check:
        result = run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-i",
                str(output_video),
                "-f",
                "null",
                "-",
            ],
            check=False,
        )
        decode_ok = result.returncode == 0 and not result.stderr.strip()
        decode_detail = (
            "full decode completed without errors"
            if decode_ok
            else (result.stderr.strip() or f"ffmpeg exit code {result.returncode}")
        )
    checks.append(("Decode", decode_ok, decode_detail))
    all_ok = all(item[1] for item in checks)
    notes = [item[2] for item in checks if not item[1]]

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VideoHub Story QA",
        "",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Output: `{output_video.as_posix()}`",
        f"- Result: **{'PASS' if all_ok else 'FAIL'}**",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for name, ok, detail in checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Job: `{plan['job_id']}`",
            f"- Source fingerprint: `{plan['source'].get('fingerprint', '')}`",
            f"- Segment count: {len(plan['segments'])}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return all_ok, notes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Compiled story_plan.json")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Override output video path")
    parser.add_argument(
        "--translated-subtitle",
        type=Path,
        help="Post-edit translated subtitle using the final output timeline",
    )
    parser.add_argument(
        "--narration-audio",
        type=Path,
        help="Aligned TTS narration audio to mix over the edited source audio",
    )
    parser.add_argument(
        "--narration-subtitle",
        type=Path,
        help="Narration subtitle using the final output timeline",
    )
    parser.add_argument(
        "--narration-plan",
        type=Path,
        help="Validated narration plan with optional source-audio anchor windows",
    )
    parser.add_argument(
        "--background-volume",
        type=float,
        default=None,
        help="Override original audio volume while narration is active",
    )
    parser.add_argument(
        "--subtitle-prefix",
        type=Path,
        help="Override subtitle output filename prefix for a render variant",
    )
    parser.add_argument("--qa-report", type=Path, help="Override QA report path")
    parser.add_argument(
        "--prepare-subtitles-only",
        action="store_true",
        help="Rebuild the selected source subtitle timeline without rendering video",
    )
    parser.add_argument(
        "--burn-subtitles",
        choices=sorted(BURN_MODES),
        default="none",
    )
    parser.add_argument("--ffmpeg", help="Path to ffmpeg executable")
    parser.add_argument("--ffprobe", help="Path to ffprobe executable")
    parser.add_argument("--keep-segments", action="store_true")
    parser.add_argument("--skip-decode-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan_path = args.plan.expanduser().resolve()
    try:
        plan = read_json(plan_path)
        evidence = read_json(args.evidence.expanduser().resolve())
        analysis = read_json(args.analysis.expanduser().resolve())
        errors, warnings = validate_plan(plan, evidence=evidence, analysis=analysis)
        for warning in warnings:
            print(f"WARNING: {warning}")
        if errors:
            raise ValueError("story plan is invalid: " + "; ".join(errors[:10]))
        if any(segment.get("transition") != "cut" for segment in plan["segments"]):
            raise ValueError(
                "The deterministic v1 renderer supports cut transitions only. "
                "Change fade/crossfade segments to cut before rendering."
            )

        narration_plan: dict[str, Any] | None = None
        source_audio_windows: list[dict[str, Any]] = []
        source_audio_volume = 1.0
        background_volume = 0.3 if args.background_volume is None else args.background_volume
        if args.narration_plan:
            narration_plan = read_json(args.narration_plan.expanduser().resolve())
            narration_errors, narration_warnings = validate_narration_plan(
                narration_plan,
                plan,
                evidence,
                analysis,
            )
            for warning in narration_warnings:
                print(f"WARNING: {warning}")
            if narration_errors:
                raise ValueError(
                    "narration plan is invalid: " + "; ".join(narration_errors[:10])
                )
            narration_settings = narration_plan.get("settings", {})
            source_audio_windows = list(
                narration_plan.get("source_audio_windows", [])
            )
            source_audio_volume = float(
                narration_settings.get("source_audio_volume", 1.0)
            )
            if args.background_volume is None:
                background_volume = float(
                    narration_settings.get("original_audio_volume", 0.3)
                )

        source_subtitle_cues = rebuild_subtitle_timeline(plan, evidence)
        if args.translated_subtitle:
            source_subtitle_cues = apply_external_translation(
                source_subtitle_cues,
                args.translated_subtitle.expanduser().resolve(),
            )
        else:
            source_language = str(plan.get("source", {}).get("language", "")).lower()
            target_language = str(plan.get("settings", {}).get("target_language", "")).lower()
            if source_language.startswith("zh") and target_language.startswith("zh"):
                source_subtitle_cues = [
                    {
                        **cue,
                        "target_text": cue.get("target_text") or cue.get("source_text", ""),
                    }
                    for cue in source_subtitle_cues
                ]

        subtitle_cues = source_subtitle_cues
        if args.narration_subtitle:
            narration_cues = narration_subtitle_timeline(
                args.narration_subtitle.expanduser().resolve()
            )
            source_audio_cues = select_subtitle_cues_for_windows(
                source_subtitle_cues,
                source_audio_windows,
            )
            subtitle_cues = combine_commentary_subtitles(
                narration_cues,
                source_audio_cues,
            )

        default_output = Path(plan["output"]["video_path"]).expanduser().resolve()
        output_video = args.output.expanduser().resolve() if args.output else default_output
        output_video.parent.mkdir(parents=True, exist_ok=True)
        subtitle_paths = write_subtitle_outputs(
            plan,
            subtitle_cues,
            output_video.parent,
            output_prefix=args.subtitle_prefix,
        )
        if args.prepare_subtitles_only:
            print(f"Source subtitles: {subtitle_paths['source_srt']}")
            if args.translated_subtitle or args.narration_subtitle:
                print(f"Translated subtitles: {subtitle_paths['translated_srt']}")
            return 0

        if args.burn_subtitles in {"translated", "bilingual"} and any(
            not normalize_text(str(cue.get("target_text", "")))
            for cue in subtitle_cues
        ):
            raise ValueError(
                "Translated/bilingual rendering requires a complete post-edit translation. "
                "Run prepare_story_subtitles.py and translate_story_subtitles.py, then pass "
                "--translated-subtitle."
            )
        if args.narration_audio and not args.narration_subtitle:
            raise ValueError("--narration-audio requires --narration-subtitle")
        if args.narration_plan and not args.narration_audio:
            raise ValueError("--narration-plan requires --narration-audio")

        ffmpeg = resolve_executable("ffmpeg", args.ffmpeg)
        ffprobe = resolve_executable("ffprobe", args.ffprobe)
        source_video = Path(plan["source"]["video_path"]).expanduser().resolve()
        if not source_video.is_file():
            raise FileNotFoundError(f"Source video not found: {source_video}")
        source_media = probe_media(source_video, ffprobe)
        source_has_audio = bool(source_media.get("audio", {}).get("present"))

        work_dir = (
            plan_path.parent
            / f".story_render_{safe_slug(str(plan['job_id']))}"
        ).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        segment_paths: list[Path] = []
        for index, segment in enumerate(plan["segments"], start=1):
            segment_path = work_dir / f"segment-{index:04d}.mp4"
            print(
                f"Rendering {index}/{len(plan['segments'])}: "
                f"{segment['source_start_sec']:.3f}s-"
                f"{segment['source_end_sec']:.3f}s"
            )
            render_segment(
                ffmpeg=ffmpeg,
                source_video=source_video,
                segment=segment,
                output_path=segment_path,
                source_has_audio=source_has_audio,
            )
            segment_paths.append(segment_path)

        unsubtitled_video = work_dir / "story_unsubtitled.mp4"
        concat_segments(ffmpeg, segment_paths, unsubtitled_video)
        render_source = unsubtitled_video
        if args.narration_audio:
            mixed_video = work_dir / "story_narration_mixed.mp4"
            mix_narration_audio(
                ffmpeg=ffmpeg,
                source_video=unsubtitled_video,
                narration_audio=args.narration_audio.expanduser().resolve(),
                output_video=mixed_video,
                background_volume=background_volume,
                source_audio_windows=source_audio_windows,
                source_audio_volume=source_audio_volume,
            )
            render_source = mixed_video

        if args.burn_subtitles == "none":
            shutil.copy2(render_source, output_video)
        else:
            selected_subtitle = {
                "source": subtitle_paths["source_ass"],
                "translated": subtitle_paths["translated_ass"],
                "bilingual": subtitle_paths["bilingual_ass"],
            }[args.burn_subtitles]
            burn_subtitles(
                ffmpeg=ffmpeg,
                source_video=render_source,
                subtitle_path=selected_subtitle,
                output_video=output_video,
            )

        if not output_video.is_file() or output_video.stat().st_size == 0:
            raise RuntimeError(f"Final output is missing or empty: {output_video}")

        qa_raw = str(plan.get("output", {}).get("qa_report_path", "")).strip()
        qa_path = (
            args.qa_report.expanduser().resolve()
            if args.qa_report
            else (
                output_video.with_name(f"{output_video.stem}_qa.md")
                if args.output
                else (
                    Path(qa_raw).expanduser().resolve()
                    if qa_raw
                    else output_video.with_name(f"{output_video.stem}_qa.md")
                )
            )
        )
        qa_ok, qa_notes = write_qa_report(
            path=qa_path,
            plan=plan,
            output_video=output_video,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            subtitle_cues=subtitle_cues,
            decode_check=not args.skip_decode_check,
        )
        if not qa_ok:
            raise RuntimeError("QA failed: " + "; ".join(qa_notes))

        if not args.keep_segments:
            _safe_cleanup_render_work(work_dir, plan_path)
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Story video: {output_video}")
    print(f"Source subtitles: {subtitle_paths['source_srt']}")
    print(f"Translated subtitles: {subtitle_paths['translated_srt']}")
    print(f"Bilingual subtitles: {subtitle_paths['bilingual_ass']}")
    print(f"QA report: {qa_path}")
    if source_audio_windows:
        print(f"Source audio windows: {len(source_audio_windows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
