"""A directory with one video and multiple subtitles is a learning project."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .media import VIDEO_EXTENSIONS
from .store import new_id, now
from .subtitles import read_track

MANIFEST = "videohub_learning.json"


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("工程清单中的文件必须位于所选工程目录内")
    return path


def signature(path: Path) -> str:
    digest = hashlib.sha256(str(path.stat().st_size).encode())
    with path.open("rb") as stream:
        digest.update(stream.read(65536))
        stream.seek(max(0, path.stat().st_size - 65536))
        digest.update(stream.read(65536))
    return digest.hexdigest()


def classify(path: Path) -> tuple[str, str]:
    name = path.stem.lower()
    explicit = re.search(r"\.(source|target)\.([a-z]{2}(?:-[a-z]{2,4})?|auto)(?:\.|$)", name)
    if explicit:
        role, language = explicit.groups()
        return role, {"zh-cn": "zh-CN", "zh-tw": "zh-TW"}.get(language, language)
    # A language suffix is stronger evidence than words in the video title.
    suffix = re.search(r"(?:^|[_. -])(zh(?:[-_]?(?:cn|tw|hans|hant))?|en(?:-orig)?|ja|ko|fr|de|es)$", name)
    if suffix:
        language = suffix.group(1)
        if language.startswith("zh"):
            return "target", "zh-TW" if language.endswith(("tw", "hant")) else "zh-CN"
        return "source", language.replace("-orig", "")
    if re.search(
        r"(?:^|[_. -])(?:zh(?:[-_]?(?:cn|tw|hans|hant))?|cn|google|polished|translated)(?:$|[_. -])|中文|简体|繁体",
        name,
    ):
        return "target", "zh-CN"
    for code, words in [
        ("en", "english|英文|英语|原文"),
        ("ja", "japanese|日文|日语"),
        ("ko", "korean|韩文|韩语"),
        ("fr", "french|法语"),
        ("de", "german|德语"),
        ("es", "spanish|西班牙"),
    ]:
        if re.search(rf"(?:^|[_. -]){code}(?:$|[_. -])|{words}", name):
            return "source", code
    cues = read_track(path)["cues"][:12]
    text = "".join(c["text"] for c in cues)
    if re.search("[\u3040-\u30ff]", text):
        return "source", "ja"
    if re.search("[\uac00-\ud7af]", text):
        return "source", "ko"
    if len(re.findall("[\u4e00-\u9fff]", text)) > len(re.findall("[a-zA-Z]", text)):
        return "target", "zh-CN"
    return "source", "en"


def inspect_project(directory: str, video_path: str = "") -> dict:
    root = Path(directory.strip().strip('"')).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("请选择存在的视频工程目录")
    manifest_path = root / MANIFEST
    previous = {}
    if manifest_path.is_file():
        if manifest_path.stat().st_size > 1_000_000:
            raise ValueError("工程清单过大")
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            raise ValueError("工程清单损坏，请检查 videohub_learning.json") from None
        if not isinstance(previous, dict) or previous.get("schema_version") != 1:
            raise ValueError("不支持此学习工程清单版本")
    videos = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    if video_path:
        video = Path(video_path).resolve()
        if video not in videos:
            raise ValueError("视频必须属于所选目录")
    elif previous.get("video"):
        video = inside(root, previous["video"])
        if not video.is_file():
            raise ValueError("工程视频已移动，请重新选择目录或修正清单中的相对路径")
    elif len(videos) == 1:
        video = videos[0]
    elif not videos:
        raise ValueError("目录中没有视频文件")
    else:
        return {
            "needs_selection": True,
            "root": str(root),
            "videos": [{"path": str(p), "title": p.stem} for p in videos],
        }
    if not video.resolve().is_relative_to(root):
        raise ValueError("工程视频必须位于所选目录内，不能通过链接指向目录外")
    files = [
        p
        for folder in (root, root / "subtitles")
        if folder.is_dir()
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa"}
    ]
    if len(files) > 80:
        raise ValueError("工程字幕超过80份，请按视频拆分目录")
    if len(videos) > 1:
        try:
            from ..series_project import normalize_asset_stem
        except ImportError:
            from series_project import normalize_asset_stem
        files = [p for p in files if normalize_asset_stem(p.stem) == normalize_asset_stem(video.stem)]
    tracks = []
    warnings = []
    for path in files:
        if not path.resolve().is_relative_to(root):
            continue
        try:
            role, language = classify(path)
            original = read_track(path, "source")["cues"]
            target = read_track(path, "target")["cues"]
            if original != target:
                tracks.extend(
                    [
                        {"path": str(path.resolve()), "role": "source", "language": "en"},
                        {"path": str(path.resolve()), "role": "target", "language": "zh-CN"},
                    ]
                )
                continue
            tracks.append({"path": str(path.resolve()), "role": role, "language": language})
        except (ValueError, UnicodeError, OSError):
            warnings.append(f"{path.name} 无法读取，已跳过")
    # Prefer a dedicated SRT original and Chinese track; preserve all alternatives.
    tracks.sort(
        key=lambda t: (
            t["role"],
            0 if re.search(r"\.(?:source|target)\.", Path(t["path"]).name) else 1,
            t["language"] != "en",
            "bilingual" in Path(t["path"]).stem.lower() or "双语" in Path(t["path"]).stem,
            (0 if "polished" in Path(t["path"]).stem.lower() else 2 if "google" in Path(t["path"]).stem.lower() else 1)
            if t["role"] == "target"
            else 0,
            {".srt": 0, ".vtt": 1, ".ass": 2, ".ssa": 3}[Path(t["path"]).suffix.lower()],
            -Path(t["path"]).stat().st_mtime_ns if re.search(r"\.(?:source|target)\.", Path(t["path"]).name) else 0,
            t["path"],
        )
    )
    if tracks and not any(t["role"] == "source" for t in tracks):
        tracks[0] = {**tracks[0], "role": "source"}
    project_id = previous.get("id", "")
    if project_id and not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise ValueError("工程编号无效")
    return {
        "root": str(root),
        "path": str(video.resolve()),
        "title": previous.get("title") or video.stem,
        "tracks": tracks,
        "id": project_id,
        "media_signature": signature(video),
        "warnings": warnings,
    }


def import_project(service, directory: str, video_path: str = "") -> dict:
    project = inspect_project(directory, video_path)
    if project.get("needs_selection"):
        return project
    root = Path(project["root"])
    previous = json.loads((root / MANIFEST).read_text(encoding="utf-8-sig")) if (root / MANIFEST).is_file() else {}
    video = service.register(
        project["path"],
        str(project["title"]),
        source_url=previous.get("source_url", ""),
        tracks=project["tracks"],
        project=project,
    )
    project["id"] = video["id"]
    try:
        write_manifest(project, source_url=video.get("source_url", ""))
    except OSError:
        project["warnings"].append("目录不可写；资料已导入本机学习库，但工程清单未保存")
    return {"video": video, "warnings": project["warnings"], "root": str(root)}


def write_manifest(project: dict, source_url: str = ""):
    root = Path(project["root"])
    manifest = {
        "schema_version": 1,
        "project_type": "video_learning",
        "id": project.get("id") or new_id(),
        "title": project["title"],
        "video": Path(project["path"]).relative_to(root).as_posix(),
        "source_url": source_url,
        "subtitles": [{**t, "path": Path(t["path"]).relative_to(root).as_posix()} for t in project["tracks"]],
        "updated": now(),
    }
    temporary = root / ("." + MANIFEST + "." + new_id() + ".tmp")
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(root / MANIFEST)
    finally:
        temporary.unlink(missing_ok=True)
