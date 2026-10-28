"""Run the local video learning workspace: python -m src.learning_server."""

from __future__ import annotations

import argparse
import hmac
import json
import secrets
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory, stream_with_context

try:
    from .learning.service import LearningService
    from .learning import media
    from .learning.assistant import Assistant
    from .learning.providers import capabilities
    from .learning.notes import NoteConflict, save_note, markdown
    from .learning.search import search_web
    from .learning.imports import recent_downloads, directory_assets, subtitle_candidates
    from .learning.preparation import start_preview, start_transcription
    from .learning.project import import_project
    from .learning.downloads import import_download
except ImportError:
    from learning.service import LearningService
    from learning import media
    from learning.assistant import Assistant
    from learning.providers import capabilities
    from learning.notes import NoteConflict, save_note, markdown
    from learning.search import search_web
    from learning.imports import recent_downloads, directory_assets, subtitle_candidates
    from learning.preparation import start_preview, start_transcription
    from learning.project import import_project
    from learning.downloads import import_download

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "workspace" / "learning"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(data_root: Path = DEFAULT_DATA, dev_origin: str = "") -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 24 * 1024 * 1024
    if dev_origin and dev_origin not in {"http://localhost:5173", "http://127.0.0.1:5173"}:
        raise ValueError("开发来源必须是本机 Vite 地址")
    app.config["LEARNING_DEV_ORIGIN"] = dev_origin
    service = LearningService(Path(data_root))
    app.config["LEARNING_SERVICE"] = service
    assistant = Assistant(service)
    assistant.search = search_web
    app.config["LEARNING_ASSISTANT"] = assistant
    token = secrets.token_urlsafe(32)

    @app.before_request
    def local_session():
        if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            return jsonify(error="仅允许本机访问"), 403
        origin = request.headers.get("Origin")
        allowed = {request.host_url.rstrip("/")}
        if app.config.get("LEARNING_DEV_ORIGIN"):
            allowed.add(app.config["LEARNING_DEV_ORIGIN"])
        if request.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and origin not in allowed):
            return jsonify(error="不允许跨站请求"), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-Learning-Token", "")
            if not hmac.compare_digest(supplied, token):
                return jsonify(error="学习会话已过期，请刷新页面"), 403

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(KeyError)
    @app.errorhandler(FileNotFoundError)
    def missing(error):
        return jsonify(error=str(error).strip("'")), 404

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(NoteConflict)
    def conflict(error):
        return jsonify(error=str(error)), 409

    @app.get("/api/learning/health")
    def health():
        return jsonify(ok=True, service="videohub-learning", version=1)

    @app.get("/api/learning/session")
    def session():
        return jsonify(token=token, providers=capabilities())

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValueError("请求须为 JSON 对象")
        return value

    @app.get("/api/learning/videos")
    def videos():
        return jsonify(videos=[{**v, "progress": service.store.progress(v["id"])} for v in service.store.videos()])

    @app.get("/api/learning/imports/recent")
    def recent():
        return jsonify(videos=recent_downloads())

    @app.post("/api/learning/imports/directory")
    def scan_directory():
        return jsonify(videos=directory_assets(str(body().get("path", ""))))

    @app.post("/api/learning/imports/project")
    def project_import():
        data = body()
        return jsonify(import_project(service, str(data.get("directory", "")), str(data.get("video_path", ""))))

    @app.post("/api/learning/videos")
    def register():
        data = body()
        if data.get("tracks") is None:
            imported = import_download(service, str(data.get("path", "")), str(data.get("title", "")), str(data.get("source_url", "")))
            if imported:
                return jsonify(imported), 201
        return jsonify(
            service.register(
                str(data.get("path", "")),
                str(data.get("title", "")),
                str(data.get("source_url", "")),
                data.get("tracks"),
            )
        ), 201

    @app.get("/api/learning/videos/<video_id>")
    def video(video_id):
        return jsonify(service.detail(video_id))

    @app.get("/api/learning/videos/<video_id>/media")
    def video_media(video_id):
        path = service.media_path(video_id)
        return send_file(path, conditional=True, mimetype=media.mime(path))

    @app.post("/api/learning/videos/<video_id>/subtitles")
    def add_track(video_id):
        return jsonify(service.add_track(video_id, body()))

    @app.get("/api/learning/videos/<video_id>/subtitle-file")
    def subtitle_file(video_id):
        role = request.args.get("role", "")
        if role not in {"source", "target"}:
            raise ValueError("字幕角色无效")
        video = service.detail(video_id)
        track = video["tracks"].get(role)
        if not track:
            raise ValueError("尚未导入该语言字幕")
        return send_file(track["path"], as_attachment=True, download_name=Path(track["path"]).name, mimetype="application/x-subrip")

    @app.get("/api/learning/videos/<video_id>/subtitle-candidates")
    def candidates(video_id):
        return jsonify(tracks=subtitle_candidates(service.store.video(video_id)["path"]))

    @app.post("/api/learning/videos/<video_id>/select-track")
    def select_track(video_id):
        return jsonify(service.select_track(video_id, body()))

    @app.put("/api/learning/videos/<video_id>/progress")
    def progress(video_id):
        return jsonify(service.progress(video_id, body()))

    @app.get("/api/learning/videos/<video_id>/study")
    def study(video_id):
        video = service.detail(video_id)
        jobs = service.store.video_jobs(video_id)
        outline = next(
            (
                j["result"]["outline"]
                for j in jobs
                if j.get("status") == "finished"
                and j.get("result", {}).get("subtitle_version") == video["subtitle_version"]
                and j.get("result", {}).get("outline")
            ),
            [],
        )
        return jsonify(
            messages=service.store.list_items("messages", video_id),
            notes=service.store.list_items("notes", video_id),
            outline=outline,
            active_job=next((j for j in jobs if j["status"] in {"queued", "running", "cancelling"}), None),
        )

    @app.get("/api/learning/videos/<video_id>/notes")
    def notes(video_id):
        service.store.video(video_id)
        return jsonify(notes=service.store.list_items("notes", video_id))

    @app.post("/api/learning/videos/<video_id>/notes")
    def create_note(video_id):
        return jsonify(save_note(service, video_id, body())), 201

    @app.patch("/api/learning/videos/<video_id>/notes/<note_id>")
    def edit_note(video_id, note_id):
        return jsonify(save_note(service, video_id, body(), note_id))

    @app.delete("/api/learning/videos/<video_id>/notes/<note_id>")
    def delete_note(video_id, note_id):
        service.store.video(video_id)
        service.store.delete_note(video_id, note_id)
        return jsonify(ok=True)

    @app.get("/api/learning/videos/<video_id>/export")
    def export_notes(video_id):
        return Response(
            markdown(service, video_id, request.host_url.rstrip("/")),
            content_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="videohub-notes.md"'},
        )

    @app.post("/api/learning/videos/<video_id>/chat")
    def chat(video_id):
        return jsonify(assistant.start_chat(video_id, body())), 202

    @app.post("/api/learning/videos/<video_id>/prepare")
    def prepare(video_id):
        data = body()
        kind = data.get("kind", "analysis")
        if kind == "analysis":
            job = assistant.start_analysis(video_id, data)
        elif kind == "translation":
            job = assistant.start_translation(video_id, data)
        elif kind == "preview":
            job = start_preview(assistant, video_id)
        elif kind == "transcription":
            job = start_transcription(assistant, video_id, data)
        else:
            raise ValueError("未知任务类型")
        return jsonify(job), 202

    @app.get("/api/learning/jobs/<job_id>")
    def job(job_id):
        return jsonify(service.store.job(job_id))

    @app.post("/api/learning/jobs/<job_id>/cancel")
    def cancel(job_id):
        return jsonify(assistant.jobs.cancel(job_id))

    @app.get("/api/learning/jobs/<job_id>/events")
    def events(job_id):
        service.store.job(job_id)

        @stream_with_context
        def stream():
            last = ""
            for _ in range(7200):
                value = service.store.job(job_id)
                payload = json.dumps(value, ensure_ascii=False)
                if last != payload:
                    yield "data: " + payload + "\n\n"
                    last = payload
                else:
                    yield ": heartbeat\n\n"
                if value["status"] not in {"queued", "running", "cancelling"}:
                    return
                time.sleep(0.5)

        return Response(stream(), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/")
    @app.get("/learn")
    def page():
        path = FRONTEND_DIST / "learning.html"
        if not path.is_file():
            return "请先在 frontend 目录执行 npm run build，再刷新视频学习页面。", 503
        return send_file(path)

    @app.get("/assets/<path:filename>")
    def asset(filename):
        return send_from_directory(FRONTEND_DIST / "assets", filename)

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--dev-origin", default="", choices=["", "http://localhost:5173", "http://127.0.0.1:5173"])
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    app = create_app(args.data, args.dev_origin)
    print(f"VideoHub 学习: http://127.0.0.1:{args.port}/learn", flush=True)
    app.run(host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
