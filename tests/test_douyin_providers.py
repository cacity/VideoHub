from __future__ import annotations

import sys
import logging
import threading
from pathlib import Path

import pytest
import requests

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


@pytest.fixture(autouse=True)
def isolate_f2_health(monkeypatch):
    monkeypatch.setattr(DouyinProviderChain, "_f2_blocked_until", {})


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
            headers={"Content-Type": "video/mp4", "Content-Length": str(len(b"\x00\x00\x00\x18ftypmp42video-data"))},
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
    class UnavailableChain:
        def get_video_info(self, url):
            raise DouyinProviderError("测试重新解析失败")

    extractor = DouyinVdExtractor(config=config, provider_chain=UnavailableChain())

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


def _video_info(url, provider="dlpanda"):
    return {
        "aweme_id": "7660369906369629476", "desc": "地址重试测试", "create_time": 0,
        "author": {"nickname": "测试"}, "video": {"play_url": url}, "provider": provider,
    }


def _media_response(body=b"video-data"):
    return _FakeResponse("", body=body, headers={"Content-Type": "video/mp4", "Content-Length": str(len(body))})


@pytest.mark.parametrize("title", ["同一个系列", "很长的系列标题" * 30])
@pytest.mark.parametrize("template", ["{title}", "{title}_{aweme_id}"])
def test_series_downloads_keep_work_identity_and_reuse_only_same_work(monkeypatch, tmp_path, title, template):
    config = DouyinConfig({"download_dir": str(tmp_path), "filename_template": template,
                           "download_cover": False, "download_music": False})
    extractor = DouyinVdExtractor(config=config, provider_chain=_UnexpectedProviderChain())
    requests_seen = []

    def get(url, **kwargs):
        requests_seen.append(url)
        return _media_response(url.encode())

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    outputs = []
    for work_id in ["7660369906369629476", "7660369906369629477", "7660369906369629477"]:
        info = _video_info("https://cdn.example/" + work_id)
        info.update(aweme_id=work_id, desc=title)
        result = extractor.download_video("https://www.douyin.com/video/" + work_id, str(tmp_path), video_info=info)
        assert result["success"], result
        outputs.append(Path(result["files"]["video"][0]))
        assert work_id in outputs[-1].stem
        assert outputs[-1].read_bytes() == info["video"]["play_url"].encode()
    assert outputs[0] != outputs[1] == outputs[2]
    assert len(requests_seen) == 2


def _blocked_response(url, status=403):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content_consumed = True
    return response


def test_media_403_refreshes_once_without_cookie_or_signed_url_logs(monkeypatch, tmp_path, capsys):
    old = "https://v3-web.douyinvod.com/old?msToken=secret-token&a_bogus=signature"
    fresh = "https://v3-web.douyinvod.com/new?sign=fresh-signature"

    class Chain:
        calls = []

        def get_video_info(self, url):
            self.calls.append(url)
            return _video_info(fresh)

    config = DouyinConfig({"download_dir": str(tmp_path), "cookie": "sessionid=private", "download_cover": False})
    chain = Chain()
    extractor = DouyinVdExtractor(config=config, provider_chain=chain)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert "Cookie" not in kwargs["headers"]
        assert "Referer" not in kwargs["headers"]
        return _blocked_response(url) if url == old else _media_response()

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    messages = []
    result = extractor.download_video(
        "https://www.douyin.com/video/7660369906369629476", str(tmp_path), video_info=_video_info(old),
        progress_callback=lambda message, progress: messages.append(message),
    )
    assert result["success"] and calls == [old, fresh]
    assert len(chain.calls) == 1
    assert result["video_info"]["video"]["play_url"] == fresh
    assert Path(result["files"]["video"][0]).read_bytes() == b"video-data"
    output = capsys.readouterr().out + " ".join(messages)
    assert "403" in output and "重试一次" in output
    assert all(secret not in output for secret in ["secret-token", "signature", "sessionid", "msToken"])
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_refresh_failure_stops_after_one_retry(monkeypatch, tmp_path, status):
    class Chain:
        calls = 0

        def get_video_info(self, url):
            self.calls += 1
            return _video_info("https://cdn.example/new?private=one")

    chain = Chain()
    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path)}), provider_chain=chain)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return _blocked_response(url, status)

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=_video_info("https://cdn.example/old"))
    assert not result["success"] and len(calls) == 2 and chain.calls == 1
    assert str(status) in result["error"] and "刷新后仍不可用" in result["error"]
    assert "private=one" not in result["error"]
    assert not list(tmp_path.glob("*.mp4")) and not list(tmp_path.glob("*.part"))


