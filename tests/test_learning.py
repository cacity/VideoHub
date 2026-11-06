import json
import threading
import time
from pathlib import Path

import pytest

from src.learning import media, subtitles
from src.learning_server import create_app


SRT = "\ufeff1\n00:00:00,500 --> 00:00:03,000\nHello, world.\n\n2\n00:00:04,000 --> 00:00:08,000\nLearning takes practice.\n"


def test_existing_subtitle_translation_retains_versions_and_survives_restart(workspace):
    app, client, headers, video = workspace
    service = app.config["LEARNING_SERVICE"]
    route = "/api/learning/videos/" + video["id"]
    app.config["LEARNING_ASSISTANT"].provider_factory = FakeProvider
    source = client.post(route + "/subtitles", headers=headers, json={"content": SRT, "role": "source", "language": "en"}).json
    original_path = source["tracks"]["source"]["path"]
    original_bytes = Path(original_path).read_bytes()
    old = client.post(route + "/subtitles", headers=headers, json={"role": "target", "content": SRT.replace("Hello, world.", "第一版译文。"), "language": "zh-CN"}).json
    old_path = old["tracks"]["target"]["path"]
    service.progress(video["id"], {"time": 27, "rate": 1.3})
    service.store.save_item("notes", video["id"], {"id": "retained-note", "text": "Keep"})
    bad = client.post(route + "/prepare", headers=headers, json={"kind": "translation", "source_hash": "stale"})
    assert bad.status_code == 400 and "原文字幕已改变" in bad.json["error"]
    response = client.post(route + "/prepare", headers=headers, json={"kind": "translation", "source_hash": source["tracks"]["source"]["hash"]})
    assert response.status_code == 202
    job = wait_job(client, response.json["id"])
    assert job["status"] == "finished", job
    translated = client.get(route).json
    assert translated["tracks"]["source"]["path"] == original_path
    assert Path(original_path).read_bytes() == original_bytes
    assert translated["playback_cues"]["target"][0]["start"] == 0.5
    assert translated["progress"]["time"] == 27 and translated["progress"]["rate"] == 1.3
    assert service.store.list_items("notes", video["id"])[0]["text"] == "Keep"
    previous = next(t for t in translated["available_tracks"] if t["key"].startswith("available-") and t["path"] == old_path)
    assert "AI翻译" in next(t for t in translated["available_tracks"] if t["key"] == "target")["label"]
    restarted_app = create_app(service.store.root)
    restarted = restarted_app.test_client()
    restarted_headers = {"X-Learning-Token": restarted.get("/api/learning/session").json["token"]}
    selected = restarted.post(route + "/select-track", headers=restarted_headers, json={"role": "target", "key": previous["key"]})
    assert selected.json["tracks"]["target"]["path"] == old_path
    assert selected.json["cues"][0]["translation"] == "第一版译文。"
    # Current + historical files can be found even with generic snapshot names.
    files = restarted.get(route + "/subtitle-candidates").json["tracks"]
    assert {original_path, old_path, translated["tracks"]["target"]["path"]} <= {f["path"] for f in files}
    assert restarted.post(route + "/select-track", headers=restarted_headers, json={"role": "source", "key": "target"}).status_code == 400
    exported = restarted.get(route + "/subtitle-file?role=target")
    assert "第一版译文" in exported.data.decode("utf-8")
    exported.close()


def test_imported_versions_keep_selected_tracks_and_distinct_edits(workspace):
    app, client, headers, video = workspace
    service = app.config["LEARNING_SERVICE"]
    vid = video["id"]
    a = service.add_track(vid, {"role": "source", "content": SRT, "language": "en"})
    b = service.add_track(vid, {"role": "source", "content": SRT.replace("Hello", "Hi"), "language": "en"})
    old = next(t for t in b["available_tracks"] if t["path"] == a["tracks"]["source"]["path"])
    service.select_track(vid, {"role": "source", "key": old["key"]})
    # Merely registering/reopening the video must not reset the chosen version.
    again = service.register(video["path"], tracks=[{"role": "source", "content": SRT.replace("Hello", "New"), "language": "en"}])
    assert again["tracks"]["source"]["path"] == a["tracks"]["source"]["path"]
    assert again["subtitle_version"] == a["subtitle_version"]
    texts = [t["cues"][0]["text"] for t in service.store.tracks(vid).values()]
    assert {"Hello, world.", "Hi, world.", "New, world."} <= set(texts)


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "source-changed"])
def test_incomplete_translation_keeps_previous_version(workspace, outcome):
    app, client, headers, video = workspace
    service = app.config["LEARNING_SERVICE"]
    vid = video["id"]
    service.add_track(vid, {"role": "source", "content": SRT, "language": "en"})
    before = service.add_track(vid, {"role": "target", "content": SRT.replace("Hello, world.", "保留旧译文。"), "language": "zh-CN"})

    class Incomplete(FakeProvider):
        def complete(self, messages, cancelled, max_tokens=1200):
            if outcome == "failure":
                raise ValueError("模拟翻译失败")
            if outcome == "cancelled":
                cancelled.set()
            else:
                service.add_track(vid, {"role": "source", "content": SRT.replace("Hello", "Changed"), "language": "en"})
            return super().complete(messages, cancelled, max_tokens)

    app.config["LEARNING_ASSISTANT"].provider_factory = Incomplete
    route = "/api/learning/videos/" + vid
    response = client.post(route + "/prepare", headers=headers, json={"kind": "translation"})
    job = wait_job(client, response.json["id"])
    assert job["status"] == ("cancelled" if outcome == "cancelled" else "failed"), job
    assert client.get(route).json["tracks"]["target"]["path"] == before["tracks"]["target"]["path"]


