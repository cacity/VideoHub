#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np


RATIOS = {
    "16:9": (1920, 1080),
    "3:4": (1080, 1440),
    "4:3": (1440, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


def run(command: list[str], log: Path, cwd: Path | None = None) -> None:
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {subprocess.list2cmdline(command)}\n")
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {subprocess.list2cmdline(command)}")


def encoder_args(quality: int) -> list[str]:
    encoders = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if "h264_nvenc" in encoders:
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p5",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            str(quality),
            "-b:v",
            "0",
        ]
    return ["-c:v", "libx264", "-preset", "slow", "-crf", str(quality)]


def safe_ratio_name(ratio: str) -> str:
    return ratio.replace(":", "x")


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def full_decode(path: Path, log: Path) -> bool:
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    return result.returncode == 0


def cut_differences(path: Path, boundaries: list[int]) -> list[float]:
    capture = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(cv2.resize(frame, (256, 144)).astype(np.float32))
    capture.release()
    values = []
    for boundary in boundaries:
        if not 0 < boundary < len(frames):
            values.append(0.0)
            continue
        values.append(float(np.mean(np.abs(frames[boundary] - frames[boundary - 1]))))
    return values


def validate_plan(plan: dict) -> None:
    segments = plan.get("segments") or []
    if not segments:
        raise ValueError("Plan has no segments")
    if sum(int(item["frames"]) for item in segments) != int(plan["total_frames"]):
        raise ValueError("Segment frame sum does not match total_frames")
    expected = 0
    for index, item in enumerate(segments, start=1):
        if int(item["index"]) != index:
            raise ValueError("Segment indices must be continuous")
        if int(item["output_start_frame"]) != expected:
            raise ValueError(f"Segment {index} output_start_frame is not continuous")
        expected += int(item["frames"])
        if int(item["output_end_frame"]) != expected:
            raise ValueError(f"Segment {index} output_end_frame is invalid")
        if not Path(item["source"]).exists():
            raise FileNotFoundError(item["source"])


def render_ratio(
    plan: dict,
    job_dir: Path,
    output_dir: Path,
    ratio: str,
    subtitle: Path | None,
    name: str,
) -> Path:
    width, height = RATIOS[ratio]
    ratio_name = safe_ratio_name(ratio)
    work = job_dir / "work" / "beat_render" / ratio_name
    segment_dir = work / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log = job_dir / "logs" / f"render_{ratio_name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    segment_encoder = encoder_args(18)
    concat_lines: list[str] = []

    for item in plan["segments"]:
        source = Path(item["source"])
        duration = int(item["frames"]) / float(plan["fps"])
        start = float(item.get("source_start_sec", float(item["source_center_sec"]) - duration / 2))
        focus_x = min(1.0, max(0.0, float(item.get("focus_x", 0.5))))
        focus_y = min(1.0, max(0.0, float(item.get("focus_y", 0.5))))
        segment = segment_dir / f"segment_{int(item['index']):03d}.mp4"
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height}:(in_w-out_w)*{focus_x:.5f}:(in_h-out_h)*{focus_y:.5f},"
            f"fps={plan['fps']},format=yuv420p"
        )
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-ss",
                f"{start:.6f}",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                video_filter,
                "-frames:v",
                str(item["frames"]),
                *segment_encoder,
                "-g",
                "300",
                "-bf",
                "2",
                "-y",
                str(segment),
            ],
            log,
        )
        concat_lines.append(f"file '{segment.as_posix()}'")

    concat_file = work / "segments.txt"
    visual_master = work / "visual_master.mp4"
    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-y",
            str(visual_master),
        ],
        log,
    )

    output = output_dir / f"{name}_{ratio_name}.mp4"
    duration = int(plan["total_frames"]) / float(plan["fps"])
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(visual_master),
        "-i",
        str(plan["audio"]),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    if subtitle:
        overlay = work / f"overlay{subtitle.suffix.lower()}"
        shutil.copy2(subtitle, overlay)
        relative_overlay = overlay.relative_to(job_dir).as_posix()
        command.extend(["-vf", f"subtitles={relative_overlay}", *encoder_args(17)])
    else:
        command.extend(["-c:v", "copy"])
    command.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{duration:.6f}",
            "-movflags",
            "+faststart",
            "-y",
            str(output),
        ]
    )
    run(command, log, cwd=job_dir)
    return output


def write_qa(plan: dict, output: Path, ratio: str, job_dir: Path) -> bool:
    info = probe(output)
    video = next(row for row in info["streams"] if row["codec_type"] == "video")
    audio = next(row for row in info["streams"] if row["codec_type"] == "audio")
    expected_width, expected_height = RATIOS[ratio]
    expected_duration = int(plan["total_frames"]) / float(plan["fps"])
    duration = float(info["format"]["duration"])
    frame_count = int(video.get("nb_read_frames") or 0)
    decode_log = job_dir / "logs" / f"decode_{safe_ratio_name(ratio)}.log"
    decode_ok = full_decode(output, decode_log)
    boundaries = [int(item["output_end_frame"]) for item in plan["segments"][:-1]]
    differences = cut_differences(output, boundaries)
    checks = {
        "duration": abs(duration - expected_duration) <= 1.0 / float(plan["fps"]) + 0.005,
        "frames": frame_count == int(plan["total_frames"]),
        "resolution": (int(video["width"]), int(video["height"])) == (expected_width, expected_height),
        "video_codec": video["codec_name"] == "h264",
        "audio_codec": audio["codec_name"] == "aac",
        "decode": decode_ok,
        "cuts": all(value >= 8.0 for value in differences),
    }
    report = {
        "output": str(output),
        "ratio": ratio,
        "duration_sec": duration,
        "expected_duration_sec": expected_duration,
        "frame_count": frame_count,
        "expected_frames": int(plan["total_frames"]),
        "cut_pixel_differences": [round(value, 3) for value in differences],
        "checks": checks,
        "overall": "PASS" if all(checks.values()) else "REVIEW",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    qa_json = output.with_suffix(".qa.json")
    qa_md = output.with_suffix(".qa.md")
    qa_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = [
        f"# QA: {output.name}",
        "",
        f"**{report['overall']}**",
        "",
        f"- Ratio: `{ratio}`",
        f"- Duration: `{duration:.6f}` / `{expected_duration:.6f}` sec",
        f"- Frames: `{frame_count}` / `{plan['total_frames']}`",
        f"- Resolution: `{video['width']}x{video['height']}`",
        f"- Full decode: `{'PASS' if decode_ok else 'FAIL'}`",
        f"- Cut checks: `{sum(value >= 8.0 for value in differences)}/{len(differences)}`",
        "",
    ]
    for key, value in checks.items():
        markdown.append(f"- [{'x' if value else ' '}] {key}")
    qa_md.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return all(checks.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Render one beat plan into multiple aspect ratios.")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ratio", action="append", choices=RATIOS, default=[])
    parser.add_argument("--subtitle", type=Path)
    parser.add_argument("--name", default="beat_edit")
    args = parser.parse_args()

    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    job_dir = plan_path.parent.parent
    ratios = args.ratio or ["16:9"]
    subtitle = args.subtitle.resolve() if args.subtitle else None
    results = []
    all_pass = True
    for ratio in ratios:
        output = render_ratio(plan, job_dir, args.output_dir.resolve(), ratio, subtitle, args.name)
        passed = write_qa(plan, output, ratio, job_dir)
        results.append({"ratio": ratio, "output": str(output), "qa": "PASS" if passed else "REVIEW"})
        all_pass = all_pass and passed
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
