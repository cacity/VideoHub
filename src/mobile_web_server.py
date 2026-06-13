"""Local mobile web downloader for VideoHub.

Run this on the computer:

    python src/mobile_web_server.py

Then open the printed LAN URL on an iPhone connected to the same network.
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, request, send_file

from paths_config import MOBILE_DOWNLOADS_DIR


DOWNLOAD_DIR = Path(MOBILE_DOWNLOADS_DIR)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>VideoHub 手机下载</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f8;
      color: #111827;
    }
    body {
      margin: 0;
      padding: 18px;
      background: #f6f7f8;
    }
    main {
      max-width: 680px;
      margin: 0 auto;
    }
    h1 {
      font-size: 24px;
      line-height: 1.2;
      margin: 14px 0 8px;
    }
    p {
      color: #4b5563;
      font-size: 15px;
      line-height: 1.55;
      margin: 0 0 16px;
    }
    label {
      display: block;
      font-size: 14px;
      font-weight: 600;
      margin: 18px 0 8px;
    }
    textarea {
      width: 100%;
      min-height: 118px;
      box-sizing: border-box;
      resize: vertical;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      font-size: 16px;
      background: #ffffff;
      color: #111827;
    }
    button, a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 16px;
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      color: #ffffff;
      background: #2563eb;
      cursor: pointer;
    }
    button:disabled {
      background: #94a3b8;
      cursor: not-allowed;
    }
    .row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .status {
      margin-top: 18px;
      padding: 14px;
      border-radius: 8px;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      min-height: 54px;
      white-space: pre-wrap;
      line-height: 1.45;
    }
    progress {
      width: 100%;
      height: 14px;
      margin-top: 12px;
    }
    video {
      display: none;
      width: 100%;
      max-height: 58vh;
      margin-top: 16px;
      background: #000;
      border-radius: 8px;
    }
    .hint {
      font-size: 13px;
      color: #6b7280;
      margin-top: 10px;
    }
    @media (prefers-color-scheme: dark) {
      :root, body { background: #0f172a; color: #e5e7eb; }
      p, .hint { color: #94a3b8; }
      textarea, .status { background: #111827; color: #e5e7eb; border-color: #334155; }
    }
  </style>
</head>
<body>
  <main>
    <h1>VideoHub 手机下载</h1>
    <p>在手机上长按输入框粘贴视频链接，下载完成后打开视频，再用 iOS 分享菜单保存到相册。</p>

    <label for="url">视频链接</label>
    <textarea id="url" inputmode="url" placeholder="长按这里粘贴链接，例如 YouTube、Instagram、Twitter/X、Bilibili 等"></textarea>

    <div class="row">
      <button id="start">下载视频</button>
      <button id="clear" type="button">清空</button>
    </div>

    <div id="status" class="status">等待粘贴链接。</div>
    <progress id="progress" max="100" value="0"></progress>

    <video id="video" controls playsinline></video>
    <div class="row" id="actions" style="display:none">
      <a id="open" class="button" target="_blank" rel="noopener">打开视频</a>
      <a id="download" class="button">下载文件</a>
    </div>
    <div class="hint">如果 iPhone 没有直接保存到相册，请先点“打开视频”，再使用 Safari 的分享按钮保存。</div>
  </main>

  <script>
    const urlInput = document.getElementById("url");
    const startButton = document.getElementById("start");
    const clearButton = document.getElementById("clear");
    const statusBox = document.getElementById("status");
    const progress = document.getElementById("progress");
    const video = document.getElementById("video");
    const actions = document.getElementById("actions");
    const openLink = document.getElementById("open");
    const downloadLink = document.getElementById("download");
    let timer = null;

    function setStatus(text) {
      statusBox.textContent = text;
    }

    function resetResult() {
      progress.value = 0;
      video.removeAttribute("src");
      video.style.display = "none";
      actions.style.display = "none";
      openLink.removeAttribute("href");
      downloadLink.removeAttribute("href");
    }

    async function poll(jobId) {
      const response = await fetch(`/api/jobs/${jobId}`);
      const job = await response.json();
      progress.value = job.progress || 0;
      setStatus(job.message || job.status);

      if (job.status === "finished") {
        clearInterval(timer);
        timer = null;
        startButton.disabled = false;
        const fileUrl = `/files/${job.id}`;
        video.src = fileUrl;
        video.style.display = "block";
        openLink.href = fileUrl;
        downloadLink.href = `${fileUrl}?download=1`;
        downloadLink.setAttribute("download", job.filename || "video.mp4");
        actions.style.display = "flex";
        setStatus(`下载完成：${job.filename || "video"}`);
      } else if (job.status === "failed") {
        clearInterval(timer);
        timer = null;
        startButton.disabled = false;
        setStatus(`下载失败：${job.error || "未知错误"}`);
      }
    }

    startButton.addEventListener("click", async () => {
      const url = urlInput.value.trim();
      if (!url) {
        setStatus("请先粘贴视频链接。");
        return;
      }

      resetResult();
      startButton.disabled = true;
      setStatus("已提交下载任务...");

      try {
        const response = await fetch("/api/download", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({url})
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.error || "提交失败");
        }
        timer = setInterval(() => poll(data.id).catch(err => setStatus(String(err))), 1200);
        await poll(data.id);
      } catch (err) {
        startButton.disabled = false;
        setStatus(`提交失败：${err.message || err}`);
      }
    });

    clearButton.addEventListener("click", () => {
      urlInput.value = "";
      resetResult();
      setStatus("等待粘贴链接。");
      urlInput.focus();
    });

    urlInput.focus();
  </script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.post("/api/download")
    def start_download():
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        if not _is_allowed_url(url):
            return jsonify({"success": False, "error": "请提供 http 或 https 视频链接"}), 400

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "url": url,
            "status": "queued",
            "progress": 0,
            "message": "等待下载...",
            "file": None,
            "filename": None,
            "error": None,
            "created_at": time.time(),
        }
        with JOBS_LOCK:
            JOBS[job_id] = job

        thread = threading.Thread(target=_download_job, args=(job_id, url), daemon=True)
        thread.start()
        return jsonify({"success": True, "id": job_id})

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return jsonify({"error": "任务不存在"}), 404
            public_job = {k: v for k, v in job.items() if k != "file"}
        return jsonify(public_job)

    @app.get("/files/<job_id>")
    def get_file(job_id: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job or job.get("status") != "finished":
                return jsonify({"error": "文件未就绪"}), 404
            file_path = Path(job["file"]).resolve()

        if not _is_safe_output_file(file_path):
            return jsonify({"error": "文件路径无效"}), 403
        if not file_path.exists():
            return jsonify({"error": "文件不存在"}), 404

        as_attachment = request.args.get("download") == "1"
        return send_file(
            file_path,
            mimetype=_guess_video_mimetype(file_path),
            as_attachment=as_attachment,
            download_name=file_path.name,
            conditional=True,
        )

    return app


def _is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_safe_output_file(file_path: Path) -> bool:
    try:
        file_path.relative_to(DOWNLOAD_DIR.resolve())
        return True
    except ValueError:
        return False


def _guess_video_mimetype(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in {".mp4", ".m4v"}:
        return "video/mp4"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".mkv":
        return "video/x-matroska"
    return "application/octet-stream"


def _update_job(job_id: str, **changes: Any) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job.update(changes)


def _download_job(job_id: str, url: str) -> None:
    started_at = time.time()
    before = {p.resolve() for p in DOWNLOAD_DIR.glob("*") if p.is_file()}

    def progress_hook(event: dict[str, Any]) -> None:
        status = event.get("status")
        if status == "downloading":
            total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
            downloaded = event.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            speed = event.get("_speed_str") or ""
            eta = event.get("_eta_str") or ""
            _update_job(
                job_id,
                status="downloading",
                progress=max(1, min(percent, 99)),
                message=f"正在下载：{percent}%  {speed}  ETA {eta}".strip(),
            )
        elif status == "finished":
            _update_job(job_id, progress=99, message="下载完成，正在整理文件...")

    try:
        _update_job(job_id, status="starting", progress=1, message="正在解析链接...")
        ydl_opts = {
            "format": (
                "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec^=h264][ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(DOWNLOAD_DIR / "%(title).180B_%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            candidates = []
            for item in info.get("requested_downloads") or []:
                if item.get("filepath"):
                    candidates.append(Path(item["filepath"]))
            candidates.append(Path(ydl.prepare_filename(info)))

        file_path = _resolve_downloaded_file(candidates, before, started_at)
        if not file_path:
            raise RuntimeError("下载结束，但没有找到本次输出的视频文件")

        _update_job(
            job_id,
            status="finished",
            progress=100,
            message=f"下载完成：{file_path.name}",
            file=str(file_path),
            filename=file_path.name,
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            progress=0,
            message="下载失败",
            error=str(exc),
        )


def _resolve_downloaded_file(candidates: list[Path], before: set[Path], started_at: float) -> Path | None:
    valid_suffixes = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
    existing = [
        path.resolve()
        for path in candidates
        if path.exists() and path.is_file() and path.suffix.lower() in valid_suffixes
    ]

    if not existing:
        for path in DOWNLOAD_DIR.glob("*"):
            if not path.is_file() or path.suffix.lower() not in valid_suffixes:
                continue
            resolved = path.resolve()
            if resolved not in before and path.stat().st_mtime >= started_at - 2:
                existing.append(resolved)

    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def get_lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VideoHub mobile LAN web downloader")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host, default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8787, help="Bind port, default: 8787")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lan_ip = get_lan_ip()
    print("VideoHub 手机网页端已启动")
    print(f"电脑本机访问: http://127.0.0.1:{args.port}")
    print(f"手机局域网访问: http://{lan_ip}:{args.port}")
    print(f"下载目录: {DOWNLOAD_DIR}")
    create_app().run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
