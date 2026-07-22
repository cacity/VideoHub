#!/usr/bin/env python3
"""Validate a VideoHub story edit plan without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from story_pipeline_common import normalize_text, overlap_duration, read_json, referenced_ids

CONTENT_TYPES = {
    "drama",
    "podcast_interview",
    "documentary",
    "speech",
    "tutorial",
    "news_commentary",
    "vlog",
    "music_performance",
    "mixed",
}
SUBTITLE_MODES = {"none", "source", "translated", "bilingual"}
TRANSLATION_STAGES = {"none", "pre_edit", "post_edit"}
SEGMENT_KINDS = {"dialogue", "visual"}
STORY_ROLES = {"hook", "context", "development", "turn", "resolution", "closing"}
AUDIO_MODES = {"source", "mute", "duck", "narration"}
TRANSITIONS = {"cut", "fade", "crossfade"}
VISUAL_RATIO_RANGES = {
    "drama": (0.10, 0.25),
    "podcast_interview": (0.00, 0.08),
    "documentary": (0.10, 0.30),
    "speech": (0.00, 0.08),
    "tutorial": (0.00, 0.15),
    "news_commentary": (0.05, 0.15),
    "vlog": (0.10, 0.30),
    "music_performance": (0.20, 0.60),
    "mixed": (0.05, 0.20),
}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _required_mapping(
    root: dict[str, Any],
    key: str,
    errors: list[str],
) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


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
            for node in item.get("arc", []) if section == "story_options" else []:
                if isinstance(node, dict) and str(node.get("id", "")).strip():
                    ids.add(str(node["id"]).strip())
    return ids


def validate_plan(
    plan: Any,
    evidence: Any | None = None,
    analysis: Any | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(plan, dict):
        return ["plan root must be an object"], warnings

    if plan.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not str(plan.get("job_id", "")).strip():
        errors.append("job_id must not be empty")

    source = _required_mapping(plan, "source", errors)
    settings = _required_mapping(plan, "settings", errors)
    classification = _required_mapping(plan, "classification", errors)
    story = _required_mapping(plan, "story", errors)
    output = _required_mapping(plan, "output", errors)

    source_duration = source.get("duration_sec")
    if not _number(source_duration) or source_duration <= 0:
        errors.append("source.duration_sec must be a positive number")
        source_duration = 0.0

    target_duration = settings.get("target_duration_sec")
    if not _number(target_duration) or target_duration <= 0:
        errors.append("settings.target_duration_sec must be a positive number")
        target_duration = 0.0

    tolerance = settings.get("duration_tolerance_ratio", 0.15)
    if not _number(tolerance) or not 0 <= tolerance <= 0.5:
        errors.append("settings.duration_tolerance_ratio must be between 0 and 0.5")
        tolerance = 0.15

    subtitle_mode = settings.get("subtitle_mode")
    if subtitle_mode not in SUBTITLE_MODES:
        errors.append(f"settings.subtitle_mode must be one of {sorted(SUBTITLE_MODES)}")

    translation_stage = settings.get("translation_stage", "post_edit")
    if translation_stage not in TRANSLATION_STAGES:
        errors.append(
            "settings.translation_stage must be one of "
            f"{sorted(TRANSLATION_STAGES)}"
        )
    translation_polish = settings.get("translation_polish", False)
    if not isinstance(translation_polish, bool):
        errors.append("settings.translation_polish must be a boolean")

    allow_speed_change = settings.get("allow_speed_change", False)
    if not isinstance(allow_speed_change, bool):
        errors.append("settings.allow_speed_change must be a boolean")
        allow_speed_change = False

    content_type = classification.get("type")
    if content_type not in CONTENT_TYPES:
        errors.append(f"classification.type must be one of {sorted(CONTENT_TYPES)}")

    confidence = classification.get("confidence")
    if not _number(confidence) or not 0 <= confidence <= 1:
        errors.append("classification.confidence must be between 0 and 1")
    elif confidence < 0.65 and content_type != "mixed":
        warnings.append("classification confidence is below 0.65; use type 'mixed' or justify the choice")

    classification_evidence = classification.get("evidence")
    if not isinstance(classification_evidence, list) or len(
        [item for item in classification_evidence if str(item).strip()]
    ) < 3:
        errors.append("classification.evidence must contain at least three non-empty items")

    if not str(story.get("premise", "")).strip():
        errors.append("story.premise must not be empty")
    if not str(story.get("selected_option_id", "")).strip():
        errors.append("story.selected_option_id must not be empty")
    arc = story.get("arc")
    if not isinstance(arc, list) or not arc:
        errors.append("story.arc must be a non-empty array")
    elif any(role not in STORY_ROLES for role in arc):
        errors.append(f"story.arc contains an unsupported role; allowed: {sorted(STORY_ROLES)}")

    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a non-empty array")
        return errors, warnings

    ids: set[str] = set()
    visual_duration = 0.0
    previous_output_end = 0.0
    missing_translation_ids: set[str] = set()
    evidence_subtitles: dict[str, dict[str, Any]] = {}
    evidence_scenes: dict[str, dict[str, Any]] = {}
    valid_evidence_refs: set[str] = set()
    valid_analysis_refs: set[str] = set()

    if evidence is not None:
        if not isinstance(evidence, dict):
            errors.append("evidence root must be an object")
        else:
            if evidence.get("job_id") != plan.get("job_id"):
                errors.append("evidence.job_id must match plan.job_id")
            evidence_source = evidence.get("source", {})
            if isinstance(evidence_source, dict):
                evidence_duration = evidence_source.get("duration_sec")
                if _number(evidence_duration) and source_duration:
                    if abs(float(evidence_duration) - float(source_duration)) > 0.05:
                        errors.append("plan source duration does not match evidence")
                plan_fingerprint = str(source.get("fingerprint", "")).strip()
                evidence_fingerprint = str(evidence_source.get("fingerprint", "")).strip()
                if plan_fingerprint and evidence_fingerprint:
                    if plan_fingerprint != evidence_fingerprint:
                        errors.append("plan source fingerprint does not match evidence")
            evidence_subtitles = {
                str(item["id"]): item
                for item in evidence.get("subtitles", [])
                if isinstance(item, dict) and item.get("id")
            }
            evidence_scenes = {
                str(item["id"]): item
                for item in evidence.get("scenes", [])
                if isinstance(item, dict) and item.get("id")
            }
            valid_evidence_refs = (
                set(evidence_subtitles)
                | set(evidence_scenes)
                | referenced_ids(evidence.get("visual_candidates", []))
                | referenced_ids(evidence.get("keyframes", []))
                | referenced_ids(evidence.get("analysis_chunks", []))
            )
            classification_refs = classification.get("evidence_refs")
            if not isinstance(classification_refs, list) or len(classification_refs) < 3:
                errors.append(
                    "classification.evidence_refs must contain at least three items"
                )
            else:
                unknown_refs = sorted(
                    str(ref).strip()
                    for ref in classification_refs
                    if str(ref).strip() not in valid_evidence_refs
                )
                if unknown_refs:
                    errors.append(
                        f"classification.evidence_refs contains unknown IDs: {unknown_refs}"
                    )

    if analysis is not None:
        if not isinstance(analysis, dict):
            errors.append("analysis root must be an object")
        else:
            if analysis.get("job_id") != plan.get("job_id"):
                errors.append("analysis.job_id must match plan.job_id")
            valid_analysis_refs = _analysis_reference_ids(analysis)
            selected_option = str(
                story.get("selected_option_id", "")
            ).strip()
            if selected_option != str(analysis.get("selected_option_id", "")).strip():
                errors.append(
                    "story.selected_option_id must match analysis.selected_option_id"
                )

    for index, segment in enumerate(segments, start=1):
        label = f"segments[{index - 1}]"
        if not isinstance(segment, dict):
            errors.append(f"{label} must be an object")
            continue

        segment_id = str(segment.get("id", "")).strip()
        if not segment_id:
            errors.append(f"{label}.id must not be empty")
        elif segment_id in ids:
            errors.append(f"{label}.id duplicates '{segment_id}'")
        ids.add(segment_id)

        if segment.get("output_order") != index:
            errors.append(f"{label}.output_order must be {index}")

        kind = segment.get("kind")
        if kind not in SEGMENT_KINDS:
            errors.append(f"{label}.kind must be one of {sorted(SEGMENT_KINDS)}")

        if segment.get("story_role") not in STORY_ROLES:
            errors.append(f"{label}.story_role must be one of {sorted(STORY_ROLES)}")

        source_start = segment.get("source_start_sec")
        source_end = segment.get("source_end_sec")
        output_start = segment.get("output_start_sec")
        output_end = segment.get("output_end_sec")
        playback_rate = segment.get("playback_rate", 1.0)

        if not _number(source_start) or source_start < 0:
            errors.append(f"{label}.source_start_sec must be non-negative")
            source_start = 0.0
        if not _number(source_end) or source_end <= source_start:
            errors.append(f"{label}.source_end_sec must be greater than source_start_sec")
            source_end = source_start
        elif source_duration and source_end > source_duration + 0.001:
            errors.append(f"{label}.source_end_sec exceeds source.duration_sec")

        if not _number(output_start) or output_start < 0:
            errors.append(f"{label}.output_start_sec must be non-negative")
            output_start = previous_output_end
        if not _number(output_end) or output_end <= output_start:
            errors.append(f"{label}.output_end_sec must be greater than output_start_sec")
            output_end = output_start

        if index == 1 and abs(output_start) > 0.05:
            errors.append(f"{label}.output_start_sec must start at 0")
        elif index > 1 and abs(output_start - previous_output_end) > 0.25:
            warnings.append(
                f"{label} output timeline differs from previous end by more than 0.25s; "
                "confirm transition overlap or gap"
            )
        previous_output_end = output_end

        if not _number(playback_rate) or not 0.5 <= playback_rate <= 2.0:
            errors.append(f"{label}.playback_rate must be between 0.5 and 2.0")
            playback_rate = 1.0
        elif not allow_speed_change and abs(playback_rate - 1.0) > 0.001:
            errors.append(
                f"{label}.playback_rate must be 1.0 when settings.allow_speed_change is false"
            )
        elif kind == "dialogue" and not 0.9 <= playback_rate <= 1.1:
            warnings.append(f"{label} dialogue speed may sound unnatural at {playback_rate:.2f}x")

        source_len = source_end - source_start
        output_len = output_end - output_start
        expected_len = source_len / playback_rate if playback_rate else source_len
        if expected_len > 0 and abs(output_len - expected_len) > max(0.25, expected_len * 0.08):
            warnings.append(
                f"{label} output duration does not match source duration/playback_rate; "
                "confirm transition math"
            )

        subtitle_ids = segment.get("source_subtitle_ids")
        if not isinstance(subtitle_ids, list):
            errors.append(f"{label}.source_subtitle_ids must be an array")
            subtitle_ids = []

        if kind == "dialogue":
            if not subtitle_ids:
                errors.append(f"{label} dialogue segment must reference source subtitles")
            if not str(segment.get("source_text", "")).strip():
                errors.append(f"{label} dialogue segment must include source_text")
        elif kind == "visual":
            visual_duration += max(0.0, output_len)
            if subtitle_ids:
                warnings.append(f"{label} visual segment should normally have no source_subtitle_ids")

        scene_ids = segment.get("source_scene_ids")
        if not isinstance(scene_ids, list):
            errors.append(f"{label}.source_scene_ids must be an array")
            scene_ids = []
        if kind == "visual" and not scene_ids:
            errors.append(f"{label} visual segment must reference at least one source scene")

        analysis_refs = segment.get("analysis_refs")
        if not isinstance(analysis_refs, list) or not [
            ref for ref in analysis_refs if str(ref).strip()
        ]:
            errors.append(f"{label}.analysis_refs must be a non-empty array")
            analysis_refs = []

        if evidence_subtitles:
            unknown_subtitle_ids = sorted(
                str(ref).strip()
                for ref in subtitle_ids
                if str(ref).strip() not in evidence_subtitles
            )
            if unknown_subtitle_ids:
                errors.append(
                    f"{label} contains unknown source_subtitle_ids: {unknown_subtitle_ids}"
                )
            referenced_cues = [
                evidence_subtitles[str(ref).strip()]
                for ref in subtitle_ids
                if str(ref).strip() in evidence_subtitles
            ]
            outside_cues = [
                str(cue["id"])
                for cue in referenced_cues
                if overlap_duration(
                    float(source_start),
                    float(source_end),
                    float(cue["start_sec"]),
                    float(cue["end_sec"]),
                )
                <= 0
            ]
            if outside_cues:
                errors.append(
                    f"{label} references subtitles outside its source range: {outside_cues}"
                )
            expected_text = normalize_text(
                " ".join(str(cue.get("source_text", "")) for cue in referenced_cues)
            )
            actual_text = normalize_text(str(segment.get("source_text", "")))
            if expected_text and actual_text and expected_text != actual_text:
                warnings.append(
                    f"{label}.source_text differs from referenced subtitle evidence"
                )
            if (
                subtitle_mode in {"translated", "bilingual"}
                and translation_stage != "post_edit"
            ):
                missing_translation_ids.update(
                    str(cue["id"])
                    for cue in referenced_cues
                    if not normalize_text(str(cue.get("target_text", "")))
                )

        if evidence_scenes:
            unknown_scene_ids = sorted(
                str(ref).strip()
                for ref in scene_ids
                if str(ref).strip() not in evidence_scenes
            )
            if unknown_scene_ids:
                errors.append(
                    f"{label} contains unknown source_scene_ids: {unknown_scene_ids}"
                )
            outside_scenes = [
                str(ref).strip()
                for ref in scene_ids
                if str(ref).strip() in evidence_scenes
                and overlap_duration(
                    float(source_start),
                    float(source_end),
                    float(evidence_scenes[str(ref).strip()]["start_sec"]),
                    float(evidence_scenes[str(ref).strip()]["end_sec"]),
                )
                <= 0
            ]
            if outside_scenes:
                errors.append(
                    f"{label} references scenes outside its source range: {outside_scenes}"
                )

        if valid_analysis_refs:
            unknown_analysis_refs = sorted(
                str(ref).strip()
                for ref in analysis_refs
                if str(ref).strip() not in valid_analysis_refs
            )
            if unknown_analysis_refs:
                errors.append(
                    f"{label} contains unknown analysis_refs: {unknown_analysis_refs}"
                )

        if segment.get("audio_mode") not in AUDIO_MODES:
            errors.append(f"{label}.audio_mode must be one of {sorted(AUDIO_MODES)}")
        elif segment.get("audio_mode") == "narration":
            if not str(segment.get("narration_text", "")).strip():
                errors.append(f"{label} narration audio requires narration_text")
            if segment.get("narration_source") != "editorial_bridge":
                errors.append(f"{label} narration_source must be 'editorial_bridge'")
            narration_audio_path = str(segment.get("narration_audio_path", "")).strip()
            if not narration_audio_path:
                warnings.append(
                    f"{label} narration has no narration_audio_path and cannot render yet"
                )

        if not str(segment.get("story_reason", "")).strip():
            errors.append(f"{label}.story_reason must not be empty")
        if segment.get("transition") not in TRANSITIONS:
            errors.append(f"{label}.transition must be one of {sorted(TRANSITIONS)}")
        elif segment.get("transition") != "cut":
            warnings.append(
                f"{label} uses {segment.get('transition')}; the deterministic v1 renderer "
                "currently supports cut transitions only"
            )

    output_duration = previous_output_end
    if target_duration and output_duration:
        lower = target_duration * (1 - tolerance)
        upper = target_duration * (1 + tolerance)
        if not lower <= output_duration <= upper:
            warnings.append(
                f"output duration {output_duration:.3f}s is outside target range "
                f"{lower:.3f}s-{upper:.3f}s"
            )

    if output_duration and content_type in VISUAL_RATIO_RANGES:
        ratio = visual_duration / output_duration
        low, high = VISUAL_RATIO_RANGES[content_type]
        if ratio < low - 0.01 or ratio > high + 0.01:
            warnings.append(
                f"visual segment ratio {ratio:.1%} is outside the suggested "
                f"{low:.0%}-{high:.0%} range for {content_type}"
            )

    source_language = str(source.get("language", "")).lower()
    target_language = str(settings.get("target_language", "")).lower()
    languages_differ = (
        source_language
        and source_language != "unknown"
        and target_language
        and not target_language.startswith(source_language)
    )
    if languages_differ:
        if subtitle_mode in {"none", "source"}:
            warnings.append("source and target languages differ; translated or bilingual subtitles are recommended")
        elif missing_translation_ids and translation_stage != "post_edit":
            errors.append(
                "translated or bilingual output references subtitles without target_text: "
                f"{sorted(missing_translation_ids)}"
            )
        elif translation_stage == "post_edit":
            warnings.append(
                "translation is deferred until after edit compilation; inject the final "
                "translated subtitle before rendering translated/bilingual output"
            )

    for key in ("video_path", "source_subtitle_path", "qa_report_path"):
        if not str(output.get(key, "")).strip():
            errors.append(f"output.{key} must not be empty")
    if subtitle_mode in {"translated", "bilingual"}:
        if not str(output.get("translated_subtitle_path", "")).strip():
            errors.append("output.translated_subtitle_path must not be empty")
    if subtitle_mode == "bilingual":
        if not str(output.get("bilingual_subtitle_path", "")).strip():
            errors.append("output.bilingual_subtitle_path must not be empty")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Path to story_plan.json")
    parser.add_argument("--evidence", type=Path, help="Path to evidence_pack.json")
    parser.add_argument("--analysis", type=Path, help="Path to story_analysis.json")
    args = parser.parse_args()

    try:
        with args.plan.open("r", encoding="utf-8-sig") as handle:
            plan = json.load(handle)
        evidence = read_json(args.evidence) if args.evidence else None
        analysis = read_json(args.analysis) if args.analysis else None
    except FileNotFoundError:
        print("ERROR: one or more input files were not found", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: failed to read plan: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate_plan(plan, evidence=evidence, analysis=analysis)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s).", file=sys.stderr)
        return 1

    print(f"Validation passed: {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
