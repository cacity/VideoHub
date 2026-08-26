from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.videohub_desktop.app import create_app
from src.videohub_desktop.config import CredentialStore, RuntimeConfig, SettingsStore
from src.videohub_desktop.extension import create_extension_app
from src.videohub_desktop.idle_queue import IdleQueueStore, is_in_idle_window

ROOT = Path(__file__).resolve().parents[1]


def test_atomic_job_status_write_is_concurrency_safe(tmp_path: Path) -> None:
    from src.videohub_desktop.jobs import _atomic_json_write

    status_path = tmp_path / "jobs" / "status.json"
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: _atomic_json_write(status_path, {"index": index}), range(80)))

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["index"] in range(80)
    assert list(status_path.parent.glob(".*.tmp")) == []


class MemoryCredentialBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, name: str) -> str | None:
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.values.pop((service, name), None)


def test_sidecar_entry_restores_non_stream_stdout(monkeypatch, tmp_path: Path) -> None:
    import os
    import sys

    from sidecar_entry import _restore_standard_stream

    output = tmp_path / "stdout.log"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    original = sys.stdout
    try:
        monkeypatch.setattr(sys, "stdout", "NUL")
        _restore_standard_stream("stdout", descriptor)
        assert callable(getattr(sys.stdout, "write", None))
        sys.stdout.write("ready")
        sys.stdout.flush()
    finally:
        monkeypatch.setattr(sys, "stdout", original)
        os.close(descriptor)
    assert output.read_text(encoding="utf-8") == "ready"


def test_log_writer_is_compatible_with_ytdlp_write_string() -> None:
    from yt_dlp.utils import write_string

    from src.videohub_desktop.operations import _LogWriter

    messages: list[str] = []
    writer = _LogWriter(messages.append)
    write_string("download started\n", out=writer)
    assert messages == ["download started"]


def test_worker_events_use_ascii_safe_json_transport(monkeypatch) -> None:
    from io import StringIO

    from src.videohub_desktop.worker import EventEmitter

    stream = StringIO()
    emitter = EventEmitter()
    monkeypatch.setattr(emitter, "stream", stream)
    title = "\u4e2d\u6587\u6807\u9898"
    file_path = "F:/\u89c6\u9891/\u6210\u54c1.mp4"
    emitter.result({"title": title, "file": file_path})

    raw = stream.getvalue()
    assert raw.isascii()
    assert json.loads(raw)["result"]["title"] == title


def test_completed_media_files_preserves_unicode_names_on_windows(tmp_path: Path) -> None:
    from src.videohub_desktop.operations import _completed_media_files

    media = tmp_path / "\u4e2d\u6587\u6807\u9898_video-id.mp4"
    partial = tmp_path / "\u4e2d\u6587\u6807\u9898_video-id.mp4.part"
    media.write_bytes(b"video")
    partial.write_bytes(b"partial")

    assert _completed_media_files(tmp_path) == {media}


def make_client(tmp_path: Path, token: str = "test-token") -> TestClient:
    runtime = RuntimeConfig(
        data_dir=tmp_path / "data",
        workspace_dir=tmp_path / "workspace",
        session_token=token,
    )
    credentials = CredentialStore(MemoryCredentialBackend())
    return TestClient(
        create_app(runtime, entry_script=ROOT / "sidecar_entry.py", credential_store=credentials)
    )


def test_health_is_available_without_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "charset=utf-8" in response.headers["content-type"].lower()


def test_private_routes_require_session_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/v1/capabilities").status_code == 401
        response = client.get("/v1/capabilities", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert any(item["id"] == "youtube.process" for item in response.json()["operations"])


@pytest.mark.parametrize(
    "failure_message",
    [
        "unable to download video data: HTTP Error 403: Forbidden",
        "Requested format is not available",
    ],
)
def test_platform_download_retries_youtube_client_errors_with_web_embedded(
    monkeypatch, tmp_path: Path, failure_message: str
) -> None:
    import yt_dlp

    from src.videohub_desktop.operations import run_operation

    output = tmp_path / "sample_video-id.mp4"
    attempts: list[dict] = []
    logs: list[str] = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            attempts.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            self.options["logger"].debug("yt-dlp fake downloader started")
            if "extractor_args" not in self.options:
                raise yt_dlp.utils.DownloadError(failure_message)
            output.write_bytes(b"video")
            return {
                "id": "video-id",
                "title": "sample",
                "requested_downloads": [{"filepath": str(tmp_path / "wrong-path.mp4")}],
            }

        def prepare_filename(self, _info):
            return str(tmp_path / "wrong-path.mp4")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)
    result = run_operation(
        "platform.download",
        {
            "url": "https://www.youtube.com/watch?v=video-id",
            "output_dir": str(tmp_path),
            "proxy": "http://127.0.0.1:7897",
        },
        lambda _value, _message: None,
        logs.append,
    )

    assert len(attempts) == 2
    assert all(callable(getattr(attempt["logger"], "debug", None)) for attempt in attempts)
    assert all(callable(getattr(attempt["logger"], "warning", None)) for attempt in attempts)
    assert all(callable(getattr(attempt["logger"], "error", None)) for attempt in attempts)
    assert logs.count("yt-dlp fake downloader started") == 2
    assert attempts[0]["proxy"] == "http://127.0.0.1:7897"
    assert attempts[0]["nocheckcertificate"] is True
    assert attempts[1]["extractor_args"] == {
        "youtube": {"player_client": ["web_embedded"]}
    }
    assert result["files"] == [str(output.resolve())]
    assert result["title"] == "sample"


