import json
import threading
import time
from pathlib import Path

import pytest

from src.learning import media, subtitles
from src.learning_server import create_app


SRT = "\ufeff1\n00:00:00,500 --> 00:00:03,000\nHello, world.\n\n2\n00:00:04,000 --> 00:00:08,000\nLearning takes practice.\n"


def test_download_import_keeps_progress_and_notes(workspace, monkeypatch, tmp_path):
    from src.learning import downloads

    app, client, headers, video = workspace
    service = app.config["LEARNING_SERVICE"]
    vid = video["id"]
    service.store.save_progress(vid, {"time": 12, "rate": 1, "mode": "source", "overlay": "source", "font": 20})
    service.store.save_item("notes", vid, {"id": "note-one", "text": "Keep this note"})
    source = Path(video["path"])
    source.with_suffix(".en.srt").write_text(SRT, encoding="utf-8")
    url = "https://www.youtube.com/watch?v=testvideo01"
    monkeypatch.setattr(
        downloads, "recent_downloads", lambda: [{"path": str(source), "source_url": url, "title": "Lesson"}]
    )
    root = tmp_path / "download-project"
    monkeypatch.setattr(downloads, "project_directory", lambda url: root)
    monkeypatch.setattr(downloads, "update_history", lambda *args: None)
    response = client.post("/api/learning/videos", json={"path": str(source)}, headers=headers)
    assert response.status_code == 201
    assert response.json["id"] == vid
    assert response.json["project_root"] == str(root.resolve())
    assert response.json["has_source"]
    assert response.json["progress"]["time"] == 12
    assert service.store.list_items("notes", vid)[0]["text"] == "Keep this note"
    again = client.post("/api/learning/videos", json={"path": response.json["path"]}, headers=headers)
    assert again.json["id"] == vid
    assert len(service.store.videos()) == 1


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    source = tmp_path / "中文 视频.mp4"
    source.write_bytes(b"0123456789" * 20)

    def probe(path):
        if not path.is_file():
            raise ValueError("请选择存在的本地视频文件")
        return {
            "duration": 60.0,
            "browser_ready": True,
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "codec": "h264",
            "audio_codec": "aac",
        }

    monkeypatch.setattr(media, "probe", probe)
    app = create_app(tmp_path / "db")
    app.testing = True
    client = app.test_client()
    headers = {"X-Learning-Token": client.get("/api/learning/session").json["token"]}
    video = client.post("/api/learning/videos", json={"path": str(source)}, headers=headers).json
    return app, client, headers, video


def test_parser_multiline_vtt_duplicate_and_invalid():
    cues = subtitles.parse(
        "WEBVTT\n\nintro\n00:00.500 --> 00:03.000 align:start\n<v teacher>Hello</v>\nworld\n\n00:00.500 --> 00:03.000\nHello\nworld",
        ".vtt",
    )
    assert len(cues) == 1
    assert cues[0]["text"] == "Hello\nworld"
    assert subtitles.parse(SRT)[0]["start"] == 0.5
    with pytest.raises(ValueError):
        subtitles.parse("1\n00:00:05,000 --> 00:00:04,000\nwrong")
    with pytest.raises(ValueError):
        subtitles.seconds("00:99:00,000")


def test_bilingual_srt_and_vtt_split_language_without_duplicate_lines(tmp_path):
    from src.learning.project import inspect_project

    content = "1\n00:00:00,000 --> 00:00:02,000\nA MacBook example.\n这是 MacBook 的例子。\n"
    for suffix in (".srt", ".vtt"):
        assert subtitles.parse(content, suffix, "source")[0]["text"] == "A MacBook example."
        assert subtitles.parse(content, suffix, "target")[0]["text"] == "这是 MacBook 的例子。"
    (tmp_path / "lesson.mp4").write_bytes(b"video")
    (tmp_path / "lesson_polished.srt").write_text(content, encoding="utf-8")
    project = inspect_project(str(tmp_path))
    assert {t["role"] for t in project["tracks"]} == {"source", "target"}
    monolingual = content.replace("这是 MacBook 的例子。", "This is a second English line.")
    assert "\n" in subtitles.parse(monolingual)[0]["text"]


def test_alignment_uses_time_instead_of_line_order():
    source = subtitles.parse(SRT)
    target = subtitles.normalize(
        [
            {"start": 0.4, "end": 2, "text": "你好"},
            {"start": 2, "end": 6, "text": "学习"},
            {"start": 6, "end": 9, "text": "需要练习"},
        ]
    )
    result = subtitles.aligned(source, target)
    assert result[0]["translation"] == "你好\n学习"
    assert result[1]["translation"] == "学习\n需要练习"
    assert result[0]["id"] == subtitles.parse(SRT)[0]["id"]


