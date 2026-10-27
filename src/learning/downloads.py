"""Keep a download and its related assets in one portable learning project."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .imports import REPO_ROOT, recent_downloads, subtitle_candidates
from .project import MANIFEST, import_project, inspect_project, signature, write_manifest


def project_directory(url: str, base: Path | None = None) -> Path:
    # Reuse a project that is already recorded, including user-created folders.
    for item in recent_downloads():
        if item["source_url"] == url and (Path(item["path"]).parent / MANIFEST).is_file():
            return Path(item["path"]).parent
    parsed = urlparse(url)
    key = parse_qs(parsed.query).get("v", [""])[0]
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        key = parsed.path.strip("/").split("/")[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", key):
        key = hashlib.sha256(url.encode()).hexdigest()[:20]
    if base is None:
        try:
            from ..paths_config import LEARNING_PROJECTS_DIR
        except ImportError:
            from paths_config import LEARNING_PROJECTS_DIR
        base = Path(LEARNING_PROJECTS_DIR)
    return base / key


def copy_asset(source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        return source
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        # Never silently replace a user's existing asset with a different file.
        if signature(source) != signature(destination):
            raise ValueError(f"工程中已有不同内容的同名文件：{destination.name}")
        return destination
    from .store import new_id

    temporary = destination.with_name("." + destination.name + "." + new_id() + ".tmp")
    try:
        shutil.copy2(source, temporary)
        if signature(source) != signature(temporary):
            raise ValueError("工程资料复制校验失败，请重试")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def bundle_download(source: Path, root: Path, url: str = "", title: str = "", video_id: str = "") -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    video = copy_asset(source, root / source.name)
    # Once the downloader writes inside its project, public legacy subtitles
    # must not replace newer translations generated in that project.
    candidates = subtitle_candidates(str(source)) if source.resolve().parent != root else []
    for track in candidates:
        path = Path(track["path"])
        if path.parent in {root, root / "subtitles"}:
            continue
        if (root / path.name).exists():
            copy_asset(path, root / path.name)
            continue
        copy_asset(path, root / "subtitles" / path.name)
    project = inspect_project(str(root), str(video))
    if video_id and not project["id"]:
        project["id"] = video_id
    if title:
        project["title"] = title
    write_manifest(project, source_url=url)
    return video


def update_history(url: str, video: Path, repo: Path = REPO_ROOT):
    """Update the path only; preserve titles and download dates without ML imports."""
    path = repo / "workspace" / "logs" / "downloaded_videos.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return
    changed = False
    for item in items if isinstance(items, list) else []:
        if item.get("url") == url and item.get("file_path") != str(video):
            item["file_path"] = str(video)
            changed = True
    if changed:
        from .store import new_id

        temporary = path.with_name("." + path.name + "." + new_id() + ".tmp")
        try:
            temporary.write_text(json.dumps(items, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def import_download(service, path: str, title: str = "", source_url: str = "") -> dict | None:
    source = Path(path.strip().strip('"')).expanduser().resolve()
    if (source.parent / MANIFEST).is_file():
        project = inspect_project(str(source.parent))
        if Path(project["path"]) == source:
            return import_project(service, str(source.parent))["video"]
    item = next((r for r in recent_downloads() if Path(r["path"]).resolve() == source), None)
    if not item:
        return None
    url = source_url or item["source_url"]
    root = project_directory(url)
    previous = next((v for v in service.store.videos() if Path(v["path"]) == source), {})
    video = bundle_download(source, root, url, title or item["title"], previous.get("id", ""))
    result = import_project(service, str(root))["video"]
    update_history(url, video)
    return result
