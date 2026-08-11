#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import librosa
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf


HOP_LENGTH = 256


def run(command: list[str]) -> None:
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {subprocess.list2cmdline(command)}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    low, high = np.percentile(values, [5, 99])
    if high <= low:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def choose_fixed_count_boundaries(
    beat_times: np.ndarray,
    onset_times: np.ndarray,
    onset_strength: np.ndarray,
    total_frames: int,
    clip_count: int,
    fps: float,
) -> list[int]:
    if clip_count < 2:
        return [0, total_frames]
    beat_frames = np.unique(np.clip(np.rint(beat_times * fps).astype(int), 1, total_frames - 1))
    selected = [0]
    average = total_frames / clip_count
    minimum_gap = max(1, int(round(average * 0.45)))
    search_radius = max(2, int(round(average * 0.72)))

    for index in range(1, clip_count):
        target = int(round(total_frames * index / clip_count))
        remaining_cuts = clip_count - index
        minimum = selected[-1] + minimum_gap
        maximum = total_frames - remaining_cuts * minimum_gap
        candidates = beat_frames[
            (beat_frames >= max(minimum, target - search_radius))
            & (beat_frames <= min(maximum, target + search_radius))
        ]
        if not len(candidates):
            chosen = max(minimum, min(target, maximum))
        else:
            times = candidates / fps
            onset_indices = np.searchsorted(onset_times, times)
            onset_indices = np.clip(onset_indices, 0, len(onset_strength) - 1)
            strengths = onset_strength[onset_indices]
            distance = np.abs(candidates - target) / search_radius
            scores = 0.72 * strengths + 0.28 * (1.0 - distance)
            chosen = int(candidates[int(np.argmax(scores))])
        selected.append(chosen)
    selected.append(total_frames)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a frame-exact beat cut plan from audio.")
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--clip-count", type=int)
    parser.add_argument("--beats-per-cut", type=int, default=1)
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()

    audio = args.audio.resolve()
    job_dir = args.output_dir.resolve()
    work_dir = job_dir / "work" / "beat_analysis"
    outputs = job_dir / "outputs"
    docs = job_dir / "docs"
    work_dir.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "audio_mono.wav"

    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(wav_path),
        ]
    )
    y, sample_rate = librosa.load(wav_path, sr=None, mono=True)
    duration = len(y) / sample_rate
    total_frames = int(round(duration * args.fps))
    if total_frames < 2:
        raise ValueError("Audio is too short")

    _, percussive = librosa.effects.hpss(y)
    onset = librosa.onset.onset_strength(
        y=percussive,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
        aggregate=np.median,
    )
    onset = normalize(onset)
    onset_times = librosa.frames_to_time(
        np.arange(len(onset)),
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    tempo, beat_frames = librosa.beat.beat_track(
        y=percussive,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
        trim=False,
    )
    beat_times = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )

    if args.clip_count:
        boundaries = choose_fixed_count_boundaries(
            beat_times,
            onset_times,
            onset,
            total_frames,
            args.clip_count,
            args.fps,
        )
    else:
        stride = max(1, args.beats_per_cut)
        internal = np.rint(beat_times[::stride] * args.fps).astype(int)
        boundaries = [0, *sorted(set(int(v) for v in internal if 0 < v < total_frames)), total_frames]

    segments = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        segments.append(
            {
                "index": index,
                "frames": end - start,
                "output_start_frame": start,
                "output_end_frame": end,
                "output_start_sec": round(start / args.fps, 6),
                "output_end_sec": round(end / args.fps, 6),
                "duration_sec": round((end - start) / args.fps, 6),
            }
        )

    tempo_value = float(np.atleast_1d(tempo)[0])
    plan = {
        "schema_version": "1.0",
        "audio": str(audio),
        "audio_sha256": sha256(audio),
        "analysis_audio": str(wav_path),
        "sample_rate": sample_rate,
        "fps": args.fps,
        "duration_sec": round(total_frames / args.fps, 6),
        "source_duration_sec": round(duration, 6),
        "total_frames": total_frames,
        "estimated_tempo_bpm": round(tempo_value, 3),
        "clip_count": len(segments),
        "cut_frames": boundaries[1:-1],
        "cut_times_sec": [round(frame / args.fps, 6) for frame in boundaries[1:-1]],
        "segments": segments,
    }
    plan_path = outputs / "beat_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (outputs / "cut_plan.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(segments[0].keys()))
        writer.writeheader()
        writer.writerows(segments)

    cut_times = np.asarray(plan["cut_times_sec"], dtype=float)
    clicks = librosa.clicks(
        times=cut_times,
        sr=sample_rate,
        click_freq=1700.0,
        click_duration=0.05,
        length=len(y),
    )
    preview = np.clip(0.70 * y + 0.58 * clicks, -1.0, 1.0)
    sf.write(outputs / "beat_click_preview.wav", preview, sample_rate, subtype="PCM_16")

    figure, axis = plt.subplots(figsize=(15, 4))
    axis.plot(onset_times, onset, color="#138a86", linewidth=0.8)
    for beat in beat_times:
        axis.axvline(float(beat), color="#e1aa2b", alpha=0.18, linewidth=0.7)
    for cut in cut_times:
        axis.axvline(float(cut), color="#df3f4f", linewidth=1.3)
    axis.set_xlim(0, duration)
    axis.set_xlabel("Time (seconds)")
    axis.set_ylabel("Onset strength")
    axis.grid(alpha=0.15)
    figure.tight_layout()
    figure.savefig(outputs / "beat_timeline.png", dpi=160)
    plt.close(figure)

    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