def test_local_security_and_registered_media_range(workspace):
    app, client, headers, video = workspace
    assert client.get("/api/learning/session", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/learning/videos", base_url="http://evil.example").status_code == 403
    assert client.post("/api/learning/videos", json={"path": "secret"}).status_code == 403
    assert (
        client.post("/api/learning/videos", headers={**headers, "Origin": "https://evil.example"}, json={}).status_code
        == 403
    )
    result = client.get(f"/api/learning/videos/{video['id']}/media", headers={"Range": "bytes=2-7"})
    assert result.status_code == 206
    assert result.data == b"234567"
    result.close()
    assert client.get("/api/learning/videos/unknown/media").status_code == 404
    assert client.get("/api/learning/videos/../../.env/media").status_code == 404


def test_progress_tracks_dedup_and_restart(workspace):
    app, client, headers, video = workspace
    vid = video["id"]
    response = client.post(
        f"/api/learning/videos/{vid}/subtitles",
        headers=headers,
        json={"role": "source", "content": SRT, "language": "en"},
    )
    assert response.status_code == 200
    version = response.json["subtitle_version"]
    assert len(response.json["cues"]) == 2
    assert (
        client.put(f"/api/learning/videos/{vid}/progress", headers=headers, json={"time": 27, "rate": 1.5}).status_code
        == 200
    )
    assert client.put(f"/api/learning/videos/{vid}/progress", headers=headers, json={"time": "NaN"}).status_code == 400
    duplicate = client.post("/api/learning/videos", headers=headers, json={"path": video["path"]})
    assert duplicate.json["id"] == vid
    restarted = create_app(app.config["LEARNING_SERVICE"].store.root).test_client()
    detail = restarted.get("/api/learning/videos/" + vid).json
    assert detail["progress"]["time"] == 27
    assert detail["subtitle_version"] == version
    assert len(restarted.get("/api/learning/videos").json["videos"]) == 1


def test_modified_video_requires_reregistration(workspace):
    _, client, headers, video = workspace
    Path(video["path"]).write_bytes(b"replaced")
    assert client.get(f"/api/learning/videos/{video['id']}/media").status_code == 400
    assert client.post("/api/learning/videos", headers=headers, json={"path": video["path"]}).status_code == 201


def wait_job(client, job_id):
    for _ in range(200):
        job = client.get("/api/learning/jobs/" + job_id).json
        if job["status"] not in {"queued", "running", "cancelling"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


class FakeProvider:
    name = "deepseek"
    model = "test-model"
    base = "http://127.0.0.1"
    budget = 24_000
    calls = []

    def __init__(self, *args):
        pass

    def require_key(self):
        pass

    def complete(self, messages, cancelled, max_tokens=1200):
        self.calls.append(messages)
        if "译为简体中文" in messages[0]["content"]:
            return json.dumps({k: "中文 " + v for k, v in json.loads(messages[1]["content"]).items()}), None
        return '{"title":"主题","summary":"学习与练习"}', None

    def stream(self, messages, cancelled, max_tokens=2200):
        self.calls.append(messages)
        import re

        ids = re.findall(r"\[cue:(c[a-f0-9]+)\]", messages[-1]["content"])
        yield {"text": "解释内容。 "}
        if cancelled.is_set():
            raise InterruptedError()
        yield {"text": "[cue:" + ids[0] + "] [cue:made-up]"}
        yield {"usage": {"total_tokens": 42}}


def with_ai(workspace):
    app, client, headers, video = workspace
    app.config["LEARNING_ASSISTANT"].provider_factory = FakeProvider
    FakeProvider.calls = []
    client.post(
        f"/api/learning/videos/{video['id']}/subtitles",
        headers=headers,
        json={"role": "source", "content": SRT, "language": "en"},
    )
    return app, client, headers, video


def test_chat_citations_usage_and_note_roundtrip(workspace):
    app, client, headers, video = with_ai(workspace)
    vid = video["id"]
    response = client.post(
        f"/api/learning/videos/{vid}/chat",
        headers=headers,
        json={"question": "Explain this", "time": 1, "scope": "current"},
    )
    assert response.status_code == 202
    job = wait_job(client, response.json["id"])
    assert job["status"] == "finished", job
    answer = job["result"]["answer"]
    assert answer["citations"][0]["text"] == "Hello, world."
    assert "[cue:made-up]" not in answer["text"]
    assert answer["warnings"]
    assert answer["usage"]["total_tokens"] == 42
    assert "Learning takes practice." not in FakeProvider.calls[-1][-1]["content"]
    note = client.post(f"/api/learning/videos/{vid}/notes", headers=headers, json={"answer_id": answer["id"]})
    assert note.status_code == 201
    item = note.json
    edited = client.patch(
        f"/api/learning/videos/{vid}/notes/{item['id']}",
        headers=headers,
        json={"text": "My note <script>alert(1)</script>", "version": item["version"], "tags": ["learning"]},
    )
    assert edited.status_code == 200
    assert (
        client.patch(
            f"/api/learning/videos/{vid}/notes/{item['id']}",
            headers=headers,
            json={"text": "stale overwrite", "version": item["version"]},
        ).status_code
        == 409
    )
    exported = client.get(f"/api/learning/videos/{vid}/export").data.decode()
    assert "&lt;script&gt;" in exported and "<script>" not in exported
    assert "Hello, world." in exported and "t=1.000" in exported
    assert "[cue:" not in exported
    restart = create_app(app.config["LEARNING_SERVICE"].store.root).test_client()
    assert len(restart.get(f"/api/learning/videos/{vid}/study").json["messages"]) == 2
    assert restart.get(f"/api/learning/videos/{vid}/notes").json["notes"][0]["tags"] == ["learning"]
    assert client.delete(f"/api/learning/videos/{vid}/notes/{item['id']}", headers=headers).status_code == 200


def test_translation_analysis_cache_and_changed_subtitles(workspace):
    _, client, headers, video = with_ai(workspace)
    vid = video["id"]
    first = client.post(f"/api/learning/videos/{vid}/prepare", headers=headers, json={"kind": "analysis"})
    assert wait_job(client, first.json["id"])["status"] == "finished"
    count = len(FakeProvider.calls)
    second = client.post(f"/api/learning/videos/{vid}/prepare", headers=headers, json={"kind": "analysis"})
    assert wait_job(client, second.json["id"])["status"] == "finished"
    assert len(FakeProvider.calls) == count
    changed = SRT.replace("Hello, world.", "Changed words.")
    client.post(f"/api/learning/videos/{vid}/subtitles", headers=headers, json={"content": changed})
    assert not client.get(f"/api/learning/videos/{vid}/study").json["outline"]
    translated = client.post(f"/api/learning/videos/{vid}/prepare", headers=headers, json={"kind": "translation"})
    assert wait_job(client, translated.json["id"])["status"] == "finished"
    detail = client.get(f"/api/learning/videos/{vid}").json
    assert detail["has_target"] and "中文 Changed words." in detail["cues"][0]["translation"]


def test_missing_key_bad_selection_and_search_validation(workspace, monkeypatch):
    app, client, headers, video = workspace
    vid = video["id"]
    client.post(f"/api/learning/videos/{vid}/subtitles", headers=headers, json={"content": SRT})
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert (
        client.post(f"/api/learning/videos/{vid}/chat", headers=headers, json={"question": "explain"}).status_code
        == 400
    )
    app.config["LEARNING_ASSISTANT"].provider_factory = FakeProvider
    assert (
        client.post(
            f"/api/learning/videos/{vid}/chat", headers=headers, json={"question": "explain", "cue_ids": ["bad"]}
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/learning/videos/{vid}/chat", headers=headers, json={"question": "explain", "search": True}
        ).status_code
        == 400
    )


def test_long_context_covers_all_chunks_without_silent_loss(tmp_path):
    from src.learning.context import build_outline, select_context
    from src.learning.store import Store

    cues = subtitles.normalize(
        [{"start": i * 10, "end": i * 10 + 8, "text": f"topic-{i} " + "learning " * 60} for i in range(100)]
    )
    store = Store(tmp_path)
    provider = FakeProvider()
    updates = []
    outline = build_outline(
        store,
        {"id": "demo", "subtitle_version": "one"},
        cues,
        provider,
        threading.Event(),
        lambda **value: updates.append(value),
    )
    assert len(outline) > 1
    assert set(c for part in outline for c in part["cue_ids"]) == {c["id"] for c in cues}
    assert updates[-1]["coverage"]["completed"] == updates[-1]["coverage"]["total"]
    picked = select_context(cues, "topic-99", 990, [cues[-1]["id"]], 4000)
    assert cues[-1]["id"] in {c["id"] for c in picked}


def test_cancellation_and_recovery(workspace):
    from src.learning.jobs import JobManager

    app, client, headers, video = workspace
    assistant = app.config["LEARNING_ASSISTANT"]

    def block(cancelled, update):
        while not cancelled.wait(0.01):
            pass
        raise InterruptedError()

    job = assistant.jobs.start(video["id"], "test", block)
    assert client.post("/api/learning/jobs/" + job["id"] + "/cancel", headers=headers, json={}).status_code == 200
    assert wait_job(client, job["id"])["status"] == "cancelled"
    assistant.store.save_job({"id": "unfinished", "video_id": video["id"], "kind": "test", "status": "cancelling"})
    JobManager(assistant.store)
    assert assistant.store.job("unfinished")["status"] == "interrupted"


def test_search_is_explicit_and_failure_preserves_video_answer(workspace):
    app, client, headers, video = with_ai(workspace)
    calls = []

    def search(name, query, cancelled):
        calls.append((name, query))
        raise ValueError("联网搜索超时")

    app.config["LEARNING_ASSISTANT"].search = search
    endpoint = f"/api/learning/videos/{video['id']}/chat"
    first = client.post(endpoint, headers=headers, json={"question": "explain"})
    assert wait_job(client, first.json["id"])["status"] == "finished"
    assert calls == []
    second = client.post(
        endpoint,
        headers=headers,
        json={"question": "explain", "search": True, "search_query": "learning research", "search_provider": "kimi"},
    )
    job = wait_job(client, second.json["id"])
    assert job["status"] == "finished"
    assert calls == [("kimi", "learning research")]
    assert any("超时" in w for w in job["result"]["answer"]["warnings"])
    assert job["result"]["answer"]["citations"]


@pytest.mark.parametrize("provider", ["deepseek", "kimi"])
def test_search_adapters_preserve_real_source_fields(monkeypatch, provider):
    from src.learning.search import search_web

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test")
    calls = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def json(self):
            item = (
                {
                    "title": "Evidence",
                    "url": "https://example.org/source",
                    "snippet": "summary",
                    "chunks": [{"text": "actual paragraph"}],
                }
                if provider == "kimi"
                else {"title": "Evidence", "url": "https://example.org/source", "content": "actual paragraph"}
            )
            return {"search_results" if provider == "kimi" else "results": [item, {"url": "javascript:bad"}]}

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return Response()

    monkeypatch.setattr("src.learning.search.requests.post", post)
    rows = search_web(provider, "only this query", threading.Event())
    assert len(rows) == 1 and rows[0]["content"] == "actual paragraph"
    assert rows[0]["url"] == "https://example.org/source" and rows[0]["retrieved"]
    assert "tools/search_pro" in calls[0][0] if provider == "kimi" else "tools/search" in calls[0][0]
    assert calls[0][1].get("text_query", calls[0][1].get("query")) == "only this query"


def test_directory_and_subtitle_reuse(workspace, tmp_path):
    from src.learning.imports import subtitle_candidates

    _, client, headers, video = workspace
    path = Path(video["path"])
    english = path.with_suffix(".en.srt")
    chinese = path.with_suffix(".zh-CN.srt")
    english.write_text(SRT, encoding="utf-8")
    chinese.write_text(SRT.replace("Hello, world.", "你好。"), encoding="utf-8")
    choices = subtitle_candidates(video["path"], tmp_path)
    assert {r["role"] for r in choices} == {"source", "target"}
    response = client.post("/api/learning/imports/directory", headers=headers, json={"path": str(path.parent)})
    assert response.status_code == 200
    assert response.json["videos"][0]["path"] == video["path"]
    candidates = client.get(f"/api/learning/videos/{video['id']}/subtitle-candidates").json["tracks"]
    source = next(c for c in candidates if c["path"] == str(english))
    assert client.post(f"/api/learning/videos/{video['id']}/subtitles", headers=headers, json=source).status_code == 200


def test_project_auto_loads_all_subtitles_and_survives_move(workspace, tmp_path):
    import shutil

    app, client, headers, video = workspace
    root = tmp_path / "课程工程"
    root.mkdir()
    shutil.copy2(video["path"], root / "lecture.mp4")
    (root / "English.srt").write_text(SRT, encoding="utf-8")
    (root / "中文字幕.srt").write_text(SRT.replace("Hello, world.", "你好。"), encoding="utf-8")
    (root / "lecture.ja.vtt").write_text(SRT.replace("Hello, world.", "こんにちは。"), encoding="utf-8")
    result = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root)})
    assert result.status_code == 200, result.json
    detail = result.json["video"]
    assert detail["has_source"] and detail["has_target"]
    assert len(detail["available_tracks"]) == 3
    assert "你好" in detail["cues"][0]["translation"]
    manifest = json.loads((root / "videohub_learning.json").read_text(encoding="utf-8"))
    assert manifest["video"] == "lecture.mp4"
    assert all(not Path(t["path"]).is_absolute() for t in manifest["subtitles"])
    assert (
        client.post(
            f"/api/learning/videos/{detail['id']}/notes", headers=headers, json={"text": "keep this note"}
        ).status_code
        == 201
    )
    moved = tmp_path / "移后的课程"
    shutil.copytree(root, moved)
    reopened = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(moved)})
    assert reopened.json["video"]["id"] == detail["id"]
    assert reopened.json["video"]["path"] == str(moved / "lecture.mp4")
    assert len(client.get(f"/api/learning/videos/{detail['id']}/notes").json["notes"]) == 1
    ja = next(t for t in reopened.json["video"]["available_tracks"] if t["language"] == "ja")
    switched = client.post(
        f"/api/learning/videos/{detail['id']}/select-track", headers=headers, json={"role": "source", "key": ja["key"]}
    )
    assert switched.status_code == 200 and switched.json["tracks"]["source"]["language"] == "ja"