def test_f2_preserves_all_candidate_addresses_and_download_tries_alternate_before_refresh(monkeypatch, tmp_path):
    raw = _RawResult()._to_raw()
    video = raw["aweme_detail"]["video"]
    first, second, third = ["https://cdn.example/" + name for name in ["blocked", "ok", "third"]]
    video["bit_rate"][0]["play_addr"]["url_list"] = [first, second, first]
    video["play_addr"] = {"url_list": [third]}
    info = F2Provider._normalize(raw, "https://www.douyin.com/video/7660369906369629476")
    assert info["video"]["play_urls"] == [first, second, third]
    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path), "download_cover": False, "download_music": False}), provider_chain=_UnexpectedProviderChain())
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return _blocked_response(url) if url == first else _media_response()

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=info)
    assert result["success"] and calls == [first, second]


def test_refresh_rejects_changed_work_id(monkeypatch, tmp_path):
    class Chain:
        def get_video_info(self, url):
            return {**_video_info("https://cdn.example/wrong"), "aweme_id": "other-work"}

    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path)}), provider_chain=Chain())
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return _blocked_response(url)

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=_video_info("https://cdn.example/old"))
    assert not result["success"] and "其他作品" in result["error"] and len(calls) == 1


@pytest.mark.parametrize("failure", [PermissionError("文件无法写入"), requests.Timeout("连接超时")])
def test_local_or_network_error_does_not_refresh_parser(monkeypatch, tmp_path, failure):
    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path)}), provider_chain=_UnexpectedProviderChain())

    def download(*args):
        raise failure

    monkeypatch.setattr(extractor, "_download_media", download)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=_video_info("https://cdn.example/video"))
    assert not result["success"] and str(failure) in result["error"]


def test_truncated_body_never_becomes_completed_file(monkeypatch, tmp_path):
    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path)}), provider_chain=_UnexpectedProviderChain())
    response = _media_response()
    response.headers["Content-Length"] = "999"
    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", lambda *args, **kwargs: response)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=_video_info("https://cdn.example/video"))
    assert not result["success"] and "不完整" in result["error"]
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("*.mp4"))


def test_f2_diagnostics_sanitize_only_scoped_records_and_restore_on_failure(caplog):
    from douyin.diagnostics import concise_f2_logs

    logger = logging.getLogger("f2")
    source = "HTTP状态错误：Client error '403 Forbidden' for url 'https://api.example/?msToken=secret&a_bogus=signature'"
    with caplog.at_level(logging.INFO, logger="f2"):
        with pytest.raises(ValueError):
            with concise_f2_logs():
                logger.error(source)
                thread = threading.Thread(target=lambda: logger.info("another thread untouched"))
                thread.start()
                thread.join()
                raise ValueError("test")
        logger.info("normal operation restored")
    assert "HTTP 403" in caplog.text and "secret" not in caplog.text and "signature" not in caplog.text
    assert "another thread untouched" in caplog.text and "normal operation restored" in caplog.text


