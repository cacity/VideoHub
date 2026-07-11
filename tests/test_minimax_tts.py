import io
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.dubbing_engine import VideoDubbingEngine
from src.minimax_tts_client import MiniMaxTTSClient


def make_wav_bytes(duration_seconds=0.1, sample_rate=32000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * int(duration_seconds * sample_rate))
    return buffer.getvalue()


def make_response(status_code=200, payload=None, text=""):
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.text = text
    response.json.return_value = payload or {}
    return response


def test_client_writes_wav_and_builds_expected_payload(monkeypatch, tmp_path):
    wav_bytes = make_wav_bytes()
    response = make_response(
        payload={
            "data": {"audio": wav_bytes.hex(), "status": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
            "trace_id": "trace-test",
        }
    )
    post = Mock(return_value=response)
    monkeypatch.setattr("src.minimax_tts_client.requests.post", post)

    target = tmp_path / "sample.wav"
    client = MiniMaxTTSClient(
        api_key="sk-test-secret",
        model="speech-2.8-turbo",
        voice_id="female-shaonv",
        speed=1.1,
        max_retries=0,
    )
    result = client.synthesize("<b>你好</b>，VideoHub。", target)

    assert Path(result) == target.resolve()
    assert target.read_bytes() == wav_bytes
    request = post.call_args.kwargs
    assert request["json"]["text"] == "你好，VideoHub。"
    assert request["json"]["audio_setting"]["format"] == "wav"
    assert request["json"]["voice_setting"]["speed"] == 1.1
    assert request["headers"]["Authorization"] == "Bearer sk-test-secret"


def test_client_retries_rate_limit(monkeypatch, tmp_path):
    wav_bytes = make_wav_bytes()
    success = make_response(
        payload={
            "data": {"audio": wav_bytes.hex()},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }
    )
    post = Mock(side_effect=[make_response(status_code=429), success])
    monkeypatch.setattr("src.minimax_tts_client.requests.post", post)
    monkeypatch.setattr("src.minimax_tts_client.time.sleep", Mock())

    client = MiniMaxTTSClient(api_key="sk-test", max_retries=1)
    client.synthesize("重试测试。", tmp_path / "retry.wav")

    assert post.call_count == 2


def test_client_retries_application_rate_limit(monkeypatch, tmp_path):
    wav_bytes = make_wav_bytes()
    limited = make_response(
        payload={
            "base_resp": {
                "status_code": 1002,
                "status_msg": "rate limit exceeded(RPM)",
            }
        }
    )
    success = make_response(
        payload={
            "data": {"audio": wav_bytes.hex()},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }
    )
    post = Mock(side_effect=[limited, success])
    sleep = Mock()
    monkeypatch.setattr("src.minimax_tts_client.requests.post", post)
    monkeypatch.setattr("src.minimax_tts_client.time.sleep", sleep)

    client = MiniMaxTTSClient(
        api_key="sk-test",
        max_retries=1,
        min_request_interval=0,
    )
    client.synthesize("应用层限流重试。", tmp_path / "app-rate-limit.wav")

    assert post.call_count == 2
    sleep.assert_called_once_with(20.0)


def test_client_redacts_keys_from_http_errors(monkeypatch, tmp_path):
    secret = "sk-test-secret-value"
    response = make_response(status_code=401, text=f"invalid token {secret}")
    monkeypatch.setattr("src.minimax_tts_client.requests.post", Mock(return_value=response))
    client = MiniMaxTTSClient(api_key=secret, max_retries=0)

    with pytest.raises(RuntimeError) as exc_info:
        client.synthesize("错误测试。", tmp_path / "error.wav")

    assert secret not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_dubbing_engine_routes_minimax_and_merges_subtitle_audio(monkeypatch, tmp_path):
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\n第一句。\n\n"
        "2\n00:00:01,000 --> 00:00:01,500\n第二句。\n",
        encoding="utf-8",
    )

    def fake_synthesize(_self, _text, output_path=None):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(make_wav_bytes(duration_seconds=0.2))
        return str(target)

    monkeypatch.setattr(MiniMaxTTSClient, "synthesize", fake_synthesize)

    engine = VideoDubbingEngine.__new__(VideoDubbingEngine)
    engine.progress_callback = None
    engine.step_callback = None
    engine.log_callback = None
    engine.kokoro_available = False
    monkeypatch.setattr(engine, "_get_temp_dir", lambda: str(tmp_path))

    result = engine._synthesize_audio(
        str(subtitle_path),
        voice="xiaobei",
        speed=1.0,
        tts_backend="minimax",
        minimax_api_key="sk-test",
    )

    assert Path(result).exists()
    assert Path(result).stat().st_size > 44


def test_dubbing_download_uses_stable_video_directory(monkeypatch, tmp_path):
    from src import youtube_transcriber

    captured = {}
    expected_video = tmp_path / "download_pZypOP-D7LU" / "video.mp4"

    def fake_download(url, output_dir, audio_only, max_height):
        captured.update({
            "url": url,
            "output_dir": output_dir,
            "audio_only": audio_only,
            "max_height": max_height,
        })
        expected_video.parent.mkdir(parents=True, exist_ok=True)
        expected_video.write_bytes(b"video")
        return str(expected_video)

    monkeypatch.setattr(youtube_transcriber, "download_youtube_video", fake_download)
    engine = VideoDubbingEngine.__new__(VideoDubbingEngine)
    engine.progress_callback = None
    engine.step_callback = None
    engine.log_callback = None
    monkeypatch.setattr(engine, "_get_temp_dir", lambda: str(tmp_path))

    result = engine._download_video("https://www.youtube.com/watch?v=pZypOP-D7LU")

    assert result == str(expected_video)
    assert Path(captured["output_dir"]).name == "download_pZypOP-D7LU"
    assert captured["audio_only"] is False
    assert captured["max_height"] == 1080


def test_exe_download_command_is_resumable_and_bounded(monkeypatch, tmp_path):
    from src import youtube_transcriber

    captured = {}

    def fake_run(cmd, timeout_seconds):
        captured["cmd"] = cmd
        captured["timeout_seconds"] = timeout_seconds
        output = tmp_path / "sample_pZypOP-D7LU.mp4"
        output.write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, stdout="downloaded", stderr="")

    monkeypatch.setattr(youtube_transcriber, "_run_process_with_live_output", fake_run)
    monkeypatch.setenv("YTDLP_DOWNLOAD_TIMEOUT_SECONDS", "1800")

    info = youtube_transcriber.download_with_exe(
        "https://www.youtube.com/watch?v=pZypOP-D7LU",
        "yt-dlp.exe",
        str(tmp_path),
        audio_only=False,
        cookies_file="browser:chrome",
        max_height=1080,
    )

    cmd = captured["cmd"]
    assert "height<=1080" in cmd[cmd.index("-f") + 1]
    assert "--newline" in cmd
    assert "--retries" in cmd
    assert "--fragment-retries" in cmd
    assert "--cookies-from-browser" in cmd
    assert "--merge-output-format" in cmd
    assert "-k" not in cmd
    assert captured["timeout_seconds"] == 1800
    assert info["filepath"].endswith("sample_pZypOP-D7LU.mp4")


def test_live_process_timeout_terminates_command():
    from src import youtube_transcriber

    with pytest.raises(RuntimeError, match="已终止下载进程"):
        youtube_transcriber._run_process_with_live_output(
            [
                sys.executable,
                "-u",
                "-c",
                "import time; print('started'); time.sleep(30)",
            ],
            timeout_seconds=1,
        )
