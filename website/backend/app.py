from __future__ import annotations
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from database import Database
from subtitle_service import SubtitleService, SubtitleServiceError


def create_app():
    app = Flask(__name__)

    # CORS
    if os.getenv("VIDEOHUB_ENABLE_CORS", "1") == "1":
        CORS(app)

    data_dir = Path(os.getenv("VIDEOHUB_SITE_DATA_DIR", "/opt/videohub-site/data/subtitles"))
    db_path = os.getenv("VIDEOHUB_SITE_DB_PATH", "/opt/videohub-site/data/videohub.db")

    subtitle_service = SubtitleService(data_dir)
    db = Database(db_path)

    @app.after_request
    def record_access(response):
        skip = request.path.startswith("/api/subtitles/files/") or request.path == "/api/health"
        if skip:
            return response
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        db.log_access(ip, request.method, request.path, response.status_code, request.headers.get("User-Agent", ""))
        return response

    @app.get("/api/health")
    def health():
        return jsonify({"success": True, "data": {"status": "ok"}})

    @app.post("/api/subtitles/youtube/inspect")
    def inspect_youtube_subtitles():
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", ""))
        result = subtitle_service.inspect(url)
        return jsonify({"success": True, "data": result})

    @app.post("/api/log/page")
    def log_page_view():
        data = request.get_json(silent=True) or {}
        path = data.get("path", "/")
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        db.log_access(ip, "PAGE", path, 200, request.headers.get("User-Agent", ""))
        return jsonify({"success": True})

    @app.post("/api/subtitles/youtube/download")
    def download_youtube_subtitle():
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", ""))
        language = data.get("language", "")
        output_format = data.get("format", "SRT")
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        result = subtitle_service.download(url, language, output_format)
        db.log_subtitle_request(ip, url, language, output_format, True, None)
        return jsonify({"success": True, "data": result})

    @app.get("/api/subtitles/files/<file_id>")
    def download_file(file_id):
        file_path = subtitle_service.resolve_file(file_id)
        return send_file(file_path, as_attachment=True, download_name=file_path.name)

    @app.errorhandler(SubtitleServiceError)
    def handle_service_error(error):
        return jsonify({"success": False, "error": str(error)}), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"success": False, "error": "接口不存在"}), 404

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        app.logger.exception("Unhandled API error")
        return jsonify({"success": False, "error": "服务器内部错误"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8787")))