def test_learning_html_is_not_stored_across_restarts(tmp_path, monkeypatch):
    from src import learning_server

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "learning.html").write_text("<html>fresh learning page</html>", encoding="utf-8")
    monkeypatch.setattr(learning_server, "FRONTEND_DIST", frontend)
    for _ in range(2):
        client = create_app(tmp_path / "store").test_client()
        for route in ("/", "/learn", "/learn?launch=fresh"):
            response = client.get(route)
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "no-store"
            response.close()


@pytest.mark.parametrize("mode", ["library", "video", "project", "project-multiple"])
def test_desktop_open_gets_fresh_url_without_disclosing_session_token(monkeypatch, mode):
    from src import learning_desktop
    from urllib.parse import parse_qs, urlparse

    class Reply:
        ok = True

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def get(url, **kwargs):
        return Reply({"service": "videohub-learning"} if url.endswith("/health") else {"token": "private-session"})

    def post(url, **kwargs):
        assert kwargs["headers"]["X-Learning-Token"] == "private-session"
        if mode == "project-multiple":
            return Reply({"needs_selection": True, "videos": [{"path": "one.mp4"}, {"path": "two.mp4"}]})
        return Reply({"video": {"id": "test-id"}} if url.endswith("/imports/project") else {"id": "test-id"})

    monkeypatch.setattr(learning_desktop.requests, "get", get)
    monkeypatch.setattr(learning_desktop.requests, "post", post)
    options = {"path": "test.mp4"} if mode == "video" else {"directory": "project"} if mode.startswith("project") else {}
    urls = [learning_desktop.learning_url(**options) for _ in range(2)]
    assert urls[0] != urls[1]
    for url in urls:
        query = parse_qs(urlparse(url).query)
        assert "private-session" not in url
        assert len(query["launch"][0]) == 16
        assert query.get("video") == (["test-id"] if mode in {"video", "project"} else None)
        if mode == "project-multiple":
            assert query["directory"] == ["project"]


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


def test_playback_tracks_keep_independent_clocks_and_exclude_alternatives(workspace):
    app, client, headers, video = workspace
    source = (
        "1\n00:00:30,240 --> 00:00:36,320\nexterior, interior\n\n"
        "2\n00:00:32,880 --> 00:00:38,399\ndetails? Some stories"
    )
    target = (
        "1\n00:00:25,919 --> 00:00:33,280\n外观、内饰有哪些细节？\n\n"
        "2\n00:00:33,839 --> 00:00:39,239\n有些内容只在这里呈现。"
    )
    service = app.config["LEARNING_SERVICE"]
    detail = service.register(video["path"], tracks=[
        {"content": source, "role": "source"},
        {"content": target, "role": "target"},
        {"content": source.replace("exterior, interior", "alternative track"), "role": "source"},
    ])
    assert len(detail["available_tracks"]) == 3
    playback = detail["playback_cues"]
    assert playback["source"] == subtitles.parse(source)
    assert playback["target"] == subtitles.parse(target, role="target")
    # The transcript may relate several translations to a source cue, but
    # the overlay must not show a later translation ahead of its own clock.
    assert len([c for c in playback["target"] if c["start"] <= 33 < c["end"]]) == 1
    assert "有些内容" in detail["cues"][0]["translation"]
    assert not any("alternative" in c["text"] for rows in playback.values() for c in rows)
    key = next(t["key"] for t in detail["available_tracks"] if t["key"].startswith("available-"))
    switched = client.post(
        f"/api/learning/videos/{video['id']}/select-track", headers=headers, json={"key": key, "role": "source"}
    ).json
    assert switched["playback_cues"]["source"][0]["text"] == "alternative track"
    assert switched["playback_cues"]["target"] == playback["target"]


