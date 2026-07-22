#!/usr/bin/env python3
"""Compile an LLM story-plan draft into a deterministic render plan."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from story_pipeline_common import (
    find_repo_root,
    finite_number,
    normalize_text,
    overlap_duration,
    read_json,
    safe_slug,
    write_json,
)
from validate_story_analysis import validate_analysis

STORY_ROLES = {"hook", "context", "development", "turn", "resolution", "closing"}
SUBTITLE_MODES = {"none", "source", "translated", "bilingual"}
TRANSLATION_STAGES = {"none", "pre_edit", "post_edit"}
SEGMENT_KINDS = {"dialogue", "visual"}
AUDIO_MODES = {"source", "mute", "duck", "narration"}
TRANSITIONS = {"cut", "fade", "crossfade"}


def _evidence_description(reference: str, evidence: dict[str, Any]) -> str:
    for item in evidence.get("subtitles", []):
        if item.get("id") == reference:
            text = normalize_text(str(item.get("source_text", "")))
            return f"{reference}: {text[:120]}"
    for item in evidence.get("analysis_chunks", []):
        if item.get("id") == reference:
            return (
                f"{reference}: {float(item.get('start_sec', 0)):.1f}s-"
                f"{float(item.get('end_sec', 0)):.1f}s"
            )
    for item in evidence.get("scenes", []):
        if item.get("id") == reference:
            return (
                f"{reference}: scene {float(item.get('start_sec', 0)):.1f}s-"
                f"{float(item.get('end_sec', 0)):.1f}s"
            )
    for item in evidence.get("keyframes", []):
        if item.get("id") == reference:
            return f"{reference}: keyframe at {float(item.get('time_sec', 0)):.1f}s"
    return reference


def _analysis_reference_ids(analysis: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in (
        "events",
        "themes",
        "visual_findings",
        "continuity_constraints",
        "story_options",
    ):
        for item in analysis.get(section, []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            if item_id:
                ids.add(item_id)
            if section == "story_options":
                for node in item.get("arc", []):
                    if isinstance(node, dict) and str(node.get("id", "")).strip():
                        ids.add(str(node["id"]).strip())
    return ids


def _overlapping_items(
    items: list[dict[str, Any]],
    start_sec: float,
    end_sec: float,
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if overlap_duration(
            start_sec,
            end_sec,
            float(item["start_sec"]),
            float(item["end_sec"]),
        )
        > 0
    ]


def _validate_draft_settings(settings: dict[str, Any]) -> None:
    target = settings.get("target_duration_sec")
    tolerance = settings.get("duration_tolerance_ratio", 0.15)
    if not finite_number(target) or target <= 0:
        raise ValueError("settings.target_duration_sec must be a positive number")
    if not finite_number(tolerance) or not 0 <= tolerance <= 0.5:
        raise ValueError("settings.duration_tolerance_ratio must be between 0 and 0.5")
    if settings.get("subtitle_mode") not in SUBTITLE_MODES:
        raise ValueError(f"settings.subtitle_mode must be one of {sorted(SUBTITLE_MODES)}")
    if settings.get("translation_stage") not in TRANSLATION_STAGES:
        raise ValueError(
            "settings.translation_stage must be one of "
            f"{sorted(TRANSLATION_STAGES)}"
        )
    if not isinstance(settings.get("translation_polish", False), bool):
        raise ValueError("settings.translation_polish must be a boolean")
    if not isinstance(settings.get("allow_speed_change", False), bool):
        raise ValueError("settings.allow_speed_change must be a boolean")


def compile_plan(
    draft: dict[str, Any],
    evidence: dict[str, Any],
    analysis: dict[str, Any],
    output_path: Path,
    render_dir: Path | None = None,
) -> dict[str, Any]:
    if draft.get("job_id") != evidence.get("job_id"):
        raise ValueError("draft.job_id must match evidence.job_id")
    if analysis.get("job_id") != evidence.get("job_id"):
        raise ValueError("analysis.job_id must match evidence.job_id")

    settings = draft.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("draft.settings must be an object")
    settings = {
        "target_duration_sec": float(settings.get("target_duration_sec", 240.0)),
        "duration_tolerance_ratio": float(
            settings.get("duration_tolerance_ratio", 0.15)
        ),
        "target_language": str(settings.get("target_language", "zh-CN")),
        "subtitle_mode": settings.get("subtitle_mode", "bilingual"),
        "translation_stage": settings.get("translation_stage", "post_edit"),
        "translation_polish": settings.get("translation_polish", False),
        "allow_speed_change": settings.get("allow_speed_change", False),
    }
    _validate_draft_settings(settings)

    selected_option_id = str(
        draft.get("selected_option_id") or analysis.get("selected_option_id") or ""
    ).strip()
    selected_option = next(
        (
            item
            for item in analysis.get("story_options", [])
            if isinstance(item, dict) and item.get("id") == selected_option_id
        ),
        None,
    )
    if not selected_option:
        raise ValueError("selected_option_id does not reference analysis.story_options")

    source = evidence.get("source", {})
    source_duration = float(source.get("duration_sec", 0))
    if source_duration <= 0:
        raise ValueError("evidence source duration is invalid")

    source_subtitles = evidence.get("subtitles", [])
    scenes = evidence.get("scenes", [])
    subtitle_by_id = {
        str(item["id"]): item
        for item in source_subtitles
        if isinstance(item, dict) and item.get("id")
    }
    scene_by_id = {
        str(item["id"]): item
        for item in scenes
        if isinstance(item, dict) and item.get("id")
    }
    valid_analysis_refs = _analysis_reference_ids(analysis)

    draft_segments = draft.get("segments")
    if not isinstance(draft_segments, list) or not draft_segments:
        raise ValueError("draft.segments must be a non-empty array")

    compiled_segments: list[dict[str, Any]] = []
    output_cursor = 0.0
    for index, item in enumerate(draft_segments, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"segments[{index - 1}] must be an object")

        kind = item.get("kind")
        if kind not in SEGMENT_KINDS:
            raise ValueError(
                f"segments[{index - 1}].kind must be one of {sorted(SEGMENT_KINDS)}"
            )
        story_role = item.get("story_role")
        if story_role not in STORY_ROLES:
            raise ValueError(
                f"segments[{index - 1}].story_role must be one of {sorted(STORY_ROLES)}"
            )
        start_sec = item.get("source_start_sec")
        end_sec = item.get("source_end_sec")
        if (
            not finite_number(start_sec)
            or not finite_number(end_sec)
            or start_sec < 0
            or end_sec <= start_sec
            or end_sec > source_duration + 0.001
        ):
            raise ValueError(f"segments[{index - 1}] has an invalid source time range")
        start_sec = round(float(start_sec), 3)
        end_sec = round(float(end_sec), 3)

        playback_rate = item.get("playback_rate", 1.0)
        if not finite_number(playback_rate) or not 0.5 <= playback_rate <= 2.0:
            raise ValueError(f"segments[{index - 1}].playback_rate must be 0.5-2.0")
        playback_rate = float(playback_rate)
        if not settings["allow_speed_change"] and abs(playback_rate - 1.0) > 0.001:
            raise ValueError(
                f"segments[{index - 1}] changes speed while allow_speed_change is false"
            )

        analysis_refs = [
            str(reference).strip()
            for reference in item.get("analysis_refs", [])
            if str(reference).strip()
        ]
        if not analysis_refs:
            raise ValueError(f"segments[{index - 1}].analysis_refs must not be empty")
        unknown_analysis_refs = sorted(set(analysis_refs) - valid_analysis_refs)
        if unknown_analysis_refs:
            raise ValueError(
                f"segments[{index - 1}] contains unknown analysis_refs: "
                f"{unknown_analysis_refs}"
            )

        overlapping_subtitles = _overlapping_items(
            source_subtitles,
            start_sec,
            end_sec,
        )
        requested_subtitle_ids = [
            str(reference).strip()
            for reference in item.get("source_subtitle_ids", [])
            if str(reference).strip()
        ]
        if requested_subtitle_ids:
            unknown_subtitles = sorted(
                set(requested_subtitle_ids) - set(subtitle_by_id)
            )
            if unknown_subtitles:
                raise ValueError(
                    f"segments[{index - 1}] contains unknown subtitle IDs: "
                    f"{unknown_subtitles}"
                )
            selected_subtitles = [
                subtitle_by_id[reference] for reference in requested_subtitle_ids
            ]
        else:
            selected_subtitles = overlapping_subtitles if kind == "dialogue" else []

        if kind == "dialogue" and not selected_subtitles:
            raise ValueError(
                f"segments[{index - 1}] is dialogue but overlaps no subtitle evidence"
            )
        if any(
            overlap_duration(
                start_sec,
                end_sec,
                float(subtitle["start_sec"]),
                float(subtitle["end_sec"]),
            )
            <= 0
            for subtitle in selected_subtitles
        ):
            raise ValueError(
                f"segments[{index - 1}] references subtitles outside its source range"
            )

        requested_scene_ids = [
            str(reference).strip()
            for reference in item.get("source_scene_ids", [])
            if str(reference).strip()
        ]
        if requested_scene_ids:
            unknown_scenes = sorted(set(requested_scene_ids) - set(scene_by_id))
            if unknown_scenes:
                raise ValueError(
                    f"segments[{index - 1}] contains unknown scene IDs: {unknown_scenes}"
                )
            selected_scenes = [scene_by_id[reference] for reference in requested_scene_ids]
        else:
            selected_scenes = _overlapping_items(scenes, start_sec, end_sec)

        audio_mode = item.get("audio_mode", "source")
        if audio_mode not in AUDIO_MODES:
            raise ValueError(
                f"segments[{index - 1}].audio_mode must be one of {sorted(AUDIO_MODES)}"
            )
        transition = item.get("transition", "cut")
        if transition not in TRANSITIONS:
            raise ValueError(
                f"segments[{index - 1}].transition must be one of {sorted(TRANSITIONS)}"
            )
        story_reason = normalize_text(str(item.get("story_reason", "")))
        if not story_reason:
            raise ValueError(f"segments[{index - 1}].story_reason must not be empty")

        output_duration = (end_sec - start_sec) / playback_rate
        output_start = output_cursor
        output_end = output_start + output_duration
        output_cursor = output_end
        segment = {
            "id": str(item.get("id") or f"seg-{index:03d}"),
            "output_order": index,
            "kind": kind,
            "story_role": story_role,
            "source_start_sec": start_sec,
            "source_end_sec": end_sec,
            "output_start_sec": round(output_start, 3),
            "output_end_sec": round(output_end, 3),
            "playback_rate": playback_rate,
            "source_subtitle_ids": [
                str(subtitle["id"]) for subtitle in selected_subtitles
            ],
            "source_scene_ids": [str(scene["id"]) for scene in selected_scenes],
            "analysis_refs": analysis_refs,
            "source_text": " ".join(
                normalize_text(str(subtitle.get("source_text", "")))
                for subtitle in selected_subtitles
                if normalize_text(str(subtitle.get("source_text", "")))
            ),
            "target_text": " ".join(
                normalize_text(str(subtitle.get("target_text", "")))
                for subtitle in selected_subtitles
                if normalize_text(str(subtitle.get("target_text", "")))
            ),
            "speaker": str(item.get("speaker") or ""),
            "audio_mode": audio_mode,
            "story_reason": story_reason,
            "transition": transition,
        }
        if audio_mode == "narration":
            narration_text = normalize_text(str(item.get("narration_text", "")))
            narration_audio_path = str(item.get("narration_audio_path", "")).strip()
            if not narration_text:
                raise ValueError(
                    f"segments[{index - 1}] narration requires narration_text"
                )
            segment["narration_text"] = narration_text
            segment["narration_source"] = "editorial_bridge"
            if narration_audio_path:
                segment["narration_audio_path"] = str(
                    Path(narration_audio_path).expanduser().resolve()
                )
        compiled_segments.append(segment)

    profile = analysis["content_profile"]
    profile_refs = [str(ref) for ref in profile.get("evidence_refs", [])]
    target_duration = settings["target_duration_sec"]
    source_slug = safe_slug(Path(str(source.get("video_path", "video"))).stem)
    render_dir = (
        render_dir.expanduser().resolve()
        if render_dir
        else find_repo_root() / "workspace" / "videos_with_subtitles"
    )
    output_video = render_dir / f"{source_slug}_story_{int(round(target_duration))}s.mp4"
    plan = {
        "schema_version": "1.0",
        "job_id": str(evidence["job_id"]),
        "evidence_pack_path": str(
            Path(str(draft.get("evidence_pack_path", ""))).resolve()
            if draft.get("evidence_pack_path")
            else ""
        ),
        "story_analysis_path": str(
            Path(str(draft.get("story_analysis_path", ""))).resolve()
            if draft.get("story_analysis_path")
            else ""
        ),
        "source": {
            "video_path": str(source["video_path"]),
            "fingerprint": str(source.get("fingerprint", "")),
            "duration_sec": source_duration,
            "language": str(source.get("language", "unknown")),
        },
        "settings": settings,
        "classification": {
            "type": profile["type"],
            "secondary_type": profile.get("secondary_type"),
            "confidence": profile["confidence"],
            "evidence_refs": profile_refs,
            "evidence": [
                _evidence_description(reference, evidence)
                for reference in profile_refs
            ],
        },
        "story": {
            "selected_option_id": selected_option_id,
            "premise": str(selected_option["premise"]),
            "angle": str(selected_option["angle"]),
            "arc": [
                str(node["role"])
                for node in selected_option.get("arc", [])
                if isinstance(node, dict) and node.get("role")
            ],
        },
        "segments": compiled_segments,
        "output": {
            "video_path": output_video.resolve().as_posix(),
            "source_subtitle_path": (
                render_dir / f"{source_slug}_story_source.srt"
            ).resolve().as_posix(),
            "translated_subtitle_path": (
                render_dir / f"{source_slug}_story_{settings['target_language']}.srt"
            ).resolve().as_posix(),
            "bilingual_subtitle_path": (
                render_dir / f"{source_slug}_story_bilingual.ass"
            ).resolve().as_posix(),
            "qa_report_path": (
                render_dir / f"{source_slug}_story_qa.md"
            ).resolve().as_posix(),
        },
    }
    return plan


def write_source_map(path: Path, plan: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "segment_id",
                "output_order",
                "kind",
                "story_role",
                "source_start_sec",
                "source_end_sec",
                "output_start_sec",
                "output_end_sec",
                "source_subtitle_ids",
                "source_scene_ids",
                "analysis_refs",
                "story_reason",
            ]
        )
        for segment in plan["segments"]:
            writer.writerow(
                [
                    segment["id"],
                    segment["output_order"],
                    segment["kind"],
                    segment["story_role"],
                    segment["source_start_sec"],
                    segment["source_end_sec"],
                    segment["output_start_sec"],
                    segment["output_end_sec"],
                    "|".join(segment["source_subtitle_ids"]),
                    "|".join(segment["source_scene_ids"]),
                    "|".join(segment["analysis_refs"]),
                    segment["story_reason"],
                ]
            )


def write_outline(path: Path, plan: dict[str, Any]) -> None:
    lines = [
        f"# {plan['story']['premise']}",
        "",
        f"- 类型：`{plan['classification']['type']}`",
        f"- 角度：{plan['story']['angle']}",
        f"- 目标时长：{plan['settings']['target_duration_sec']:.1f} 秒",
        f"- 计划时长：{plan['segments'][-1]['output_end_sec']:.1f} 秒",
        "",
        "## 剪辑顺序",
        "",
    ]
    for segment in plan["segments"]:
        lines.extend(
            [
                (
                    f"### {segment['output_order']}. {segment['story_role']} "
                    f"({segment['source_start_sec']:.3f}s-"
                    f"{segment['source_end_sec']:.3f}s)"
                ),
                "",
                segment["story_reason"],
                "",
                f"证据：`{', '.join(segment['analysis_refs'])}`",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="Path to story_plan.draft.json")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--render-dir",
        type=Path,
        help="Final video/subtitle directory (defaults to workspace/videos_with_subtitles)",
    )
    args = parser.parse_args()

    try:
        draft = read_json(args.draft)
        evidence = read_json(args.evidence)
        analysis = read_json(args.analysis)
        analysis_errors, analysis_warnings = validate_analysis(analysis, evidence)
        for warning in analysis_warnings:
            print(f"WARNING: analysis: {warning}")
        if analysis_errors:
            raise ValueError(
                "story analysis is invalid: " + "; ".join(analysis_errors[:8])
            )

        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        draft["evidence_pack_path"] = args.evidence.expanduser().resolve().as_posix()
        draft["story_analysis_path"] = args.analysis.expanduser().resolve().as_posix()
        plan = compile_plan(
            draft,
            evidence,
            analysis,
            output_path,
            render_dir=args.render_dir,
        )
        write_json(output_path, plan)
        write_source_map(output_path.parent / "story_source_map.csv", plan)
        write_outline(output_path.parent / "story_outline.md", plan)
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Compiled story plan: {output_path}")
    print(f"Segments: {len(plan['segments'])}")
    print(f"Planned duration: {plan['segments'][-1]['output_end_sec']:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
