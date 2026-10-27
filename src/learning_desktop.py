"""Small desktop bridge; no Qt widgets are touched from server threads."""

from __future__ import annotations

import threading

import requests

_lock = threading.Lock()
_server = None
BASE_URL = "http://127.0.0.1:8767"


def learning_url(path: str = "", directory: str = "") -> str:
    """Start/reuse the local service and optionally register a user-selected video."""
    global _server
    with _lock:
        try:
            response = requests.get(BASE_URL + "/api/learning/health", timeout=1)
            healthy = response.ok and response.json().get("service") == "videohub-learning"
        except (requests.RequestException, ValueError):
            healthy = False
        if not healthy:
            try:
                from .learning_server import create_app
            except ImportError:
                from learning_server import create_app
            from werkzeug.serving import make_server

            try:
                _server = make_server("127.0.0.1", 8767, create_app(), threaded=True)
            except (OSError, SystemExit):
                raise ValueError("8767 端口已被其他程序占用，请先释放端口，或用独立学习服务配置其他端口") from None
            threading.Thread(target=_server.serve_forever, name="learning-http", daemon=True).start()
        if not path and not directory:
            return BASE_URL + "/learn"
        session = requests.get(BASE_URL + "/api/learning/session", timeout=3).json()
        endpoint = "/imports/project" if directory else "/videos"
        result = requests.post(
            BASE_URL + "/api/learning" + endpoint,
            json={"directory": directory} if directory else {"path": path},
            headers={"X-Learning-Token": session["token"]},
            timeout=35,
        )
        data = result.json()
        if not result.ok:
            raise ValueError(data.get("error", "导入学习资料失败"))
        if directory:
            if data.get("needs_selection"):
                raise ValueError("目录中有多个视频，请在网页“导入视频 → 视频工程”中选择本次学习的视频")
            data = data["video"]
        return BASE_URL + "/learn?video=" + data["id"]