def test_target_only_playback_does_not_duplicate_track_as_source(workspace):
    _, client, headers, video = workspace
    result = client.post(
        f"/api/learning/videos/{video['id']}/subtitles", headers=headers,
        json={"role": "target", "language": "zh-CN", "content": SRT.replace("Hello, world.", "你好，世界。")},
    ).json
    assert result["playback_cues"]["source"] == []
    assert result["playback_cues"]["target"][0]["text"] == "你好，世界。"
    assert result["cues"][0]["translation"] == "你好，世界。"


def test_bilingual_import_creates_downloadable_single_language_files_without_changing_version(workspace):
    app, client, headers, video = workspace
    service = app.config["LEARNING_SERVICE"]
    mixed = "1\n00:00:01,250 --> 00:00:03,500\nHello.\n你好。\n"
    source = service.prepare_track({"content": mixed, "role": "source", "language": "en"})
    target = service.prepare_track({"content": mixed, "role": "target", "language": "zh-CN"})
    service.store.save_tracks(video["id"], {"source": source, "target": target})
    service.store.save_progress(video["id"], {"time": 12, "font": 20, "rate": 1, "mode": "bilingual", "overlay": "target"})
    import hashlib
    expected_version = hashlib.sha256((source["hash"] + "|" + target["hash"]).encode()).hexdigest()
    detail = client.get(f"/api/learning/videos/{video['id']}").json
    assert detail["subtitle_version"] == expected_version and detail["progress"]["time"] == 12
    for role, wanted, unwanted in [("source", "Hello.", "你好"), ("target", "你好。", "Hello")]:
        track = detail["tracks"][role]
        assert f".{role}." in Path(track["path"]).name and track["separate_file"]
        response = client.get(detail["subtitle_urls"][role])
        content = response.data.decode("utf-8")
        assert wanted in content and unwanted not in content and "00:00:01,250" in content
        assert response.status_code == 200 and "attachment" in response.headers["Content-Disposition"]
    assert client.get(f"/api/learning/videos/{video['id']}/subtitle-file?role=../../file").status_code == 400
    again = client.get(f"/api/learning/videos/{video['id']}").json
    assert again["subtitle_version"] == detail["subtitle_version"] and again["tracks"] == detail["tracks"]


def test_subtitle_style_persists_without_modifying_cues_and_rejects_css_values(workspace):
    _, client, headers, video = workspace
    route = f"/api/learning/videos/{video['id']}"
    before = client.get(route).json
    style = {"font_family": "serif", "source_color": "#123456", "target_color": "#abcdef", "background": 0.6,
             "position": "top", "bold": True, "outline": False, "line_height": 1.8}
    response = client.put(route + "/progress", headers=headers, json={"style": style, "font": 28, "time": 10})
    assert response.status_code == 200 and response.json["style"] == style
    detail = client.get(route).json
    assert detail["progress"]["style"] == style and detail["progress"]["font"] == 28
    assert detail["cues"] == before["cues"] and detail["subtitle_version"] == before["subtitle_version"]
    for patch in [{"source_color": "url(secret)"}, {"font_family": "anything"}, {"font_family": []}, {"background": "nan"}, {"bold": "yes"}, {"position": "fixed"}, {"position": {}}, {"extra_css": "red"}]:
        assert client.put(route + "/progress", headers=headers, json={"style": patch}).status_code == 400
    assert client.get(route).json["progress"]["style"] == style


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


