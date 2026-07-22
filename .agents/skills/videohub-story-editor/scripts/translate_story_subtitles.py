#!/usr/bin/env python3
"""Translate the final reordered story subtitles, with optional DeepSeek polish."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from story_pipeline_common import (
    find_repo_root,
    pair_translations,
    parse_subtitle,
    read_json,
    write_json,
)


def _translate(
    source: Path,
    *,
    target_language: str,
    polish: bool,
    output_dir: Path,
) -> Path:
    repo_root = find_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from src.youtube_transcriber import translate_subtitle_file

    result = translate_subtitle_file(
        str(source),
        target_language=target_language,
        output_dir=str(output_dir),
        enable_translation_polish=polish,
    )
    if not result:
        raise RuntimeError("subtitle translation returned no output path")
    translated = Path(result).expanduser().resolve()
    if not translated.is_file() or translated.stat().st_size == 0:
        raise RuntimeError(f"translated subtitle is missing or empty: {translated}")
    return translated


def _validate_coverage(source: Path, translated: Path) -> tuple[int, int]:
    source_cues = parse_subtitle(source)
    target_cues = parse_subtitle(translated)
    paired = pair_translations(source_cues, target_cues)
    missing = sum(1 for text in paired if not text.strip())
    if missing:
        raise ValueError(
            f"translated subtitle misses {missing}/{len(source_cues)} final story cue(s)"
        )
    return len(source_cues), len(target_cues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-language")
    polish_group = parser.add_mutually_exclusive_group()
    polish_group.add_argument("--polish", action="store_true")
    polish_group.add_argument("--no-polish", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    try:
        plan_path = args.plan.expanduser().resolve()
        plan = read_json(plan_path)
        settings = plan.get("settings", {})
        source = (
            args.source.expanduser().resolve()
            if args.source
            else Path(plan["output"]["source_subtitle_path"]).expanduser().resolve()
        )
        if not source.is_file():
            raise FileNotFoundError(
                f"post-edit source subtitle not found: {source}; "
                "run prepare_story_subtitles.py first"
            )
        output = (
            args.output.expanduser().resolve()
            if args.output
            else Path(plan["output"]["translated_subtitle_path"]).expanduser().resolve()
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        target_language = (
            args.target_language
            or str(settings.get("target_language", "zh-CN"))
        )
        polish = (
            args.polish
            if args.polish
            else (
                False
                if args.no_polish
                else bool(settings.get("translation_polish", False))
            )
        )
        generated = _translate(
            source,
            target_language=target_language,
            polish=polish,
            output_dir=output.parent,
        )
        if generated != output:
            shutil.copy2(generated, output)
        source_count, target_count = _validate_coverage(source, output)
        google_candidate = generated.with_name(
            f"{generated.stem.removesuffix('_polished')}_google{generated.suffix}"
        )
        google_output = google_candidate if google_candidate.is_file() else None
        polished_output = (
            generated if generated.stem.endswith("_polished") else None
        )

        manifest = (
            args.manifest.expanduser().resolve()
            if args.manifest
            else plan_path.parent / "post_edit_translation.json"
        )
        write_json(
            manifest,
            {
                "schema_version": "1.0",
                "job_id": plan.get("job_id"),
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "translation_stage": "post_edit",
                "source_subtitle_path": source.as_posix(),
                "translated_subtitle_path": output.as_posix(),
                "translator_output_path": generated.as_posix(),
                "google_translation_path": (
                    google_output.as_posix() if google_output else None
                ),
                "polished_translation_path": (
                    polished_output.as_posix() if polished_output else None
                ),
                "target_language": target_language,
                "polish_requested": polish,
                "deepseek_configured": bool(
                    os.getenv("DEEPSEEK_API_KEY", "").strip()
                ),
                "source_cue_count": source_count,
                "translated_cue_count": target_count,
            },
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Post-edit translated subtitles: {output}")
    print(f"Translation manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
