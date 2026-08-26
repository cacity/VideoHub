from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from datetime import time as clock_time
from pathlib import Path
from typing import Any

from .jobs import utc_now
from .operations import OPERATION_IDS


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _parse_clock(value: str) -> clock_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"Invalid idle time '{value}', expected HH:MM") from exc


def is_in_idle_window(now: datetime, start: str, end: str) -> bool:
    current = now.time().replace(second=0, microsecond=0)
    start_time = _parse_clock(start)
    end_time = _parse_clock(end)
    if start_time == end_time:
        return True
    if start_time < end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time


def task_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation", "")).strip()
    parameters = dict(payload.get("parameters") or {})
    platform = str(payload.get("platform", "")).strip().lower()
    url = str(payload.get("url", "")).strip()

    if not operation:
        operation_by_platform = {
            "youtube": "youtube.process",
            "douyin": "douyin.download",
            "koushare": "koushare.download",
            "twitter": "platform.download",
            "x": "platform.download",
            "tiktok": "platform.download",
            "instagram": "platform.download",
            "bilibili": "platform.download",
        }
        operation = operation_by_platform.get(platform, "platform.download")
        if url:
            parameters["url"] = url
        if platform in {"twitter", "x", "tiktok", "instagram", "bilibili"}:
            parameters["platform"] = "twitter" if platform == "x" else platform

    if operation not in OPERATION_IDS:
        raise ValueError(f"Unsupported operation: {operation}")
    title = str(payload.get("title") or parameters.get("url") or operation).strip()
    if not title:
        raise ValueError("Queue task title is required")
    return {
        "id": uuid.uuid4().hex,
        "title": title,
        "operation": operation,
        "parameters": parameters,
        "created_at": utc_now(),
    }


class IdleQueueStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir.expanduser().resolve() / "idle_queue.json"
        self._lock = threading.RLock()
        self._tasks: list[dict[str, Any]] = []
        self._paused = False
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, list):
            tasks = payload
            paused = False
        else:
            tasks = payload.get("tasks", [])
            paused = bool(payload.get("paused", False))
        self._tasks = [item for item in tasks if isinstance(item, dict)]
        self._paused = paused

    def _save(self) -> None:
        _atomic_json_write(self.path, {"paused": self._paused, "tasks": self._tasks})

    def snapshot(self, idle_start: str, idle_end: str) -> dict[str, Any]:
        with self._lock:
            tasks = [dict(item) for item in self._tasks]
            paused = self._paused
        return {
            "tasks": tasks,
            "idle_start_time": idle_start,
            "idle_end_time": idle_end,
            "is_idle_running": bool(tasks) and not paused,
            "idle_paused": paused,
            "in_idle_window": is_in_idle_window(datetime.now(), idle_start, idle_end),
        }

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = task_from_payload(payload)
        with self._lock:
            identity = (task["operation"], json.dumps(task["parameters"], sort_keys=True, ensure_ascii=False))
            for existing in self._tasks:
                existing_identity = (
                    existing.get("operation"),
                    json.dumps(existing.get("parameters", {}), sort_keys=True, ensure_ascii=False),
                )
                if identity == existing_identity:
                    raise ValueError("Task already exists in queue")
            self._tasks.append(task)
            self._save()
        return dict(task)

    def remove(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            index = int(task_id) if task_id.isdigit() else -1
            if index < 0:
                index = next(
                    (position for position, item in enumerate(self._tasks) if item.get("id") == task_id),
                    -1,
                )
            if index < 0 or index >= len(self._tasks):
                raise KeyError(task_id)
            task = self._tasks.pop(index)
            self._save()
        return dict(task)

    def clear(self) -> None:
        with self._lock:
            self._tasks = []
            self._save()

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused
            self._save()

    def take_due(self, idle_start: str, idle_end: str) -> dict[str, Any] | None:
        with self._lock:
            if self._paused or not self._tasks:
                return None
            if not is_in_idle_window(datetime.now(), idle_start, idle_end):
                return None
            task = self._tasks.pop(0)
            self._save()
        return dict(task)

    def take(self, task_id: str) -> dict[str, Any]:
        return self.remove(task_id)

    def restore_front(self, task: dict[str, Any]) -> None:
        with self._lock:
            self._tasks.insert(0, task)
            self._save()
