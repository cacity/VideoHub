from __future__ import annotations

import sys
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import koushare_downloader as downloader  # noqa: E402


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.koushare.com/live/details/44288?vid=183306",
            ("44288", "183306"),
        ),
        ("https://koushare.com/video/details/203628", (None, "203628")),
        ("https://www.koushare.com/video/videodetail/203628", (None, "203628")),
    ],
)
def test_parse_supported_urls(url, expected):
    assert downloader.parse_koushare_url(url) == expected
    assert downloader.is_koushare_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/live/details/44288?vid=183306",
        "https://notkoushare.com/video/details/203628",
        "https://www.koushare.com/live/details/44288",
        "https://www.koushare.com/",
    ],
)
def test_rejects_unrelated_or_incomplete_urls(url):
    with pytest.raises(ValueError):
        downloader.parse_koushare_url(url)
    assert not downloader.is_koushare_url(url)


def test_signature_is_stable_and_normalizes_boolean(monkeypatch):
    monkeypatch.setattr(downloader.time, "time", lambda: 1_700_000_000.123)
    sign, timestamp = downloader.generate_ks_sign(
        {"username": "user", "flag": False, "empty": ""},
        "post",
    )

    assert timestamp == 1_700_000_000_123
    salt_md5 = hashlib.md5(downloader.SALT_KEY.encode("utf-8")).hexdigest()
    message = (
        "flag=false&username=user&method=POST&timestamp=1700000000123"
        f"&saltmd5={salt_md5}"
    )
    assert sign == hashlib.md5(message.encode("utf-8")).hexdigest()


def test_set_token_updates_and_clears_authorization_header():
    downloader.set_token("token-for-test")
    assert downloader._get_session().headers["Authorization"] == "token-for-test"

    downloader.set_token("")
    assert "Authorization" not in downloader._get_session().headers


def test_quality_selection_prefers_requested_then_falls_back():
    playback = {
        "playbackUrls": [
            {
                "list": [
                    {"labelEn": "HD", "height": 720, "fileUrl": "https://cdn/hd.m3u8"},
                    {"labelEn": "SD", "height": 480, "fileUrl": "https://cdn/sd.m3u8"},
                ]
            }
        ]
    }

    assert downloader.select_quality(playback, "HD") == "https://cdn/hd.m3u8"
    assert downloader.select_quality(playback, "FHD") == "https://cdn/hd.m3u8"


def test_download_uses_video_title_and_selected_stream(monkeypatch, tmp_path):
    monkeypatch.setattr(
        downloader,
        "_signed_headers",
        lambda *_args, **_kwargs: {},
    )

    class Response:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class Session:
        headers = {}

        def post(self, *_args, **_kwargs):
            return Response({"success": True, "data": {"secret": "secret"}})

        def get(self, url, *_args, **_kwargs):
            if url.endswith("/info"):
                return Response({"success": True, "data": {"title": "测试/课程"}})
            return Response(
                {
                    "success": True,
                    "data": [
                        {
                            "type": "HLS",
                            "list": [
                                {
                                    "labelEn": "FHD",
                                    "height": 1080,
                                    "fileUrl": "https://cdn/fhd.m3u8",
                                }
                            ],
                        }
                    ],
                }
            )

    monkeypatch.setattr(downloader, "_get_session", lambda: Session())
    captured = {}

    def fake_download(stream_url, output_path, progress_callback=None):
        captured["stream_url"] = stream_url
        captured["output_path"] = output_path
        Path(output_path).write_bytes(b"video")

    monkeypatch.setattr(downloader, "download_with_ffmpeg", fake_download)

    result = downloader.download(
        "https://www.koushare.com/video/details/203628",
        output_dir=str(tmp_path),
    )

    assert result["success"] is True
    assert result["title"] == "测试_课程"
    assert Path(result["file_path"]).name == "测试_课程.mp4"
    assert captured["stream_url"] == "https://cdn/fhd.m3u8"
