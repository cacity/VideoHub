from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from douyin.config import DouyinConfig
from douyin.douyinvd_extractor import DouyinVdExtractor
from douyin.hellotik import HelloTikProvider
from douyin.providers import DouyinProviderChain, DouyinProviderError

URL = "https://www.douyin.com/video/7709439864568051162"


@pytest.fixture(autouse=True)
def isolate_provider_health(monkeypatch):
    monkeypatch.setattr(DouyinProviderChain, "_f2_blocked_until", {})


PROFILE = {
    "id": "rotated-profile", "authRoute": "gate-new",
    "ticketResponseFields": {"key": "ticket_new"},
    "parseRequestFields": {"key": "ticket_new", "fallback": "plain_new"},
}
DATA = {"title": "测试作品", "videos": [{"url": "https://cdn.example/video.mp4"}], "pics": ["https://cdn.example/cover.jpg"]}


def encrypted_response(data):
    iv = b"0123456789abcdef"
    encrypted = AES.new(HelloTikProvider.response_codec_key, AES.MODE_CBC, iv).encrypt(
        pad(json.dumps(data).encode(), 16)
    )

    def encode(value):
        table = str.maketrans(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
            "ZYXABCDEFGHIJKLMNOPQRSTUVWzyxabcdefghijklmnopqrstuvw9876543210-_",
        )
        value = base64.b64encode(value).decode().translate(table)
        value = "".join(value[i:i + 8][::-1] for i in range(0, len(value), 8))
        return base64.b64encode(bytes(ord(c) ^ 90 for c in value)).decode()

    return {"status": 0, "encrypt": True, "data": encode(encrypted), "key": encode(iv)}