def test_project_multiple_videos_requires_selection(workspace, tmp_path):
    import shutil

    _, client, headers, video = workspace
    root = tmp_path / "multiple"
    root.mkdir()
    for name in ("one", "two"):
        shutil.copy2(video["path"], root / (name + ".mp4"))
        (root / (name + ".en.srt")).write_text(SRT.replace("Hello", name), encoding="utf-8")
    result = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root)})
    assert result.json["needs_selection"] and len(result.json["videos"]) == 2
    chosen = client.post(
        "/api/learning/imports/project",
        headers=headers,
        json={"directory": str(root), "video_path": str(root / "two.mp4")},
    )
    assert chosen.json["video"]["cues"][0]["text"] == "two, world."
    assert len(chosen.json["video"]["available_tracks"]) == 1


def test_learning_service_import_does_not_require_ml_runtime():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.learning_server; assert 'torch' not in sys.modules; assert 'whisper' not in sys.modules",
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_transcription_padding_is_never_used_as_video_evidence(tmp_path):
    cues = subtitles.normalize(
        [
            {"start": 0, "end": 5, "text": "real speech"},
            {"start": 59, "end": 65, "text": "crossing boundary"},
            {"start": 60, "end": 84, "text": "padding hallucination"},
        ]
    )
    valid, changed = subtitles.bound_transcription(cues, 60)
    assert changed == 2
    assert len(valid) == 2 and valid[-1]["end"] == 60
    path = tmp_path / "validated.srt"
    subtitles.write_srt(path, valid)
    assert len(subtitles.read_track(path)["cues"]) == 2
    assert "hallucination" not in path.read_text()


