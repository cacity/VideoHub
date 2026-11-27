"""Public-link fallback through PeanutDL's web parser. No account cookies."""

from urllib.parse import urlparse

import requests

from .config import DouyinConfig
from .diagnostics import concise_error
from .providers import DouyinProviderError, F2Provider
from .utils import DouyinUtils


class PeanutDLProvider:
    name = "peanutdl"
    endpoint = "https://xapi.peanutdl.com/douyin"

    def __init__(self, config=None, session=None):
        self.config = config or DouyinConfig()
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.get("user_agent"),
            "Origin": "https://peanutdl.com",
            "Referer": "https://peanutdl.com/zh/douyin",
        })

    def get_video_info(self, url):
        try:
            response = self.session.post(self.endpoint, json={
                "api": "DOUYIN", "url": url,
                "captcha": "", "id": "", "captcha_code": "", "captcha_id": "",
                "turnstile_token": "", "captcha_type": "",
            }, timeout=max(self.config.get("timeout", 30), 60))
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise DouyinProviderError("PeanutDL 返回格式已变化")
            if result.get("code") == 2 or result.get("captcha") or result.get("require_captcha"):
                raise DouyinProviderError("PeanutDL 要求验证码，请在网页完成验证；已停止自动请求")
            if result.get("success") is not True:
                raise DouyinProviderError("PeanutDL 未成功解析，请检查链接或稍后重试")
            return self._normalize(result.get("data"), url)
        except DouyinProviderError:
            raise
        except requests.RequestException as exc:
            raise DouyinProviderError(f"PeanutDL 请求失败：{concise_error(exc)}") from exc
        except Exception as exc:
            raise DouyinProviderError(f"PeanutDL 解析失败（{type(exc).__name__}），网页协议可能已变化") from exc

    @staticmethod
    def _urls(value):
        if isinstance(value, dict):
            value = value.get("urls") or value.get("url_list") or value.get("url") or []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(v for v in value if isinstance(v, str)
                                  and urlparse(v).scheme in {"http", "https"} and urlparse(v).hostname))

    @classmethod
    def _normalize(cls, data, source_url):
        if not isinstance(data, dict):
            raise DouyinProviderError("PeanutDL 响应中缺少作品信息")
        work_id = str(data.get("video_id") or DouyinUtils.extract_video_id(source_url) or "unknown")
        expected_id = DouyinUtils.extract_video_id(source_url)
        if expected_id and work_id != expected_id:
            raise DouyinProviderError("PeanutDL 返回了其他作品，已停止下载")
        groups = [cls._urls(image) for image in data.get("images") or []]
        if any(not group for group in groups):
            raise DouyinProviderError("PeanutDL 图集含缺失的图片地址，不能保存完整图集")
        videos = [url for video in data.get("videos") or [] for url in cls._urls(video)]
        if not groups and not videos:
            raise DouyinProviderError("PeanutDL 结果没有可下载的视频或图片")
        covers = cls._urls(data.get("covers"))
        author = data.get("author") or {}
        raw = {
            "aweme_id": work_id, "desc": data.get("title"),
            "author": {"nickname": author.get("nickname"), "uid": author.get("unique_id")},
            "video": {"play_addr": {"url_list": videos}, "cover": {"url_list": covers}},
            "images": [{"url_list": group} for group in groups],
        }
        info = F2Provider._normalize(raw, source_url)
        info.update(provider=cls.name, from_peanutdl=True, raw_data={})
        info.pop("from_f2", None)
        return info
