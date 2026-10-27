"""Isolated worker reusing the existing resource-controlled Whisper pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="")
    args = parser.parse_args()
    from src.youtube_transcriber import extract_audio_from_video, transcribe_audio_unified

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    audio = extract_audio_from_video(args.video, output_dir=str(output))
    _, subtitle = transcribe_audio_unified(
        audio,
        output_dir=str(output),
        subtitle_dir=str(output),
        model_size=args.model,
        generate_subtitles=True,
        translate_to_chinese=False,
        source_language=args.language or None,
        enable_translation_polish=False,
    )
    if not subtitle or not Path(subtitle).is_file():
        raise RuntimeError("转写没有生成字幕")
    from .project import classify

    _, detected = classify(Path(subtitle))
    (output / "result.json").write_text(
        json.dumps({"subtitle": str(Path(subtitle).resolve()), "language": args.language or detected}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