def response(data, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = (data if isinstance(data, str) else json.dumps(data)).encode()
    return result


class Session:
    def __init__(self, result=None, quote=None):
        self.headers = {}
        self.calls = []
        self.result = result or encrypted_response(DATA)
        self.quote = quote or {"success": True, "quoteToken": "ephemeral-quote", "data": {"defaultTier": "hd"}}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/zh/douyin"):
            return response('<script src="https://unrelated.example/111-abc.js"></script><script src="/_next/static/chunks/4368-new.js"></script>')
        assert url.endswith("4368-new.js")
        config = {"activeProfileId": PROFILE["id"], "profiles": [PROFILE]}
        return response("let config=JSON.parse('" + json.dumps(config, separators=(",", ":")) + "')")

    def post(self, url, json, **kwargs):
        self.calls.append((url, {**kwargs, "json": json}))
        if url.endswith("generate-id"):
            return response({"success": True, "data": {"uwx_id": "ephemeral-device"}})
        if url.endswith("parse-entitlement-status"):
            return response(self.quote)
        if url.endswith("gate-new"):
            return response({"success": True, "ticket_new": "ephemeral-ticket"})
        assert url.endswith("/api/parse")
        assert json["ticket_new"] == "ephemeral-ticket" and json["plain_new"] is True
        return response(self.result)


def test_current_encrypted_web_flow_and_cookie_isolation(tmp_path):
    session = Session()
    provider = HelloTikProvider(DouyinConfig({"download_dir": str(tmp_path), "cookie": "sessionid=must-not-leak"}), session)
    for count in range(2):
        info = provider.get_video_info(URL)
        assert info["provider"] == "hellotik" and info["aweme_id"] == "7709439864568051162"
        assert info["video"]["play_url"] == DATA["videos"][0]["url"]
        assert info["video"]["cover_url"] == DATA["pics"][0]
        assert info["images"] == [] and "from_f2" not in info
        assert session.calls[-1][1]["json"]["successCount"] == str(count)
    assert len([url for url, _ in session.calls if url.endswith("generate-id")]) == 1
    assert "Cookie" not in session.headers and "must-not-leak" not in repr(session.calls)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("data", [None, {}, {"videos": ["javascript:alert(1)"]}])
def test_empty_and_invalid_media_is_not_success(data):
    with pytest.raises(DouyinProviderError, match="HelloTik"):
        HelloTikProvider._normalize(data, URL)


def test_image_post_and_plain_response(tmp_path):
    provider = HelloTikProvider(DouyinConfig({"download_dir": str(tmp_path)}), Session({"status": 0, "data": {"pics": DATA["pics"]}}))
    info = provider.get_video_info(URL)
    assert info["type"] == "image" and info["images"] == DATA["pics"]


def test_points_requirement_stops_before_requesting_ticket(tmp_path):
    session = Session(quote={"success": True, "data": {"showQuote": True}})
    provider = HelloTikProvider(DouyinConfig({"download_dir": str(tmp_path)}), session)
    with pytest.raises(DouyinProviderError, match="点数"):
        provider.get_video_info(URL)
    assert not any(url.endswith("gate-new") for url, _ in session.calls)


def test_rate_limit_is_reported_without_retry_or_secret_logs(tmp_path, capsys):
    session = Session()
    original = session.post

    def post(url, **kwargs):
        if url.endswith("gate-new"):
            return response({"message": "请稍后重试"}, status=429)
        return original(url, **kwargs)

    session.post = post
    provider = HelloTikProvider(DouyinConfig({"download_dir": str(tmp_path)}), session)
    with pytest.raises(DouyinProviderError, match="HTTP 429"):
        provider.get_video_info(URL)
    assert not any(url.endswith("/api/parse") for url, _ in session.calls)
    assert "ephemeral" not in capsys.readouterr().out


def test_default_chain_order_and_dlpanda_parse_failure(tmp_path, monkeypatch):
    config = DouyinConfig({"download_dir": str(tmp_path)})
    chain = DouyinProviderChain(config)
    assert [p.name for p in chain.providers] == ["f2", "dlpanda", "hellotik", "peanutdl"]
    calls = []
    for provider in chain.providers[:2]:
        def fail(url, name=provider.name):
            calls.append(name)
            raise DouyinProviderError("解析失败")
        monkeypatch.setattr(provider, "get_video_info", fail)
    chain.providers[2].session = Session()
    info = chain.get_video_info(URL)
    assert calls == ["f2", "dlpanda"]
    assert info["provider"] == "hellotik" and set(info["provider_errors"]) == {"f2", "dlpanda"}


@pytest.mark.parametrize("initial_provider", ["dlpanda", "f2"])
def test_dlpanda_cdn_403_switches_to_hellotik_and_saves_file(tmp_path, monkeypatch, initial_provider):
    config = DouyinConfig({"download_dir": str(tmp_path), "download_cover": False, "download_music": False, "cookie": "private"})
    chain = DouyinProviderChain(config)
    chain.providers[2].session = Session()
    for provider in chain.providers[:2]:
        monkeypatch.setattr(provider, "get_video_info", lambda url: pytest.fail("must continue after DLPanda"))
    old = HelloTikProvider._normalize(DATA, URL)
    old.update(provider="dlpanda", provider_errors={"f2": "HTTP 403"})
    old["video"]["play_url"] = old["video"]["play_url_no_watermark"] = "https://www.douyin.com/dead"
    old["video"]["play_urls"] = []
    initial = {**old, "provider": initial_provider}
    if initial_provider == "f2":
        def fail(url):
            raise DouyinProviderError("F2 解析失败")
        monkeypatch.setattr(chain.providers[0], "get_video_info", fail)
        monkeypatch.setattr(chain.providers[1], "get_video_info", lambda url: old)
    seen = []

    def get(url, **kwargs):
        seen.append(url)
        if len(seen) > 1 or initial_provider != "f2":
            assert "Cookie" not in kwargs["headers"] and "Referer" not in kwargs["headers"]
        if url.endswith("/dead"):
            result = response("", 403)
        else:
            result = response("video-bytes")
            result.headers["Content-Length"] = "11"
        result._content_consumed = True
        return result

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = DouyinVdExtractor(config=config, provider_chain=chain).download_video(URL, str(tmp_path), video_info=initial)
    assert result["success"] and result["provider"] == "hellotik"
    assert len(seen) == (2 if initial_provider == "dlpanda" else 3)
    assert "dlpanda" in result["video_info"]["provider_errors"]
    assert "f2" in result["video_info"]["provider_errors"]
    assert Path(result["files"]["video"][0]).read_bytes() == b"video-bytes"
    assert not list(tmp_path.glob("*.part"))


def test_successful_primary_does_not_contact_fallbacks(tmp_path, monkeypatch):
    chain = DouyinProviderChain(DouyinConfig({"download_dir": str(tmp_path)}))
    monkeypatch.setattr(chain.providers[0], "get_video_info", lambda url: {"provider": "f2"})
    for provider in chain.providers[1:]:
        monkeypatch.setattr(provider, "get_video_info", lambda url: pytest.fail("primary succeeded"))
    assert chain.get_video_info(URL)["provider"] == "f2"


def test_changed_encryption_protocol_reports_failure_without_dumping_response(tmp_path):
    provider = HelloTikProvider(DouyinConfig({"download_dir": str(tmp_path)}), Session({
        "status": 0, "encrypt": True, "data": "private-encrypted-data", "key": "private-key",
    }))
    with pytest.raises(DouyinProviderError, match="HelloTik") as exc:
        provider.get_video_info(URL)
    assert "private" not in str(exc.value)
