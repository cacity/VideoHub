#!/usr/bin/env python3
"""Generate thumbnail-first multi-format covers from one source image."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SIZES = {
    "cover_9x16.jpg": (1080, 1920),
    "cover_3x4.jpg": (1080, 1440),
    "cover_4x3.jpg": (1440, 1080),
    "cover_16x9.jpg": (1920, 1080),
}

WHITE = (250, 249, 245)
MUTED = (205, 208, 211)
INK = (10, 12, 14)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--landscape-source",
        type=Path,
        help="Optional source image used only for landscape covers.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--episode", default="")
    parser.add_argument("--episode-label", default="")
    parser.add_argument("--hook", action="append", default=[])
    parser.add_argument("--category", default="影视解说")
    parser.add_argument("--focus-x", type=float, default=0.63)
    parser.add_argument("--focus-y", type=float, default=0.48)
    parser.add_argument("--landscape-focus-x", type=float)
    parser.add_argument("--landscape-focus-y", type=float)
    parser.add_argument("--accent", default="#F7BA34")
    parser.add_argument("--badge-color", default="#CD2A30")
    parser.add_argument("--font-bold", type=Path)
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=tuple(SIZES),
        default=list(SIZES),
        help="Cover filenames to generate. Defaults to all supported formats.",
    )
    parser.add_argument(
        "--no-thumbnail-preview",
        action="store_true",
        help="Do not generate thumbnail_preview.jpg.",
    )
    args = parser.parse_args()
    args.formats = list(dict.fromkeys(args.formats))
    if len(args.hook) > 2:
        parser.error("--hook can be provided at most twice")
    if not 0.0 <= args.focus_x <= 1.0 or not 0.0 <= args.focus_y <= 1.0:
        parser.error("--focus-x and --focus-y must be between 0 and 1")
    for name in ("landscape_focus_x", "landscape_focus_y"):
        value = getattr(args, name)
        if value is not None and not 0.0 <= value <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    return args


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"invalid RGB color: {value}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def find_font(explicit: Path | None, bold: bool) -> Path:
    candidates = [explicit] if explicit else []
    candidates.extend(
        Path(path)
        for path in (
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        )
    )
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError("No usable font found; provide --font-bold and --font-regular")


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=max(10, size))


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    start_size: int,
    min_size: int,
    max_width: int,
) -> ImageFont.FreeTypeFont:
    for size in range(start_size, min_size - 1, -2):
        selected = load_font(font_path, size)
        box = draw.textbbox((0, 0), text, font=selected, stroke_width=1)
        if box[2] - box[0] <= max_width:
            return selected
    raise ValueError(f"text is too long for cover: {text!r}; shorten it")


def cover_crop(
    source: Image.Image,
    size: tuple[int, int],
    focus_x: float,
    focus_y: float,
) -> Image.Image:
    width, height = size
    scale = max(width / source.width, height / source.height)
    resized = source.resize(
        (round(source.width * scale), round(source.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = round((resized.width - width) * focus_x)
    top = round((resized.height - height) * focus_y)
    left = max(0, min(left, resized.width - width))
    top = max(0, min(top, resized.height - height))
    return resized.crop((left, top, left + width, top + height))


def draw_fitted(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font_path: Path,
    start_size: int,
    min_size: int,
    max_width: int,
    fill: tuple[int, int, int],
) -> int:
    selected = fit_font(draw, text, font_path, start_size, min_size, max_width)
    draw.text(xy, text, font=selected, fill=fill, stroke_width=1, stroke_fill=INK)
    return selected.size


def episode_mark(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    episode: str,
    label: str,
    bold_font: Path,
    badge_color: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    draw.rounded_rectangle(box, radius=max(10, width // 18), fill=badge_color)
    number_font = fit_font(draw, episode, bold_font, int(width * 0.50), 30, int(width * 0.86))
    number_box = draw.textbbox((0, 0), episode, font=number_font)
    number_x = left + (width - (number_box[2] - number_box[0])) // 2
    number_y = top + int(height * 0.02)
    draw.text((number_x, number_y), episode, font=number_font, fill=WHITE)
    label_font = fit_font(draw, label, bold_font, int(width * 0.20), 18, int(width * 0.86))
    label_box = draw.textbbox((0, 0), label, font=label_font)
    label_x = left + (width - (label_box[2] - label_box[0])) // 2
    label_y = bottom - int(height * 0.27)
    draw.text((label_x, label_y), label, font=label_font, fill=WHITE)


def portrait(
    source: Image.Image,
    size: tuple[int, int],
    args: argparse.Namespace,
    bold_font: Path,
    regular_font: Path,
    accent: tuple[int, int, int],
    badge_color: tuple[int, int, int],
) -> Image.Image:
    width, height = size
    image = cover_crop(source, size, args.focus_x, args.focus_y)
    image = ImageEnhance.Contrast(image).enhance(1.07)
    image = ImageEnhance.Color(image).enhance(0.94)
    panel_top = int(height * 0.605)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    fade = int(height * 0.08)
    for y in range(panel_top - fade, panel_top):
        alpha = int(232 * (y - panel_top + fade) / fade)
        overlay_draw.line((0, y, width, y), fill=(*INK, alpha))
    overlay_draw.rectangle((0, panel_top, width, height), fill=(*INK, 240))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.065)
    if args.episode:
        mark_width = int(width * 0.235)
        mark_height = int(mark_width * 1.12)
        episode_mark(
            draw,
            (width - margin - mark_width, int(height * 0.055), width - margin,
             int(height * 0.055) + mark_height),
            args.episode,
            args.episode_label,
            bold_font,
            badge_color,
        )
    draw.rounded_rectangle(
        (margin, panel_top + int(height * 0.035), margin + int(width * 0.23),
         panel_top + int(height * 0.045)),
        radius=4,
        fill=badge_color,
    )
    title_y = panel_top + int(height * 0.055)
    title_size = draw_fitted(
        draw, (margin, title_y), args.title, bold_font, int(width * 0.125),
        int(width * 0.06), int(width * 0.87), accent,
    )
    hook_y = title_y + int(title_size * 1.30)
    for hook in args.hook:
        hook_size = draw_fitted(
            draw, (margin, hook_y), hook, bold_font, int(width * 0.073),
            int(width * 0.046), int(width * 0.87), WHITE,
        )
        hook_y += int(hook_size * 1.28)
    category_font = load_font(regular_font, int(width * 0.034))
    draw.text((margin, height - int(height * 0.065)), args.category,
              font=category_font, fill=MUTED)
    return image


def landscape(
    source: Image.Image,
    size: tuple[int, int],
    args: argparse.Namespace,
    bold_font: Path,
    regular_font: Path,
    accent: tuple[int, int, int],
    badge_color: tuple[int, int, int],
) -> Image.Image:
    width, height = size
    focus_x = args.focus_x if args.landscape_focus_x is None else args.landscape_focus_x
    focus_y = args.focus_y if args.landscape_focus_y is None else args.landscape_focus_y
    background = cover_crop(source, size, focus_x, focus_y).filter(
        ImageFilter.GaussianBlur(radius=max(8, height // 110))
    )
    background = ImageEnhance.Brightness(background).enhance(0.42)
    foreground = cover_crop(source, size, focus_x, focus_y)
    split = int(width * 0.42)
    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle((split, 0, width, height), fill=255)
    blend = int(width * 0.06)
    for x in range(split - blend, split):
        mask_draw.line((x, 0, x, height), fill=int(255 * (x - split + blend) / blend))
    image = Image.composite(foreground, background, mask)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, int(width * 0.50), height), fill=(*INK, 220))
    margin = int(width * 0.052)
    if args.episode:
        mark_width = int(height * 0.23)
        mark_height = int(mark_width * 1.12)
        episode_mark(
            draw,
            (margin, int(height * 0.075), margin + mark_width,
             int(height * 0.075) + mark_height),
            args.episode,
            args.episode_label,
            bold_font,
            badge_color,
        )
    title_y = int(height * (0.38 if args.episode else 0.26))
    max_text_width = int(width * 0.39)
    title_size = draw_fitted(
        draw, (margin, title_y), args.title, bold_font, int(height * 0.115),
        int(height * 0.06), max_text_width, accent,
    )
    hook_y = title_y + int(title_size * 1.45)
    for hook in args.hook:
        hook_size = draw_fitted(
            draw, (margin, hook_y), hook, bold_font, int(height * 0.068),
            int(height * 0.042), max_text_width, WHITE,
        )
        hook_y += int(hook_size * 1.50)
    draw.rounded_rectangle(
        (margin, height - int(height * 0.12), margin + int(width * 0.14),
         height - int(height * 0.108)),
        radius=4,
        fill=badge_color,
    )
    category_font = load_font(regular_font, int(height * 0.032))
    draw.text((margin, height - int(height * 0.088)), args.category,
              font=category_font, fill=MUTED)
    return image


def save_cover(image: Image.Image, path: Path) -> None:
    image.save(path, quality=95, subsampling=0, optimize=True)
    with Image.open(path) as checked:
        checked.load()
        if checked.size != image.size:
            raise RuntimeError(f"cover size mismatch: {path}")


def thumbnail_preview(output_dir: Path, title: str, label: str, bold_font: Path) -> Path:
    source = Image.open(output_dir / "cover_3x4.jpg").convert("RGB")
    thumb = source.resize((220, 293), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (260, 353), (24, 26, 31))
    canvas.paste(thumb, (20, 20))
    draw = ImageDraw.Draw(canvas)
    caption = f"{title} {label}".strip()
    caption_font = fit_font(draw, caption, bold_font, 18, 12, 220)
    draw.text((20, 320), caption, font=caption_font, fill=WHITE)
    target = output_dir / "thumbnail_preview.jpg"
    save_cover(canvas, target)
    return target


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    landscape_source_path = (
        args.landscape_source.resolve() if args.landscape_source else source_path
    )
    output_dir = args.output_dir.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not landscape_source_path.is_file():
        raise FileNotFoundError(landscape_source_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.episode and not args.episode_label:
        args.episode_label = f"第{int(args.episode)}集" if args.episode.isdigit() else args.episode
    bold_font = find_font(args.font_bold, bold=True)
    regular_font = find_font(args.font_regular, bold=False)
    accent = rgb(args.accent)
    badge_color = rgb(args.badge_color)
    with Image.open(source_path) as opened:
        opened.load()
        source = opened.convert("RGB")
    with Image.open(landscape_source_path) as opened:
        opened.load()
        landscape_source = opened.convert("RGB")
    outputs: list[Path] = []
    for filename in args.formats:
        size = SIZES[filename]
        if size[0] < size[1]:
            image = portrait(source, size, args, bold_font, regular_font, accent, badge_color)
        else:
            image = landscape(
                landscape_source, size, args, bold_font, regular_font, accent, badge_color
            )
        target = output_dir / filename
        save_cover(image, target)
        outputs.append(target)
    if not args.no_thumbnail_preview and "cover_3x4.jpg" in args.formats:
        outputs.append(thumbnail_preview(output_dir, args.title, args.episode_label, bold_font))
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path),
        "source_sha256": sha256(source_path),
        "landscape_source": str(landscape_source_path),
        "landscape_source_sha256": sha256(landscape_source_path),
        "formats": args.formats,
        "title": args.title,
        "episode": args.episode,
        "episode_label": args.episode_label,
        "hooks": args.hook,
        "category": args.category,
        "focus": {"x": args.focus_x, "y": args.focus_y},
        "landscape_focus": {
            "x": args.focus_x if args.landscape_focus_x is None else args.landscape_focus_x,
            "y": args.focus_y if args.landscape_focus_y is None else args.landscape_focus_y,
        },
        "colors": {"accent": args.accent, "badge": args.badge_color},
        "fonts": {"bold": str(bold_font), "regular": str(regular_font)},
        "outputs": [
            {
                "name": path.name,
                "size": list(Image.open(path).size),
                "sha256": sha256(path),
            }
            for path in outputs
        ],
    }
    manifest_path = output_dir / "cover_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "output_dir": str(output_dir),
                      "files": [path.name for path in outputs] + [manifest_path.name]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
