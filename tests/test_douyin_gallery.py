from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from douyin.config import DouyinConfig
from douyin.douyinvd_extractor import DouyinVdExtractor
from douyin.hellotik import HelloTikProvider
from douyin.peanutdl import PeanutDLProvider
from douyin.providers import DLPandaProvider, DouyinProviderChain, DouyinProviderError, F2Provider
from learning.downloads import download_douyin

URL = "https://www.douyin.com/note/7629442747300907001"


@pytest.fixture(autouse=True)
def isolate_provider_health(monkeypatch):
    monkeypatch.setattr(DouyinProviderChain, "_f2_blocked_until", {})


def payload():
    return {"video_id": "7629442747300907001", "title": "图集测试", "covers": ["https://cdn.test/cover"],
            "images": [{"urls": ["https://cdn.test/1", "https://backup.test/1"]},
                       {"urls": ["https://cdn.test/2"]}, {"urls": ["https://cdn.test/3"]}],
            "videos": [{"urls": ["https://cdn.test/slideshow"]}]}


def picture(format):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 24), "red").save(buffer, format=format)
    return buffer.getvalue()


def response(body=b"", status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body
    result._content_consumed = True
    result.headers["Content-Length"] = str(len(body))
    return result


def extractor(tmp_path, chain=None):
    return DouyinVdExtractor(config=DouyinConfig({"download_dir": str(tmp_path), "download_cover": False,
                                               "download_music": False, "cookie": "private-session"}), provider_chain=chain)


def test_peanut_normalizes_gallery_order_and_alternates_not_cover_or_video():
    info = PeanutDLProvider._normalize(payload(), URL)
    assert info["type"] == "image" and len(info["images"]) == 3
    assert info["images"] == ["https://cdn.test/1", "https://cdn.test/2", "https://cdn.test/3"]
    assert info["image_url_groups"][0] == ["https://cdn.test/1", "https://backup.test/1"]
    assert info["video"]["cover_url"] not in info["images"]


def test_peanut_posts_public_url_only_and_stops_at_captcha(tmp_path):
    class Session:
        headers = {}
        calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return response(json.dumps({"code": 2, "success": False}).encode())

    session = Session()
    provider = PeanutDLProvider(DouyinConfig({"download_dir": str(tmp_path), "cookie": "private-value"}), session)
    with pytest.raises(DouyinProviderError, match="验证码"):
        provider.get_video_info(URL)
    assert len(session.calls) == 1 and session.calls[0][1]["json"]["url"] == URL
    assert "Cookie" not in session.headers and "private-value" not in repr(session.calls)


@pytest.mark.parametrize("change", ["missing", "invalid", "wrong-id", "empty"])
def test_peanut_rejects_incomplete_or_wrong_gallery(change):
    data = payload()
    if change == "missing": data["images"][1] = {}
    if change == "invalid": data["images"][1] = {"urls": ["javascript:alert(1)"]}
    if change == "wrong-id": data["video_id"] = "7777777777777777777"
    if change == "empty": data.update(images=[], videos=[])
    with pytest.raises(DouyinProviderError):
        PeanutDLProvider._normalize(data, URL)


def test_f2_gallery_wins_over_slideshow_and_preserves_repeated_slots():
    raw = {"aweme_id": "7629442747300907001", "images": [{"url_list": ["https://cdn.test/a", "https://backup.test/a"]}] * 2,
           "video": {"play_addr": {"url_list": ["https://cdn.test/slideshow"]}}}
    info = F2Provider._normalize(raw, URL)
    assert info["type"] == "image" and len(info["images"]) == 2
    assert info["image_url_groups"][1] == ["https://cdn.test/a", "https://backup.test/a"]


def test_hellotik_gallery_wins_over_slideshow_and_keeps_slots():
    info = HelloTikProvider._normalize({"videos": ["https://cdn.test/slideshow"], "pics": ["https://cdn.test/a"] * 3}, URL)
    assert info["type"] == "image" and len(info["images"]) == 3


def test_dlpanda_does_not_mistake_first_image_link_for_video_or_add_previews():
    info = DLPandaProvider._parse_result('''<div id="result"><h2>图集</h2>
    <img src="https://cdn.test/avatar.jpg">
    <a data-download-name="01.webp" data-download-url="https://cdn.test/full1.webp">图片</a>
    <a data-download-name="02.jpg" data-download-url="https://cdn.test/full2.jpg">图片</a>
    </div>''', URL)
    assert info["type"] == "image" and len(info["images"]) == 2
    assert not info["video"]["play_url"] and "avatar" not in repr(info["images"])


def test_complete_gallery_real_formats_counts_and_repeat_reuses_files(tmp_path, monkeypatch):
    info = PeanutDLProvider._normalize(payload(), URL)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert "Cookie" not in kwargs["headers"] and "Referer" not in kwargs["headers"]
        return response(picture({"1": "JPEG", "2": "WEBP", "3": "PNG"}[url[-1]]))

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    worker = extractor(tmp_path)
    messages = []
    first = worker.download_video(URL, str(tmp_path), video_info=info, progress_callback=lambda text, percent: messages.append(text))
    assert first["success"] and first["image_count"] == 3 and not first["files"]["video"]
    paths = [Path(p) for p in first["files"]["image"]]
    assert [p.name for p in paths] == ["001.jpg", "002.webp", "003.png"]
    manifest = json.loads((paths[0].parent / "gallery.json").read_text(encoding="utf8"))
    assert manifest["expected_count"] == manifest["saved_count"] == 3
    assert "3/3" in " ".join(messages)
    second = worker.download_video(URL, str(tmp_path), video_info=info)
    assert second["success"] and len(calls) == 3 and all(row["reused"] for row in second["downloaded_files"])
    assert not list(tmp_path.rglob("*.part")) and not list(tmp_path.rglob("*.download"))


def test_per_image_alternate_before_source_fallback(tmp_path, monkeypatch):
    info = PeanutDLProvider._normalize(payload(), URL)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return response(status=403) if url == "https://cdn.test/1" else response(picture("JPEG"))

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor(tmp_path).download_video(URL, str(tmp_path), video_info=info)
    assert result["success"] and calls[:2] == ["https://cdn.test/1", "https://backup.test/1"]


def test_partial_invalid_gallery_does_not_report_success_and_can_resume(tmp_path, monkeypatch):
    info = PeanutDLProvider._normalize(payload(), URL)
    state = {"fail": True}
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return response(b'{"error":"not an image"}') if state["fail"] and url.endswith("/2") else response(picture("JPEG"))

    class Chain:
        def get_video_info(self, url):
            return info

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    worker = extractor(tmp_path, Chain())
    failed = worker.download_video(URL, str(tmp_path), video_info=info)
    assert not failed["success"] and not list(tmp_path.rglob("gallery.json"))
    assert len(list(tmp_path.rglob("*.jpg"))) == 1
    state["fail"] = False
    result = worker.download_video(URL, str(tmp_path), video_info=info)
    assert result["success"] and calls.count("https://cdn.test/1") == 1
    assert not list(tmp_path.rglob("*.part")) and not list(tmp_path.rglob("*.download"))


def test_hellotik_media_failure_continues_to_peanut(tmp_path, monkeypatch):
    chain = DouyinProviderChain(DouyinConfig({"download_dir": str(tmp_path)}))
    old = PeanutDLProvider._normalize(payload(), URL)
    old["provider"] = "hellotik"
    fresh = PeanutDLProvider._normalize(payload(), URL)
    for provider in chain.providers[:-1]:
        monkeypatch.setattr(provider, "get_video_info", lambda url: pytest.fail("must continue after HelloTik"))
    monkeypatch.setattr(chain.providers[-1], "get_video_info", lambda url: fresh)
    worker = extractor(tmp_path, chain)
    original = worker._download_image

    def download(candidates, folder, index, provider, *args):
        from douyin.douyinvd_extractor import MediaAddressError
        if provider == "hellotik": raise MediaAddressError("HTTP 403")
        return original(candidates, folder, index, provider, *args)

    monkeypatch.setattr(worker, "_download_image", download)
    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", lambda *a, **k: response(picture("JPEG")))
    result = worker.download_video(URL, str(tmp_path), video_info=old)
    assert result["success"] and result["provider"] == "peanutdl" and result["image_count"] == 3


def test_gallery_skips_learning_video_import(tmp_path):
    class Downloader:
        def download_video(self, url, **kwargs):
            assert "download_dir" not in kwargs
            return {"success": True, "files": {"image": ["1.jpg", "2.jpg"]}}

    result = download_douyin(Downloader(), URL, video_info={"type": "image", "images": ["1", "2"]})
    assert result["success"] and "project_root" not in result


@pytest.mark.parametrize("short_link", [False, True])
def test_gallery_chain_skips_video_only_response_and_resolves_short_link(tmp_path, monkeypatch, short_link):
    chain = DouyinProviderChain(DouyinConfig({"download_dir": str(tmp_path)}))
    seen = []

    def blocked(url):
        seen.append(url)
        raise DouyinProviderError("HTTP 403")

    monkeypatch.setattr(chain.providers[0], "get_video_info", blocked)
    monkeypatch.setattr(chain.providers[1], "get_video_info", lambda url: {"provider": "dlpanda", "type": "video"})
    monkeypatch.setattr(chain.providers[2], "get_video_info", blocked)
    monkeypatch.setattr(chain.providers[3], "get_video_info", lambda url: PeanutDLProvider._normalize(payload(), url))
    redirect = response()
    redirect.url = URL
    monkeypatch.setattr("douyin.providers.requests.get", lambda *a, **k: redirect)
    info = chain.get_video_info("https://v.douyin.com/example/" if short_link else URL)
    assert info["provider"] == "peanutdl" and info["type"] == "image"
    assert all(url == URL for url in seen)
    assert "图集" in info["provider_errors"]["dlpanda"]


def test_image_timeout_uses_alternate_without_false_completion(tmp_path, monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url == "https://cdn.test/1":
            raise requests.ReadTimeout("timeout")
        return response(picture("WEBP"))

    monkeypatch.setattr("douyin.douyinvd_extractor.requests.get", get)
    result = extractor(tmp_path).download_video(URL, str(tmp_path), video_info=PeanutDLProvider._normalize(payload(), URL))
    assert result["success"] and result["image_count"] == 3
    assert calls[:2] == ["https://cdn.test/1", "https://backup.test/1"]


def test_gallery_source_switch_rejects_missing_images(tmp_path, monkeypatch):
    from douyin.douyinvd_extractor import MediaAddressError

    chain = DouyinProviderChain(DouyinConfig({"download_dir": str(tmp_path)}))
    old = PeanutDLProvider._normalize(payload(), URL)
    old["provider"] = "hellotik"
    data = payload()
    data["images"] = data["images"][:2]
    monkeypatch.setattr(chain.providers[-1], "get_video_info", lambda url: PeanutDLProvider._normalize(data, url))
    worker = extractor(tmp_path, chain)

    def fail(*args, **kwargs):
        raise MediaAddressError("HTTP 403")

    monkeypatch.setattr(worker, "_download_image", fail)
    result = worker.download_video(URL, str(tmp_path), video_info=old)
    assert not result["success"] and "数量" in result["error"]