def test_failed_chat_restores_reason_and_retries_original_context_without_duplicate_question(workspace):
    app, client, headers, video = with_ai(workspace)
    assistant = app.config["LEARNING_ASSISTANT"]
    service = app.config["LEARNING_SERVICE"]
    route = f"/api/learning/videos/{video['id']}"
    searches = []
    assistant.search = lambda provider, query, cancelled: searches.append(query) or []

    class Failing(FakeProvider):
        def stream(self, messages, cancelled, max_tokens=2200):
            yield {"text": "保留已返回的部分正文"}
            raise ValueError("模型回复未完整结束（达到输出长度限制）")

    assistant.provider_factory = Failing
    response = client.post(route + "/chat", headers=headers, json={
        "question": "Explain this", "time": 1, "scope": "current", "search": True, "search_query": "concept",
    })
    failed = wait_job(client, response.json["id"])
    assert failed["status"] == "failed"
    study = client.get(route + "/study").json
    answer = study["messages"][-1]
    assert "输出长度限制" in answer["error"] and answer["text"] == "保留已返回的部分正文"
    assert study["latest_job"]["id"] == failed["id"] and study["active_job"] is None
    # Old failed messages had no error field; recover it from their linked job.
    answer.pop("error")
    service.store.save_item("messages", video["id"], answer)
    assert "输出长度限制" in client.get(route + "/study").json["messages"][-1]["error"]
    service.progress(video["id"], {"time": 23})
    assistant.provider_factory = FakeProvider
    retried = client.post(route + "/messages/" + answer["id"] + "/retry", headers=headers, json={
        "provider": "deepseek", "model": "test-model", "question": "must be ignored", "time": 59, "scope": "full",
    })
    assert retried.status_code == 202
    result = wait_job(client, retried.json["id"])
    assert result["status"] == "finished", result
    messages = client.get(route + "/study").json["messages"]
    assert len(messages) == 3 and sum(m["role"] == "user" for m in messages) == 1
    assert messages[-1]["time"] == 1 and messages[-1]["scope"] == "current"
    assert "Learning takes practice." not in FakeProvider.calls[-1][-1]["content"]
    assert "must be ignored" not in FakeProvider.calls[-1][-1]["content"]
    assert searches == ["concept", "concept"]
    assert service.detail(video["id"])["progress"]["time"] == 23
    assert client.post(route + "/messages/" + messages[-1]["id"] + "/retry", headers=headers, json={}).status_code == 400
    service.add_track(video["id"], {"role": "source", "content": SRT.replace("Hello", "Changed")})
    stale = client.post(route + "/messages/" + answer["id"] + "/retry", headers=headers, json={})
    assert stale.status_code == 400 and "字幕已改变" in stale.json["error"]


def mock_model_streams(monkeypatch, responses):
    """Exercise the real provider parser with synthetic HTTP/SSE only."""
    from src.learning.providers import Provider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://model.example.test")
    calls = []

    class Reply:
        status_code = 200

        def __init__(self, spec):
            self.spec = spec
            self.status_code = spec.get("status", 200)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_lines(self, **kwargs):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": self.spec.get("text", "")},
                                                       "finish_reason": self.spec.get("finish", "stop")}],
                                         "usage": {"total_tokens": 10}})
            yield "data: [DONE]"

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        assert responses, "unexpected extra model attempt"
        return Reply(responses.pop(0))

    monkeypatch.setattr("src.learning.providers.requests.post", post)
    return Provider("deepseek", "deepseek-chat"), calls


def test_structured_output_length_retry_discards_partial_json_and_is_bounded(monkeypatch):
    from src.learning.providers import OutputLimitError

    replies = [{"text": '{"title":"cut', "finish": "length"}, {"text": '{"title":"ok"}'}]
    provider, calls = mock_model_streams(monkeypatch, replies)
    messages = [{"role": "user", "content": "json please"}]
    text, usage = provider.complete(messages, threading.Event(), 650)
    assert text == '{"title":"ok"}' and usage["total_tokens"] == 10
    assert [c["max_tokens"] for c in calls] == [650, 2048]
    assert all(c["model"] == "deepseek-chat" and c["messages"] == messages for c in calls)
    replies.extend([{"finish": "length"}, {"finish": "length"}])
    with pytest.raises(OutputLimitError):
        provider.complete(messages, threading.Event(), 6000)
    assert [c["max_tokens"] for c in calls[-2:]] == [6000, 8192]


@pytest.mark.parametrize("spec", [{"status": 401}, {"finish": None}, {"text": "", "finish": "stop"}])
def test_structured_output_does_not_retry_auth_disconnection_or_empty_body(monkeypatch, spec):
    provider, calls = mock_model_streams(monkeypatch, [spec])
    with pytest.raises(ValueError):
        provider.complete([{"role": "user", "content": "test"}], threading.Event(), 650)
    assert len(calls) == 1


def test_streamed_chat_is_not_replayed_after_output_limit(monkeypatch):
    from src.learning.providers import OutputLimitError

    provider, calls = mock_model_streams(monkeypatch, [{"text": "partial answer", "finish": "length"}])
    events = []
    with pytest.raises(OutputLimitError):
        for event in provider.stream([{"role": "user", "content": "test"}], threading.Event()):
            events.append(event)
    assert len(calls) == 1 and any(e.get("text") == "partial answer" for e in events)


