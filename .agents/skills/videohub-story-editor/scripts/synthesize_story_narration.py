#!/usr/bin/env python3
"""Synthesize an aligned MiniMax or Doubao narration track for a story edit."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from story_pipeline_common import (
    find_repo_root,
    probe_media,
    read_json,
    resolve_executable,
    run_command,
    safe_slug,
    write_json,
    write_srt,
)
from validate_narration_plan import validate_narration_plan


def _provider_identity(provider: str, tts: dict[str, Any], text: str) -> str:
    if provider == "minimax":
        settings = (
            tts.get("model", "speech-2.8-turbo"),
            tts.get("voice_id", "female-shaonv"),
            float(tts.get("speed", 1.0)),
            tts.get("language_boost", "Chinese"),
        )
    else:
        settings = (
            tts.get("voice_type", "BV701_streaming"),
            float(tts.get("speed", 1.0)),
            float(tts.get("volume", 1.0)),
            float(tts.get("pitch", 1.0)),
            int(tts.get("sample_rate", 24000)),
        )
    value = "|".join([provider, *(str(item) for item in settings), text])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_client(provider: str, tts: dict[str, Any]) -> Any:
    repo_root = find_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from dotenv import load_dotenv

        load_dotenv(repo_root / ".env", override=False)
    except ImportError:
        pass
    if provider == "minimax":
        from src.minimax_tts_client import MiniMaxTTSClient

        return MiniMaxTTSClient(
            model=str(tts.get("model", "speech-2.8-turbo")),
            voice_id=str(tts.get("voice_id", "female-shaonv")),
            speed=float(tts.get("speed", 1.0)),
            language_boost=str(tts.get("language_boost", "Chinese")),
        )
    if provider == "doubao":
        from src.doubao_tts_client import DoubaoTTSClient

        return DoubaoTTSClient(
            voice_type=str(tts.get("voice_type", "BV701_streaming")),
            speed=float(tts.get("speed", 1.0)),
            volume=float(tts.get("volume", 1.0)),
            pitch=float(tts.get("pitch", 1.0)),
            sample_rate=int(tts.get("sample_rate", 24000)),
        )
    raise ValueError(f"unsupported TTS provider: {provider}")


def _normalize_clip(
    *,
    ffmpeg: str,
    source: Path,
    output: Path,
    speedup: float,
    max_duration: float,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-af",
            (
                "aresample=48000,"
                "aformat=sample_fmts=s16:channel_layouts=stereo,"
                f"atempo={speedup:.8f}"
            ),
            "-t",
            f"{max_duration:.6f}",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(output),
        ]
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"normalized narration clip is missing: {output}")


def _mix_aligned_track(
    *,
    ffmpeg: str,
    clips: list[tuple[Path, float]],
    duration: float,
    output: Path,
) -> None:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.6f}",
        "-i",
        "anullsrc=r=48000:cl=stereo",
    ]
    for path, _start in clips:
        command.extend(["-i", str(path)])

    filters: list[str] = []
    labels = ["[0:a]"]
    for index, (_path, start) in enumerate(clips, start=1):
        delay_ms = max(0, int(round(start * 1000)))
        label = f"narration{index}"
        filters.append(f"[{index}:a]adelay={delay_ms}:all=1[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[out]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-t",
            f"{duration:.6f}",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-y",
            str(output),
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"narration track is missing or empty: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("narration", type=Path)
    parser.add_argument("--story-plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--provider", choices=("minimax", "doubao"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--subtitle-output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    args = parser.parse_args()

    try:
        narration_path = args.narration.expanduser().resolve()
        narration = read_json(narration_path)
        story_plan = read_json(args.story_plan.expanduser().resolve())
        evidence = read_json(args.evidence.expanduser().resolve())
        analysis = read_json(args.analysis.expanduser().resolve())
        if args.provider:
            narration.setdefault("tts", {})["provider"] = args.provider
        errors, warnings = validate_narration_plan(
            narration,
            story_plan,
            evidence,
            analysis,
        )
        for warning in warnings:
            print(f"WARNING: {warning}")
        if errors:
            raise ValueError("narration plan is invalid: " + "; ".join(errors[:10]))

        provider = str(narration["tts"]["provider"])
        output = (
            args.output.expanduser().resolve()
            if args.output
            else narration_path.parent / f"narration_audio_{provider}.wav"
        )
        subtitle_output = (
            args.subtitle_output.expanduser().resolve()
            if args.subtitle_output
            else narration_path.parent / f"narration_{provider}.srt"
        )
        manifest = (
            args.manifest.expanduser().resolve()
            if args.manifest
            else narration_path.parent / f"narration_audio_{provider}.json"
        )
        ffmpeg = resolve_executable("ffmpeg", args.ffmpeg)
        ffprobe = resolve_executable("ffprobe", args.ffprobe)
        client = _create_client(provider, narration["tts"])
        story_duration = float(story_plan["segments"][-1]["output_end_sec"])
        max_speedup = float(narration["settings"].get("max_audio_speedup", 1.25))
        original_audio_volume = float(
            narration["settings"].get("original_audio_volume", 0.3)
        )
        cache_dir = narration_path.parent / ".narration_cache" / provider
        normalized_dir = cache_dir / "normalized"
        cache_dir.mkdir(parents=True, exist_ok=True)

        aligned_clips: list[tuple[Path, float]] = []
        subtitle_cues: list[dict[str, Any]] = []
        manifest_blocks: list[dict[str, Any]] = []
        cache_hits = 0
        for index, block in enumerate(narration["blocks"], start=1):
            text = str(block["text"]).strip()
            identity = _provider_identity(provider, narration["tts"], text)
            raw_path = cache_dir / f"{identity}.wav"
            cache_hit = raw_path.is_file() and raw_path.stat().st_size > 0
            if cache_hit:
                cache_hits += 1
            else:
                print(f"Synthesizing narration {index}/{len(narration['blocks'])}: {block['id']}")
                client.synthesize(text, raw_path)

            raw_duration = float(probe_media(raw_path, ffprobe)["duration_sec"])
            slot_duration = float(block["end_sec"]) - float(block["start_sec"])
            speedup = max(1.0, raw_duration / slot_duration)
            if speedup > max_speedup + 0.001:
                raise ValueError(
                    f"{block['id']} TTS duration {raw_duration:.2f}s exceeds its "
                    f"{slot_duration:.2f}s slot and requires {speedup:.2f}x speed; "
                    f"rewrite the narration or raise max_audio_speedup"
                )
            normalized_path = normalized_dir / f"{safe_slug(str(block['id']))}_{identity[:12]}.wav"
            _normalize_clip(
                ffmpeg=ffmpeg,
                source=raw_path,
                output=normalized_path,
                speedup=speedup,
                max_duration=slot_duration,
            )
            actual_duration = min(
                slot_duration,
                float(probe_media(normalized_path, ffprobe)["duration_sec"]),
            )
            aligned_clips.append((normalized_path, float(block["start_sec"])))
            subtitle_cues.append(
                {
                    "start_sec": float(block["start_sec"]),
                    "end_sec": float(block["start_sec"]) + actual_duration,
                    "target_text": str(block.get("subtitle_text") or text),
                }
            )
            manifest_blocks.append(
                {
                    "id": block["id"],
                    "cache_hit": cache_hit,
                    "raw_audio_path": raw_path.as_posix(),
                    "normalized_audio_path": normalized_path.as_posix(),
                    "slot_start_sec": float(block["start_sec"]),
                    "slot_end_sec": float(block["end_sec"]),
                    "raw_duration_sec": raw_duration,
                    "final_duration_sec": actual_duration,
                    "audio_speedup": round(speedup, 6),
                    "evidence_refs": block["evidence_refs"],
                }
            )

        _mix_aligned_track(
            ffmpeg=ffmpeg,
            clips=aligned_clips,
            duration=story_duration,
            output=output,
        )
        written = write_srt(subtitle_output, subtitle_cues, "target_text")
        write_json(
            manifest,
            {
                "schema_version": "1.0",
                "job_id": narration["job_id"],
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "provider": provider,
                "voice": narration["tts"].get("voice_id")
                or narration["tts"].get("voice_type"),
                "original_audio_volume": original_audio_volume,
                "audio_strategy": narration["settings"].get(
                    "audio_strategy", "narration_only"
                ),
                "source_audio_volume": narration["settings"].get(
                    "source_audio_volume", 1.0
                ),
                "source_audio_windows": narration.get("source_audio_windows", []),
                "narration_audio_path": output.as_posix(),
                "narration_subtitle_path": subtitle_output.as_posix(),
                "duration_sec": story_duration,
                "block_count": len(manifest_blocks),
                "subtitle_cue_count": written,
                "cache_hits": cache_hits,
                "blocks": manifest_blocks,
            },
        )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Narration audio: {output}")
    print(f"Narration subtitles: {subtitle_output}")
    print(f"Narration manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
