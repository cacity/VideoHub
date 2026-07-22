#!/usr/bin/env python3
"""Build a verified Douyin publishing folder from a completed story video."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from story_pipeline_common import (
    find_repo_root,
    probe_media,
    resolve_executable,
    run_command,
    safe_slug,
    write_json,
)

MIN_CAPTION_CHARS = 50
MAX_CAPTION_CHARS = 100
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


def normalize_caption(value: str) -> str:
    """Collapse line breaks and repeated whitespace into one publishable paragraph."""
    return re.sub(r"\s+", " ", value or "").strip()


def count_caption_chars(value: str) -> int:
    """Count visible caption characters while ignoring whitespace."""
    return len(re.sub(r"\s+", "", value or ""))


def validate_caption(value: str) -> tuple[str, int]:
    caption = normalize_caption(value)
    length = count_caption_chars(caption)
    if not caption:
        raise ValueError("抖音文案不能为空")
    if not MIN_CAPTION_CHARS <= length <= MAX_CAPTION_CHARS:
        raise ValueError(
            f"抖音文案需为 {MIN_CAPTION_CHARS}-{MAX_CAPTION_CHARS} 个可见字符，"
            f"当前为 {length} 个"
        )
    if not CJK_PATTERN.search(caption):
        raise ValueError("抖音文案必须包含中文内容")
    return caption, length


def normalize_hashtags(values: list[str]) -> list[str]:
    hashtags: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in re.split(r"[,，\s]+", value or ""):
            tag = item.strip().lstrip("#")
            if not tag:
                continue
            normalized = f"#{tag}"
            if normalized not in seen:
                seen.add(normalized)
                hashtags.append(normalized)
    return hashtags


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_qa_passed(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"QA report not found: {path}")
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    if not re.search(
        r"(?:Result|结果)\s*[:：]\s*\*{0,2}PASS\*{0,2}",
        content,
        re.IGNORECASE,
    ):
        raise ValueError(f"QA report does not contain a PASS result: {path}")


def transfer_video(
    *,
    source: Path,
    target: Path,
    source_media: dict,
    ffmpeg: str,
    force_copy: bool,
    force_transcode: bool,
) -> str:
    video_codec = str(source_media.get("video", {}).get("codec") or "").lower()
    audio = source_media.get("audio", {})
    audio_codec = str(audio.get("codec") or "").lower()
    needs_transcode = (
        force_transcode
        or source.suffix.lower() != ".mp4"
        or video_codec != "h264"
        or not audio.get("present")
        or audio_codec != "aac"
    )

    if target.exists():
        target.unlink()

    if needs_transcode:
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-y",
                str(target),
            ]
        )
        return "transcode"

    if not force_copy:
        try:
            os.link(source, target)
            return "hardlink"
        except OSError:
            pass
    shutil.copy2(source, target)
    return "copy"


def extract_cover(*, video: Path, output: Path, timestamp: float, ffmpeg: str) -> None:
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(output),
        ]
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"封面候选图生成失败: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="已通过 QA 的最终成片")
    parser.add_argument("--title", required=True, help="发布标题和文件夹名称")
    caption_group = parser.add_mutually_exclusive_group(required=True)
    caption_group.add_argument("--caption", help="50-100 字中文发布文案")
    caption_group.add_argument("--caption-file", type=Path, help="UTF-8 文案文件")
    parser.add_argument("--hashtag", action="append", default=[], help="可重复填写")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--qa-report", type=Path)
    parser.add_argument("--package-name", default="")
    parser.add_argument("--video-name", default="")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cover-time", type=float)
    parser.add_argument("--copy", action="store_true", help="禁用硬链接并复制视频")
    parser.add_argument("--transcode", action="store_true", help="强制转为 H.264/AAC MP4")
    parser.add_argument("--force", action="store_true", help="覆盖同名发布包文件")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.video.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")
    title = args.title.strip()
    if not title:
        raise ValueError("抖音发布标题不能为空")

    caption_value = args.caption
    if args.caption_file:
        caption_path = args.caption_file.expanduser().resolve()
        if not caption_path.is_file():
            raise FileNotFoundError(f"Caption file not found: {caption_path}")
        caption_value = caption_path.read_text(encoding="utf-8-sig")
    caption, caption_length = validate_caption(caption_value or "")
    hashtags = normalize_hashtags(args.hashtag)

    qa_report = args.qa_report.expanduser().resolve() if args.qa_report else None
    if qa_report:
        ensure_qa_passed(qa_report)

    repo_root = find_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from src.paths_config import DOUYIN_PUBLISH_PACKAGES_DIR

    package_slug = safe_slug(args.package_name or title, fallback=source.stem)
    package_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else Path(DOUYIN_PUBLISH_PACKAGES_DIR) / package_slug
    )
    package_dir.mkdir(parents=True, exist_ok=True)

    video_slug = safe_slug(args.video_name or title, fallback=source.stem)
    output_video = package_dir / f"{video_slug}_douyin.mp4"
    output_caption = package_dir / "caption.txt"
    output_hashtags = package_dir / "hashtags.txt"
    output_notes = package_dir / "publish_notes.md"
    output_manifest = package_dir / "publish_manifest.json"
    output_cover = package_dir / "cover.jpg"
    managed_outputs = [
        output_video,
        output_caption,
        output_hashtags,
        output_notes,
        output_manifest,
    ]
    if args.cover_time is not None:
        managed_outputs.append(output_cover)
    existing = [path.name for path in managed_outputs if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            f"发布包已存在这些文件，请使用 --force 覆盖: {', '.join(existing)}"
        )

    ffprobe = resolve_executable("ffprobe", args.ffprobe)
    ffmpeg = resolve_executable("ffmpeg", args.ffmpeg)
    source_media = probe_media(source, ffprobe)
    transfer_mode = transfer_video(
        source=source,
        target=output_video,
        source_media=source_media,
        ffmpeg=ffmpeg,
        force_copy=args.copy,
        force_transcode=args.transcode,
    )
    packaged_media = probe_media(output_video, ffprobe)
    if packaged_media["video"].get("codec") != "h264":
        raise RuntimeError("发布视频不是 H.264 编码")
    if not packaged_media["audio"].get("present"):
        raise RuntimeError("发布视频缺少音轨")
    if packaged_media["audio"].get("codec") != "aac":
        raise RuntimeError("发布视频音轨不是 AAC 编码")

    cover_file = None
    if args.cover_time is not None:
        if not 0 <= args.cover_time < packaged_media["duration_sec"]:
            raise ValueError(
                f"封面时间必须位于 0-{packaged_media['duration_sec']:.3f} 秒之间"
            )
        extract_cover(
            video=output_video,
            output=output_cover,
            timestamp=args.cover_time,
            ffmpeg=ffmpeg,
        )
        cover_file = output_cover.name

    output_caption.write_text(caption + "\n", encoding="utf-8", newline="\n")
    output_hashtags.write_text(
        (" ".join(hashtags) + "\n") if hashtags else "",
        encoding="utf-8",
        newline="\n",
    )
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest = {
        "schema_version": "1.0",
        "platform": "douyin",
        "generated_at": generated_at,
        "title": title,
        "caption": caption,
        "caption_visible_chars": caption_length,
        "hashtags": hashtags,
        "source_url": args.source_url.strip(),
        "source_video": str(source),
        "qa_report": str(qa_report) if qa_report else "",
        "video_file": output_video.name,
        "cover_file": cover_file,
        "transfer_mode": transfer_mode,
        "sha256": sha256_file(output_video),
        "media": packaged_media,
    }
    write_json(output_manifest, manifest)

    notes = [
        "# 抖音发布包",
        "",
        f"- 标题：{title}",
        f"- 视频：`{output_video.name}`",
        f"- 文案：`{output_caption.name}`（{caption_length} 个可见字符）",
        f"- 话题：`{output_hashtags.name}`",
        f"- 封面：`{cover_file or '未生成'}`",
        f"- 时长：{packaged_media['duration_sec']:.3f} 秒",
        (
            f"- 分辨率：{packaged_media['video'].get('width')}x"
            f"{packaged_media['video'].get('height')}"
        ),
        "- 编码：H.264/AAC MP4",
        f"- 来源：{args.source_url.strip() or '未填写'}",
        "",
        "发布前请人工复核标题、字幕、文案、封面、版权授权和平台规则。",
        "",
    ]
    output_notes.write_text("\n".join(notes), encoding="utf-8", newline="\n")

    print(f"Douyin package: {package_dir}")
    print(f"Video: {output_video}")
    print(f"Caption: {output_caption} ({caption_length} chars)")
    print(f"Manifest: {output_manifest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