def test_outline_length_failure_retains_completed_parts_and_retry_resumes_cache(workspace, monkeypatch):
    from src.learning.context import build_outline

    app, _, _, video = workspace
    good = {"text": '{"title":"Topic","summary":"A concise summary"}'}
    replies = [good, {"finish": "length"}, {"finish": "length"}]
    provider, calls = mock_model_streams(monkeypatch, replies)
    provider.budget = 8000
    cues = subtitles.normalize([{"start": i * 10, "end": i * 10 + 5, "text": "A" * 2800} for i in range(3)])
    service = app.config["LEARNING_SERVICE"]
    detail = service.detail(video["id"])
    with pytest.raises(ValueError, match="第 2/3 段未完成"):
        build_outline(service.store, detail, cues, provider, threading.Event(), lambda **kw: None)
    replies.extend([good, good])
    outline = build_outline(service.store, detail, cues, provider, threading.Event(), lambda **kw: None)
    assert len(outline) == 3 and len(calls) == 5, "retry only unfinished parts; preserve successful first part"
    assert build_outline(service.store, detail, cues, provider, threading.Event(), lambda **kw: None) == outline
    assert len(calls) == 5


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


class MindmapProvider(FakeProvider):
    def complete(self, messages, cancelled, max_tokens=1200):
        if "一张中文脑图" not in messages[-1]["content"]:
            return super().complete(messages, cancelled, max_tokens)
        import re
        self.calls.append(messages)
        indices = [int(i) for i in re.findall(r"^(\d+)\. ", messages[-1]["content"], re.M)]
        return json.dumps({"organization": "topics", "explanation": "多个话题，按主题归纳，不推断因果。",
                           "root": {"label": "视频学习", "summary": "主题概览", "children": [
                               {"label": f"主题{i}", "summary": "来自字幕的主题", "chapter_indices": [i]}
                               for i in indices]}}, ensure_ascii=False), {"total_tokens": 23}


def test_mindmap_generation_coverage_cache_export_restart_and_version(workspace):
    app, client, headers, video = with_ai(workspace)
    assistant = app.config["LEARNING_ASSISTANT"]
    assistant.provider_factory = MindmapProvider
    vid = video["id"]
    endpoint = f"/api/learning/videos/{vid}"
    assert client.get("/api/learning/session").json["features"]["mindmap"] is True
    assert client.get(endpoint + "/study").json["mindmap"] is None
    assert client.get(endpoint + "/mindmap/export").status_code == 404
    assert client.post(endpoint + "/prepare", json={"kind": "mindmap"}).status_code == 403
    created = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"})
    assert created.status_code == 202
    finished = wait_job(client, created.json["id"])
    assert finished["status"] == "finished", finished
    value = finished["result"]["mindmap"]
    assert value["organization"] == "topics" and value["coverage"]["cues"] == 2
    assert value["root"]["start"] == .5 and value["root"]["end"] == 8
    assert value["root"]["chapter_indices"] == [0]
    study = client.get(endpoint + "/study").json
    assert study["mindmap"] == value and len(study["outline"]) == 1
    count = len(FakeProvider.calls)
    again = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"})
    assert wait_job(client, again.json["id"])["status"] == "finished"
    assert len(FakeProvider.calls) == count
    regenerated = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap", "force": True})
    assert wait_job(client, regenerated.json["id"])["status"] == "finished"
    assert len(FakeProvider.calls) == count + 1, "reuse chapter cache but regenerate the semantic map"
    markdown = client.get(endpoint + "/mindmap/export")
    assert markdown.status_code == 200 and "attachment" in markdown.headers["Content-Disposition"]
    assert f"/learn?video={vid}&t=0.500" in markdown.text
    assert client.get(endpoint + "/mindmap/export?format=json").json["root"]["label"] == "视频学习"
    assert client.get(endpoint + "/mindmap/export?format=html").status_code == 400
    restarted = create_app(assistant.store.root).test_client()
    assert restarted.get(endpoint + "/study").json["mindmap"] is not None
    for i in range(31):
        assistant.store.save_job({"id": f"later-{i}", "video_id": vid, "kind": "chat", "status": "finished"})
    assert client.get(endpoint + "/study").json["mindmap"] is not None, "map is durable beyond the recent-job window"
    client.post(endpoint + "/subtitles", headers=headers, json={"content": SRT.replace("Hello", "Changed")})
    assert client.get(endpoint + "/study").json["mindmap"] is None
    assert client.get(endpoint + "/mindmap/export").status_code == 404


def test_mindmap_failure_preserves_last_valid_result_and_requires_source(workspace):
    app, client, headers, video = workspace
    vid = video["id"]
    endpoint = f"/api/learning/videos/{vid}"
    assert client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"}).status_code == 400
    app, client, headers, video = with_ai(workspace)
    assistant = app.config["LEARNING_ASSISTANT"]
    assistant.provider_factory = MindmapProvider
    request = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"})
    assert wait_job(client, request.json["id"])["status"] == "finished"
    before = client.get(endpoint + "/study").json["mindmap"]

    class Invalid(MindmapProvider):
        def complete(self, messages, cancelled, max_tokens=1200):
            if "一张中文脑图" in messages[-1]["content"]:
                return '{"organization":"logical","explanation":"test","root":{"label":"bad","chapter_indices":[999]}}', None
            return super().complete(messages, cancelled, max_tokens)

    assistant.provider_factory = Invalid
    request = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap", "force": True})
    result = wait_job(client, request.json["id"])
    assert result["status"] == "failed" and "不存在的字幕章节" in result["message"]
    assert client.get(endpoint + "/study").json["mindmap"] == before


