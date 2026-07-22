"""Local visual timeline editor service for VideoHub story projects.

The service imports the deterministic story-editor artifacts, exposes an
editable clip-relative timeline, stores every edit as a new revision, and can
launch the existing full renderer without mutating the source project.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = REPO_ROOT / "workspace"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
RENDER_SCRIPT = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "videohub-story-editor"
    / "scripts"
    / "render_story.py"
)
MIN_CLIP_DURATION_SEC = 0.25
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return min(end_a, end_b) - max(start_a, start_b) > 0.001


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        text = str(cue.get("text", "")).strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n"
            f"{format_srt_time(as_float(cue['start_sec']))} --> "
            f"{format_srt_time(as_float(cue['end_sec']))}\n{text}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def resolve_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    for candidate in (
        REPO_ROOT / "ffmpeg" / "bin" / f"{name}.exe",
        REPO_ROOT / "ytdlp" / f"{name}.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"{name} executable was not found")


def safe_child(parent: Path, child_name: str) -> Path:
    if not SAFE_ID.fullmatch(child_name):
        raise ValueError("Invalid identifier")
    candidate = (parent / child_name).resolve()
    if parent.resolve() not in candidate.parents:
        raise ValueError("Path escapes the project directory")
    return candidate


class StoryTimelineService:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self._projects: dict[str, dict[str, Path]] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._thumbnail_locks: dict[str, threading.Lock] = {}
        self.refresh_projects()

    def refresh_projects(self) -> None:
        projects: dict[str, dict[str, Path]] = {}
        if not self.workspace_root.is_dir():
            self._projects = projects
            return
        for plan_path in self.workspace_root.glob(
            "project*/docs/story_job/story_plan.json"
        ):
            project_root = plan_path.parents[2].resolve()
            relative = project_root.relative_to(self.workspace_root).as_posix()
            project_id = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:12]
            projects[project_id] = {
                "root": project_root,
                "story_plan": plan_path.resolve(),
                "job_dir": plan_path.parent.resolve(),
            }
        self._projects = projects

    def _project(self, project_id: str) -> dict[str, Path]:
        project = self._projects.get(project_id)
        if not project:
            self.refresh_projects()
            project = self._projects.get(project_id)
        if not project:
            raise KeyError("Project was not found")
        return project

    @staticmethod
    def _resolve_document_path(
        raw_path: Any,
        fallback: Path,
        plan_path: Path,
    ) -> Path:
        raw = str(raw_path or "").strip()
        if not raw:
            return fallback.resolve()
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = plan_path.parent / candidate
        return candidate.resolve()

    def _documents(self, project_id: str) -> dict[str, Any]:
        project = self._project(project_id)
        plan_path = project["story_plan"]
        plan = read_json(plan_path)
        evidence_path = self._resolve_document_path(
            plan.get("evidence_pack_path"),
            project["job_dir"] / "evidence_pack.json",
            plan_path,
        )
        analysis_path = self._resolve_document_path(
            plan.get("story_analysis_path"),
            project["job_dir"] / "story_analysis.json",
            plan_path,
        )
        narration_path = project["job_dir"] / "narration_plan.json"
        evidence = read_json(evidence_path)
        analysis = read_json(analysis_path)
        narration = read_json(narration_path) if narration_path.is_file() else {}
        return {
            "project": project,
            "plan": plan,
            "plan_path": plan_path,
            "evidence": evidence,
            "evidence_path": evidence_path,
            "analysis": analysis,
            "analysis_path": analysis_path,
            "narration": narration,
            "narration_path": narration_path.resolve(),
        }

    def _manifest(self, project: dict[str, Path]) -> tuple[Path | None, dict[str, Any]]:
        candidates = list(project["root"].glob("outputs/narration_manifest*.json"))
        candidates.extend(project["job_dir"].glob("narration_manifest*.json"))
        candidates = [item.resolve() for item in candidates if item.is_file()]
        if not candidates:
            return None, {}
        manifest_path = max(candidates, key=lambda item: item.stat().st_mtime)
        return manifest_path, read_json(manifest_path)

    @staticmethod
    def _source_registry_path(project: dict[str, Path]) -> Path:
        return project["root"] / ".story_editor_cache" / "sources.json"

    def _source_registry(self, project: dict[str, Path]) -> dict[str, dict[str, Any]]:
        path = self._source_registry_path(project)
        if not path.is_file():
            return {}
        payload = read_json(path)
        return {
            str(item["id"]): item
            for item in payload.get("sources", [])
            if isinstance(item, dict) and item.get("id") and item.get("path")
        }

    @staticmethod
    def _probe_video(path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [
                resolve_executable("ffprobe"),
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        payload = json.loads(result.stdout)
        video = next(
            (item for item in payload.get("streams", []) if item.get("codec_type") == "video"),
            None,
        )
        if not video:
            raise ValueError("文件中没有视频轨")
        audio_present = any(
            item.get("codec_type") == "audio" for item in payload.get("streams", [])
        )
        raw_rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
        numerator, _, denominator = raw_rate.partition("/")
        fps = as_float(numerator) / max(1.0, as_float(denominator, 1.0))
        return {
            "duration_sec": as_float(payload.get("format", {}).get("duration")),
            "width": int(video.get("width", 0) or 0),
            "height": int(video.get("height", 0) or 0),
            "fps": fps,
            "audio_present": audio_present,
        }

    def register_source(self, project_id: str, path_value: str) -> dict[str, Any]:
        path = Path(path_value.strip().strip('"')).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"视频素材不存在: {path}")
        metadata = self._probe_video(path)
        if metadata["duration_sec"] <= 0:
            raise ValueError("无法读取视频素材时长")
        project = self._project(project_id)
        source_id = "source-" + hashlib.sha1(str(path).casefold().encode()).hexdigest()[:12]
        registry = self._source_registry(project)
        stored = {
            "id": source_id,
            "path": str(path),
            "filename": path.name,
            **metadata,
        }
        registry[source_id] = stored
        write_json_atomic(
            self._source_registry_path(project),
            {"schema_version": "1.0", "sources": list(registry.values())},
        )
        return {
            key: value for key, value in stored.items() if key != "path"
        } | {
            "media_url": f"/api/story-editor/projects/{project_id}/media/{source_id}",
        }

    def _source_path_by_id(
        self,
        docs: dict[str, Any],
        source_id: str,
    ) -> Path:
        if not source_id or source_id == "source-main":
            raw = str(
                docs["evidence"].get("source", {}).get("video_path")
                or docs["plan"].get("source", {}).get("video_path", "")
            )
        else:
            item = self._source_registry(docs["project"]).get(source_id)
            if not item:
                raise FileNotFoundError(f"素材源不存在: {source_id}")
            raw = str(item["path"])
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"视频素材不存在: {path}")
        return path

    def list_projects(self) -> list[dict[str, Any]]:
        self.refresh_projects()
        results: list[dict[str, Any]] = []
        for project_id in sorted(self._projects):
            try:
                project = self._project(project_id)
                plan_path = project["story_plan"]
                plan = read_json(plan_path)
                segments = list(plan.get("segments", []))
                duration = sum(
                    max(0.0, as_float(item.get("output_end_sec")) - as_float(item.get("output_start_sec")))
                    for item in segments
                )
                results.append(
                    {
                        "id": project_id,
                        "name": project["root"].name,
                        "jobId": str(plan.get("job_id", "")),
                        "clipCount": len(segments),
                        "durationSec": round(duration, 3),
                        "modifiedAt": datetime.fromtimestamp(
                            plan_path.stat().st_mtime
                        ).astimezone().isoformat(timespec="seconds"),
                    }
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return results

    @staticmethod
    def _segment_for_output(
        segments: list[dict[str, Any]],
        start_sec: float,
        end_sec: float,
    ) -> dict[str, Any] | None:
        midpoint = (start_sec + end_sec) / 2
        for segment in segments:
            start = as_float(segment.get("output_start_sec"))
            end = as_float(segment.get("output_end_sec"))
            if start <= midpoint <= end:
                return segment
        candidates = [
            segment
            for segment in segments
            if overlaps(
                start_sec,
                end_sec,
                as_float(segment.get("output_start_sec")),
                as_float(segment.get("output_end_sec")),
            )
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda segment: min(end_sec, as_float(segment["output_end_sec"]))
            - max(start_sec, as_float(segment["output_start_sec"])),
        )

    @classmethod
    def _anchor_item(
        cls,
        segments: list[dict[str, Any]],
        item: dict[str, Any],
    ) -> dict[str, Any] | None:
        start = as_float(item.get("start_sec"))
        end = as_float(item.get("end_sec"))
        segment = cls._segment_for_output(segments, start, end)
        if not segment:
            return None
        segment_start = as_float(segment.get("output_start_sec"))
        segment_duration = as_float(segment.get("output_end_sec")) - segment_start
        local_start = min(max(0.0, start - segment_start), segment_duration)
        local_end = min(max(local_start + 0.01, end - segment_start), segment_duration)
        return {
            **item,
            "segment_id": str(segment["id"]),
            "local_start_sec": round(local_start, 3),
            "local_end_sec": round(local_end, 3),
        }

    def _source_subtitle_items(
        self,
        segments: list[dict[str, Any]],
        evidence: dict[str, Any],
        source_windows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not source_windows:
            return []
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for segment in segments:
            output_start = as_float(segment.get("output_start_sec"))
            output_end = as_float(segment.get("output_end_sec"))
            playback_rate = max(0.01, as_float(segment.get("playback_rate"), 1.0))
            source_start = as_float(segment.get("source_start_sec"))
            for window in source_windows:
                window_start = as_float(window.get("start_sec"))
                window_end = as_float(window.get("end_sec"))
                if not overlaps(output_start, output_end, window_start, window_end):
                    continue
                local_window_start = max(output_start, window_start) - output_start
                local_window_end = min(output_end, window_end) - output_start
                source_window_start = source_start + local_window_start * playback_rate
                source_window_end = source_start + local_window_end * playback_rate
                for cue in evidence.get("subtitles", []):
                    cue_start = as_float(cue.get("start_sec"))
                    cue_end = as_float(cue.get("end_sec"))
                    if not overlaps(cue_start, cue_end, source_window_start, source_window_end):
                        continue
                    key = (str(segment["id"]), str(cue.get("id", "")))
                    if key in seen:
                        continue
                    seen.add(key)
                    local_start = max(0.0, (cue_start - source_start) / playback_rate)
                    local_end = min(
                        output_end - output_start,
                        (cue_end - source_start) / playback_rate,
                    )
                    if local_end <= local_start:
                        continue
                    source_text = str(cue.get("source_text", "")).strip()
                    target_text = str(cue.get("target_text", "")).strip()
                    items.append(
                        {
                            "id": f"source-{segment['id']}-{cue.get('id', len(items) + 1)}",
                            "segment_id": str(segment["id"]),
                            "local_start_sec": round(local_start, 3),
                            "local_end_sec": round(local_end, 3),
                            "source_text": source_text,
                            "target_text": target_text,
                            "text": target_text or source_text,
                            "kind": "source_dialogue",
                            "editable": False,
                        }
                    )
        return items

    def load_timeline(self, project_id: str, revision_id: str | None = None) -> dict[str, Any]:
        docs = self._documents(project_id)
        if revision_id:
            revision_dir = safe_child(docs["project"]["root"] / "revisions", revision_id)
            timeline_path = revision_dir / "timeline_project.json"
            if not timeline_path.is_file():
                raise FileNotFoundError("Revision timeline was not found")
            timeline = read_json(timeline_path)
            timeline["revisionId"] = revision_id
            return timeline

        plan = docs["plan"]
        evidence = docs["evidence"]
        narration = docs["narration"]
        segments = list(plan.get("segments", []))
        manifest_path, manifest = self._manifest(docs["project"])
        manifest_blocks = {
            str(item.get("id")): item for item in manifest.get("blocks", [])
        }

        clips: list[dict[str, Any]] = []
        original_audio: list[dict[str, Any]] = []
        for segment in segments:
            clip_id = str(segment.get("id", ""))
            source_start = as_float(segment.get("source_start_sec"))
            source_end = as_float(segment.get("source_end_sec"))
            output_start = as_float(segment.get("output_start_sec"))
            output_end = as_float(segment.get("output_end_sec"))
            clip = {
                "id": clip_id,
                "base_segment_id": clip_id,
                "source_id": str(segment.get("source_id", "source-main")),
                "label": str(segment.get("story_reason") or clip_id),
                "source_start_sec": source_start,
                "source_end_sec": source_end,
                "output_start_sec": output_start,
                "output_end_sec": output_end,
                "duration_sec": round(output_end - output_start, 3),
                "playback_rate": as_float(segment.get("playback_rate"), 1.0),
                "kind": str(segment.get("kind", "visual")),
                "story_role": str(segment.get("story_role", "development")),
                "audio_mode": str(segment.get("audio_mode", "source")),
                "transition": str(segment.get("transition", "cut")),
                "transition_duration_sec": as_float(
                    segment.get("transition_duration_sec"), 0.5
                ),
                "fade_in_sec": as_float(segment.get("fade_in_sec")),
                "fade_out_sec": as_float(segment.get("fade_out_sec")),
                "volume_keyframes": list(segment.get("volume_keyframes", [])),
                "story_reason": str(segment.get("story_reason", "")),
                "analysis_refs": list(segment.get("analysis_refs", [])),
                "source_subtitle_ids": list(segment.get("source_subtitle_ids", [])),
                "source_scene_ids": list(segment.get("source_scene_ids", [])),
                "source_text": str(segment.get("source_text", "")),
                "target_text": str(segment.get("target_text", "")),
                "speaker": str(segment.get("speaker", "")),
                "thumbnail_url": (
                    f"/api/story-editor/projects/{project_id}/thumbnail"
                    f"?source={segment.get('source_id', 'source-main')}"
                    f"&time={source_start + max(0.0, source_end - source_start) / 2:.3f}"
                ),
            }
            clips.append(clip)
            original_audio.append(
                {
                    "id": f"audio-{clip_id}",
                    "segment_id": clip_id,
                    "local_start_sec": 0.0,
                    "local_end_sec": round(output_end - output_start, 3),
                    "volume": as_float(
                        narration.get("settings", {}).get("original_audio_volume"),
                        0.3,
                    ),
                }
            )

        narration_items: list[dict[str, Any]] = []
        narration_subtitles: list[dict[str, Any]] = []
        for block in narration.get("blocks", []):
            block_id = str(block.get("id", ""))
            anchored = self._anchor_item(
                segments,
                {
                    "id": block_id,
                    "start_sec": block.get("start_sec"),
                    "end_sec": block.get("end_sec"),
                    "text": str(block.get("text", "")),
                    "original_text": str(block.get("text", "")),
                    "generated_text": str(block.get("text", "")),
                    "subtitle_text": str(block.get("subtitle_text") or block.get("text", "")),
                    "purpose": str(block.get("purpose", "")),
                    "evidence_refs": list(block.get("evidence_refs", [])),
                    "asset_id": block_id if block_id in manifest_blocks else "",
                    "audio_stale": False,
                    "audio_url": (
                        f"/api/story-editor/projects/{project_id}/narration/{block_id}"
                        if block_id in manifest_blocks
                        else ""
                    ),
                },
            )
            if not anchored:
                continue
            anchored.pop("start_sec", None)
            anchored.pop("end_sec", None)
            narration_items.append(anchored)
            narration_subtitles.append(
                {
                    "id": f"subtitle-{block_id}",
                    "segment_id": anchored["segment_id"],
                    "local_start_sec": anchored["local_start_sec"],
                    "local_end_sec": anchored["local_end_sec"],
                    "text": anchored["subtitle_text"],
                    "source_text": "",
                    "target_text": anchored["subtitle_text"],
                    "kind": "narration",
                    "editable": False,
                }
            )

        source_audio_items: list[dict[str, Any]] = []
        for window in narration.get("source_audio_windows", []):
            anchored = self._anchor_item(segments, dict(window))
            if not anchored:
                continue
            anchored.pop("start_sec", None)
            anchored.pop("end_sec", None)
            source_audio_items.append(anchored)

        subtitle_items = narration_subtitles + self._source_subtitle_items(
            segments,
            evidence,
            list(narration.get("source_audio_windows", [])),
        )
        subtitle_items.sort(
            key=lambda item: (
                next(
                    (
                        index
                        for index, clip in enumerate(clips)
                        if clip["id"] == item["segment_id"]
                    ),
                    len(clips),
                ),
                as_float(item.get("local_start_sec")),
            )
        )

        source = evidence.get("source", {})
        source_video = Path(str(source.get("video_path") or plan.get("source", {}).get("video_path", "")))
        revisions_dir = docs["project"]["root"] / "revisions"
        revisions = []
        if revisions_dir.is_dir():
            for item in sorted(revisions_dir.glob("rev-*"), reverse=True):
                if (item / "timeline_project.json").is_file():
                    revisions.append(item.name)

        sources = [
            {
                "id": "source-main",
                "filename": source_video.name,
                "duration_sec": as_float(source.get("duration_sec")),
                "width": int(source.get("video", {}).get("width", 0) or 0),
                "height": int(source.get("video", {}).get("height", 0) or 0),
                "fps": as_float(source.get("video", {}).get("fps")),
                "audio_present": bool(source.get("audio", {}).get("present", True)),
                "media_url": f"/api/story-editor/projects/{project_id}/media/source-main",
            }
        ]
        for item in self._source_registry(docs["project"]).values():
            sources.append(
                {
                    key: value for key, value in item.items() if key != "path"
                }
                | {
                    "media_url": (
                        f"/api/story-editor/projects/{project_id}/media/{item['id']}"
                    )
                }
            )

        return {
            "schema_version": "1.0",
            "projectId": project_id,
            "projectName": docs["project"]["root"].name,
            "jobId": str(plan.get("job_id", "")),
            "revisionId": None,
            "source": {
                "filename": source_video.name,
                "duration_sec": as_float(source.get("duration_sec")),
                "width": int(source.get("video", {}).get("width", 0) or 0),
                "height": int(source.get("video", {}).get("height", 0) or 0),
                "fps": as_float(source.get("video", {}).get("fps")),
                "language": str(source.get("language") or plan.get("source", {}).get("language", "")),
                "media_url": f"/api/story-editor/projects/{project_id}/media",
            },
            "sources": sources,
            "settings": {
                "snap_sec": 0.1,
                "burn_subtitles": "none",
                "original_audio_volume": as_float(
                    narration.get("settings", {}).get("original_audio_volume"),
                    0.3,
                ),
                "source_audio_volume": as_float(
                    narration.get("settings", {}).get("source_audio_volume"),
                    1.0,
                ),
            },
            "clips": clips,
            "tracks": {
                "original_audio": original_audio,
                "narration": narration_items,
                "source_audio": source_audio_items,
                "subtitles": subtitle_items,
            },
            "assets": {
                "narration_manifest": manifest_path.name if manifest_path else "",
                "narration_ready": bool(manifest_blocks),
            },
            "revisions": revisions,
        }

    @staticmethod
    def _validate_timeline(timeline: dict[str, Any], source_duration: float) -> list[str]:
        errors: list[str] = []
        clips = timeline.get("clips")
        if not isinstance(clips, list) or not clips:
            return ["Timeline must contain at least one video clip"]
        ids: set[str] = set()
        source_durations = {
            str(item.get("id")): as_float(item.get("duration_sec"))
            for item in timeline.get("sources", [])
        }
        source_durations.setdefault("source-main", source_duration)
        for index, clip in enumerate(clips, start=1):
            clip_id = str(clip.get("id", "")).strip()
            if not clip_id or not SAFE_ID.fullmatch(clip_id):
                errors.append(f"Clip {index} has an invalid id")
            elif clip_id in ids:
                errors.append(f"Duplicate clip id: {clip_id}")
            ids.add(clip_id)
            start = as_float(clip.get("source_start_sec"), -1.0)
            end = as_float(clip.get("source_end_sec"), -1.0)
            source_id = str(clip.get("source_id", "source-main"))
            clip_source_duration = source_durations.get(source_id)
            if clip_source_duration is None:
                errors.append(f"{clip_id or index} points to a missing source: {source_id}")
                clip_source_duration = 0.0
            if start < 0 or end > clip_source_duration + 0.05:
                errors.append(f"{clip_id or index} exceeds source media bounds")
            if end - start < MIN_CLIP_DURATION_SEC:
                errors.append(f"{clip_id or index} is shorter than {MIN_CLIP_DURATION_SEC}s")
            transition = str(clip.get("transition", "cut"))
            if transition not in {"cut", "crossfade"}:
                errors.append(f"{clip_id or index} uses an unsupported transition")
            transition_duration = as_float(
                clip.get("transition_duration_sec"), 0.5
            )
            if transition == "crossfade" and not 0.05 <= transition_duration <= 3.0:
                errors.append(
                    f"{clip_id or index} crossfade duration must be 0.05-3.0 seconds"
                )
        tracks = timeline.get("tracks", {})
        for track_name in ("narration", "source_audio", "subtitles"):
            for item in tracks.get(track_name, []):
                segment_id = str(item.get("segment_id", ""))
                if segment_id not in ids:
                    errors.append(f"{track_name} item {item.get('id')} points to a missing clip")
                    continue
                clip = next(entry for entry in clips if str(entry.get("id")) == segment_id)
                duration = (
                    as_float(clip.get("source_end_sec"))
                    - as_float(clip.get("source_start_sec"))
                ) / max(0.01, as_float(clip.get("playback_rate"), 1.0))
                local_start = as_float(item.get("local_start_sec"), -1.0)
                local_end = as_float(item.get("local_end_sec"), -1.0)
                if local_start < 0 or local_end <= local_start or local_end > duration + 0.05:
                    errors.append(
                        f"{track_name} item {item.get('id')} is outside clip {segment_id}"
                    )
        return errors

    @staticmethod
    def _clip_output_map(clips: list[dict[str, Any]]) -> tuple[dict[str, float], float]:
        output_starts: dict[str, float] = {}
        cursor = 0.0
        previous_duration = 0.0
        for index, clip in enumerate(clips):
            duration = (
                as_float(clip["source_end_sec"])
                - as_float(clip["source_start_sec"])
            ) / max(0.01, as_float(clip.get("playback_rate"), 1.0))
            if index and str(clip.get("transition", "cut")) == "crossfade":
                requested = max(0.0, as_float(clip.get("transition_duration_sec"), 0.5))
                cursor -= min(requested, previous_duration / 2, duration / 2)
            output_starts[str(clip["id"])] = cursor
            cursor += duration
            previous_duration = duration
        return output_starts, cursor

    @staticmethod
    def _overlap_ids(
        items: list[dict[str, Any]],
        start_sec: float,
        end_sec: float,
    ) -> list[str]:
        return [
            str(item.get("id"))
            for item in items
            if overlaps(
                start_sec,
                end_sec,
                as_float(item.get("start_sec")),
                as_float(item.get("end_sec")),
            )
        ]

    def _compile_revision(
        self,
        docs: dict[str, Any],
        timeline: dict[str, Any],
        revision_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, float]]:
        clips = list(timeline["clips"])
        output_starts, total_duration = self._clip_output_map(clips)
        evidence = docs["evidence"]
        base_plan = copy.deepcopy(docs["plan"])
        timeline_sources = {
            str(item.get("id")): item for item in timeline.get("sources", [])
        }
        segments: list[dict[str, Any]] = []
        for order, clip in enumerate(clips, start=1):
            start = as_float(clip["source_start_sec"])
            end = as_float(clip["source_end_sec"])
            rate = max(0.01, as_float(clip.get("playback_rate"), 1.0))
            duration = (end - start) / rate
            output_start = output_starts[str(clip["id"])]
            source_id = str(clip.get("source_id", "source-main"))
            external_source = source_id != "source-main"
            subtitle_ids = (
                []
                if external_source
                else self._overlap_ids(evidence.get("subtitles", []), start, end)
            )
            scene_ids = (
                []
                if external_source
                else self._overlap_ids(evidence.get("scenes", []), start, end)
            )
            subtitle_lookup = {
                str(item.get("id")): item for item in evidence.get("subtitles", [])
            }
            selected_subtitles = [subtitle_lookup[item] for item in subtitle_ids]
            source_text = " ".join(
                str(item.get("source_text", "")).strip()
                for item in selected_subtitles
                if str(item.get("source_text", "")).strip()
            )
            target_text = " ".join(
                str(item.get("target_text", "")).strip()
                for item in selected_subtitles
                if str(item.get("target_text", "")).strip()
            )
            speakers = {
                str(item.get("speaker", "")).strip()
                for item in selected_subtitles
                if str(item.get("speaker", "")).strip()
            }
            compiled_segment = {
                    "id": str(clip["id"]),
                    "source_id": source_id,
                    "output_order": order,
                    "kind": (
                        "visual"
                        if external_source
                        else str(clip.get("kind", "visual"))
                    ),
                    "story_role": str(clip.get("story_role", "development")),
                    "source_start_sec": round(start, 3),
                    "source_end_sec": round(end, 3),
                    "output_start_sec": round(output_start, 3),
                    "output_end_sec": round(output_start + duration, 3),
                    "playback_rate": rate,
                    "source_subtitle_ids": subtitle_ids,
                    "source_scene_ids": scene_ids,
                    "analysis_refs": list(clip.get("analysis_refs", [])),
                    "source_text": source_text,
                    "target_text": target_text,
                    "speaker": next(iter(speakers)) if len(speakers) == 1 else "",
                    "audio_mode": str(clip.get("audio_mode", "source")),
                    "story_reason": str(clip.get("story_reason") or clip.get("label", "")),
                    "transition": "cut",
                    "transition_duration_sec": as_float(
                        clip.get("transition_duration_sec"), 0.5
                    ),
                    "fade_in_sec": as_float(clip.get("fade_in_sec")),
                    "fade_out_sec": as_float(clip.get("fade_out_sec")),
                    "volume_keyframes": list(clip.get("volume_keyframes", [])),
                    "output_width": int(
                        evidence.get("source", {}).get("video", {}).get("width", 1920)
                    ),
                    "output_height": int(
                        evidence.get("source", {}).get("video", {}).get("height", 1080)
                    ),
                    "output_fps": as_float(
                        evidence.get("source", {}).get("video", {}).get("fps"),
                        25.0,
                    ),
                }
            compiled_segment["transition"] = str(clip.get("transition", "cut"))
            if external_source:
                source_meta = timeline_sources.get(source_id, {})
                source_path = self._source_path_by_id(docs, source_id)
                compiled_segment["source_video_path"] = str(source_path)
                compiled_segment["source_duration_sec"] = as_float(
                    source_meta.get("duration_sec")
                )
            segments.append(compiled_segment)

        story_plan = base_plan
        story_plan["segments"] = segments
        story_plan.setdefault("settings", {})["target_duration_sec"] = round(total_duration, 3)
        story_plan["settings"]["duration_tolerance_ratio"] = 0.005
        story_plan.setdefault("output", {})["video_path"] = str(
            (revision_dir / "render" / "story_revision.mp4").resolve()
        )
        story_plan["output"]["source_subtitle_path"] = str(
            (revision_dir / "render" / "story_revision_source.srt").resolve()
        )
        story_plan["output"]["translated_subtitle_path"] = str(
            (revision_dir / "render" / "story_revision_zh-CN.srt").resolve()
        )
        story_plan["output"]["bilingual_subtitle_path"] = str(
            (revision_dir / "render" / "story_revision_bilingual.ass").resolve()
        )
        story_plan["output"]["qa_report_path"] = str(
            (revision_dir / "render" / "story_revision_qa.md").resolve()
        )

        base_narration = copy.deepcopy(docs["narration"])
        segment_ids = {str(item["id"]) for item in segments}
        analysis_ids: set[str] = set()
        for key in (
            "events",
            "themes",
            "visual_findings",
            "continuity_constraints",
            "story_options",
        ):
            analysis_ids.update(
                str(item.get("id")) for item in docs["analysis"].get(key, [])
            )

        def absolute_item(item: dict[str, Any]) -> dict[str, Any]:
            segment_id = str(item["segment_id"])
            start = output_starts[segment_id] + as_float(item["local_start_sec"])
            end = output_starts[segment_id] + as_float(item["local_end_sec"])
            original_refs = [str(value) for value in item.get("evidence_refs", [])]
            refs = [segment_id]
            refs.extend(value for value in original_refs if value in analysis_ids)
            result = {
                key: copy.deepcopy(value)
                for key, value in item.items()
                if key
                not in {
                    "segment_id",
                    "local_start_sec",
                    "local_end_sec",
                    "audio_url",
                    "asset_id",
                    "editable",
                    "kind",
                    "source_text",
                    "target_text",
                }
            }
            result["start_sec"] = round(start, 3)
            result["end_sec"] = round(end, 3)
            result["evidence_refs"] = list(dict.fromkeys(refs))
            if item.get("asset_id"):
                result["audio_asset_id"] = str(item["asset_id"])
            if item.get("audio_stale"):
                result["audio_stale"] = True
            return result

        narration_blocks = [
            absolute_item(item)
            for item in timeline.get("tracks", {}).get("narration", [])
            if str(item.get("segment_id")) in segment_ids
        ]
        source_audio_windows = [
            absolute_item(item)
            for item in timeline.get("tracks", {}).get("source_audio", [])
            if str(item.get("segment_id")) in segment_ids
        ]
        narration_plan = base_narration or {
            "schema_version": "1.0",
            "job_id": story_plan.get("job_id"),
            "style": "film_commentary",
            "settings": {},
            "tts": {},
        }
        narration_plan["blocks"] = narration_blocks
        narration_plan["source_audio_windows"] = source_audio_windows
        narration_plan.setdefault("settings", {}).update(
            {
                "audio_strategy": (
                    "hybrid_source_anchors"
                    if source_audio_windows
                    else "narration_only"
                ),
                "original_audio_volume": as_float(
                    timeline.get("settings", {}).get("original_audio_volume"), 0.3
                ),
                "source_audio_volume": as_float(
                    timeline.get("settings", {}).get("source_audio_volume"), 1.0
                ),
            }
        )
        return story_plan, narration_plan, output_starts

    def save_revision(
        self,
        project_id: str,
        timeline: dict[str, Any],
        note: str = "",
    ) -> dict[str, Any]:
        docs = self._documents(project_id)
        source_duration = as_float(docs["evidence"].get("source", {}).get("duration_sec"))
        errors = self._validate_timeline(timeline, source_duration)
        if errors:
            raise ValueError("; ".join(errors[:20]))
        revisions_dir = docs["project"]["root"] / "revisions"
        revisions_dir.mkdir(parents=True, exist_ok=True)
        base_id = datetime.now().astimezone().strftime("rev-%Y%m%d-%H%M%S")
        revision_id = base_id
        suffix = 2
        while (revisions_dir / revision_id).exists():
            revision_id = f"{base_id}-{suffix}"
            suffix += 1
        revision_dir = safe_child(revisions_dir, revision_id)
        revision_dir.mkdir(parents=True)

        stored_timeline = copy.deepcopy(timeline)
        stored_timeline["projectId"] = project_id
        stored_timeline["revisionId"] = revision_id
        stored_timeline["savedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        stored_timeline["note"] = note.strip()
        story_plan, narration_plan, _ = self._compile_revision(
            docs, stored_timeline, revision_dir
        )
        write_json_atomic(revision_dir / "timeline_project.json", stored_timeline)
        write_json_atomic(revision_dir / "story_plan.json", story_plan)
        write_json_atomic(revision_dir / "narration_plan.json", narration_plan)
        output_starts, _ = self._clip_output_map(list(stored_timeline["clips"]))
        subtitle_cues = []
        for item in stored_timeline.get("tracks", {}).get("subtitles", []):
            segment_id = str(item.get("segment_id", ""))
            if segment_id not in output_starts:
                continue
            subtitle_cues.append(
                {
                    "start_sec": output_starts[segment_id]
                    + as_float(item.get("local_start_sec")),
                    "end_sec": output_starts[segment_id]
                    + as_float(item.get("local_end_sec")),
                    "text": str(item.get("text", "")),
                }
            )
        subtitle_cues.sort(key=lambda item: (item["start_sec"], item["end_sec"]))
        write_srt(revision_dir / "timeline_subtitles.srt", subtitle_cues)
        write_json_atomic(
            revision_dir / "render_state.json",
            {
                "revisionId": revision_id,
                "status": "saved",
                "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
        )
        return {
            "revisionId": revision_id,
            "revisionDir": str(revision_dir),
            "savedAt": stored_timeline["savedAt"],
        }

    def _manifest_audio_paths(self, docs: dict[str, Any]) -> dict[str, Path]:
        manifest_path, manifest = self._manifest(docs["project"])
        if not manifest_path:
            return {}
        result: dict[str, Path] = {}
        for block in manifest.get("blocks", []):
            block_id = str(block.get("id", ""))
            raw = str(block.get("normalized_audio_path", "")).strip()
            if not block_id or not raw:
                continue
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = manifest_path.parent / path
            if path.is_file():
                result[block_id] = path.resolve()
        return result

    @staticmethod
    def _custom_narration_dir(project: dict[str, Path]) -> Path:
        return project["root"] / ".story_editor_cache" / "narration" / "minimax"

    def _all_narration_assets(self, docs: dict[str, Any]) -> dict[str, Path]:
        result = self._manifest_audio_paths(docs)
        cache_dir = self._custom_narration_dir(docs["project"])
        if cache_dir.is_dir():
            for path in cache_dir.glob("custom-*.wav"):
                if path.is_file() and path.stat().st_size > 0:
                    result[path.stem] = path.resolve()
        return result

    def narration_asset(self, project_id: str, block_id: str) -> Path:
        if not SAFE_ID.fullmatch(block_id):
            raise ValueError("Invalid narration block id")
        docs = self._documents(project_id)
        path = self._all_narration_assets(docs).get(block_id)
        if not path:
            raise FileNotFoundError("Narration audio was not found")
        return path

    @staticmethod
    def _probe_audio_duration(path: Path) -> float:
        result = subprocess.run(
            [
                resolve_executable("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        raw_duration = result.stdout.strip()
        if not raw_duration or raw_duration.upper() == "N/A":
            raise RuntimeError(f"音频没有可识别的有效时长: {path.name}")
        duration = float(raw_duration)
        if duration < 0.05:
            raise RuntimeError(f"音频时长异常（{duration:.3f} 秒）: {path.name}")
        return duration

    def regenerate_minimax_block(
        self,
        project_id: str,
        *,
        text: str,
        slot_duration_sec: float,
        voice_id: str = "",
        model: str = "",
        speed: float | None = None,
    ) -> dict[str, Any]:
        clean_text = re.sub(r"\s+", " ", text or "").strip()
        if not clean_text:
            raise ValueError("旁白文本不能为空")
        if slot_duration_sec <= 0.1:
            raise ValueError("旁白时间槽必须大于 0.1 秒")
        docs = self._documents(project_id)
        tts = dict(docs["narration"].get("tts", {}))
        selected_voice = voice_id.strip() or str(
            tts.get("voice_id", "female-shaonv")
        )
        selected_model = model.strip() or str(
            tts.get("model", "speech-2.8-turbo")
        )
        selected_speed = float(speed if speed is not None else tts.get("speed", 1.0))
        identity = hashlib.sha256(
            json.dumps(
                {
                    "provider": "minimax",
                    "text": clean_text,
                    "voice_id": selected_voice,
                    "model": selected_model,
                    "speed": selected_speed,
                    "slot_duration_sec": round(slot_duration_sec, 3),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cache_dir = self._custom_narration_dir(docs["project"])
        cache_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"custom-{identity[:20]}"
        normalized_path = cache_dir / f"{asset_id}.wav"
        raw_path = cache_dir / f"raw-{identity}.wav"
        cache_hit = normalized_path.is_file() and normalized_path.stat().st_size > 0
        if cache_hit:
            try:
                self._probe_audio_duration(normalized_path)
            except RuntimeError:
                normalized_path.unlink(missing_ok=True)
                cache_hit = False
        if not cache_hit:
            try:
                from dotenv import load_dotenv

                load_dotenv(REPO_ROOT / ".env", override=False)
            except ImportError:
                pass
            try:
                from src.minimax_tts_client import MiniMaxTTSClient
            except ModuleNotFoundError:
                from minimax_tts_client import MiniMaxTTSClient

            client = MiniMaxTTSClient(
                model=selected_model,
                voice_id=selected_voice,
                speed=selected_speed,
                language_boost=str(tts.get("language_boost", "Chinese")),
            )
            client.synthesize(clean_text, raw_path)
            try:
                raw_duration = self._probe_audio_duration(raw_path)
            except RuntimeError:
                raw_path.unlink(missing_ok=True)
                normalized_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "MiniMax 返回了没有有效语音内容的 WAV，请稍后重试或调整文本"
                ) from None
            max_speedup = as_float(
                docs["narration"].get("settings", {}).get("max_audio_speedup"),
                1.25,
            )
            required_speedup = max(1.0, raw_duration / slot_duration_sec)
            if required_speedup > max_speedup + 0.001:
                raise ValueError(
                    f"生成语音 {raw_duration:.2f} 秒，超过 {slot_duration_sec:.2f} 秒时间槽；"
                    f"需要 {required_speedup:.2f}x，加快上限为 {max_speedup:.2f}x"
                )
            subprocess.run(
                [
                    resolve_executable("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(raw_path),
                    "-af",
                    (
                        "aresample=48000,"
                        "aformat=sample_fmts=s16:channel_layouts=stereo,"
                        f"atempo={required_speedup:.8f}"
                    ),
                    "-t",
                    f"{slot_duration_sec:.6f}",
                    "-c:a",
                    "pcm_s16le",
                    "-y",
                    str(normalized_path),
                ],
                check=True,
                capture_output=True,
            )
        try:
            duration = self._probe_audio_duration(normalized_path)
        except RuntimeError:
            normalized_path.unlink(missing_ok=True)
            raise
        return {
            "assetId": asset_id,
            "audioUrl": (
                f"/api/story-editor/projects/{project_id}/narration/{asset_id}"
            ),
            "durationSec": round(duration, 3),
            "cacheHit": cache_hit,
            "voiceId": selected_voice,
            "model": selected_model,
            "speed": selected_speed,
        }

    def source_media(self, project_id: str, source_id: str = "source-main") -> Path:
        docs = self._documents(project_id)
        return self._source_path_by_id(docs, source_id)

    def thumbnail(
        self,
        project_id: str,
        time_sec: float,
        source_id: str = "source-main",
    ) -> Path:
        source = self.source_media(project_id, source_id)
        docs = self._documents(project_id)
        if source_id == "source-main":
            duration = as_float(docs["evidence"].get("source", {}).get("duration_sec"))
        else:
            duration = as_float(
                self._source_registry(docs["project"])
                .get(source_id, {})
                .get("duration_sec")
            )
        seek = min(max(0.0, time_sec), max(0.0, duration - 0.05))
        cache_dir = docs["project"]["root"] / ".story_editor_cache" / "thumbnails"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha1(f"{source}:{seek:.3f}".encode()).hexdigest()[:16]
        output = cache_dir / f"{cache_key}.jpg"
        lock = self._thumbnail_locks.setdefault(cache_key, threading.Lock())
        with lock:
            if not output.is_file() or output.stat().st_size == 0:
                command = [
                    resolve_executable("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{seek:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=320:-2",
                    "-q:v",
                    "4",
                    "-y",
                    str(output),
                ]
                subprocess.run(command, check=True, capture_output=True)
        return output

    def rewrite_text(
        self,
        *,
        text: str,
        instruction: str,
        context: str = "",
    ) -> dict[str, str]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("需要重写的文本不能为空")
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env", override=False)
        except ImportError:
            pass
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY，原文本保持不变")
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        )
        prompt = (
            "你是影视解说稿编辑。只重写用户提供的局部文本，不补写未经证据支持的剧情。"
            "保持人物、事实和叙事视角不变，长度变化控制在 20% 以内。只返回重写后的正文。"
        )
        user_content = f"修改要求：{instruction.strip() or '让表达更自然、紧凑'}\n"
        if context.strip():
            user_content += f"相邻上下文（仅用于衔接）：{context.strip()}\n"
        user_content += f"待重写文本：{clean_text}"
        response = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.35,
            max_tokens=800,
        )
        rewritten = str(response.choices[0].message.content or "").strip()
        if not rewritten:
            raise RuntimeError("DeepSeek 没有返回重写结果")
        return {"text": rewritten, "provider": "deepseek"}

    @staticmethod
    def _link_or_copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    def _build_aligned_narration(
        self,
        docs: dict[str, Any],
        revision_dir: Path,
        timeline: dict[str, Any],
        narration_plan: dict[str, Any],
    ) -> tuple[Path | None, Path | None]:
        blocks = list(narration_plan.get("blocks", []))
        if not blocks:
            return None, None
        audio_paths = self._all_narration_assets(docs)
        stale = [str(block.get("id")) for block in blocks if block.get("audio_stale")]
        if stale:
            raise ValueError(
                "旁白文本已修改但尚未重新生成语音: " + ", ".join(stale[:10])
            )
        missing = [
            str(block.get("id"))
            for block in blocks
            if str(block.get("audio_asset_id") or block.get("id")) not in audio_paths
        ]
        if missing:
            raise FileNotFoundError(
                "Narration cache is missing for blocks: " + ", ".join(missing[:10])
            )
        _, total_duration = self._clip_output_map(list(timeline["clips"]))
        input_dir = revision_dir / ".render_inputs"
        input_paths: list[Path] = []
        for index, block in enumerate(blocks):
            target = input_dir / f"narration-{index:04d}.wav"
            asset_id = str(block.get("audio_asset_id") or block["id"])
            self._link_or_copy(audio_paths[asset_id], target)
            input_paths.append(target)

        filter_lines: list[str] = []
        labels: list[str] = []
        for index, block in enumerate(blocks):
            delay_ms = max(0, round(as_float(block["start_sec"]) * 1000))
            slot_duration = max(0.01, as_float(block["end_sec"]) - as_float(block["start_sec"]))
            label = f"n{index}"
            filter_lines.append(
                f"[{index}:a]aresample=48000,atrim=0:{slot_duration:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
        filter_lines.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
            f"atrim=0:{total_duration:.3f}[outa]"
        )
        filter_script = revision_dir / "narration_mix.ffscript"
        filter_script.write_text(";\n".join(filter_lines), encoding="utf-8")
        narration_audio = revision_dir / "narration_aligned.wav"
        command = [resolve_executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
        for input_path in input_paths:
            command.extend(["-i", str(input_path)])
        command.extend(
            [
                "-filter_complex_script",
                str(filter_script),
                "-map",
                "[outa]",
                "-c:a",
                "pcm_s16le",
                str(narration_audio),
            ]
        )
        subprocess.run(command, check=True, capture_output=True)
        narration_srt = revision_dir / "narration_aligned.srt"
        write_srt(
            narration_srt,
            [
                {
                    "start_sec": block["start_sec"],
                    "end_sec": block["end_sec"],
                    "text": block.get("subtitle_text") or block.get("text", ""),
                }
                for block in blocks
            ],
        )
        return narration_audio, narration_srt

    def start_render(self, project_id: str, revision_id: str) -> dict[str, Any]:
        docs = self._documents(project_id)
        revision_dir = safe_child(docs["project"]["root"] / "revisions", revision_id)
        if not (revision_dir / "timeline_project.json").is_file():
            raise FileNotFoundError("Revision was not found")
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "projectId": project_id,
            "revisionId": revision_id,
            "status": "queued",
            "progress": 0,
            "message": "等待完整重新渲染",
            "logs": [],
            "outputUrl": "",
        }
        with self._jobs_lock:
            self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._render_worker,
            args=(job_id, docs, revision_dir),
            daemon=True,
        )
        thread.start()
        return copy.deepcopy(job)

    def _update_job(self, job_id: str, **updates: Any) -> None:
        with self._jobs_lock:
            self._jobs[job_id].update(updates)

    def _append_job_log(self, job_id: str, line: str) -> None:
        with self._jobs_lock:
            logs = self._jobs[job_id].setdefault("logs", [])
            logs.append(line.rstrip())
            del logs[:-200]

    def _render_worker(
        self,
        job_id: str,
        docs: dict[str, Any],
        revision_dir: Path,
    ) -> None:
        try:
            self._update_job(job_id, status="running", progress=2, message="准备修订数据")
            timeline = read_json(revision_dir / "timeline_project.json")
            story_plan = read_json(revision_dir / "story_plan.json")
            narration_plan = read_json(revision_dir / "narration_plan.json")
            self._update_job(job_id, progress=5, message="重建旁白时间轴")
            narration_audio, narration_srt = self._build_aligned_narration(
                docs, revision_dir, timeline, narration_plan
            )
            output = revision_dir / "render" / "story_revision.mp4"
            command = [
                sys.executable,
                str(RENDER_SCRIPT),
                str(revision_dir / "story_plan.json"),
                "--evidence",
                str(docs["evidence_path"]),
                "--analysis",
                str(docs["analysis_path"]),
                "--output",
                str(output),
                "--burn-subtitles",
                str(timeline.get("settings", {}).get("burn_subtitles", "none")),
                "--ffmpeg",
                resolve_executable("ffmpeg"),
                "--ffprobe",
                resolve_executable("ffprobe"),
                "--segment-cache-dir",
                str(
                    docs["project"]["root"]
                    / ".story_editor_cache"
                    / "segments"
                ),
            ]
            if timeline.get("tracks", {}).get("subtitles"):
                command.extend(
                    [
                        "--final-subtitle",
                        str(revision_dir / "timeline_subtitles.srt"),
                    ]
                )
            if narration_audio and narration_srt:
                command.extend(
                    [
                        "--narration-audio",
                        str(narration_audio),
                        "--narration-subtitle",
                        str(narration_srt),
                        "--narration-plan",
                        str(revision_dir / "narration_plan.json"),
                    ]
                )
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            clip_count = max(1, len(story_plan.get("segments", [])))
            pattern = re.compile(r"(?:Rendering|Cache hit)\s+(\d+)/(\d+)")
            assert process.stdout is not None
            for line in process.stdout:
                self._append_job_log(job_id, line)
                match = pattern.search(line)
                if match:
                    current = int(match.group(1))
                    progress = 8 + round((current / clip_count) * 78)
                    self._update_job(
                        job_id,
                        progress=min(progress, 86),
                        message=f"完整渲染片段 {current}/{clip_count}",
                    )
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"Renderer exited with code {return_code}")
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("Rendered video is missing")
            project_id = self.job(job_id)["projectId"]
            self._update_job(
                job_id,
                status="finished",
                progress=100,
                message="完整重新渲染完成",
                outputUrl=(
                    f"/api/story-editor/projects/{project_id}"
                    f"/revisions/{revision_dir.name}/output"
                ),
            )
            write_json_atomic(
                revision_dir / "render_state.json",
                {
                    "revisionId": revision_dir.name,
                    "status": "finished",
                    "output": str(output.resolve()),
                    "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
            )
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
            self._append_job_log(job_id, f"ERROR: {exc}")
            self._update_job(
                job_id,
                status="failed",
                message=str(exc),
            )
            write_json_atomic(
                revision_dir / "render_state.json",
                {
                    "revisionId": revision_dir.name,
                    "status": "failed",
                    "error": str(exc),
                    "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
            )

    def job(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("Render job was not found")
            return copy.deepcopy(job)

    def revision_output(self, project_id: str, revision_id: str) -> Path:
        project = self._project(project_id)
        revision_dir = safe_child(project["root"] / "revisions", revision_id)
        output = revision_dir / "render" / "story_revision.mp4"
        if not output.is_file():
            raise FileNotFoundError("Rendered revision was not found")
        return output


def create_app(workspace_root: Path = DEFAULT_WORKSPACE) -> Flask:
    app = Flask(__name__, static_folder=None)
    service = StoryTimelineService(workspace_root)
    app.config["STORY_TIMELINE_SERVICE"] = service

    @app.errorhandler(KeyError)
    @app.errorhandler(FileNotFoundError)
    def handle_not_found(error: Exception):
        return jsonify({"error": str(error).strip("'")}), 404

    @app.errorhandler(ValueError)
    def handle_bad_request(error: ValueError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(RuntimeError)
    @app.errorhandler(subprocess.SubprocessError)
    def handle_processing_error(error: Exception):
        return jsonify({"error": str(error)}), 502

    @app.get("/api/story-editor/health")
    def health():
        return jsonify({"ok": True, "workspace": str(service.workspace_root)})

    @app.get("/api/story-editor/projects")
    def projects():
        return jsonify({"projects": service.list_projects()})

    @app.get("/api/story-editor/projects/<project_id>")
    def project_timeline(project_id: str):
        revision_id = request.args.get("revision") or None
        return jsonify(service.load_timeline(project_id, revision_id))

    @app.get("/api/story-editor/projects/<project_id>/media")
    def project_media(project_id: str):
        path = service.source_media(project_id, "source-main")
        return send_file(path, conditional=True, mimetype="video/mp4")

    @app.get("/api/story-editor/projects/<project_id>/media/<source_id>")
    def project_source_media(project_id: str, source_id: str):
        path = service.source_media(project_id, source_id)
        return send_file(path, conditional=True, mimetype="video/mp4")

    @app.get("/api/story-editor/projects/<project_id>/thumbnail")
    def project_thumbnail(project_id: str):
        path = service.thumbnail(
            project_id,
            as_float(request.args.get("time")),
            str(request.args.get("source") or "source-main"),
        )
        return send_file(path, conditional=True, mimetype="image/jpeg", max_age=86400)

    @app.post("/api/story-editor/projects/<project_id>/sources")
    def add_source(project_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(service.register_source(project_id, str(payload.get("path", "")))), 201

    @app.post("/api/story-editor/rewrite")
    def rewrite_text():
        payload = request.get_json(silent=True) or {}
        return jsonify(
            service.rewrite_text(
                text=str(payload.get("text", "")),
                instruction=str(payload.get("instruction", "")),
                context=str(payload.get("context", "")),
            )
        )

    @app.get("/api/story-editor/projects/<project_id>/narration/<block_id>")
    def narration_audio(project_id: str, block_id: str):
        path = service.narration_asset(project_id, block_id)
        return send_file(path, conditional=True, mimetype="audio/wav", max_age=86400)

    @app.post("/api/story-editor/projects/<project_id>/tts/minimax")
    def regenerate_minimax(project_id: str):
        payload = request.get_json(silent=True) or {}
        result = service.regenerate_minimax_block(
            project_id,
            text=str(payload.get("text", "")),
            slot_duration_sec=as_float(payload.get("slotDurationSec")),
            voice_id=str(payload.get("voiceId", "")),
            model=str(payload.get("model", "")),
            speed=(
                as_float(payload.get("speed"))
                if payload.get("speed") is not None
                else None
            ),
        )
        return jsonify(result)

    @app.post("/api/story-editor/projects/<project_id>/revisions")
    def save_revision(project_id: str):
        payload = request.get_json(silent=True) or {}
        timeline = payload.get("timeline")
        if not isinstance(timeline, dict):
            raise ValueError("timeline must be a JSON object")
        result = service.save_revision(project_id, timeline, str(payload.get("note", "")))
        return jsonify(result), 201

    @app.post("/api/story-editor/projects/<project_id>/render")
    def render_revision(project_id: str):
        payload = request.get_json(silent=True) or {}
        revision_id = str(payload.get("revisionId", "")).strip()
        if not revision_id:
            raise ValueError("revisionId is required")
        return jsonify(service.start_render(project_id, revision_id)), 202

    @app.get("/api/story-editor/jobs/<job_id>")
    def render_job(job_id: str):
        return jsonify(service.job(job_id))

    @app.get(
        "/api/story-editor/projects/<project_id>/revisions/<revision_id>/output"
    )
    def rendered_output(project_id: str, revision_id: str):
        path = service.revision_output(project_id, revision_id)
        return send_file(path, conditional=True, mimetype="video/mp4")

    @app.get("/")
    @app.get("/story-editor")
    def editor_page():
        page = FRONTEND_DIST / "story-editor.html"
        if not page.is_file():
            return (
                "Story editor frontend has not been built. "
                "Run `cd frontend; npm run build`.",
                503,
            )
        return send_file(page)

    @app.get("/assets/<path:filename>")
    def frontend_asset(filename: str):
        return send_from_directory(FRONTEND_DIST / "assets", filename)

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.workspace)
    print(f"VideoHub story editor: http://{args.host}:{args.port}/story-editor")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
