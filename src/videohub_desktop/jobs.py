from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "interrupted"}
SECRET_PARAMETER_NAMES = {
    "api_key",
    "deepseek_api_key",
    "minimax_api_key",
    "openai_api_key",
    "password",
    "secret",
    "token",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SECRET_PARAMETER_NAMES or normalized.endswith("_api_key"):
                return True
            if _contains_secret_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


class JobManager:
    def __init__(self, data_dir: Path, entry_script: Path | None = None):
        self.root = data_dir.expanduser().resolve() / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.entry_script = entry_script or Path(__file__).resolve().parents[2] / "sidecar_entry.py"
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for status_path in self.root.glob("*/status.json"):
            try:
                job = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") in {"queued", "running"}:
                job.update(
                    status="interrupted",
                    message="The desktop service stopped before this job completed.",
                    finished_at=utc_now(),
                )
                _atomic_json_write(status_path, job)
            self._jobs[str(job["id"])] = job

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted((dict(job) for job in jobs), key=lambda item: item["created_at"], reverse=True)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    def create(self, operation: str, parameters: dict[str, Any]) -> dict[str, Any]:
        from .operations import OPERATION_IDS

        if operation not in OPERATION_IDS:
            raise ValueError(f"Unsupported operation: {operation}")
        if _contains_secret_key(parameters):
            raise ValueError("Secrets must be configured in the credential store, not submitted in a job payload.")
        job_id = uuid.uuid4().hex
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True)
        request_payload = {"operation": operation, "parameters": parameters}
        job = {
            "id": job_id,
            "operation": operation,
            "parameters": parameters,
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "logs": [],
            "result": None,
            "error": "",
            "created_at": utc_now(),
            "started_at": None,
            "finished_at": None,
        }
        _atomic_json_write(job_dir / "request.json", request_payload)
        _atomic_json_write(job_dir / "status.json", job)
        with self._lock:
            self._jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id,), daemon=True, name=f"videohub-job-{job_id[:8]}").start()
        return dict(job)

    def _command(self, job_dir: Path) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "worker", "--job-dir", str(job_dir)]
        return [sys.executable, str(self.entry_script), "worker", "--job-dir", str(job_dir)]

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            snapshot = dict(job)
            _atomic_json_write(self.root / job_id / "status.json", snapshot)

    def _append_log(self, job_id: str, message: str) -> None:
        message = message.strip()
        if not message:
            return
        with self._lock:
            job = self._jobs[job_id]
            logs = list(job.get("logs", []))
            logs.append(message)
            job["logs"] = logs[-300:]
            snapshot = dict(job)
            _atomic_json_write(self.root / job_id / "status.json", snapshot)

    def _run(self, job_id: str) -> None:
        job_dir = self.root / job_id
        self._update(job_id, status="running", started_at=utc_now(), message="Starting worker", progress=1)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        env = os.environ.copy()
        env.pop("VIDEOHUB_SESSION_TOKEN", None)
        # Frozen Windows workers can otherwise inherit a legacy ANSI code page.
        # The worker protocol and downloaded media paths must always use UTF-8.
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            process = subprocess.Popen(
                self._command(job_dir),
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=creation_flags,
            )
            with self._lock:
                self._processes[job_id] = process
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    self._append_log(job_id, line)
                    continue
                event_type = event.get("type")
                if event_type == "progress":
                    self._update(
                        job_id,
                        progress=max(0, min(int(event.get("progress", 0)), 100)),
                        message=str(event.get("message", "")),
                    )
                elif event_type == "log":
                    self._append_log(job_id, str(event.get("message", "")))
                elif event_type == "result":
                    self._update(job_id, result=event.get("result"))
                elif event_type == "error":
                    self._append_log(job_id, str(event.get("message", "Worker failed")))
            return_code = process.wait()
            current = self.get(job_id)
            if current["status"] == "cancelled":
                return
            if return_code == 0:
                self._update(
                    job_id,
                    status="succeeded",
                    progress=100,
                    message="Completed",
                    finished_at=utc_now(),
                )
            else:
                self._update(
                    job_id,
                    status="failed",
                    message=f"Worker exited with code {return_code}",
                    error=f"Worker exited with code {return_code}",
                    finished_at=utc_now(),
                )
        except Exception as exc:
            self._append_log(job_id, traceback.format_exc())
            self._update(
                job_id,
                status="failed",
                message=str(exc),
                error=str(exc),
                finished_at=utc_now(),
            )
        finally:
            with self._lock:
                self._processes.pop(job_id, None)

    def cancel(self, job_id: str) -> dict[str, Any]:
        current = self.get(job_id)
        if current["status"] in TERMINAL_STATES:
            return current
        with self._lock:
            process = self._processes.get(job_id)
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                process.terminate()
        self._update(
            job_id,
            status="cancelled",
            message="Cancelled",
            error="",
            finished_at=utc_now(),
        )
        return self.get(job_id)

    def shutdown(self) -> None:
        with self._lock:
            job_ids = list(self._processes)
        for job_id in job_ids:
            self.cancel(job_id)
