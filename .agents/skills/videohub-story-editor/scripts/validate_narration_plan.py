#!/usr/bin/env python3
"""Validate an evidence-grounded TTS narration plan for a story edit."""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

from story_pipeline_common import read_json, referenced_ids

NARRATION_STYLES = {
    "film_commentary",
    "drama_recap",
    "documentary_commentary",
    "podcast_recap",
    "knowledge_explainer",
}
TTS_PROVIDERS = {"minimax", "doubao"}
AUDIO_STRATEGIES = {"narration_only", "hybrid_source_anchors"}


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _analysis_ids(analysis: dict[str, Any]) -> set[str]:
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
            if str(item.get("id", "")).strip():
                ids.add(str(item["id"]).strip())
            if section == "story_options":
                for node in item.get("arc", []):
                    if isinstance(node, dict) and str(node.get("id", "")).strip():
                        ids.add(str(node["id"]).strip())
    return ids


def _spoken_character_count(text: str) -> int:
    return len(re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()\-—…]", "", text or ""))


def _latin_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:[.,]\d+)*", text or ""))


def _uses_latin_word_rate(text: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text or ""))
    return latin > 0 and latin >= cjk * 2


def validate_narration_plan(
    narration: Any,
    story_plan: Any,
    evidence: Any,
    analysis: Any,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not all(isinstance(item, dict) for item in (narration, story_plan, evidence, analysis)):
        return ["narration, story plan, evidence, and analysis must be objects"], warnings

    if narration.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    job_id = str(narration.get("job_id", "")).strip()
    if not job_id or any(
        str(item.get("job_id", "")).strip() != job_id
        for item in (story_plan, evidence, analysis)
    ):
        errors.append("job_id must match story plan, evidence, and analysis")
    if narration.get("style") not in NARRATION_STYLES:
        errors.append(f"style must be one of {sorted(NARRATION_STYLES)}")

    settings = narration.get("settings")
    if not isinstance(settings, dict):
        errors.append("settings must be an object")
        settings = {}
    background_volume = settings.get("original_audio_volume", 0.3)
    if not _number(background_volume) or not 0 <= background_volume <= 1:
        errors.append("settings.original_audio_volume must be between 0 and 1")
    source_audio_volume = settings.get("source_audio_volume", 1.0)
    if not _number(source_audio_volume) or not 0 <= source_audio_volume <= 1:
        errors.append("settings.source_audio_volume must be between 0 and 1")
    audio_strategy = settings.get("audio_strategy", "narration_only")
    if audio_strategy not in AUDIO_STRATEGIES:
        errors.append(f"settings.audio_strategy must be one of {sorted(AUDIO_STRATEGIES)}")
    max_speedup = settings.get("max_audio_speedup", 1.25)
    if not _number(max_speedup) or not 1 <= max_speedup <= 2:
        errors.append("settings.max_audio_speedup must be between 1 and 2")

    tts = narration.get("tts")
    if not isinstance(tts, dict):
        errors.append("tts must be an object")
        tts = {}
    provider = tts.get("provider")
    if provider not in TTS_PROVIDERS:
        errors.append(f"tts.provider must be one of {sorted(TTS_PROVIDERS)}")
    speed = tts.get("speed", 1.0)
    if not _number(speed) or not 0.5 <= speed <= 2.0:
        errors.append("tts.speed must be between 0.5 and 2.0")
    if provider == "minimax" and not str(tts.get("voice_id", "")).strip():
        errors.append("MiniMax narration requires tts.voice_id")
    if provider == "doubao" and not str(tts.get("voice_type", "")).strip():
        errors.append("Doubao narration requires tts.voice_type")

    valid_refs = (
        referenced_ids(evidence.get("subtitles", []))
        | referenced_ids(evidence.get("scenes", []))
        | referenced_ids(evidence.get("visual_candidates", []))
        | referenced_ids(evidence.get("keyframes", []))
        | referenced_ids(evidence.get("analysis_chunks", []))
        | _analysis_ids(analysis)
        | referenced_ids(story_plan.get("segments", []))
    )
    story_duration = 0.0
    segments = story_plan.get("segments", [])
    if isinstance(segments, list) and segments:
        story_duration = float(segments[-1].get("output_end_sec", 0) or 0)
    if story_duration <= 0:
        errors.append("story plan has no valid output duration")

    blocks = narration.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errors.append("blocks must be a non-empty array")
        return errors, warnings
    if len(blocks) > 120:
        errors.append("blocks must not exceed 120 items")

    ids: set[str] = set()
    block_ranges: list[tuple[float, float, str]] = []
    previous_end = 0.0
    for index, block in enumerate(blocks):
        label = f"blocks[{index}]"
        if not isinstance(block, dict):
            errors.append(f"{label} must be an object")
            continue
        block_id = str(block.get("id", "")).strip()
        if not block_id:
            errors.append(f"{label}.id must not be empty")
        elif block_id in ids:
            errors.append(f"{label}.id duplicates '{block_id}'")
        ids.add(block_id)

        start = block.get("start_sec")
        end = block.get("end_sec")
        if not _number(start) or not _number(end) or start < 0 or end <= start:
            errors.append(f"{label} has an invalid time range")
            continue
        start = float(start)
        end = float(end)
        if start < previous_end - 0.01:
            errors.append(f"{label} overlaps the previous narration block")
        previous_end = end
        if story_duration and end > story_duration + 0.05:
            errors.append(f"{label}.end_sec exceeds the story duration")
        block_ranges.append((start, end, block_id or label))

        text = str(block.get("text", "")).strip()
        if not text:
            errors.append(f"{label}.text must not be empty")
        else:
            duration = end - start
            if _uses_latin_word_rate(text):
                words_per_second = _latin_word_count(text) / duration
                if words_per_second > 3.4:
                    errors.append(
                        f"{label} narration is too dense at "
                        f"{words_per_second:.2f} words/s"
                    )
                elif words_per_second > 2.8:
                    warnings.append(
                        f"{label} narration may sound rushed at "
                        f"{words_per_second:.2f} words/s"
                    )
            else:
                chars_per_second = _spoken_character_count(text) / duration
                if chars_per_second > 6.5:
                    errors.append(
                        f"{label} narration is too dense at "
                        f"{chars_per_second:.2f} chars/s"
                    )
                elif chars_per_second > 5.0:
                    warnings.append(
                        f"{label} narration may sound rushed at "
                        f"{chars_per_second:.2f} chars/s"
                    )

        refs = block.get("evidence_refs")
        if not isinstance(refs, list) or not [ref for ref in refs if str(ref).strip()]:
            errors.append(f"{label}.evidence_refs must be a non-empty array")
        else:
            unknown = sorted(
                str(ref).strip()
                for ref in refs
                if str(ref).strip() not in valid_refs
            )
            if unknown:
                errors.append(f"{label}.evidence_refs contains unknown IDs: {unknown}")
        if not str(block.get("purpose", "")).strip():
            errors.append(f"{label}.purpose must not be empty")

    source_windows = narration.get("source_audio_windows", [])
    if not isinstance(source_windows, list):
        errors.append("source_audio_windows must be an array")
        source_windows = []
    if audio_strategy == "hybrid_source_anchors" and not source_windows:
        errors.append(
            "hybrid_source_anchors requires at least one source_audio_windows item"
        )
    if audio_strategy == "narration_only" and source_windows:
        errors.append(
            "source_audio_windows require settings.audio_strategy="
            "'hybrid_source_anchors'"
        )

    source_duration = 0.0
    previous_source_end = 0.0
    for index, window in enumerate(source_windows):
        label = f"source_audio_windows[{index}]"
        if not isinstance(window, dict):
            errors.append(f"{label} must be an object")
            continue
        window_id = str(window.get("id", "")).strip()
        if not window_id:
            errors.append(f"{label}.id must not be empty")
        elif window_id in ids:
            errors.append(f"{label}.id duplicates '{window_id}'")
        ids.add(window_id)

        start = window.get("start_sec")
        end = window.get("end_sec")
        if not _number(start) or not _number(end) or start < 0 or end <= start:
            errors.append(f"{label} has an invalid time range")
            continue
        start = float(start)
        end = float(end)
        if start < previous_source_end - 0.01:
            errors.append(f"{label} overlaps the previous source audio window")
        previous_source_end = end
        if story_duration and end > story_duration + 0.05:
            errors.append(f"{label}.end_sec exceeds the story duration")
        duration = end - start
        source_duration += duration
        if duration < 1.0:
            warnings.append(f"{label} is shorter than 1 second")
        if duration > 20.0:
            warnings.append(
                f"{label} keeps {duration:.2f}s of source audio; verify it cannot be compressed"
            )
        if duration > 30.0:
            errors.append(f"{label} must not exceed 30 seconds")

        for block_start, block_end, block_id in block_ranges:
            if min(end, block_end) - max(start, block_start) > 0.01:
                errors.append(f"{label} overlaps narration block '{block_id}'")

        refs = window.get("evidence_refs")
        if not isinstance(refs, list) or not [ref for ref in refs if str(ref).strip()]:
            errors.append(f"{label}.evidence_refs must be a non-empty array")
        else:
            unknown = sorted(
                str(ref).strip()
                for ref in refs
                if str(ref).strip() not in valid_refs
            )
            if unknown:
                errors.append(f"{label}.evidence_refs contains unknown IDs: {unknown}")
        if not str(window.get("purpose", "")).strip():
            errors.append(f"{label}.purpose must not be empty")

    if audio_strategy == "hybrid_source_anchors" and story_duration > 0:
        source_ratio = source_duration / story_duration
        if source_ratio < 0.03:
            warnings.append(
                f"source audio ratio is only {source_ratio:.1%}; character voices may feel absent"
            )
        if source_ratio > 0.20:
            warnings.append(
                f"source audio ratio is {source_ratio:.1%}; verify the result remains commentary-led"
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("narration", type=Path)
    parser.add_argument("--story-plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args()
    try:
        narration = read_json(args.narration.expanduser().resolve())
        story_plan = read_json(args.story_plan.expanduser().resolve())
        evidence = read_json(args.evidence.expanduser().resolve())
        analysis = read_json(args.analysis.expanduser().resolve())
        errors, warnings = validate_narration_plan(
            narration,
            story_plan,
            evidence,
            analysis,
        )
    except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"Validation passed: {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
