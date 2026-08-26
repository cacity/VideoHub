from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path

from .config import RuntimeConfig


def _watch_parent(parent_pid: int) -> None:
    try:
        import psutil
    except ImportError:
        return
    while psutil.pid_exists(parent_pid):
        time.sleep(1.0)
    os._exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoHub Tauri sidecar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Start the authenticated loopback API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--data-dir")
    serve.add_argument("--workspace-dir")
    serve.add_argument("--parent-pid", type=int)
    serve.add_argument("--extension-port", type=int, default=8765)
    serve.add_argument("--no-extension-bridge", action="store_true")
    worker = subparsers.add_parser("worker", help="Run one persisted desktop job")
    worker.add_argument("--job-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "worker":
        from .worker import run_job

        return run_job(args.job_dir.expanduser().resolve())

    if args.data_dir:
        os.environ["VIDEOHUB_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    if args.workspace_dir:
        os.environ["VIDEOHUB_WORKSPACE_DIR"] = str(Path(args.workspace_dir).expanduser().resolve())
    if args.parent_pid:
        os.environ["VIDEOHUB_PARENT_PID"] = str(args.parent_pid)
    runtime = RuntimeConfig.from_environment()
    runtime.apply_environment()
    if runtime.parent_pid:
        threading.Thread(target=_watch_parent, args=(runtime.parent_pid,), daemon=True).start()
    import uvicorn

    from .app import create_app
    from .extension import create_extension_app

    application = create_app(runtime)
    extension_server = None
    extension_thread = None
    if not args.no_extension_bridge and args.extension_port != args.port:
        extension_app = create_extension_app(
            application.state.idle_queue,
            application.state.settings,
        )
        extension_server = uvicorn.Server(
            uvicorn.Config(
                extension_app,
                host="127.0.0.1",
                port=args.extension_port,
                log_level="warning",
            )
        )
        extension_thread = threading.Thread(
            target=extension_server.run,
            daemon=True,
            name="videohub-extension-bridge",
        )
        extension_thread.start()
    try:
        uvicorn.run(application, host=args.host, port=args.port, log_level="info")
    finally:
        if extension_server is not None:
            extension_server.should_exit = True
        if extension_thread is not None:
            extension_thread.join(timeout=5)
    return 0