def test_settings_persist_without_exposing_secrets(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer test-token"}
    with make_client(tmp_path) as client:
        response = client.put(
            "/v1/settings",
            headers=headers,
            json={"values": {"whisper_model": "base", "target_language": "ja"}},
        )
        assert response.status_code == 200
        assert response.json()["values"]["whisper_model"] == "base"
        rejected = client.put(
            "/v1/settings",
            headers=headers,
            json={"values": {"minimax_api_key": "do-not-store"}},
        )
    assert rejected.status_code == 400


def test_credentials_are_write_only(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer test-token"}
    with make_client(tmp_path) as client:
        response = client.put(
            "/v1/credentials",
            headers=headers,
            json={"values": {"minimax_api_key": "test-secret"}},
        )
        assert response.status_code == 200
        assert response.json()["configured"]["minimax_api_key"] is True
        status = client.get("/v1/credentials", headers=headers)
    assert "test-secret" not in status.text


def test_echo_job_runs_in_isolated_worker(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer test-token"}
    with make_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            headers=headers,
            json={"operation": "system.echo", "parameters": {"message": "ready", "delay": 0}},
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        deadline = time.monotonic() + 10
        job = response.json()
        while time.monotonic() < deadline and job["status"] not in {"succeeded", "failed"}:
            time.sleep(0.05)
            job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "succeeded", job
    assert job["result"] == {"message": "ready"}


def test_job_payload_rejects_secret_fields(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer test-token"}
    with make_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            headers=headers,
            json={"operation": "system.echo", "parameters": {"api_key": "secret"}},
        )
    assert response.status_code == 400


def test_idle_queue_persists_and_can_run_now(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer test-token"}
    with make_client(tmp_path) as client:
        created = client.post(
            "/v1/idle-queue",
            headers=headers,
            json={
                "title": "Queued echo",
                "operation": "system.echo",
                "parameters": {"message": "from-queue", "delay": 0},
            },
        )
        assert created.status_code == 201
        task_id = created.json()["task"]["id"]
        executed = client.post(f"/v1/idle-queue/{task_id}/run", headers=headers)
        assert executed.status_code == 202
        job_id = executed.json()["job"]["id"]
        deadline = time.monotonic() + 10
        job = executed.json()["job"]
        while time.monotonic() < deadline and job["status"] not in {"succeeded", "failed"}:
            time.sleep(0.05)
            job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        queue = client.get("/v1/idle-queue", headers=headers).json()
    assert job["status"] == "succeeded", job
    assert queue["tasks"] == []


def test_extension_bridge_keeps_legacy_queue_contract(tmp_path: Path) -> None:
    queue = IdleQueueStore(tmp_path / "data")
    settings = SettingsStore(tmp_path / "data")
    with TestClient(create_extension_app(queue, settings)) as client:
        response = client.post(
            "/api/queue/add",
            json={
                "platform": "youtube",
                "url": "https://www.youtube.com/watch?v=test",
                "title": "Extension task",
            },
        )
        assert response.status_code == 201
        snapshot = client.get("/api/queue").json()
        assert snapshot["success"] is True
        assert snapshot["data"]["tasks"][0]["operation"] == "youtube.process"
        removed = client.delete(f"/api/queue/remove/{response.json()['task_id']}")
    assert removed.status_code == 200


def test_story_editor_routes_require_session_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        unauthorized = client.get("/api/story-editor/health")
        authorized = client.get("/api/story-editor/health?token=test-token")
        cookie_authorized = client.get("/api/story-editor/health")
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert cookie_authorized.status_code == 200


def test_idle_window_supports_overnight_ranges() -> None:
    from datetime import datetime

    assert is_in_idle_window(datetime(2026, 8, 24, 23, 30), "23:00", "07:00")
    assert is_in_idle_window(datetime(2026, 8, 24, 6, 30), "23:00", "07:00")
    assert not is_in_idle_window(datetime(2026, 8, 24, 12, 0), "23:00", "07:00")
