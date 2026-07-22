#!/usr/bin/env python3
"""Rebuild selected source subtitles on the final reordered story timeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_story import rebuild_subtitle_timeline
from story_pipeline_common import read_json, write_srt
from validate_story_plan import validate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        plan = read_json(args.plan.expanduser().resolve())
        evidence = read_json(args.evidence.expanduser().resolve())
        analysis = read_json(args.analysis.expanduser().resolve())
        errors, warnings = validate_plan(plan, evidence=evidence, analysis=analysis)
        for warning in warnings:
            print(f"WARNING: {warning}")
        if errors:
            raise ValueError("story plan is invalid: " + "; ".join(errors[:10]))

        output = (
            args.output.expanduser().resolve()
            if args.output
            else Path(plan["output"]["source_subtitle_path"]).expanduser().resolve()
        )
        cues = rebuild_subtitle_timeline(plan, evidence)
        written = write_srt(output, cues, "source_text")
        if written == 0:
            raise ValueError("selected story contains no source subtitle cues")
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Post-edit source subtitles: {output}")
    print(f"Cues: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
