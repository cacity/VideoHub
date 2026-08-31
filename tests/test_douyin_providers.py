from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from douyin.config import DouyinConfig  # noqa: E402
from douyin.douyinvd_extractor import DouyinVdExtractor  # noqa: E402
from douyin.providers import (  # noqa: E402
    DLPandaProvider,
    DouyinProviderChain,
    DouyinProviderError,
    F2Provider,
)


class _RawResult:
    def _to_raw(self):
        return {
            "aweme_detail": {
                "aweme_id": "7660369906369629476",
                "desc": "测试作品",
                "create_time": 1_725_000_000,
                "duration": 42_000,
                "author": {"uid": "u1", "nickname": "测试作者"},
                "music": {
                    "id": "m1",
                    "title": "测试音乐",
                    "play_url": {"url_list": ["https://music.example/audio.mp3"]},
                },
                "video": {
                    "width": 1080,
                    "height": 1920,
                    "origin_cover": {"url_list": ["https://img.example/cover.jpg"]},
                    "bit_rate": [
                        {
                            "play_addr": {
                                "url_list": ["https://video.example/no-watermark.mp4"]
                            }
                        }
                    ],
                },
                "statistics": {"digg_count": 12, "comment_count": 3},
            }
        }


class _FakeAwemeIdFetcher:
    @classmethod
    async def get_aweme_id(cls, url):
        assert url.endswith("7660369906369629476")
        return "7660369906369629476"


class _FakeF2Handler:
    kwargs = None

    def __init__(self, kwargs):
        type(self).kwargs = kwargs

    async def fetch_one_video(self, aweme_id):
        assert aweme_id == "7660369906369629476"
        assert self.enable_bark is False
        return _RawResult()


def test_f2_provider_normalizes_single_video_and_uses_config_cookie(tmp_path):
    config = DouyinConfig(
        {"download_dir": str(tmp_path), "cookie": "sessionid=private-value"}
    )
    provider = F2Provider(
        config,
        handler_cls=_FakeF2Handler,
        aweme_id_fetcher=_FakeAwemeIdFetcher,
        token_manager=None,
    )

    info = provider.get_video_info(
        "https://www.douyin.com/video/7660369906369629476"
    )

    assert info["provider"] == "f2"
    assert info["duration"] == 42
    assert info["author"]["nickname"] == "测试作者"
    assert info["video"]["play_url"] == "https://video.example/no-watermark.mp4"
    assert _FakeF2Handler.kwargs["cookie"] == "sessionid=private-value"
    assert "Cookie" not in _FakeF2Handler.kwargs["headers"]
    assert "Accept-Encoding" not in _FakeF2Handler.kwargs["headers"]


class _FailingProvider:
    name = "f2"

    def get_video_info(self, url):
        raise DouyinProviderError("签名接口不可用")


class _SuccessfulProvider:
    name = "dlpanda"

    def get_video_info(self, url):
        return {"provider": "dlpanda", "source_url": url, "video": {"play_url": "ok"}}


def test_provider_chain_falls_back_and_preserves_primary_error(tmp_path):
    config = DouyinConfig({"download_dir": str(tmp_path)})
    chain = DouyinProviderChain(
        config=config,
        providers=[_FailingProvider(), _SuccessfulProvider()],
    )

    info = chain.get_video_info("https://www.douyin.com/video/1")

    assert info["provider"] == "dlpanda"
    assert info["provider_errors"] == {"f2": "签名接口不可用"}


DLPANDA_RESULT_HTML = """
<html><body>
  <div id="result">
    <h2>作品标题</h2>
    <span>Video ID: 7660369906369629476</span>
    <video><source src="https://cdn.example/video.mp4" type="video/mp4"></video>
    <a data-download-url="https://cdn.example/video.mp4"
       data-download-name="[DLPanda.com][熊猫作者]作品标题.mp4">下载</a>
    <button data-copy-text="完整作品文案">复制文案</button>
  </div>
</body></html>
"""