def test_mindmap_long_video_reads_every_original_chunk(workspace):
    app, client, headers, video = with_ai(workspace)
    from src.learning.store import Store
    from src.learning.mindmap import build_mindmap
    from types import SimpleNamespace
    cues = subtitles.normalize([{"start": i * 10, "end": i * 10 + 8,
                                 "text": f"topic-{i} " + "learning " * 60} for i in range(100)])
    detail = {"id": "demo", "subtitle_version": "v1", "cues": cues}
    store = Store(app.config["LEARNING_SERVICE"].store.root / "map-fixture")
    assistant = SimpleNamespace(store=store, service=SimpleNamespace(detail=lambda _: detail))
    provider = MindmapProvider()
    FakeProvider.calls = []
    result = build_mindmap(assistant, detail, provider, threading.Event(), lambda **_: None)
    assert result["coverage"]["cues"] == 100 and result["coverage"]["parts"] > 1
    supplied = "\n".join(m[-1]["content"] for m in FakeProvider.calls[:-1])
    assert all(f"[cue:{c['id']}]" in supplied for c in cues)
    assert result["root"]["end"] == cues[-1]["end"]
    assert len(result["root"]["chapter_indices"]) == result["coverage"]["parts"]


@pytest.mark.parametrize("invalid", ["missing", "invented", "bool", "deep", "many"])
def test_mindmap_rejects_missing_evidence_and_unbounded_trees(invalid):
    from src.learning.mindmap import validate_tree
    outline = [{"start": 0, "end": 1}, {"start": 2, "end": 3}]
    root = {"label": "主题", "chapter_indices": [0, 1]}
    if invalid == "missing":
        root["chapter_indices"] = [0]
    elif invalid == "invented":
        root["chapter_indices"] = [0, 1, 999]
    elif invalid == "bool":
        root["chapter_indices"] = [False, True]
    elif invalid == "many":
        root["children"] = [{"label": "一", "chapter_indices": [0]} for _ in range(100)]
    else:
        for _ in range(6):
            root = {"label": "深层", "children": [root]}
    with pytest.raises(ValueError):
        validate_tree({"organization": "logical", "explanation": "测试", "root": root}, outline)


def test_mindmap_cancellation_and_subtitle_change_do_not_publish(workspace):
    app, client, headers, video = with_ai(workspace)
    assistant = app.config["LEARNING_ASSISTANT"]
    vid = video["id"]
    endpoint = f"/api/learning/videos/{vid}"

    class Changing(MindmapProvider):
        def complete(self, messages, cancelled, max_tokens=1200):
            result = super().complete(messages, cancelled, max_tokens)
            if "一张中文脑图" in messages[-1]["content"]:
                assistant.service.add_track(vid, {"content": SRT.replace("Hello", "Changed")})
            return result

    assistant.provider_factory = Changing
    request = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"})
    result = wait_job(client, request.json["id"])
    assert result["status"] == "failed" and "字幕在生成过程中已改变" in result["message"]
    assert client.get(endpoint + "/study").json["mindmap"] is None

    class Cancelling(MindmapProvider):
        def complete(self, messages, cancelled, max_tokens=1200):
            result = super().complete(messages, cancelled, max_tokens)
            if "一张中文脑图" in messages[-1]["content"]:
                cancelled.set()
            return result

    assistant.provider_factory = Cancelling
    request = client.post(endpoint + "/prepare", headers=headers, json={"kind": "mindmap"})
    assert wait_job(client, request.json["id"])["status"] == "cancelled"
    assert client.get(endpoint + "/study").json["mindmap"] is None


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


