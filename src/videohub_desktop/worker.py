from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from .operations import run_operation


class EventEmitter:
    def __init__(self) -> None:
        self.stream = sys.stdout

    def _emit(self, payload: dict[str, Any]) -> None:
        # The frozen Windows worker can inherit a legacy console code page.
        # ASCII JSON keeps the pipe protocol lossless for Chinese titles and paths.
        self.stream.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self.stream.flush()

    def progress(self, value: int, message: str) -> None:
        self._emit({"type": "progress", "progress": int(value), "message": message})

    def log(self, message: str) -> None:
        self._emit({"type": "log", "message": str(message)})

    def result(self, result: Any) -> None:
        self._emit({"type": "result", "result": result})

    def error(self, message: str) -> None:
        self._emit({"type": "error", "message": message})


def run_job(job_dir: Path) -> int:
    emitter = EventEmitter()
    try:
        payload = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
        result = run_operation(
            str(payload["operation"]),
            dict(payload.get("parameters") or {}),
            emitter.progress,
            emitter.log,
        )
        emitter.result(result)
        return 0
    except Exception as exc:
        emitter.error(str(exc))
        emitter.log(traceback.format_exc())
        return 1
