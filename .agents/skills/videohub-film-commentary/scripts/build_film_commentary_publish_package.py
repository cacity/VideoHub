#!/usr/bin/env python3
"""Build a complete Douyin publishing package for a film-commentary video."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SKILLS_DIR = Path(__file__).resolve().parents[2]
STORY_SCRIPTS = SKILLS_DIR / "videohub-story-editor" / "scripts"
if str(STORY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STORY_SCRIPTS))

from build_douyin_publish_package import (  # noqa: E402
    ensure_qa_passed,
    extract_cover,
    normalize_hashtags,
    sha256_file,
    transfer_video,
    validate_caption,
)
from story_pipeline_common import (  # noqa: E402
    find_repo_root,
    probe_media,
    read_json,
    resolve_executable,
    safe_slug,
    write_json,
)

TITLE_MIN_CHARS = 8
TITLE_MAX_CHARS = 38
MIN_TITLE_CANDIDATES = 3
MAX_TITLE_CANDIDATES = 5
COVER_WIDTH = 1080
COVER_HEIGHT = 1920
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


def visible_chars(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def _required_text(value: Any, label: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    return text


def _bounded_text(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int,
) -> str:
    text = _required_text(value, label)
    length = visible_chars(text)
    if not minimum <= length <= maximum:
        raise ValueError(f"{label}需为 {minimum}-{maximum} 个可见字符，当前为 {length} 个")
    return text


def validate_publish_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("发布计划必须是 JSON 对象")
    if value.get("schema_version") != "1.0":
        raise ValueError("schema_version 必须为 1.0")
    if value.get("platform") != "douyin":
        raise ValueError("platform 必须为 douyin")

    candidates = value.get("title_candidates")
    if not isinstance(candidates, list) or not MIN_TITLE_CANDIDATES <= len(candidates) <= MAX_TITLE_CANDIDATES:
        raise ValueError(
            f"title_candidates 必须包含 {MIN_TITLE_CANDIDATES}-{MAX_TITLE_CANDIDATES} 个候选"
        )

    normalized_candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise ValueError(f"title_candidates[{index}] 必须是对象")
        title = _bounded_text(
            candidate.get("title"),
            f"title_candidates[{index}].title",
            minimum=TITLE_MIN_CHARS,
            maximum=TITLE_MAX_CHARS,
        )
        if not CJK_PATTERN.search(title):
            raise ValueError(f"title_candidates[{index}].title 必须包含中文")
        if title in seen_titles:
            raise ValueError(f"标题候选重复: {title}")
        seen_titles.add(title)
        angle = _bounded_text(
            candidate.get("angle"),
            f"title_candidates[{index}].angle",
            maximum=30,
        )
        refs = candidate.get("evidence_refs")
        if not isinstance(refs, list) or not [ref for ref in refs if str(ref).strip()]:
            raise ValueError(f"title_candidates[{index}].evidence_refs 不能为空")
        normalized_candidates.append(
            {
                "title": title,
                "angle": angle,
                "evidence_refs": [str(ref).strip() for ref in refs if str(ref).strip()],
            }
        )

    selected_title = _required_text(value.get("selected_title"), "selected_title")
    if selected_title not in seen_titles:
        raise ValueError("selected_title 必须与一个标题候选完全一致")

    caption, caption_chars = validate_caption(str(value.get("caption") or ""))
    hashtags = normalize_hashtags(
        [str(item) for item in value.get("hashtags", [])]
        if isinstance(value.get("hashtags"), list)
        else []
    )
    if not 3 <= len(hashtags) <= 8:
        raise ValueError(f"hashtags 必须包含 3-8 个去重话题，当前为 {len(hashtags)} 个")

    cover = value.get("cover")
    if not isinstance(cover, dict):
        raise ValueError("cover 必须是对象")
    timestamp = cover.get("timestamp_sec")
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool) or timestamp < 0:
        raise ValueError("cover.timestamp_sec 必须为非负数字")
    layout = str(cover.get("layout") or "top").strip().lower()
    if layout not in {"top", "bottom"}:
        raise ValueError("cover.layout 必须为 top 或 bottom")
    focus_x = cover.get("focus_x", 0.5)
    focus_y = cover.get("focus_y", 0.5)
    for label, coordinate in (("focus_x", focus_x), ("focus_y", focus_y)):
        if not isinstance(coordinate, (int, float)) or isinstance(coordinate, bool) or not 0 <= coordinate <= 1:
            raise ValueError(f"cover.{label} 必须位于 0-1")

    normalized_cover = {
        "timestamp_sec": float(timestamp),
        "focus_x": float(focus_x),
        "focus_y": float(focus_y),
        "layout": layout,
        "kicker": _bounded_text(cover.get("kicker"), "cover.kicker", maximum=12),
        "headline": _bounded_text(
            cover.get("headline"),
            "cover.headline",
            minimum=4,
            maximum=20,
        ),
        "subheadline": _bounded_text(
            cover.get("subheadline"),
            "cover.subheadline",
            maximum=28,
        ),
        "episode_label": _bounded_text(
            cover.get("episode_label"),
            "cover.episode_label",
            maximum=24,
        ),
    }
    if not CJK_PATTERN.search(normalized_cover["headline"] + normalized_cover["subheadline"]):
        raise ValueError("封面主副标题必须包含中文")

    return {
        "schema_version": "1.0",
        "platform": "douyin",
        "package_name": str(value.get("package_name") or "").strip(),
        "video_name": str(value.get("video_name") or "").strip(),
        "selected_title": selected_title,
        "title_candidates": normalized_candidates,
        "caption": caption,
        "caption_visible_chars": caption_chars,
        "hashtags": hashtags,
        "source_url": str(value.get("source_url") or "").strip(),
        "cover": normalized_cover,
    }


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageStat
    except ImportError as exc:
        raise RuntimeError("生成影视解说封面需要 Pillow，请先执行: pip install Pillow") from exc
    return Image, ImageDraw, ImageFont, ImageStat


def _font_candidates(bold: bool) -> list[str]:
    windows = Path("C:/Windows/Fonts")
    candidates = [
        windows / ("msyhbd.ttc" if bold else "msyh.ttc"),
        windows / "simhei.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    return [str(path) for path in candidates]


def load_font(size: int, *, bold: bool):
    _, _, image_font, _ = _load_pillow()
    for candidate in _font_candidates(bold):
        try:
            return image_font.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return image_font.truetype(
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            size=size,
        )
    except OSError as exc:
        raise RuntimeError("找不到可用于封面的字体，请安装微软雅黑或 Noto Sans CJK") from exc


def crop_to_vertical(image, *, focus_x: float, focus_y: float):
    image_module, _, _, _ = _load_pillow()
    scale = max(COVER_WIDTH / image.width, COVER_HEIGHT / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        image_module.Resampling.LANCZOS,
    )
    max_left = max(0, resized.width - COVER_WIDTH)
    max_top = max(0, resized.height - COVER_HEIGHT)
    left = min(max(0, round(resized.width * focus_x - COVER_WIDTH / 2)), max_left)
    top = min(max(0, round(resized.height * focus_y - COVER_HEIGHT / 2)), max_top)
    return resized.crop((left, top, left + COVER_WIDTH, top + COVER_HEIGHT))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+:/-]*|\s+|.", value)


def wrap_text_pixels(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in _tokens(text):
        candidate = (current + token).strip() if current else token.strip()
        if not candidate:
            continue
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current.strip())
            current = token.strip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    return lines


def fit_text(draw, text: str, *, max_width: int, max_lines: int, max_size: int, min_size: int, bold: bool):
    for size in range(max_size, min_size - 1, -2):
        font = load_font(size, bold=bold)
        lines = wrap_text_pixels(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, size
    raise ValueError(f"封面文字过长，无法在 {max_lines} 行内排版: {text}")


def _draw_lines(draw, lines: list[str], *, x: int, y: int, font, fill: tuple[int, int, int, int], spacing: int, stroke_width: int = 0) -> int:
    cursor = y
    for line in lines:
        box = draw.textbbox((x, cursor), line, font=font, stroke_width=stroke_width)
        draw.text(
            (x, cursor),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 220),
        )
        cursor += box[3] - box[1] + spacing
    return cursor


def render_vertical_cover(*, source: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    image_module, image_draw, _, image_stat = _load_pillow()
    with image_module.open(source) as opened:
        frame = opened.convert("RGB")
    canvas = crop_to_vertical(
        frame,
        focus_x=float(config["focus_x"]),
        focus_y=float(config["focus_y"]),
    ).convert("RGBA")

    overlay = image_module.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = image_draw.Draw(overlay)
    if config["layout"] == "top":
        band_top, band_bottom = 100, 730
        content_y = 175
    else:
        band_top, band_bottom = 1090, 1780
        content_y = 1160
    overlay_draw.rectangle((0, band_top, COVER_WIDTH, band_bottom), fill=(7, 9, 12, 178))
    canvas = image_module.alpha_composite(canvas, overlay)
    draw = image_draw.Draw(canvas)
    left = 76
    max_width = COVER_WIDTH - left * 2

    kicker_font = load_font(42, bold=True)
    draw.text((left, content_y), config["kicker"], font=kicker_font, fill=(255, 204, 64, 255))
    accent_y = content_y + 68
    draw.rectangle((left, accent_y, left + 152, accent_y + 12), fill=(230, 55, 50, 255))

    headline_font, headline_lines, headline_size = fit_text(
        draw,
        config["headline"],
        max_width=max_width,
        max_lines=2,
        max_size=104,
        min_size=68,
        bold=True,
    )
    cursor = _draw_lines(
        draw,
        headline_lines,
        x=left,
        y=accent_y + 36,
        font=headline_font,
        fill=(255, 255, 255, 255),
        spacing=14,
        stroke_width=2,
    )
    sub_font, sub_lines, sub_size = fit_text(
        draw,
        config["subheadline"],
        max_width=max_width,
        max_lines=2,
        max_size=54,
        min_size=38,
        bold=False,
    )
    cursor = _draw_lines(
        draw,
        sub_lines,
        x=left,
        y=cursor + 20,
        font=sub_font,
        fill=(255, 221, 116, 255),
        spacing=10,
        stroke_width=1,
    )
    label_font = load_font(34, bold=False)
    label_y = cursor + 24
    label_box = draw.textbbox((left, label_y), config["episode_label"], font=label_font)
    if label_box[3] > band_bottom - 18:
        raise ValueError("封面文字纵向空间不足，请缩短主标题或副标题")
    draw.text((left, label_y), config["episode_label"], font=label_font, fill=(235, 238, 242, 255))

    output.parent.mkdir(parents=True, exist_ok=True)
    rgb = canvas.convert("RGB")
    rgb.save(output, format="JPEG", quality=95, subsampling=0)
    gray_stats = image_stat.Stat(rgb.convert("L"))
    metrics = {
        "width": rgb.width,
        "height": rgb.height,
        "format": "JPEG",
        "luma_stddev": round(float(gray_stats.stddev[0]), 3),
        "layout": config["layout"],
        "headline_font_size": headline_size,
        "subheadline_font_size": sub_size,
        "headline_lines": headline_lines,
        "subheadline_lines": sub_lines,
    }
    if (rgb.width, rgb.height) != (COVER_WIDTH, COVER_HEIGHT):
        raise RuntimeError("封面尺寸不是 1080x1920")
    if metrics["luma_stddev"] < 8:
        raise RuntimeError("封面画面变化过低，可能是空白帧或纯色帧")
    if output.stat().st_size < 10_000:
        raise RuntimeError("封面文件过小，可能生成失败")
    return metrics


def _write_titles(path: Path, plan: dict[str, Any]) -> None:
    rows = ["# 已选标题", "", plan["selected_title"], "", "# 标题候选", ""]
    for index, candidate in enumerate(plan["title_candidates"], start=1):
        marker = " [已选]" if candidate["title"] == plan["selected_title"] else ""
        rows.extend(
            [
                f"{index}. {candidate['title']}{marker}",
                f"   角度：{candidate['angle']}",
                f"   证据：{', '.join(candidate['evidence_refs'])}",
            ]
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="已通过 QA 的影视解说成片")
    parser.add_argument("--plan", type=Path, required=True, help="publish_plan.json")
    parser.add_argument("--qa-report", type=Path, required=True)
    parser.add_argument("--cover-source", type=Path, help="可选的无解说字幕封面取帧视频")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--copy", action="store_true", help="禁用硬链接并复制视频")
    parser.add_argument("--transcode", action="store_true", help="强制转为 H.264/AAC MP4")
    parser.add_argument("--force", action="store_true", help="覆盖同名发布包")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.video.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")
    plan_path = args.plan.expanduser().resolve()
    plan = validate_publish_plan(read_json(plan_path))
    qa_report = args.qa_report.expanduser().resolve()
    ensure_qa_passed(qa_report)
    cover_source = (
        args.cover_source.expanduser().resolve() if args.cover_source else source
    )
    if not cover_source.is_file():
        raise FileNotFoundError(f"Cover source not found: {cover_source}")

    repo_root = find_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from src.paths_config import DOUYIN_PUBLISH_PACKAGES_DIR

    package_slug = safe_slug(plan["package_name"] or plan["selected_title"], fallback=source.stem)
    package_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else Path(DOUYIN_PUBLISH_PACKAGES_DIR) / package_slug
    )
    package_dir.mkdir(parents=True, exist_ok=True)
    video_slug = safe_slug(plan["video_name"] or plan["selected_title"], fallback=source.stem)
    outputs = {
        "video": package_dir / f"{video_slug}_douyin.mp4",
        "cover": package_dir / "cover_9x16.jpg",
        "cover_source": package_dir / "cover_source.jpg",
        "titles": package_dir / "titles.txt",
        "caption": package_dir / "caption.txt",
        "hashtags": package_dir / "hashtags.txt",
        "notes": package_dir / "publish_notes.md",
        "manifest": package_dir / "publish_manifest.json",
        "plan": package_dir / "publish_plan.json",
    }
    existing = [path.name for path in outputs.values() if path.exists()]
    if existing and not args.force:
        raise FileExistsError(f"发布包已存在这些文件，请使用 --force 覆盖: {', '.join(existing)}")

    ffmpeg = resolve_executable("ffmpeg", args.ffmpeg)
    ffprobe = resolve_executable("ffprobe", args.ffprobe)
    source_media = probe_media(source, ffprobe)
    transfer_mode = transfer_video(
        source=source,
        target=outputs["video"],
        source_media=source_media,
        ffmpeg=ffmpeg,
        force_copy=args.copy,
        force_transcode=args.transcode,
    )
    packaged_media = probe_media(outputs["video"], ffprobe)
    if packaged_media["video"].get("codec") != "h264":
        raise RuntimeError("发布视频不是 H.264 编码")
    if packaged_media["audio"].get("codec") != "aac":
        raise RuntimeError("发布视频缺少 AAC 音轨")

    cover_media = probe_media(cover_source, ffprobe)
    cover_time = float(plan["cover"]["timestamp_sec"])
    if not 0 <= cover_time < cover_media["duration_sec"]:
        raise ValueError(f"封面时间必须位于 0-{cover_media['duration_sec']:.3f} 秒之间")
    extract_cover(
        video=cover_source,
        output=outputs["cover_source"],
        timestamp=cover_time,
        ffmpeg=ffmpeg,
    )
    cover_metrics = render_vertical_cover(
        source=outputs["cover_source"],
        output=outputs["cover"],
        config=plan["cover"],
    )

    _write_titles(outputs["titles"], plan)
    outputs["caption"].write_text(plan["caption"] + "\n", encoding="utf-8", newline="\n")
    outputs["hashtags"].write_text(
        " ".join(plan["hashtags"]) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if plan_path != outputs["plan"]:
        shutil.copy2(plan_path, outputs["plan"])

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest = {
        "schema_version": "2.0",
        "platform": "douyin",
        "content_type": "film_commentary",
        "generated_at": generated_at,
        "selected_title": plan["selected_title"],
        "title_candidates": plan["title_candidates"],
        "caption": plan["caption"],
        "caption_visible_chars": plan["caption_visible_chars"],
        "hashtags": plan["hashtags"],
        "source_url": plan["source_url"],
        "source_video": str(source),
        "cover_source_video": str(cover_source),
        "qa_report": str(qa_report),
        "video_file": outputs["video"].name,
        "cover_file": outputs["cover"].name,
        "titles_file": outputs["titles"].name,
        "transfer_mode": transfer_mode,
        "video_sha256": sha256_file(outputs["video"]),
        "cover_sha256": sha256_file(outputs["cover"]),
        "media": packaged_media,
        "cover": {**plan["cover"], **cover_metrics},
    }
    write_json(outputs["manifest"], manifest)

    notes = [
        "# 影视解说抖音发布包",
        "",
        f"- 已选标题：{plan['selected_title']}",
        f"- 标题候选：`{outputs['titles'].name}`",
        f"- 视频：`{outputs['video'].name}`",
        f"- 竖版封面：`{outputs['cover'].name}`（1080x1920）",
        f"- 文案：`{outputs['caption'].name}`（{plan['caption_visible_chars']} 个可见字符）",
        f"- 话题：`{outputs['hashtags'].name}`",
        f"- 时长：{packaged_media['duration_sec']:.3f} 秒",
        f"- 分辨率：{packaged_media['video'].get('width')}x{packaged_media['video'].get('height')}",
        f"- 来源：{plan['source_url'] or '未填写'}",
        "",
        "发布前必须人工复核封面人物、标题事实、字幕、音量、版权授权和平台规则。",
        "",
    ]
    outputs["notes"].write_text("\n".join(notes), encoding="utf-8", newline="\n")

    print(f"Film commentary package: {package_dir}")
    print(f"Video: {outputs['video']}")
    print(f"Cover: {outputs['cover']}")
    print(f"Titles: {outputs['titles']}")
    print(f"Caption: {outputs['caption']} ({plan['caption_visible_chars']} chars)")
    print(f"Manifest: {outputs['manifest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