def test_collection_import_retains_each_video_versions_and_state_after_move(workspace, tmp_path):
    import shutil

    app, client, headers, fixture = workspace
    service = app.config["LEARNING_SERVICE"]
    root = tmp_path / "课程合集"
    root.mkdir()
    for name in ("one", "two"):
        (root / f"{name}.mp4").write_bytes(Path(fixture["path"]).read_bytes() + name.encode())
        (root / f"{name}.en.srt").write_text(SRT.replace("Hello", name), encoding="utf-8")
        (root / f"{name}.zh-CN.srt").write_text(SRT.replace("Hello", name + "中文"), encoding="utf-8")
    endpoint = "/api/learning/imports/project"
    result = client.post(endpoint, headers=headers, json={"directory": str(root), "import_all": True})
    assert result.status_code == 200 and not result.json["errors"], result.json
    first, second = result.json["imported"]
    assert first["id"] != second["id"]
    for item in (first, second):
        assert item["cues"][0]["text"] == item["title"] + ", world."
        assert item["cues"][0]["translation"] == item["title"] + "中文, world."
        assert len(item["available_tracks"]) == 2
    service.progress(first["id"], {"time": 19, "rate": 1.3})
    service.progress(second["id"], {"time": 35, "rate": 1.1})
    service.store.save_item("notes", first["id"], {"id": "one-note", "text": "one only"})
    old = service.add_track(first["id"], {"role": "target", "content": SRT.replace("Hello", "新译文"), "language": "zh-CN"})
    current = old["tracks"]["target"]["path"]
    assert Path(current).parent.name == first["id"]
    again = client.post(endpoint, headers=headers, json={"directory": str(root), "import_all": True}).json
    assert [v["id"] for v in again["imported"]] == [first["id"], second["id"]]
    assert again["imported"][0]["tracks"]["target"]["path"] == current
    manifest = json.loads((root / "videohub_learning.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2 and len(manifest["videos"]) == 2
    assert {v["video"] for v in manifest["videos"]} == {"one.mp4", "two.mp4"}
    moved = tmp_path / "移动后的合集"
    shutil.move(str(root), moved)
    reopened = client.post(endpoint, headers=headers, json={"directory": str(moved), "import_all": True}).json
    assert not reopened["errors"], reopened
    a, b = reopened["imported"]
    assert [a["id"], b["id"]] == [first["id"], second["id"]]
    assert [a["progress"]["time"], b["progress"]["time"]] == [19, 35]
    assert "新译文" in a["cues"][0]["translation"]
    assert service.store.list_items("notes", a["id"])[0]["text"] == "one only"
    assert not service.store.list_items("notes", b["id"])
    choices = service.subtitle_candidates(a["id"])
    assert a["tracks"]["target"]["path"] in {t["path"] for t in choices}
    assert all("two" not in t["name"] for t in choices)
    assert all(Path(t["path"]).is_relative_to(moved) for t in a["available_tracks"])
    # Removing a lesson's media must not make its leftover captions become
    # generic single-video captions belonging to the remaining lesson.
    (moved / "two.mp4").unlink()
    remaining = client.post(endpoint, headers=headers, json={"directory": str(moved)}).json["video"]
    assert remaining["id"] == a["id"]
    assert all("two" not in t["name"] for t in remaining["available_tracks"])
    assert all("two" not in t["name"] for t in service.subtitle_candidates(a["id"]))


def test_collection_upgrades_single_manifest_without_reusing_identity(workspace, tmp_path):
    _, client, headers, fixture = workspace
    root = tmp_path / "growing"
    root.mkdir()
    (root / "one.mp4").write_bytes(Path(fixture["path"]).read_bytes())
    (root / "English.srt").write_text(SRT, encoding="utf-8")
    endpoint = "/api/learning/imports/project"
    original = client.post(endpoint, headers=headers, json={"directory": str(root)}).json["video"]
    (root / "two.mp4").write_bytes(b"second")
    (root / "two.en.srt").write_text(SRT.replace("Hello", "second"), encoding="utf-8")
    preview = client.post(endpoint, headers=headers, json={"directory": str(root)}).json
    assert preview["needs_selection"] and len(preview["videos"]) == 2
    # Importing a different video first must not borrow the old manifest's ID/title.
    second = client.post(endpoint, headers=headers, json={"directory": str(root), "video_paths": [str(root / "two.mp4")]}).json
    assert len(second["imported"]) == 1 and second["video"]["id"] != original["id"]
    assert second["video"]["title"] == "two"
    first = client.post(endpoint, headers=headers, json={"directory": str(root), "video_path": str(root / "one.mp4")}).json["video"]
    assert first["id"] == original["id"] and first["has_source"]
    assert first["cues"][0]["text"] == "Hello, world."
    # Desktop/history single-file entries into a collection still open that file.
    direct = client.post("/api/learning/videos", headers=headers, json={"path": str(root / "two.mp4")})
    assert direct.status_code == 201 and direct.json["id"] == second["video"]["id"]


def test_collection_partial_failure_and_selection_validation(workspace, tmp_path, monkeypatch):
    _, client, headers, fixture = workspace
    root = tmp_path / "partial"
    root.mkdir()
    for name in ("good", "broken"):
        (root / f"{name}.mp4").write_bytes(b"media")
    probe = media.probe

    def selective_probe(path):
        if path.stem == "broken":
            raise ValueError("无法读取视频，请检查文件完整性")
        return probe(path)

    monkeypatch.setattr(media, "probe", selective_probe)
    endpoint = "/api/learning/imports/project"
    response = client.post(endpoint, headers=headers, json={"directory": str(root), "import_all": True}).json
    assert len(response["imported"]) == len(response["errors"]) == 1
    assert response["video"]["title"] == "good" and "broken.mp4" in response["errors"][0]["path"]
    for selection in ([], "not-a-list", [fixture["path"]], [str(root / "good.mp4")] * 2):
        assert client.post(endpoint, headers=headers, json={"directory": str(root), "video_paths": selection}).status_code == 400
    failed = client.post(endpoint, headers=headers, json={"directory": str(root), "video_paths": [str(root / "broken.mp4")]}).json
    assert not failed["imported"] and failed["video"] is None and len(failed["errors"]) == 1
    # A corrupt collection must never merge two learning records by ID.
    manifest = {"schema_version": 2, "videos": [{"video": name + ".mp4", "id": "a" * 32} for name in ("good", "broken")]}
    (root / "videohub_learning.json").write_text(json.dumps(manifest), encoding="utf-8")
    rejected = client.post(endpoint, headers=headers, json={"directory": str(root), "import_all": True})
    assert rejected.status_code == 400 and "重复" in rejected.json["error"]


def test_collection_ambiguous_names_do_not_share_subtitles(workspace, tmp_path):
    _, client, headers, _ = workspace
    root = tmp_path / "ambiguous"
    root.mkdir()
    for filename in ("lesson.mp4", "lesson.mkv"):
        (root / filename).write_bytes(b"video")
    (root / "lesson.en.srt").write_text(SRT, encoding="utf-8")
    result = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root), "import_all": True}).json
    assert not result["imported"] and len(result["errors"]) == 2
    assert all("不同名称" in e["error"] for e in result["errors"])


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


