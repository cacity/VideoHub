from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import SettingsStore
from .idle_queue import IdleQueueStore


class ExtensionQueueTask(BaseModel):
    platform: str
    url: str
    title: str
    author: str = ""
    text: str = ""


class ExtensionSettings(BaseModel):
    idle_start_time: str | None = None
    idle_end_time: str | None = None


def create_extension_app(queue: IdleQueueStore, settings: SettingsStore) -> FastAPI:
    app = FastAPI(title="VideoHub browser extension bridge", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    def queue_snapshot() -> dict[str, Any]:
        values = settings.settings
        return queue.snapshot(values.idle_start, values.idle_end)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "message": "VideoHub extension bridge is running"}

    @app.get("/api/queue")
    def get_queue() -> dict[str, Any]:
        return {"success": True, "data": queue_snapshot()}

    @app.post("/api/queue/add", status_code=201)
    def add_task(body: ExtensionQueueTask) -> dict[str, Any]:
        try:
            task = queue.add(body.model_dump())
        except ValueError as exc:
            status = 409 if "already exists" in str(exc) else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        snapshot = queue_snapshot()
        return {
            "success": True,
            "message": "Task added to queue successfully",
            "task_id": task["id"],
            "queue_length": len(snapshot["tasks"]),
        }

    @app.delete("/api/queue/clear")
    def clear_queue() -> dict[str, Any]:
        queue.clear()
        return {"success": True, "message": "Queue cleared successfully"}

    @app.delete("/api/queue/remove/{task_id}")
    def remove_task(task_id: str) -> dict[str, Any]:
        try:
            task = queue.remove(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Invalid task ID") from exc
        return {
            "success": True,
            "message": "Task removed successfully",
            "removed_task": task["title"],
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        snapshot = queue_snapshot()
        return {
            "success": True,
            "data": {
                "idle_start_time": snapshot["idle_start_time"],
                "idle_end_time": snapshot["idle_end_time"],
                "is_idle_running": snapshot["is_idle_running"],
                "idle_paused": snapshot["idle_paused"],
            },
        }

    @app.put("/api/settings")
    def update_settings(body: ExtensionSettings) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if body.idle_start_time is not None:
            changes["idle_start"] = body.idle_start_time
        if body.idle_end_time is not None:
            changes["idle_end"] = body.idle_end_time
        try:
            if changes:
                settings.update(changes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"success": True, "message": "Settings updated successfully"}

    return app
