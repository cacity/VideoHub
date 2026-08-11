#!/usr/bin/env python3
"""Audit a completed episodic film-commentary project and delivery package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

COVER_SPECS = {
    "cover_9x16.jpg": (1080, 1920),
    "cover_3x4.jpg": (1080, 1440),
    "cover_4x3.jpg": (1440, 1080),
    "cover_16x9.jpg": (1920, 1080),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--expected-duration", type=float, required=True)
    parser.add_argument("--duration-tolerance", type=float, default=0.08)
    parser.add_argument("--expected-width", type=int, default=1920)
    parser.add_argument("--expected-height", type=int, default=1080)
    parser.add_argument(
        "--cover-dir",
        type=Path,
        help="Cover directory, relative to the package unless absolute.",
    )
    parser.add_argument(
        "--expected-cover",
        action="append",
        choices=sorted(COVER_SPECS),
        help="Cover filename to require. Repeat as needed; defaults to all formats.",
    )
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--full-decode", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def resolve_under(project: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def probe(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    return run_json([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(path),
    ])


def audit_checksums(package: Path) -> tuple[bool, list[str]]:
    checksum_file = package / "SHA256SUMS.txt"
    if not checksum_file.is_file():
        return False, ["missing SHA256SUMS.txt"]
    errors: list[str] = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            errors.append(f"invalid checksum line: {line}")
            continue
        target = package / Path(relative)
        if not target.is_file():
            errors.append(f"missing: {relative}")
        elif sha256(target).lower() != expected.lower():
            errors.append(f"hash mismatch: {relative}")
    return not errors, errors


def manifest_video_path(package: Path, manifest: dict[str, Any]) -> Path | None:
    video_file = str(manifest.get("video_file") or "").strip()
    if video_file:
        return package / video_file
    for item in manifest.get("assets", []):
        name = str(item.get("name") or "")
        if name.lower().endswith(".mp4"):
            return package / name
    return None


def main() -> int:
    args = parse_args()
    project = args.project_dir.resolve()
    video = resolve_under(project, args.video)
    package = resolve_under(project, args.package)
    coverage_report = resolve_under(project, args.coverage_report)
    json_out = resolve_under(project, args.json_out)
    checks: list[dict[str, Any]] = []

    add_check(checks, "project_exists", project.is_dir(), str(project))
    add_check(checks, "video_exists", bool(video and video.is_file()), str(video))
    if not video or not video.is_file():
        report = {"status": "FAIL", "checks": checks}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    media = probe(video, args.ffprobe)
    streams = media.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float(media["format"]["duration"])
    add_check(
        checks,
        "duration",
        abs(duration - args.expected_duration) <= args.duration_tolerance,
        {"actual": duration, "expected": args.expected_duration, "tolerance": args.duration_tolerance},
    )
    add_check(checks, "video_stream", video_stream.get("codec_name") == "h264", video_stream)
    add_check(checks, "audio_stream", audio_stream.get("codec_name") == "aac", audio_stream)
    add_check(
        checks,
        "resolution",
        (video_stream.get("width"), video_stream.get("height"))
        == (args.expected_width, args.expected_height),
        {
            "actual": [video_stream.get("width"), video_stream.get("height")],
            "expected": [args.expected_width, args.expected_height],
        },
    )

    if coverage_report:
        if coverage_report.is_file():
            coverage = json.loads(coverage_report.read_text(encoding="utf-8"))
            passed = coverage.get("status") == "PASS" and coverage.get("missing_count") == 0
            add_check(
                checks,
                "source_dialogue_coverage",
                passed,
                {"status": coverage.get("status"), "missing_count": coverage.get("missing_count")},
            )
        else:
            add_check(checks, "source_dialogue_coverage", False, f"missing: {coverage_report}")

    video_hash = sha256(video)
    if package:
        add_check(checks, "package_exists", package.is_dir(), str(package))
        if package.is_dir():
            manifest_path = package / "publish_manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                package_video = manifest_video_path(package, manifest)
                package_hash = sha256(package_video) if package_video and package_video.is_file() else None
                add_check(
                    checks,
                    "package_video_hash",
                    package_hash == video_hash,
                    {"official": video_hash, "package": package_hash},
                )
            else:
                add_check(checks, "package_manifest", False, f"missing: {manifest_path}")

            cover_root = resolve_under(package, args.cover_dir)
            if cover_root is None:
                nested = package / "cover_assets"
                cover_root = nested if nested.is_dir() else package
            expected_covers = args.expected_cover or sorted(COVER_SPECS)
            for name in expected_covers:
                expected = COVER_SPECS[name]
                cover = cover_root / name
                if not cover.is_file():
                    add_check(checks, f"cover_{name}", False, "missing")
                    continue
                cover_probe = probe(cover, args.ffprobe)
                cover_stream = next(
                    (s for s in cover_probe.get("streams", []) if s.get("codec_type") == "video"), {}
                )
                actual = (cover_stream.get("width"), cover_stream.get("height"))
                add_check(checks, f"cover_{name}", actual == expected, {"actual": actual, "expected": expected})

            checksums_pass, checksum_errors = audit_checksums(package)
            add_check(checks, "package_checksums", checksums_pass, checksum_errors or "all matched")

    if args.full_decode:
        result = subprocess.run(
            [
                args.ffmpeg, "-v", "error", "-xerror", "-i", str(video),
                "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        add_check(
            checks,
            "full_decode",
            result.returncode == 0,
            result.stderr.decode("utf-8", errors="replace")[-2000:] or "clean",
        )

    status = "PASS" if all(item["passed"] for item in checks) else "FAIL"
    report = {
        "schema_version": "1.0",
        "status": status,
        "project": str(project),
        "video": str(video),
        "video_sha256": video_hash,
        "checks": checks,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