def test_f2_fetch_failure_is_sanitized_before_fallback(tmp_path, caplog, capsys):
    class FailingHandler(_FakeF2Handler):
        async def fetch_one_video(self, aweme_id):
            logging.getLogger("f2").error("Client error '403 Forbidden' for url 'https://api.example/?msToken=secret'")
            raise RuntimeError("Client error '403 Forbidden' for url 'https://api.example/?msToken=secret'")

    config = DouyinConfig({"download_dir": str(tmp_path)})
    chain = DouyinProviderChain(config, providers=[F2Provider(config, handler_cls=FailingHandler, aweme_id_fetcher=_FakeAwemeIdFetcher), _SuccessfulProvider()])
    info = chain.get_video_info("https://www.douyin.com/video/7660369906369629476")
    assert info["provider"] == "dlpanda" and "403" in info["provider_errors"]["f2"]
    assert "secret" not in caplog.text + capsys.readouterr().out + str(info["provider_errors"])


def test_html_address_is_refreshed_and_old_partial_removed(monkeypatch, tmp_path):
    class Chain:
        def get_video_info(self, url):
            return _video_info("https://cdn.example/fresh")

    extractor = DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path)}), provider_chain=Chain())
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url.endswith("expired"):
            return _FakeResponse("", body=b"<!doctype html><html>expired</html>", headers={"Content-Type": "application/octet-stream"})
        return _media_response()

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor.download_video("https://www.douyin.com/video/1", str(tmp_path), video_info=_video_info("https://cdn.example/expired"))
    assert result["success"] and len(calls) == 2
    assert not list(tmp_path.glob("*.part"))
    assert Path(result["files"]["video"][0]).read_bytes() == b"video-data"


def test_downloader_replaces_refreshed_cache_and_evicts_failed_cache(monkeypatch, tmp_path):
    from douyin.downloader import DouyinDownloader

    downloader = DouyinDownloader(DouyinConfig({"download_dir": str(tmp_path)}))
    url = "https://www.douyin.com/video/1"
    old, fresh = _video_info("https://cdn.example/old"), _video_info("https://cdn.example/fresh")
    downloader._video_info_cache[url] = old
    calls = []

    def download(source, progress_callback, video_info):
        calls.append(video_info)
        return {"success": True, "video_info": fresh} if len(calls) == 1 else {"success": False, "error": "HTTP 403"}

    monkeypatch.setattr(downloader, "_download_with_douyinvd", download)
    assert downloader.download_video(url)["success"]
    assert downloader._video_info_cache[url] == fresh
    assert not downloader.download_video(url)["success"]
    assert calls == [old, fresh] and url not in downloader._video_info_cache


class _ForbiddenF2:
    name = "f2"

    def __init__(self):
        self.calls = 0
        self.recovered = False

    def get_video_info(self, url):
        self.calls += 1
        if self.recovered:
            return {"provider": "f2", "aweme_id": "123456", "video": {"play_url": "ok"}}
        raise RuntimeError("HTTP 403 for https://api.example/?signed=must-not-leak")


def test_403_cooldown_is_shared_across_new_downloaders_and_retries_after_expiry(tmp_path, monkeypatch, capsys):
    import douyin.providers as providers

    now = [100.0]
    monkeypatch.setattr(providers, "monotonic", lambda: now[0])
    f2 = _ForbiddenF2()
    for index in range(3):
        config = DouyinConfig({"download_dir": str(tmp_path / str(index))})
        chain = DouyinProviderChain(config, providers=[f2, _SuccessfulProvider()])
        info = chain.get_video_info("https://www.douyin.com/video/123456")
        assert info["provider"] == "dlpanda" and "403" in info["provider_errors"]["f2"]
    assert f2.calls == 1
    f2.recovered = True
    now[0] += 901
    recovered = chain.get_video_info("https://www.douyin.com/video/123456")
    assert recovered["provider"] == "f2" and f2.calls == 2
    assert "provider_errors" not in recovered
    output = capsys.readouterr().out
    assert "15 分钟" in output and "暂跳过 F2" in output
    assert "must-not-leak" not in output


