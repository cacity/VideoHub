#!/usr/bin/env python3
"""Validate a hybrid film-commentary narration plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _story_scripts_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "videohub-story-editor" / "scripts"
        if candidate.is_dir():
            return candidate
        candidate = parent / ".agents" / "skills" / "videohub-story-editor" / "scripts"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("videohub-story-editor scripts directory was not found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("narration", type=Path)
    parser.add_argument("--story-plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args()

    scripts_dir = _story_scripts_dir()
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from story_pipeline_common import read_json
    from validate_narration_plan import validate_narration_plan

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
        if narration.get("style") not in {"film_commentary", "drama_recap"}:
            errors.append("film commentary style must be film_commentary or drama_recap")
        if narration.get("settings", {}).get("audio_strategy") != "hybrid_source_anchors":
            errors.append("film commentary requires audio_strategy=hybrid_source_anchors")
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
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
