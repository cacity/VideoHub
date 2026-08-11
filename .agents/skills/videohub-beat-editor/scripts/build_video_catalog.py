#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts"}


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def extract_frame(video: Path, timestamp: float, output: Path) -> None:
    if output.exists():
        return
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.6f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:360:force_original_aspect_ratio=increase,crop=640:360",
            "-q:v",
            "2",
            "-y",
            str(output),
        ],
        check=True,
    )


def normalize(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    low, high = np.percentile(array, [5, 95])
    if high <= low:
        return np.zeros_like(array)
    return np.clip((array - low) / (high - low), 0.0, 1.0)


def metrics(path: Path) -> dict:
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Cannot read frame: {path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    luminance = gray.astype(np.float32)
    histogram = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    return {
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "contrast": float(luminance.std()),
        "saturation": float(hsv[:, :, 1].mean()),
        "brightness": float(luminance.mean()),
        "dark_ratio": float(np.mean(luminance < 10)),
        "bright_ratio": float(np.mean(luminance > 245)),
        "histogram": histogram.flatten().astype(np.float32),
    }


def histogram_distance(left: dict, right: dict) -> float:
    return float(
        cv2.compareHist(
            left["histogram"],
            right["histogram"],
            cv2.HISTCMP_BHATTACHARYYA,
        )
    )


def choose_candidates(rows: list[dict], count: int) -> list[dict]:
    eligible = [
        row
        for row in rows
        if 22 <= row["brightness"] <= 234
        and row["dark_ratio"] <= 0.58
        and row["bright_ratio"] <= 0.38
    ]
    ranked = sorted(eligible, key=lambda row: row["quality_score"], reverse=True)
    chosen: list[dict] = []
    source_counts: dict[str, int] = {}
    while ranked and len(chosen) < count:
        best_index = None
        best_score = -1e9
        for index, row in enumerate(ranked):
            same_source_near = any(
                item["video"] == row["video"]
                and abs(item["time_sec"] - row["time_sec"]) < 8.0
                for item in chosen
            )
            if same_source_near:
                continue
            minimum_distance = min(
                (histogram_distance(row, item) for item in chosen),
                default=1.0,
            )
            source_penalty = 0.025 * source_counts.get(str(row["video"]), 0)
            score = 0.68 * row["quality_score"] + 0.32 * minimum_distance - source_penalty
            if chosen and minimum_distance < 0.10:
                score -= 0.25
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            break
        selected = ranked.pop(best_index)
        chosen.append(selected)
        source_counts[str(selected["video"])] = source_counts.get(str(selected["video"]), 0) + 1

    if len(chosen) < count:
        used = {(str(row["video"]), row["time_sec"]) for row in chosen}
        for row in sorted(rows, key=lambda item: item["quality_score"], reverse=True):
            key = (str(row["video"]), row["time_sec"])
            if key in used:
                continue
            chosen.append(row)
            used.add(key)
            if len(chosen) == count:
                break
    if len(chosen) < count:
        raise RuntimeError(f"Only {len(chosen)} usable candidates for {count} clips")

    sequence = [max(chosen, key=lambda row: row["quality_score"])]
    remaining = [row for row in chosen if row is not sequence[0]]
    while remaining:
        previous = sequence[-1]
        next_row = max(
            remaining,
            key=lambda row: 0.72 * histogram_distance(previous, row)
            + 0.28 * row["quality_score"],
        )
        sequence.append(next_row)
        remaining.remove(next_row)
    return sequence


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path(r"C:\Windows\Fonts\msyh.ttc")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def make_sheets(rows: list[dict], output_dir: Path, prefix: str, page_size: int = 25) -> None:
    columns = 5
    tile_width, tile_height, label_height = 640, 360, 40
    label_font = font(22)
    for page_index in range(math.ceil(len(rows) / page_size)):
        page = rows[page_index * page_size : (page_index + 1) * page_size]
        row_count = math.ceil(len(page) / columns)
        sheet = Image.new("RGB", (columns * tile_width, row_count * (tile_height + label_height)), "#111")
        draw = ImageDraw.Draw(sheet)
        for index, row in enumerate(page):
            x = (index % columns) * tile_width
            y = (index // columns) * (tile_height + label_height)
            sheet.paste(Image.open(row["frame"]).convert("RGB"), (x, y))
            label = f"{row['video'].name} | {row['time_sec']:.1f}s | {row['quality_score']:.3f}"
            draw.rectangle((x, y + tile_height, x + tile_width, y + tile_height + label_height), fill="#111")
            draw.text((x + 8, y + tile_height + 5), label, fill="white", font=label_font)
        suffix = f"_{page_index + 1:02d}" if len(rows) > page_size else ""
        sheet.save(output_dir / f"{prefix}{suffix}.jpg", quality=92)


def gather_videos(explicit: list[Path], directory: Path | None) -> list[Path]:
    videos = [path.resolve() for path in explicit]
    if directory:
        videos.extend(
            path.resolve()
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in videos:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    if not unique:
        raise ValueError("No video inputs were found")
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a quality-ranked video shot catalog.")
    parser.add_argument("--cut-plan", required=True, type=Path)
    parser.add_argument("--video", action="append", default=[], type=Path)
    parser.add_argument("--video-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sample-interval", type=float, default=20.0)
    parser.add_argument("--max-candidates", type=int, default=240)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    job_dir = args.output_dir.resolve()
    outputs = job_dir / "outputs"
    docs = job_dir / "docs"
    frame_dir = job_dir / "work" / "video_catalog" / "frames"
    outputs.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)

    beat_plan = json.loads(args.cut_plan.read_text(encoding="utf-8"))
    clip_count = len(beat_plan["segments"])
    videos = gather_videos(args.video, args.video_dir)
    video_info = [(video, probe_duration(video)) for video in videos]
    per_video_limit = max(clip_count, args.max_candidates // len(videos))

    samples: list[dict] = []
    global_index = 0
    for video_index, (video, duration) in enumerate(video_info, start=1):
        interval = max(args.sample_interval, duration / max(1, per_video_limit))
        times = np.arange(max(1.0, interval / 2.0), max(1.1, duration - 1.0), interval)
        for timestamp in times[:per_video_limit]:
            global_index += 1
            frame = frame_dir / f"v{video_index:02d}_{global_index:04d}_{int(timestamp):06d}ms.jpg"
            samples.append(
                {
                    "video": video,
                    "video_duration": duration,
                    "time_sec": float(timestamp),
                    "frame": frame,
                }
            )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(extract_frame, row["video"], row["time_sec"], row["frame"])
            for row in samples
        ]
        for future in as_completed(futures):
            future.result()

    for row in samples:
        row.update(metrics(row["frame"]))
    sharp = normalize([row["sharpness"] for row in samples])
    contrast = normalize([row["contrast"] for row in samples])
    saturation = normalize([row["saturation"] for row in samples])
    for row, a, b, c in zip(samples, sharp, contrast, saturation):
        exposure = min(1.0, row["dark_ratio"] + row["bright_ratio"])
        row["quality_score"] = float(0.45 * a + 0.25 * b + 0.20 * c + 0.10 * (1 - exposure))

    selected = choose_candidates(samples, clip_count)
    make_sheets(sorted(samples, key=lambda row: row["quality_score"], reverse=True), outputs, "all_candidates")
    make_sheets(selected, outputs, "selected_candidates", page_size=max(25, clip_count))

    with (outputs / "video_catalog.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "video",
            "time_sec",
            "quality_score",
            "sharpness",
            "contrast",
            "saturation",
            "brightness",
            "selected",
            "frame",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        selected_keys = {(str(row["video"]), row["time_sec"]) for row in selected}
        for row in samples:
            writer.writerow(
                {
                    "video": str(row["video"]),
                    "time_sec": f"{row['time_sec']:.6f}",
                    "quality_score": f"{row['quality_score']:.6f}",
                    "sharpness": f"{row['sharpness']:.3f}",
                    "contrast": f"{row['contrast']:.3f}",
                    "saturation": f"{row['saturation']:.3f}",
                    "brightness": f"{row['brightness']:.3f}",
                    "selected": (str(row["video"]), row["time_sec"]) in selected_keys,
                    "frame": str(row["frame"]),
                }
            )

    edit_segments = []
    for beat_segment, candidate in zip(beat_plan["segments"], selected):
        duration = beat_segment["frames"] / beat_plan["fps"]
        source_start = max(
            0.0,
            min(candidate["time_sec"] - duration / 2.0, candidate["video_duration"] - duration),
        )
        edit_segments.append(
            {
                **beat_segment,
                "source": str(candidate["video"]),
                "source_center_sec": round(source_start + duration / 2.0, 6),
                "source_start_sec": round(source_start, 6),
                "focus_x": 0.5,
                "focus_y": 0.5,
                "scene": f"{candidate['video'].stem} @ {candidate['time_sec']:.1f}s",
                "quality_score": round(candidate["quality_score"], 6),
            }
        )
    edit_plan = {
        "schema_version": "1.0",
        "audio": beat_plan["audio"],
        "audio_sha256": beat_plan["audio_sha256"],
        "fps": beat_plan["fps"],
        "duration_sec": beat_plan["duration_sec"],
        "total_frames": beat_plan["total_frames"],
        "segments": edit_segments,
    }
    draft = docs / "edit_plan.draft.json"
    draft.write_text(json.dumps(edit_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Candidates: {len(samples)}")
    print(f"Selected: {len(selected)}")
    print(f"Draft plan: {draft}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
