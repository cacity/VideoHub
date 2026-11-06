"""Portable single-video projects and directories containing several lessons."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .media import VIDEO_EXTENSIONS
from .store import new_id, now
from .subtitles import read_track

MANIFEST = "videohub_learning.json"


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST
    if not path.is_file():
        return {}
    if path.stat().st_size > 1_000_000:
        raise ValueError("工程清单过大")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ValueError("工程清单损坏，请检查 videohub_learning.json") from None
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in (1, 2):
        raise ValueError("不支持此学习工程清单版本")
    entries = manifest.get("videos") if manifest["schema_version"] == 2 else [manifest]
    if not isinstance(entries, list) or len(entries) > 200 or any(not isinstance(e, dict) for e in entries):
        raise ValueError("工程视频清单格式无效，最多200个视频")
    paths, ids = set(), set()
    for entry in entries:
        if not isinstance(entry.get("video"), str) or not entry["video"]:
            raise ValueError("工程视频路径无效")
        tracks = entry.get("subtitles", [])
        if not isinstance(tracks, list) or any(
            not isinstance(t, dict) or not isinstance(t.get("path"), str) for t in tracks
        ) or not isinstance(entry.get("source_url", ""), str):
            raise ValueError("工程字幕或来源链接格式无效")
        video = inside(root, entry["video"])
        project_id = entry.get("id", "")
        if project_id and (not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id)):
            raise ValueError("工程编号无效")
        if video in paths or (project_id and project_id in ids):
            raise ValueError("工程清单中存在重复视频或编号")
        paths.add(video)
        if project_id:
            ids.add(project_id)
    return manifest


def project_videos(root: Path) -> list[Path]:
    if not root.is_dir():
        raise ValueError("请选择存在的视频工程目录")
    videos = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        raise ValueError("目录中没有视频文件")
    if len(videos) > 200:
        raise ValueError("目录视频超过200个，请分批放入不同目录")
    return videos


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
    manifest = load_manifest(root)
    videos = project_videos(root)
    if video_path:
        video = Path(video_path).resolve()
        if video not in videos:
            raise ValueError("视频必须属于所选目录")
    elif len(videos) == 1:
        video = videos[0]
    else:
        return {
            "needs_selection": True,
            "root": str(root),
            "videos": [{"path": str(p), "title": p.stem} for p in videos],
        }
    if not video.resolve().is_relative_to(root):
        raise ValueError("工程视频必须位于所选目录内，不能通过链接指向目录外")
    entries = manifest.get("videos", []) if manifest.get("schema_version") == 2 else [manifest]
    previous = next((e for e in entries if e.get("video") and inside(root, e["video"]) == video), {})
    project_id = previous.get("id", "")
    dedicated = root / "subtitles" / "learning_tracks" / project_id if project_id else None
    files = [
        p
        for folder in (root, root / "subtitles", root / "subtitles" / "learning_tracks", dedicated)
        if folder and folder.is_dir()
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa"}
    ]
    if len(videos) > 1 or manifest.get("schema_version") == 2:
        try:
            from ..series_project import normalize_asset_stem
        except ImportError:
            from series_project import normalize_asset_stem
        if sum(normalize_asset_stem(p.stem) == normalize_asset_stem(video.stem) for p in videos) > 1:
            raise ValueError("多个视频名称无法区分对应字幕，请为视频及配套字幕使用不同名称")
        owned = {inside(root, t["path"]) for t in previous.get("subtitles", []) if isinstance(t, dict) and t.get("path")}
        files = [
            p for p in files if p.parent == dedicated or p.resolve() in owned
            or normalize_asset_stem(p.stem) == normalize_asset_stem(video.stem)
        ]
    if len(files) > 80:
        raise ValueError("单个视频字幕超过80份，请整理后再导入")
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
    return {
        "root": str(root),
        "path": str(video.resolve()),
        "title": previous.get("title") or video.stem,
        "tracks": tracks,
        "id": project_id,
        "media_signature": signature(video),
        "warnings": warnings,
        "source_url": previous.get("source_url", ""),
        "collection": len(videos) > 1 or manifest.get("schema_version") == 2,
    }


def import_project(service, directory: str, video_path: str = "", *, video_paths=None, import_all=False) -> dict:
    if video_paths is not None or import_all:
        root = Path(directory.strip().strip('"')).expanduser().resolve()
        videos = project_videos(root)
        load_manifest(root)
        if not isinstance(import_all, bool):
            raise ValueError("全部导入参数无效")
        if video_paths is not None and (
            not isinstance(video_paths, list) or not 1 <= len(video_paths) <= 200
            or any(not isinstance(p, str) for p in video_paths)
        ):
            raise ValueError("请选择1至200个视频")
        selected = videos if import_all else [Path(p).resolve() for p in video_paths]
        if any(p not in videos for p in selected) or len(set(selected)) != len(selected):
            raise ValueError("所选视频必须属于该目录且不能重复")
        imported, errors, warnings = [], [], []
        for path in selected:
            try:
                result = import_project(service, str(root), str(path))
                imported.append(result["video"])
                warnings.extend(f"{path.name}：{message}" for message in result["warnings"])
            except (ValueError, OSError) as exc:
                errors.append({"path": str(path), "error": str(exc)})
        return {"root": str(root), "video": imported[0] if imported else None,
                "imported": imported, "errors": errors, "warnings": warnings}
    project = inspect_project(directory, video_path)
    if project.get("needs_selection"):
        return project
    root = Path(project["root"])
    video = service.register(
        project["path"],
        str(project["title"]),
        source_url=project["source_url"],
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
    previous = load_manifest(root)
    if project.get("collection") or previous.get("schema_version") == 2:
        entries = previous.get("videos", []) if previous.get("schema_version") == 2 else ([previous] if previous else [])
        entry = {k: v for k, v in manifest.items() if k not in {"schema_version", "project_type"}}
        entries = [e for e in entries if e["video"] != entry["video"]] + [entry]
        manifest = {"schema_version": 2, "project_type": "video_learning_collection",
                    "videos": entries, "updated": now()}
    temporary = root / ("." + MANIFEST + "." + new_id() + ".tmp")
    try:
        content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if len(content.encode("utf-8")) > 1_000_000:
            raise OSError("工程清单过大，未保存")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(root / MANIFEST)
    finally:
        temporary.unlink(missing_ok=True)
