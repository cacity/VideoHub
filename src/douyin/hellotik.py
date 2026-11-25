"""HelloTik public single-post fallback using its current anonymous web flow.

This is a website protocol, not a supported public API. Tickets and the anonymous
device identifier stay in this provider's independent session and are never saved.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import DouyinConfig
from .diagnostics import concise_error
from .providers import DouyinProviderError, F2Provider
from .utils import DouyinUtils


class HelloTikProvider:
    name = "hellotik"
    base_url = "https://www.hellotik.app"
    page_path = "/zh/douyin"
    # Public response-codec constant used by the website's generateOutput call.
    response_codec_key = b"93838338562359368888868323563256"

    def __init__(self, config=None, session=None):
        self.config = config or DouyinConfig()
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.get("user_agent"),
            "Referer": self.base_url + self.page_path,
            "Origin": self.base_url,
        })
        self._profile = None
        self._device_id = None
        self._success_count = 0

    def _post(self, path, payload):
        response = self.session.post(
            self.base_url + path, json=payload,
            timeout=max(self.config.get("timeout", 30), 40),
        )
        data = response.json()
        if not isinstance(data, dict):
            raise DouyinProviderError("HelloTik 返回了无法识别的数据格式")
        if not response.ok or data.get("success") is False:
            message = data.get("message") or data.get("error") or "请求失败"
            raise DouyinProviderError(f"HelloTik HTTP {response.status_code}：{concise_error(message)}")
        return data

    def _load_profile(self):
        page = self.session.get(self.base_url + self.page_path, timeout=self.config.get("timeout", 30))
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        for script in soup.select("script[src]"):
            address = urljoin(self.base_url, script["src"])
            parsed = urlparse(address)
            if parsed.netloc != "www.hellotik.app" or not re.fullmatch(
                r"/_next/static/chunks/\d+-[\w]+\.js", parsed.path
            ):
                continue
            response = self.session.get(address, timeout=self.config.get("timeout", 30))
            response.raise_for_status()
            match = re.search(r"JSON\.parse\('(\{\"activeProfileId\".*?\})'\)", response.text)
            if match:
                config = json.loads(match.group(1))
                profile = next((p for p in config["profiles"] if p["id"] == config["activeProfileId"]), None)
                if profile and re.fullmatch(r"[\w-]+", profile.get("authRoute", "")):
                    self._profile = profile
                    return
        raise DouyinProviderError("HelloTik 网页凭证协议已变化，暂无法解析")

    @classmethod
    def _decode_response(cls, data, key):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        alphabet = str.maketrans(
            "ZYXABCDEFGHIJKLMNOPQRSTUVWzyxabcdefghijklmnopqrstuvw9876543210-_",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
        )

        def decode(value):
            text = "".join(chr(b ^ 90) for b in base64.b64decode(value))
            text = "".join(text[i:i + 8][::-1] for i in range(0, len(text), 8))
            return base64.b64decode(text.translate(alphabet))

        plain = AES.new(cls.response_codec_key, AES.MODE_CBC, decode(key)).decrypt(decode(data))
        return json.loads(unpad(plain, AES.block_size).decode("utf-8"))

    def get_video_info(self, url):
        try:
            if self._profile is None:
                self._load_profile()
            if not self._device_id:
                device = self._post("/account/user/api/uwx/generate-id", {})
                self._device_id = (device.get("data") or {}).get("uwx_id")
                if not self._device_id:
                    raise DouyinProviderError("HelloTik 未返回匿名设备标识")
            payload = {
                "requestURL": url, "uwx_id": self._device_id,
                "isMobile": "false", "isoCode": "Other", "adType": "adsense",
                "successCount": str(self._success_count),
                "totalSuccessCount": str(self._success_count),
                "firstSuccessDate": None, "geoipIp": "", "pagePath": self.page_path,
                "externalRequestId": str(uuid.uuid4()),
            }
            quote = self._post("/api/parse-entitlement-status", {
                **payload, "request_url": url, "page_path": self.page_path,
            })
            entitlement = quote.get("data") or {}
            tier = entitlement.get("defaultTier") or "hd"
            if entitlement.get("showQuote") or (entitlement.get("tiers", {}).get(tier) or {}).get("chargeCost", 0):
                raise DouyinProviderError("HelloTik 本次解析需要点数，请在网页处理")
            payload.update(quoteToken=quote.get("quoteToken"), qualityTier=tier)
            profile = self._profile
            ticket_data = self._post("/api/" + profile["authRoute"], {
                "requestURL": url, "isBatch": False, "mode": "single",
            })
            ticket = ticket_data.get(profile["ticketResponseFields"]["key"])
            if not ticket:
                raise DouyinProviderError("HelloTik 未返回解析凭证")
            fields = profile["parseRequestFields"]
            # The site's supported fallback for clients without Web Crypto.
            result = self._post("/api/parse", {
                **payload, fields["key"]: ticket, fields["fallback"]: True,
            })
            if result.get("status") != 0:
                raise DouyinProviderError("HelloTik 未成功解析：" + concise_error(result.get("error") or "无有效结果"))
            data = result.get("data")
            if result.get("encrypt"):
                data = self._decode_response(data, result.get("key"))
            info = self._normalize(data, url)
            self._success_count += 1
            return info
        except DouyinProviderError:
            raise
        except Exception as exc:
            # Response text, tickets and device identifiers must not enter logs.
            raise DouyinProviderError(f"HelloTik 解析失败（{type(exc).__name__}），请检查网络或网页协议") from exc

    @staticmethod
    def _normalize(data, source_url):
        if not isinstance(data, dict):
            raise DouyinProviderError("HelloTik 解析结果格式已变化")

        def urls(values):
            return list(dict.fromkeys(
                address for value in (values or [])
                if isinstance(value, (str, dict))
                for address in [value.get("url", "") if isinstance(value, dict) else value]
                if isinstance(address, str) and urlparse(address).scheme in {"http", "https"}
            ))

        videos = urls(data.get("videos"))
        pictures = urls(data.get("pics"))
        if not videos and not pictures:
            raise DouyinProviderError("HelloTik 结果中没有可下载的视频或图片地址")
        work_id = DouyinUtils.extract_video_id(source_url)
        # A single picture alongside a video is its preview, not an image post.
        raw = {
            "aweme_id": work_id or "unknown", "desc": data.get("title"),
            "video": {"play_addr": {"url_list": videos}, "cover": {"url_list": pictures[:1]}},
            "images": [] if videos else pictures,
        }
        info = F2Provider._normalize(raw, source_url)
        info.update(provider="hellotik", from_hellotik=True, raw_data={})
        info.pop("from_f2", None)
        return info