def test_dlpanda_parses_current_server_rendered_result():
    info = DLPandaProvider._parse_result(
        DLPANDA_RESULT_HTML,
        "https://www.douyin.com/video/7660369906369629476",
    )

    assert info["provider"] == "dlpanda"
    assert info["aweme_id"] == "7660369906369629476"
    assert info["author"]["nickname"] == "熊猫作者"
    assert info["desc"] == "完整作品文案"
    assert info["video"]["play_url"] == "https://cdn.example/video.mp4"


class _FakeResponse:
    def __init__(self, text, *, body=b"", headers=None):
        self.text = text
        self._body = body
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def iter_content(self, chunk_size):
        yield self._body


class _FakeSession:
    def __init__(self):
        self.headers = {}
        self.post_data = None
        self.post_headers = None

    def get(self, url, timeout):
        return _FakeResponse(
            """
            <form id="dlpanda-download-form" data-platform="douyin" action="/douyin">
              <input name="_token" value="csrf-value">
              <input name="t0ken" value="parser-value">
            </form>
            """
        )

    def post(self, url, data, headers, timeout):
        self.post_data = data
        self.post_headers = headers
        return _FakeResponse(DLPANDA_RESULT_HTML)


def test_dlpanda_posts_dynamic_tokens_without_douyin_cookie(tmp_path):
    session = _FakeSession()
    config = DouyinConfig(
        {"download_dir": str(tmp_path), "cookie": "sessionid=must-not-leak"}
    )
    provider = DLPandaProvider(config, session=session)

    provider.get_video_info("https://www.douyin.com/video/7660369906369629476")

    assert session.post_data == {
        "_token": "csrf-value",
        "t0ken": "parser-value",
        "url": "https://www.douyin.com/video/7660369906369629476",
    }
    assert "Cookie" not in session.headers
    assert "Cookie" not in session.post_headers


class _UnexpectedProviderChain:
    def get_video_info(self, url):
        raise AssertionError("download should reuse the already parsed video_info")


def test_download_reuses_video_info_and_does_not_leak_cookie(monkeypatch, tmp_path):
    config = DouyinConfig(
        {
            "download_dir": str(tmp_path),
            "cookie": "sessionid=must-not-leak",
            "download_cover": False,
            "download_music": False,
        }
    )
    extractor = DouyinVdExtractor(
        config=config,
        provider_chain=_UnexpectedProviderChain(),
    )
    captured_headers = {}

    def fake_get(url, **kwargs):
        captured_headers.update(kwargs["headers"])
        return _FakeResponse(
            "",
            body=b"\x00\x00\x00\x18ftypmp42video-data",
            headers={"Content-Type": "video/mp4", "Content-Length": "26"},
        )

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", fake_get)
    info = {
        "aweme_id": "7660369906369629476",
        "desc": "复用解析结果",
        "create_time": 0,
        "author": {"nickname": "测试作者"},
        "video": {"play_url": "https://third-party-cdn.example/video.mp4"},
        "provider": "dlpanda",
    }

    result = extractor.download_video(
        "https://www.douyin.com/video/7660369906369629476",
        download_dir=str(tmp_path),
        video_info=info,
    )

    assert result["success"] is True
    assert result["provider"] == "dlpanda"
    assert len(result["files"]["video"]) == 1
    assert Path(result["files"]["video"][0]).read_bytes().endswith(b"video-data")
    assert "Cookie" not in captured_headers
    assert "Referer" not in captured_headers


def test_download_removes_partial_file_when_media_is_html(monkeypatch, tmp_path):
    config = DouyinConfig(
        {
            "download_dir": str(tmp_path),
            "download_cover": False,
            "download_music": False,
        }
    )
    extractor = DouyinVdExtractor(config=config)

    def fake_get(url, **kwargs):
        return _FakeResponse(
            "",
            body=b"<!doctype html><html>expired</html>",
            headers={"Content-Type": "text/html"},
        )

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", fake_get)
    info = {
        "aweme_id": "7660369906369629476",
        "desc": "过期链接",
        "create_time": 0,
        "author": {"nickname": "测试作者"},
        "video": {"play_url": "https://cdn.example/expired"},
        "provider": "dlpanda",
    }

    result = extractor.download_video(
        "https://www.douyin.com/video/1",
        download_dir=str(tmp_path),
        video_info=info,
    )

    assert result["success"] is False
    assert not list(tmp_path.glob("*.part"))