def test_bilingual_ass_is_split_into_real_source_and_target_tracks(workspace, tmp_path):
    import shutil

    _, client, headers, video = workspace
    root = tmp_path / "ass-project"
    root.mkdir()
    shutil.copy2(video["path"], root / "lesson.mp4")
    ass = """[Script Info]
ScriptType: v4.00+
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.50,0:00:03.00,Primary,,0,0,0,,Hello, world.
Dialogue: 0,0:00:00.50,0:00:03.00,Secondary,,0,0,0,,你好，世界。
"""
    (root / "bilingual.ass").write_text(ass, encoding="utf-8")
    result = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root)})
    assert result.status_code == 200, result.json
    detail = result.json["video"]
    assert detail["has_source"] and detail["has_target"]
    assert len(detail["cues"]) == 1 and detail["cues"][0]["text"] == "Hello, world."
    assert detail["cues"][0]["translation"] == "你好，世界。"


def test_manual_track_overrun_is_rejected_and_optional_ai_config_cannot_break_playback(workspace, monkeypatch):
    _, client, headers, video = workspace
    result = client.post(
        f"/api/learning/videos/{video['id']}/subtitles",
        headers=headers,
        json={"content": "1\n00:00:59,000 --> 00:01:30,000\nwrong duration"},
    )
    assert result.status_code == 400
    monkeypatch.setenv("DEEPSEEK_MODEL", "invalid model name")
    response = client.get("/api/learning/session")
    assert response.status_code == 200 and response.json["providers"]["deepseek"]["error"]
    assert client.get(f"/api/learning/videos/{video['id']}").status_code == 200