def test_project_accepts_lingering_platform_captions_without_changing_originals(workspace, tmp_path):
    import shutil

    app, client, headers, video = workspace
    root = tmp_path / "platform-project"
    root.mkdir()
    shutil.copy2(video["path"], root / "lesson.mp4")
    content = (
        SRT + "\n3\n00:00:54,490 --> 00:01:01,770\non the EV side\n"
        "\n4\n00:00:58,650 --> 00:01:01,770\nrecent SUV reviews\n"
    )
    original = root / "lesson.en-orig.srt"
    original.write_text(content, encoding="utf-8")
    (root / "lesson.zh.srt").write_text("1\n00:00:58,650 --> 00:00:59,900\n更多评测\n", encoding="utf-8")
    before = original.read_bytes()
    imported = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root)})
    assert imported.status_code == 200, imported.json
    detail = imported.json["video"]
    assert detail["has_source"] and detail["has_target"]
    assert len(detail["available_tracks"]) == 2
    assert [c["end"] for c in detail["cues"][-2:]] == [60, 60]
    assert [c["text"] for c in detail["cues"][-2:]] == ["on the EV side", "recent SUV reviews"]
    assert "1.77" in detail["subtitle_warnings"][0] and "2 条" in detail["subtitle_warnings"][0]
    assert original.read_bytes() == before
    reloaded = client.get(f"/api/learning/videos/{detail['id']}").json
    assert reloaded["subtitle_warnings"] == detail["subtitle_warnings"]
    assert reloaded["subtitle_version"] == detail["subtitle_version"]
    again = client.post("/api/learning/imports/project", headers=headers, json={"directory": str(root)}).json["video"]
    assert again["id"] == detail["id"] and again["subtitle_version"] == detail["subtitle_version"]
    assert len(app.config["LEARNING_SERVICE"].store.videos()) == 2


@pytest.mark.parametrize(
    ("start", "end", "accepted"),
    [(59, "00:01:05,000", True), (59, "00:01:05,001", False), (60, "00:01:01,000", False)],
)
def test_manual_subtitle_tail_tolerance_keeps_mismatch_guard(workspace, start, end, accepted):
    _, client, headers, video = workspace
    before = client.get(f"/api/learning/videos/{video['id']}").json
    result = client.post(
        f"/api/learning/videos/{video['id']}/subtitles",
        headers=headers,
        json={"content": f"1\n00:{start // 60:02}:{start % 60:02},000 --> {end}\nlast words"},
    )
    if accepted:
        assert result.status_code == 200
        assert result.json["cues"][0]["start"] == start and result.json["cues"][0]["end"] == 60
        assert result.json["subtitle_warnings"]
    else:
        assert result.status_code == 400 and "字幕超出视频时长" in result.json["error"]
        assert client.get(f"/api/learning/videos/{video['id']}").json == before