@pytest.mark.parametrize("setting,value", [("cookie", "sessionid=new-private-value"), ("proxy", "127.0.0.1:7890")])
def test_f2_auth_or_network_change_can_retry_without_waiting(tmp_path, setting, value):
    config = DouyinConfig({"download_dir": str(tmp_path)})
    f2 = _ForbiddenF2()
    chain = DouyinProviderChain(config, providers=[f2, _SuccessfulProvider()])
    chain.get_video_info("https://www.douyin.com/video/123456")
    f2.recovered = True
    updated = DouyinConfig({"download_dir": str(tmp_path), setting: value})
    result = DouyinProviderChain(updated, providers=[f2, _SuccessfulProvider()]).get_video_info("https://www.douyin.com/video/123456")
    assert result["provider"] == "f2" and f2.calls == 2
    assert all(value not in key for key in DouyinProviderChain._f2_blocked_until)


def test_non_403_errors_do_not_disable_f2_and_all_sources_failure_is_clear(tmp_path):
    class TimeoutF2(_ForbiddenF2):
        def get_video_info(self, url):
            self.calls += 1
            raise TimeoutError("request timed out")

    config = DouyinConfig({"download_dir": str(tmp_path)})
    f2 = TimeoutF2()
    chain = DouyinProviderChain(config, providers=[f2, _SuccessfulProvider()])
    for _ in range(2):
        assert chain.get_video_info("https://www.douyin.com/video/123456")["provider"] == "dlpanda"
    assert f2.calls == 2
    blocked = _ForbiddenF2()
    fallback = _FailingProvider()
    fallback.name = "dlpanda"
    chain = DouyinProviderChain(config, providers=[blocked, fallback])
    with pytest.raises(DouyinProviderError, match="尚未下载文件"):
        chain.get_video_info("https://www.douyin.com/video/123456")
    with pytest.raises(DouyinProviderError, match="尚未下载文件"):
        chain.get_video_info("https://www.douyin.com/video/123456")
    assert blocked.calls == 1 and "dlpanda" in chain.last_errors


def test_quiet_f2_logging_is_scoped_and_restored_on_failure(caplog):
    from douyin.diagnostics import concise_f2_logs

    logger = logging.getLogger("f2")
    with caplog.at_level(logging.INFO, logger="f2"):
        with pytest.raises(ValueError):
            with concise_f2_logs(quiet=True):
                logger.info("processing work internal status")
                logger.error("internal QA https://qa.example/private")
                thread = threading.Thread(target=lambda: logger.info("other task remains visible"))
                thread.start()
                thread.join()
                raise ValueError("test")
        logger.info("normal logs restored")
    assert "internal" not in caplog.text and "qa.example" not in caplog.text
    assert "other task remains visible" in caplog.text and "normal logs restored" in caplog.text


def test_download_status_identifies_work_provider_path_and_local_reuse(tmp_path, monkeypatch, capsys):
    from douyin.downloader import DouyinDownloader

    downloader = DouyinDownloader(DouyinConfig({"download_dir": str(tmp_path), "download_cover": False}))
    info = _video_info("https://cdn.example/video")
    info.update(desc="系列第二集", provider_errors={"f2": "HTTP 403"})
    monkeypatch.setattr(downloader.douyinvd_extractor, "get_video_info", lambda url: info)
    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", lambda *args, **kwargs: _media_response())
    url = "https://www.douyin.com/video/7660369906369629476?token=must-not-leak"
    parsed = downloader.get_video_info(url)
    first = downloader.download_video(url, video_info=parsed)
    assert first["success"] and not first["downloaded_files"][0]["reused"]
    second = downloader.download_video(url)
    assert second["success"] and second["downloaded_files"][0]["reused"]
    output = capsys.readouterr().out
    assert "系列第二集" in output and "7660369906369629476" in output
    assert "DLPanda" in output and first["files"]["video"][0] in output
    assert "解析完成" in output and "文件已就绪" in output and "已复用本地文件" in output
    assert "F2 主解析" not in output and "must-not-leak" not in output
    messages = []
    downloader.download_video(url, progress_callback=lambda message, progress: messages.append(message))
    assert any("文件已就绪" in message for message in messages)
    assert "文件已就绪" not in capsys.readouterr().out
