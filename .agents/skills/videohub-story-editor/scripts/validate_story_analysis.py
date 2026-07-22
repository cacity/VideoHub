#!/usr/bin/env python3
"""Validate grounded story understanding against a VideoHub evidence pack."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from story_pipeline_common import (
    finite_number,
    read_json,
    referenced_ids,
)

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
STORY_ROLES = {"hook", "context", "development", "turn", "resolution", "closing"}
EVENT_KINDS = {"event", "claim", "question", "answer", "step", "result"}
CONSTRAINT_TYPES = {
    "chronology",
    "causality",
    "pronoun",
    "speaker",
    "location",
    "tutorial_order",
    "question_answer",
    "visual_reaction",
}


def _mapping(root: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _list(root: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    value = root.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    return value


def _non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _check_refs(
    refs: Any,
    *,
    label: str,
    valid_refs: set[str],
    errors: list[str],
    minimum: int = 1,
) -> list[str]:
    if not isinstance(refs, list):
        errors.append(f"{label} must be an array")
        return []
    normalized = [str(ref).strip() for ref in refs if str(ref).strip()]
    if len(normalized) < minimum:
        errors.append(f"{label} must contain at least {minimum} reference(s)")
    unknown = sorted(set(normalized) - valid_refs)
    if unknown:
        errors.append(f"{label} contains unknown evidence refs: {unknown}")
    return normalized


def _collect_analysis_ids(groups: Iterable[list[Any]]) -> set[str]:
    ids: set[str] = set()
    for group in groups:
        ids.update(referenced_ids(item for item in group if isinstance(item, dict)))
    return ids


def validate_analysis(
    analysis: Any,
    evidence: Any,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(analysis, dict):
        return ["analysis root must be an object"], warnings
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"], warnings

    if analysis.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if analysis.get("job_id") != evidence.get("job_id"):
        errors.append("analysis.job_id must match evidence.job_id")

    subtitle_ids = referenced_ids(evidence.get("subtitles", []))
    scene_ids = referenced_ids(evidence.get("scenes", []))
    visual_candidate_ids = referenced_ids(evidence.get("visual_candidates", []))
    keyframe_ids = referenced_ids(evidence.get("keyframes", []))
    chunk_ids = referenced_ids(evidence.get("analysis_chunks", []))
    evidence_refs = (
        subtitle_ids
        | scene_ids
        | visual_candidate_ids
        | keyframe_ids
        | chunk_ids
    )

    profile = _mapping(analysis, "content_profile", errors)
    content_type = profile.get("type")
    if content_type not in CONTENT_TYPES:
        errors.append(f"content_profile.type must be one of {sorted(CONTENT_TYPES)}")
    confidence = profile.get("confidence")
    if not finite_number(confidence) or not 0 <= confidence <= 1:
        errors.append("content_profile.confidence must be between 0 and 1")
    elif confidence < 0.65 and content_type != "mixed":
        warnings.append("low classification confidence should normally use type 'mixed'")
    _check_refs(
        profile.get("evidence_refs"),
        label="content_profile.evidence_refs",
        valid_refs=evidence_refs,
        errors=errors,
        minimum=3,
    )
    if not _non_empty(analysis.get("global_summary")):
        errors.append("global_summary must not be empty")

    chunk_findings = _list(analysis, "chunk_findings", errors)
    finding_ids: set[str] = set()
    covered_chunks: set[str] = set()
    for index, item in enumerate(chunk_findings):
        label = f"chunk_findings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            errors.append(f"{label}.id must not be empty")
        elif item_id in finding_ids:
            errors.append(f"{label}.id duplicates '{item_id}'")
        finding_ids.add(item_id)
        chunk_id = str(item.get("chunk_id", "")).strip()
        if chunk_id not in chunk_ids:
            errors.append(f"{label}.chunk_id is not in evidence analysis_chunks")
        else:
            covered_chunks.add(chunk_id)
        if not _non_empty(item.get("summary")):
            errors.append(f"{label}.summary must not be empty")
        _check_refs(
            item.get("evidence_refs"),
            label=f"{label}.evidence_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )
    missing_chunks = sorted(chunk_ids - covered_chunks)
    if missing_chunks:
        errors.append(f"chunk_findings do not cover chunks: {missing_chunks}")

    entities = _list(analysis, "entities", errors)
    entity_ids: set[str] = set()
    for index, item in enumerate(entities):
        label = f"entities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            errors.append(f"{label}.id must not be empty")
        elif item_id in entity_ids:
            errors.append(f"{label}.id duplicates '{item_id}'")
        entity_ids.add(item_id)
        if not _non_empty(item.get("name")) or not _non_empty(item.get("role")):
            errors.append(f"{label} must include name and role")
        _check_refs(
            item.get("evidence_refs"),
            label=f"{label}.evidence_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )

    events = _list(analysis, "events", errors)
    if not events:
        errors.append("events must contain at least one grounded event or claim")
    event_ids: set[str] = set()
    for index, item in enumerate(events):
        label = f"events[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        event_id = str(item.get("id", "")).strip()
        if not event_id:
            errors.append(f"{label}.id must not be empty")
        elif event_id in event_ids:
            errors.append(f"{label}.id duplicates '{event_id}'")
        event_ids.add(event_id)
        if item.get("kind") not in EVENT_KINDS:
            errors.append(f"{label}.kind must be one of {sorted(EVENT_KINDS)}")
        if not _non_empty(item.get("label")) or not _non_empty(item.get("summary")):
            errors.append(f"{label} must include label and summary")
        if not isinstance(item.get("chronology_index"), int):
            errors.append(f"{label}.chronology_index must be an integer")
        item_confidence = item.get("confidence")
        if not finite_number(item_confidence) or not 0 <= item_confidence <= 1:
            errors.append(f"{label}.confidence must be between 0 and 1")
        _check_refs(
            item.get("evidence_refs"),
            label=f"{label}.evidence_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )
    for index, item in enumerate(events):
        if not isinstance(item, dict):
            continue
        causes = item.get("cause_event_ids", [])
        if not isinstance(causes, list):
            errors.append(f"events[{index}].cause_event_ids must be an array")
            continue
        unknown_causes = sorted(
            str(cause).strip()
            for cause in causes
            if str(cause).strip() not in event_ids
        )
        if unknown_causes:
            errors.append(f"events[{index}] has unknown cause_event_ids: {unknown_causes}")

    themes = _list(analysis, "themes", errors)
    for index, item in enumerate(themes):
        label = f"themes[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if not _non_empty(item.get("id")) or not _non_empty(item.get("label")):
            errors.append(f"{label} must include id and label")
        _check_refs(
            item.get("evidence_refs"),
            label=f"{label}.evidence_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )

    visual_findings = _list(analysis, "visual_findings", errors)
    for index, item in enumerate(visual_findings):
        label = f"visual_findings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if not _non_empty(item.get("id")) or not _non_empty(item.get("summary")):
            errors.append(f"{label} must include id and summary")
        _check_refs(
            item.get("frame_refs"),
            label=f"{label}.frame_refs",
            valid_refs=keyframe_ids,
            errors=errors,
        )
        _check_refs(
            item.get("scene_refs", []),
            label=f"{label}.scene_refs",
            valid_refs=scene_ids,
            errors=errors,
            minimum=0,
        )
        _check_refs(
            item.get("candidate_refs", []),
            label=f"{label}.candidate_refs",
            valid_refs=visual_candidate_ids,
            errors=errors,
            minimum=0,
        )

    constraints = _list(analysis, "continuity_constraints", errors)
    for index, item in enumerate(constraints):
        label = f"continuity_constraints[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if not _non_empty(item.get("id")) or not _non_empty(item.get("description")):
            errors.append(f"{label} must include id and description")
        if item.get("type") not in CONSTRAINT_TYPES:
            errors.append(f"{label}.type must be one of {sorted(CONSTRAINT_TYPES)}")
        _check_refs(
            item.get("protected_refs"),
            label=f"{label}.protected_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )
        _check_refs(
            item.get("required_before_refs", []),
            label=f"{label}.required_before_refs",
            valid_refs=evidence_refs,
            errors=errors,
            minimum=0,
        )

    options = _list(analysis, "story_options", errors)
    if not options:
        errors.append("story_options must contain at least one option")
    option_ids: set[str] = set()
    arc_ids: set[str] = set()
    for index, item in enumerate(options):
        label = f"story_options[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        option_id = str(item.get("id", "")).strip()
        if not option_id:
            errors.append(f"{label}.id must not be empty")
        elif option_id in option_ids:
            errors.append(f"{label}.id duplicates '{option_id}'")
        option_ids.add(option_id)
        if not _non_empty(item.get("premise")) or not _non_empty(item.get("angle")):
            errors.append(f"{label} must include premise and angle")
        estimated_duration = item.get("estimated_duration_sec")
        if not finite_number(estimated_duration) or estimated_duration <= 0:
            errors.append(f"{label}.estimated_duration_sec must be positive")
        arc = item.get("arc")
        if not isinstance(arc, list) or not arc:
            errors.append(f"{label}.arc must be a non-empty array")
            continue
        for arc_index, node in enumerate(arc):
            arc_label = f"{label}.arc[{arc_index}]"
            if not isinstance(node, dict):
                errors.append(f"{arc_label} must be an object")
                continue
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                errors.append(f"{arc_label}.id must not be empty")
            elif node_id in arc_ids:
                errors.append(f"{arc_label}.id duplicates '{node_id}'")
            arc_ids.add(node_id)
            if node.get("role") not in STORY_ROLES:
                errors.append(f"{arc_label}.role must be one of {sorted(STORY_ROLES)}")
            if not _non_empty(node.get("purpose")):
                errors.append(f"{arc_label}.purpose must not be empty")
            _check_refs(
                node.get("evidence_refs"),
                label=f"{arc_label}.evidence_refs",
                valid_refs=evidence_refs,
                errors=errors,
            )

    selected_option_id = str(analysis.get("selected_option_id", "")).strip()
    if selected_option_id not in option_ids:
        errors.append("selected_option_id must reference a story option")

    uncertainties = _list(analysis, "uncertainties", errors)
    for index, item in enumerate(uncertainties):
        label = f"uncertainties[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if not _non_empty(item.get("id")) or not _non_empty(item.get("description")):
            errors.append(f"{label} must include id and description")
        if not _non_empty(item.get("impact")):
            errors.append(f"{label}.impact must not be empty")
        _check_refs(
            item.get("evidence_refs"),
            label=f"{label}.evidence_refs",
            valid_refs=evidence_refs,
            errors=errors,
        )

    analysis_ids = _collect_analysis_ids(
        [events, themes, visual_findings, constraints, options]
    ) | arc_ids
    if len(analysis_ids) != sum(
        len(referenced_ids(group))
        for group in [events, themes, visual_findings, constraints, options]
    ) + len(arc_ids):
        warnings.append("analysis IDs should be globally unique across analysis sections")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path, help="Path to story_analysis.json")
    parser.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="Path to evidence_pack.json",
    )
    args = parser.parse_args()

    try:
        analysis = read_json(args.analysis)
        evidence = read_json(args.evidence)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: failed to read input: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate_analysis(analysis, evidence)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(
            f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s).",
            file=sys.stderr,
        )
        return 1
    print(f"Validation passed: {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
