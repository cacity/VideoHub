from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.wsgi import WSGIMiddleware

from . import __version__
from .config import CredentialStore, RuntimeConfig, SettingsStore
from .idle_queue import IdleQueueStore
from .jobs import TERMINAL_STATES, JobManager
from .operations import operation_catalog


class JobCreate(BaseModel):
    operation: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class CredentialsUpdate(BaseModel):
    values: dict[str, str | None]


class IdleQueueCreate(BaseModel):
    title: str = ""
    operation: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    platform: str = ""
    url: str = ""


class IdleQueueState(BaseModel):
    paused: bool


def create_app(
    runtime: RuntimeConfig | None = None,
    entry_script: Path | None = None,
    credential_store: CredentialStore | None = None,
) -> FastAPI:
    runtime = runtime or RuntimeConfig.from_environment()
    runtime.apply_environment()
    settings = SettingsStore(runtime.data_dir)
    settings.apply_environment()
    credentials = credential_store or CredentialStore()
    credentials.apply_environment()
    manager = JobManager(runtime.data_dir, entry_script=entry_script)
    idle_queue = IdleQueueStore(runtime.data_dir)

    async def schedule_idle_jobs() -> None:
        while True:
            task = idle_queue.take_due(settings.settings.idle_start, settings.settings.idle_end)
            if task:
                try:
                    manager.create(str(task["operation"]), dict(task.get("parameters") or {}))
                except (KeyError, TypeError, ValueError):
                    idle_queue.restore_front(task)
            await asyncio.sleep(2.0)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler = asyncio.create_task(schedule_idle_jobs())
        try:
            yield
        finally:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler
            manager.shutdown()

    app = FastAPI(title="VideoHub Desktop API", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime
    app.state.settings = settings
    app.state.credentials = credentials
    app.state.jobs = manager
    app.state.idle_queue = idle_queue
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def authorize_story_editor(request: Request, call_next):
        path = request.url.path
        story_request = (
            path == "/story-editor"
            or path.startswith("/api/story-editor/")
            or path.startswith("/assets/")
        )
        set_session_cookie = False
        if story_request and runtime.session_token:
            header = request.headers.get("Authorization", "")
            query_token = request.query_params.get("token", "")
            cookie_token = request.cookies.get("videohub_session", "")
            valid = (
                header == f"Bearer {runtime.session_token}"
                or query_token == runtime.session_token
                or cookie_token == runtime.session_token
            )
            if not valid:
                return JSONResponse({"detail": "Invalid desktop session token"}, status_code=401)
            set_session_cookie = query_token == runtime.session_token
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.lower().startswith("application/json") and "charset=" not in content_type.lower():
            # Some Windows clients otherwise decode JSON with the local ANSI code page.
            response.headers["content-type"] = f"{content_type}; charset=utf-8"
        if set_session_cookie:
            response.set_cookie(
                "videohub_session",
                runtime.session_token,
                httponly=True,
                samesite="strict",
            )
        return response

    def authorize(authorization: str = Header(default="")) -> None:
        if runtime.session_token and authorization != f"Bearer {runtime.session_token}":
            raise HTTPException(status_code=401, detail="Invalid desktop session token")

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        jobs = manager.list()
        return {
            "status": "ok",
            "version": __version__,
            "pid": os.getpid(),
            "data_dir": str(runtime.data_dir),
            "workspace_dir": str(runtime.workspace_dir),
            "active_jobs": sum(item["status"] not in TERMINAL_STATES for item in jobs),
        }

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)])
    def capabilities() -> dict[str, Any]:
        return {"operations": operation_catalog()}

    @app.get("/v1/paths", dependencies=[Depends(authorize)])
    def paths() -> dict[str, Any]:
        from paths_config import list_all_directories

        return {
            "data_dir": str(runtime.data_dir),
            "workspace_dir": str(runtime.workspace_dir),
            "directories": list_all_directories(),
        }

    @app.get("/v1/settings", dependencies=[Depends(authorize)])
    def get_settings() -> dict[str, Any]:
        return {"values": settings.settings.public_dict(), "restart_required": False}

    @app.put("/v1/settings", dependencies=[Depends(authorize)])
    def update_settings(body: SettingsUpdate) -> dict[str, Any]:
        previous_workspace = settings.settings.workspace_dir
        try:
            updated = settings.update(body.values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        settings.apply_environment()
        return {
            "values": updated.public_dict(),
            "restart_required": updated.workspace_dir != previous_workspace,
        }

    @app.get("/v1/credentials", dependencies=[Depends(authorize)])
    def credential_status() -> dict[str, Any]:
        return {"configured": credentials.status()}

    @app.put("/v1/credentials", dependencies=[Depends(authorize)])
    def update_credentials(body: CredentialsUpdate) -> dict[str, Any]:
        try:
            configured = credentials.update(body.values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"configured": configured}

    @app.get("/v1/jobs", dependencies=[Depends(authorize)])
    def list_jobs() -> dict[str, Any]:
        return {"items": manager.list()}

    @app.post("/v1/jobs", status_code=202, dependencies=[Depends(authorize)])
    def create_job(body: JobCreate) -> dict[str, Any]:
        try:
            return manager.create(body.operation, body.parameters)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(authorize)])
    def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            return manager.cancel(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/v1/jobs/{job_id}/events")
    async def job_events(request: Request, job_id: str, authorization: str = Header(default="")) -> StreamingResponse:
        authorize(authorization)
        try:
            manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

        async def stream() -> AsyncIterator[str]:
            previous = ""
            while not await request.is_disconnected():
                snapshot = manager.get(job_id)
                serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
                if serialized != previous:
                    yield f"event: job\ndata: {serialized}\n\n"
                    previous = serialized
                if snapshot["status"] in TERMINAL_STATES:
                    break
                await asyncio.sleep(0.35)

        return StreamingResponse(stream(), media_type="text/event-stream")

    def queue_snapshot() -> dict[str, Any]:
        values = settings.settings
        return idle_queue.snapshot(values.idle_start, values.idle_end)

    @app.get("/v1/idle-queue", dependencies=[Depends(authorize)])
    def get_idle_queue() -> dict[str, Any]:
        return queue_snapshot()

    @app.post("/v1/idle-queue", status_code=201, dependencies=[Depends(authorize)])
    def add_idle_queue_task(body: IdleQueueCreate) -> dict[str, Any]:
        try:
            task = idle_queue.add(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"task": task, "queue": queue_snapshot()}

    @app.put("/v1/idle-queue/state", dependencies=[Depends(authorize)])
    def update_idle_queue_state(body: IdleQueueState) -> dict[str, Any]:
        idle_queue.set_paused(body.paused)
        return queue_snapshot()

    @app.delete("/v1/idle-queue", dependencies=[Depends(authorize)])
    def clear_idle_queue() -> dict[str, Any]:
        idle_queue.clear()
        return queue_snapshot()

    @app.delete("/v1/idle-queue/{task_id}", dependencies=[Depends(authorize)])
    def remove_idle_queue_task(task_id: str) -> dict[str, Any]:
        try:
            idle_queue.remove(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Queue task not found") from exc
        return queue_snapshot()

    @app.post("/v1/idle-queue/{task_id}/run", status_code=202, dependencies=[Depends(authorize)])
    def run_idle_queue_task(task_id: str) -> dict[str, Any]:
        try:
            task = idle_queue.take(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Queue task not found") from exc
        try:
            job = manager.create(str(task["operation"]), dict(task.get("parameters") or {}))
        except ValueError as exc:
            idle_queue.restore_front(task)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job": job, "queue": queue_snapshot()}

    try:
        from story_timeline_server import create_app as create_story_timeline_app
    except ModuleNotFoundError as exc:
        if exc.name != "story_timeline_server":
            raise
        from src.story_timeline_server import create_app as create_story_timeline_app
    app.state.story_editor_available = True
    app.mount("/", WSGIMiddleware(create_story_timeline_app(runtime.workspace_dir)))

    return app
