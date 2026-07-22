import json

from src.doubao_tts_client import DoubaoTTSClient


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.post_call = None
        self.query_call = None

    def post(self, url, *, json, headers, timeout):
        self.post_call = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        }
        return FakeResponse(payload={"task_id": "task-001"})

    def get(self, url, *, params=None, headers=None, timeout):
        if url.endswith("/query"):
            self.query_call = {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
            return FakeResponse(
                payload={
                    "task_status": 1,
                    "audio_url": "https://audio.example/narration.wav",
                    "sentences": [],
                }
            )
        return FakeResponse(content=b"RIFF" + b"\x00" * 40)


def test_doubao_async_tts_saves_wav_without_persisting_token(tmp_path):
    session = FakeSession()
    client = DoubaoTTSClient(
        app_id="app-001",
        access_token="secret-access-token-1234567890",
        session=session,
        poll_interval=1,
    )
    output = tmp_path / "speech.wav"

    result = client.synthesize("这是一段测试解说。", output)

    assert result == str(output.resolve())
    assert output.read_bytes().startswith(b"RIFF")
    assert session.post_call["url"].endswith("/submit")
    assert session.post_call["json"]["format"] == "wav"
    assert session.post_call["json"]["enable_subtitle"] == 1
    assert session.post_call["headers"]["Authorization"].startswith("Bearer; ")
    assert session.query_call["params"] == {
        "appid": "app-001",
        "task_id": "task-001",
    }

    task_record = json.loads(
        output.with_suffix(".wav.task.json").read_text(encoding="utf-8")
    )
    assert task_record["status"] == "complete"
    assert "secret-access-token" not in json.dumps(task_record)


def test_doubao_tts_resumes_completed_task_when_local_wav_is_missing(tmp_path):
    session = FakeSession()
    client = DoubaoTTSClient(
        app_id="app-001",
        access_token="secret-access-token-1234567890",
        session=session,
        poll_interval=1,
    )
    output = tmp_path / "speech.wav"
    text = "继续查询已经提交的任务。"
    task_record = output.with_suffix(".wav.task.json")
    task_record.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "provider": "doubao",
                "task_id": "task-001",
                "identity": client._identity(text),
                "status": "complete",
            }
        ),
        encoding="utf-8",
    )

    client.synthesize(text, output)

    assert session.post_call is None
    assert session.query_call["params"]["task_id"] == "task-001"
    assert output.read_bytes().startswith(b"RIFF")
