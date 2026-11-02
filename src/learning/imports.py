"""Read existing VideoHub assets; selection remains explicit."""

from __future__ import annotations

import json
from pathlib import Path

from .media import VIDEO_EXTENSIONS
from .project import classify

REPO_ROOT = Path(__file__).resolve().parents[2]


def recent_downloads(root: Path = REPO_ROOT) -> list[dict]:
    result, seen = [], set()
    log = root / "workspace" / "logs" / "downloaded_videos.json"
    try:
        items = json.loads(log.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        items = []
    for item in reversed(items if isinstance(items, list) else []):
        path = Path(str(item.get("file_path", "")))
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                result.append(
                    {"path": resolved, "title": item.get("title") or path.stem, "source_url": item.get("url", "")}
                )
        if len(result) >= 80:
            break
    return result


def directory_assets(path: str) -> list[dict]:
    try:
        from ..series_project import discover_series_project
    except ImportError:
        from series_project import discover_series_project
    root = Path(path.strip().strip('"')).expanduser().resolve()
    # Uses the existing manifest/discovery conventions without writing beside the originals.
    manifest = discover_series_project(root)
    result = []
    for episode in manifest["episodes"][:200]:
        source = (root / episode["video"]).resolve()
        result.append(
            {
                "path": str(source),
                "title": source.stem,
                "subtitle_count": sum(len(p) for p in episode["subtitles"].values()),
            }
        )
    return result


def subtitle_candidates(
    video_path: str, root: Path = REPO_ROOT, *, project_root: Path | None = None,
    snapshot_folders: list[Path] | None = None,
) -> list[dict]:
    from .subtitles import read_track
    try:
        from ..series_project import normalize_asset_stem
    except ImportError:
        from series_project import normalize_asset_stem
    video = Path(video_path).resolve()
    # Shared folders must match the video name. A single-video project and its
    # dedicated snapshot folders may also contain renamed/truncated versions.
    directories = {p.resolve(): False for p in (
        video.parent, video.parent / "subtitles",
        root / "workspace" / "subtitles", root / "workspace" / "native_subtitles",
    )}
    if project_root and project_root.is_dir():
        project_root = project_root.resolve()
        videos = [p.resolve() for p in project_root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        directories[(project_root / "subtitles" / "learning_tracks").resolve()] = False
        if videos == [video]:
            for folder in (project_root, project_root / "subtitles", project_root / "subtitles" / "learning_tracks"):
                directories[folder.resolve()] = True
    for folder in snapshot_folders or []:
        directories[folder.resolve()] = True
    result, seen = [], set()
    for directory, dedicated in sorted(directories.items()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".srt", ".vtt", ".ass", ".ssa"} or not path.is_file():
                continue
            if not dedicated and normalize_asset_stem(path.stem) != normalize_asset_stem(video.stem):
                continue
            full = str(path.resolve())
            if full in seen:
                continue
            seen.add(full)
            try:
                role, language = classify(path)
                source = read_track(path, "source")["cues"]
                target = read_track(path, "target")["cues"]
                mixed = source != target
                modified = path.stat().st_mtime
            except (ValueError, OSError, UnicodeError):
                continue
            roles = [("source", "en"), ("target", "zh-CN")] if mixed else [(role, language)]
            for role, language in roles:
                result.append({
                    "path": full, "name": path.name, "role": role, "language": language,
                    "format": path.suffix[1:].upper(), "bilingual": mixed, "modified": modified,
                })
            if len(result) >= 80:
                return result
    return sorted(result, key=lambda r: (r["role"], r["name"]))
