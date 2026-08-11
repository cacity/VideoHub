"""Project layout and asset discovery for local video series.

A series project keeps generated artifacts beside the source episodes and uses
relative paths in its manifest, so the whole directory can be moved or passed
to an editing skill as a single input.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "videohub_project.json"
VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
    ".wmv",
}
SUBTITLE_EXTENSIONS = {".ass", ".srt", ".vtt"}

_SUBTITLE_VARIANT_SUFFIXES = (
    "polished",
    "google",
    "translated",
    "translation",
    "bilingual",
    "source",
    "original",
)
_LANGUAGE_SUFFIX_RE = re.compile(
    r"(?:[_ .-](?:zh(?:[_-](?:cn|tw))?|en|ja|jp|ko|kr|fr|de|es|it|pt|ru|ar))$",
    re.IGNORECASE,
)
_NATURAL_PART_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class SeriesProjectLayout:
    root: Path
    audio_dir: Path
    subtitles_dir: Path
    transcripts_dir: Path
    summaries_dir: Path
    videos_with_subtitles_dir: Path
    manifest_path: Path

    def as_relative_directories(self) -> dict[str, str]:
        return {
            "videos": ".",
            "audio": self.audio_dir.relative_to(self.root).as_posix(),
            "subtitles": self.subtitles_dir.relative_to(self.root).as_posix(),
            "transcripts": self.transcripts_dir.relative_to(self.root).as_posix(),
            "summaries": self.summaries_dir.relative_to(self.root).as_posix(),
            "videos_with_subtitles": self.videos_with_subtitles_dir.relative_to(self.root).as_posix(),
        }


def get_series_project_layout(project_root: str | Path) -> SeriesProjectLayout:
    root = Path(project_root).expanduser().resolve()
    return SeriesProjectLayout(
        root=root,
        audio_dir=root / "audio",
        subtitles_dir=root / "subtitles",
        transcripts_dir=root / "transcripts",
        summaries_dir=root / "summaries",
        videos_with_subtitles_dir=root / "videos_with_subtitles",
        manifest_path=root / MANIFEST_NAME,
    )


def ensure_series_project(project_root: str | Path) -> SeriesProjectLayout:
    layout = get_series_project_layout(project_root)
    if not layout.root.is_dir():
        raise ValueError(f"剧集项目目录不存在: {layout.root}")

    for directory in (
        layout.audio_dir,
        layout.subtitles_dir,
        layout.transcripts_dir,
        layout.summaries_dir,
        layout.videos_with_subtitles_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return layout


def natural_sort_key(path: str | Path) -> list[object]:
    text = Path(path).name.casefold()
    return [int(part) if part.isdigit() else part for part in _NATURAL_PART_RE.split(text)]


def list_series_videos(project_root: str | Path) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        return []
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.casefold() in VIDEO_EXTENSIONS
        ),
        key=natural_sort_key,
    )


def _strip_subtitle_variant(stem: str) -> str:
    value = stem
    changed = True
    while changed:
        changed = False
        lowered = value.casefold()
        for suffix in _SUBTITLE_VARIANT_SUFFIXES:
            match = re.search(rf"(?:[_ .-]{re.escape(suffix)})$", lowered)
            if match:
                value = value[: match.start()]
                changed = True
                break
        if changed:
            continue
        language_match = _LANGUAGE_SUFFIX_RE.search(value)
        if language_match:
            value = value[: language_match.start()]
            changed = True
    return value


def normalize_asset_stem(stem: str) -> str:
    """Normalize filename differences without changing episode numbers."""
    base = _strip_subtitle_variant(stem)
    return "".join(char for char in base.casefold() if char.isalnum())


def subtitle_role(path: str | Path) -> str:
    stem = Path(path).stem.casefold()
    if re.search(r"(?:^|[_ .-])polished$", stem):
        return "polished"
    if re.search(r"(?:^|[_ .-])(google|translated|translation)$", stem):
        return "translated"
    if _LANGUAGE_SUFFIX_RE.search(stem):
        return "translated"
    return "source"


def _relative_paths(root: Path, paths: Iterable[Path]) -> list[str]:
    return [path.relative_to(root).as_posix() for path in sorted(paths, key=natural_sort_key)]


def _matching_files(files: Iterable[Path], video_stem: str) -> list[Path]:
    normalized_video = normalize_asset_stem(video_stem)
    return [path for path in files if normalize_asset_stem(path.stem) == normalized_video]


def discover_series_project(project_root: str | Path) -> dict[str, object]:
    layout = get_series_project_layout(project_root)
    root = layout.root
    if not root.is_dir():
        raise ValueError(f"剧集项目目录不存在: {root}")

    videos = list_series_videos(root)
    subtitle_files = [
        path
        for directory in (root, layout.subtitles_dir)
        if directory.is_dir()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.casefold() in SUBTITLE_EXTENSIONS
    ]
    transcript_files = list(layout.transcripts_dir.glob("*.txt")) if layout.transcripts_dir.is_dir() else []
    summary_files = (
        [path for path in layout.summaries_dir.iterdir() if path.is_file()]
        if layout.summaries_dir.is_dir()
        else []
    )
    rendered_files = (
        [path for path in layout.videos_with_subtitles_dir.iterdir() if path.is_file()]
        if layout.videos_with_subtitles_dir.is_dir()
        else []
    )

    episodes: list[dict[str, object]] = []
    for video in videos:
        subtitles = _matching_files(subtitle_files, video.stem)
        grouped_subtitles = {"source": [], "translated": [], "polished": []}
        for subtitle in subtitles:
            grouped_subtitles[subtitle_role(subtitle)].append(subtitle.relative_to(root).as_posix())
        for values in grouped_subtitles.values():
            values.sort(key=str.casefold)

        episodes.append(
            {
                "id": video.stem,
                "video": video.relative_to(root).as_posix(),
                "subtitles": grouped_subtitles,
                "transcripts": _relative_paths(root, _matching_files(transcript_files, video.stem)),
                "summaries": _relative_paths(root, _matching_files(summary_files, video.stem)),
                "rendered_videos": _relative_paths(root, _matching_files(rendered_files, video.stem)),
            }
        )

    return {
        "schema_version": 1,
        "project_type": "video_series",
        "name": root.name,
        "directories": layout.as_relative_directories(),
        "episodes": episodes,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def refresh_series_project_manifest(project_root: str | Path, create_dirs: bool = True) -> Path:
    layout = ensure_series_project(project_root) if create_dirs else get_series_project_layout(project_root)
    manifest = discover_series_project(layout.root)
    temporary_path = layout.manifest_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(layout.manifest_path)
    return layout.manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或刷新 VideoHub 剧集项目清单")
    parser.add_argument("project_dir", help="包含剧集视频的目录")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="仅扫描并输出 JSON，不创建目录或写入清单",
    )
    args = parser.parse_args()

    if args.inspect:
        print(json.dumps(discover_series_project(args.project_dir), ensure_ascii=False, indent=2))
        return 0

    manifest_path = refresh_series_project_manifest(args.project_dir)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
