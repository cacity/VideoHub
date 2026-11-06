#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""F2-first metadata resolution with a DLPanda public-link fallback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import DouyinConfig
from .diagnostics import concise_error, concise_f2_logs, http_status, provider_label
from .utils import DouyinUtils


class DouyinProviderError(RuntimeError):
    """A provider could not resolve a Douyin post."""


def _first_url(values: Any) -> str:
    if isinstance(values, str):
        return values.strip()
    if isinstance(values, Iterable) and not isinstance(values, (bytes, dict)):
        for value in values:
            result = _first_url(value)
            if result:
                return result
    return ""


def _all_urls(values: Any) -> list[str]:
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    if isinstance(values, Iterable) and not isinstance(values, (bytes, dict)):
        return list(dict.fromkeys(url for value in values for url in _all_urls(value)))
    return []


def _run_async(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class F2Provider:
    """Resolve a single Douyin post through F2's signed web API client."""

    name = "f2"

    def __init__(
        self,
        config: Optional[DouyinConfig] = None,
        handler_cls=None,
        aweme_id_fetcher=None,
        token_manager=None,
    ):
        self.config = config or DouyinConfig()
        self._handler_cls = handler_cls
        self._aweme_id_fetcher = aweme_id_fetcher
        self._token_manager = token_manager

    def _load_f2(self):
        if self._handler_cls and self._aweme_id_fetcher:
            return self._handler_cls, self._aweme_id_fetcher, self._token_manager

        try:
            from f2.apps.douyin.handler import DouyinHandler
            from f2.apps.douyin.utils import AwemeIdFetcher, TokenManager
        except Exception as exc:
            raise DouyinProviderError(
                "F2 不可用或依赖版本不兼容"
                f"（{type(exc).__name__}: {exc}）。请在干净环境中安装 requirements.txt。"
            ) from exc

        return DouyinHandler, AwemeIdFetcher, TokenManager

    def _build_kwargs(self, token_manager) -> Dict[str, Any]:
        headers = self.config.get_headers().copy()
        headers.pop("Cookie", None)
        # Let httpx advertise only compression codecs available in the active
        # environment. Claiming Brotli support without a decoder makes F2 try
        # to parse compressed response bytes as UTF-8 JSON.
        headers.pop("Accept-Encoding", None)
        headers["Referer"] = "https://www.douyin.com/"

        cookie = self.config.get_cookie() or ""
        if not cookie and token_manager is not None:
            try:
                ttwid = token_manager.gen_ttwid()
                if ttwid:
                    cookie = f"ttwid={ttwid};"
            except Exception:
                cookie = ""

        proxies = self.config.get_proxies() or {}
        return {
            "headers": headers,
            "proxies": {
                "http://": proxies.get("http"),
                "https://": proxies.get("https"),
            },
            "timeout": self.config.get("timeout", 30),
            "cookie": cookie,
        }

    async def _fetch(self, url: str):
        handler_cls, aweme_id_fetcher, token_manager = self._load_f2()
        # The provider chain reports a single scoped result. F2's internal
        # retries/QA links should not look like a failed VideoHub download.
        with concise_f2_logs(quiet=True):
            aweme_id = await aweme_id_fetcher.get_aweme_id(url)
            if not aweme_id:
                raise DouyinProviderError("F2 未能从链接中提取作品 ID")
            handler = handler_cls(self._build_kwargs(token_manager))
            # F2 0.0.1.7 enables Bark globally by default, even when no Bark key is
            # configured. VideoHub only needs metadata resolution here.
            handler.enable_bark = False
            return await handler.fetch_one_video(str(aweme_id))

    def get_video_info(self, url: str) -> Dict[str, Any]:
        try:
            result = _run_async(self._fetch(url))
            raw = result._to_raw() if hasattr(result, "_to_raw") else result
            if not isinstance(raw, dict):
                raise DouyinProviderError("F2 返回了无法识别的数据格式")
            return self._normalize(raw, url)
        except DouyinProviderError:
            raise
        except Exception as exc:
            raise DouyinProviderError(
                f"F2 解析失败（{type(exc).__name__}: {concise_error(exc)}）"
            ) from exc

    @staticmethod
    def _normalize(raw: Dict[str, Any], source_url: str) -> Dict[str, Any]:
        detail = raw.get("aweme_detail") or raw.get("aweme") or raw
        if not isinstance(detail, dict):
            raise DouyinProviderError("F2 响应中缺少 aweme_detail")

        video = detail.get("video") or {}
        play_urls = []
        for bit_rate in video.get("bit_rate") or []:
            play_urls.extend(_all_urls((bit_rate.get("play_addr") or {}).get("url_list")))
        play_urls.extend(_all_urls((video.get("play_addr") or {}).get("url_list")))
        play_urls = list(dict.fromkeys(play_urls))
        play_url = play_urls[0] if play_urls else ""

        images = []
        for image in detail.get("images") or []:
            image_url = _first_url(image.get("url_list") if isinstance(image, dict) else image)
            if image_url:
                images.append(image_url)

        aweme_id = str(detail.get("aweme_id") or DouyinUtils.extract_video_id(source_url) or "unknown")
        author = detail.get("author") or {}
        music = detail.get("music") or {}
        statistics = detail.get("statistics") or {}
        duration_ms = detail.get("duration") or video.get("duration") or 0
        try:
            duration = int(duration_ms)
            if duration > 1000:
                duration //= 1000
        except (TypeError, ValueError):
            duration = 0

        normalized = {
            "aweme_id": aweme_id,
            "desc": detail.get("desc") or f"douyin_{aweme_id}",
            "create_time": detail.get("create_time") or 0,
            "duration": duration,
            "author": {
                "uid": author.get("uid") or "",
                "short_id": author.get("short_id") or "",
                "nickname": author.get("nickname") or "未知用户",
                "signature": author.get("signature") or "",
                "avatar_thumb": _first_url((author.get("avatar_thumb") or {}).get("url_list")),
            },
            "music": {
                "id": str(music.get("id") or music.get("mid") or ""),
                "title": music.get("title") or "",
                "author": music.get("author") or "",
                "play_url": _first_url((music.get("play_url") or {}).get("url_list")),
            },
            "video": {
                "play_url": play_url,
                "play_url_no_watermark": play_url,
                "play_urls": play_urls,
                "cover_url": _first_url((video.get("origin_cover") or video.get("cover") or {}).get("url_list")),
                "duration": duration,
                "width": video.get("width") or 0,
                "height": video.get("height") or 0,
            },
            "statistics": {
                "digg_count": statistics.get("digg_count") or 0,
                "comment_count": statistics.get("comment_count") or 0,
                "share_count": statistics.get("share_count") or 0,
                "collect_count": statistics.get("collect_count") or 0,
            },
            "images": images,
            "type": "image" if images and not play_url else "video",
            "source_url": source_url,
            "provider": "f2",
            "from_f2": True,
            "raw_data": detail,
        }

        if not play_url and not images:
            raise DouyinProviderError("F2 响应中没有可下载的视频或图片地址")
        return normalized


class DLPandaProvider:
    """Resolve public Douyin posts through DLPanda's current HTML form."""

    name = "dlpanda"
    base_url = "https://dlpanda.com/douyin"

    def __init__(
        self,
        config: Optional[DouyinConfig] = None,
        session: Optional[requests.Session] = None,
    ):
        self.config = config or DouyinConfig()
        # Never reuse the Douyin session: account cookies must not reach DLPanda.
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.get("user_agent"),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )

    def get_video_info(self, url: str) -> Dict[str, Any]:
        timeout = self.config.get("timeout", 30)
        try:
            page = self.session.get(self.base_url, timeout=timeout)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "html.parser")
            form = soup.select_one("form[data-platform='douyin']") or soup.select_one(
                "form#dlpanda-download-form"
            )
            if form is None:
                raise DouyinProviderError("DLPanda 页面中未找到抖音解析表单")

            csrf = form.select_one("input[name='_token']")
            parser_token = form.select_one("input[name='t0ken']")
            if csrf is None or parser_token is None:
                raise DouyinProviderError("DLPanda 页面令牌结构已变化")

            response = self.session.post(
                urljoin(self.base_url, form.get("action") or self.base_url),
                data={
                    "_token": csrf.get("value", ""),
                    "t0ken": parser_token.get("value", ""),
                    "url": url,
                },
                headers={"Referer": self.base_url},
                timeout=max(timeout, 40),
            )
            response.raise_for_status()
            return self._parse_result(response.text, url)
        except DouyinProviderError:
            raise
        except Exception as exc:
            raise DouyinProviderError(
                f"DLPanda 解析失败（{type(exc).__name__}: {concise_error(exc)}）"
            ) from exc

    @classmethod
    def _parse_result(cls, html: str, source_url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        result = soup.select_one("#result")
        if result is None:
            status = soup.select_one("[data-download-status]")
            message = status.get_text(" ", strip=True) if status else "未返回解析结果"
            raise DouyinProviderError(f"DLPanda {message}")

        video_url = ""
        download = result.select_one("[data-download-url]")
        if download:
            video_url = download.get("data-download-url") or download.get("href") or ""
        if not video_url:
            source = result.select_one("video source[src]")
            if source:
                video_url = source.get("src") or ""
        video_url = urljoin(cls.base_url, video_url) if video_url else ""
        play_urls = list(dict.fromkeys(
            ([video_url] if video_url else []) + [
                urljoin(cls.base_url, node["src"]) for node in result.select("video source[src]") if node["src"]
            ]
        ))

        image_urls = []
        for node in result.select("a[data-download-name], img[src]"):
            name = (node.get("data-download-name") or "").lower()
            candidate = node.get("data-download-url") or node.get("href") or node.get("src") or ""
            if candidate and (
                re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", candidate, re.I)
                or re.search(r"\.(?:jpe?g|png|webp)$", name, re.I)
            ):
                normalized = urljoin(cls.base_url, candidate)
                if normalized not in image_urls:
                    image_urls.append(normalized)

        heading = result.find("h2")
        desc_button = result.select_one("button[data-copy-text]")
        desc = (
            desc_button.get("data-copy-text", "").strip()
            if desc_button
            else (heading.get_text(" ", strip=True) if heading else "")
        )

        download_name = download.get("data-download-name", "") if download else ""
        author_match = re.match(r"\[DLPanda\.com\]\[([^\]]+)\]", download_name)
        nickname = author_match.group(1).strip() if author_match else "未知用户"

        result_text = result.get_text(" ", strip=True)
        aweme_id_match = re.search(r"(?<!\d)(\d{15,22})(?!\d)", result_text)
        aweme_id = (
            aweme_id_match.group(1)
            if aweme_id_match
            else (DouyinUtils.extract_video_id(source_url) or "unknown")
        )

        if not video_url and not image_urls:
            raise DouyinProviderError("DLPanda 结果中没有可下载的视频或图片地址")

        return {
            "aweme_id": str(aweme_id),
            "desc": desc or f"douyin_{aweme_id}",
            "create_time": 0,
            "duration": 0,
            "author": {
                "uid": "",
                "short_id": "",
                "nickname": nickname,
                "signature": "",
                "avatar_thumb": "",
            },
            "music": {"id": "", "title": "", "author": "", "play_url": ""},
            "video": {
                "play_url": video_url,
                "play_url_no_watermark": video_url,
                "play_urls": play_urls,
                "cover_url": "",
                "duration": 0,
                "width": 0,
                "height": 0,
            },
            "statistics": {
                "digg_count": 0,
                "comment_count": 0,
                "share_count": 0,
                "collect_count": 0,
            },
            "images": image_urls,
            "type": "image" if image_urls and not video_url else "video",
            "source_url": source_url,
            "provider": "dlpanda",
            "from_dlpanda": True,
            "raw_data": {},
        }


class DouyinProviderChain:
    """Try F2 first, then DLPanda, retaining useful failure details."""

    F2_COOLDOWN_SECONDS = 15 * 60
    _f2_blocked_until = {}
    _f2_health_lock = Lock()

    def __init__(
        self,
        config: Optional[DouyinConfig] = None,
        providers=None,
    ):
        self.config = config or DouyinConfig()
        self.providers = providers or [
            F2Provider(self.config),
            DLPandaProvider(self.config),
        ]
        self.last_errors: Dict[str, str] = {}

    def _f2_key(self):
        # Share health across downloaders, but retry immediately after a user
        # changes authorization or network settings. Never retain raw secrets.
        settings = {
            "cookie": self.config.get_cookie() or "",
            "proxies": self.config.get_proxies(),
            "user_agent": self.config.get("user_agent"),
        }
        return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()

    def _f2_pause_remaining(self):
        with self._f2_health_lock:
            return max(0, self._f2_blocked_until.get(self._f2_key(), 0) - monotonic())

    def _pause_f2(self):
        with self._f2_health_lock:
            self._f2_blocked_until[self._f2_key()] = monotonic() + self.F2_COOLDOWN_SECONDS

    def get_video_info(self, url: str) -> Dict[str, Any]:
        self.last_errors = {}
        for index, provider in enumerate(self.providers):
            name = getattr(provider, "name", provider.__class__.__name__)
            label = provider_label(name)
            next_source = "，继续尝试其他解析源" if index + 1 < len(self.providers) else ""
            if name == "f2":
                remaining = self._f2_pause_remaining()
                if remaining:
                    minutes = max(1, int((remaining + 59) // 60))
                    message = f"此前请求返回 HTTP 403，暂跳过 F2（约 {minutes} 分钟后再试）"
                    self.last_errors[name] = message
                    print(f"[抖音解析] {message}{next_source}")
                    continue
            try:
                print(f"[抖音解析] 正在通过 {label} 获取媒体地址...")
                info = provider.get_video_info(url)
                if info:
                    info.setdefault("provider", name)
                    if self.last_errors:
                        info["provider_errors"] = self.last_errors.copy()
                    print(f"[抖音解析] {label} 已获取媒体地址，可继续下载")
                    return info
                self.last_errors[name] = "未返回有效作品信息"
            except Exception as exc:
                message = concise_error(exc)
                self.last_errors[name] = message
                if name == "f2" and http_status(exc) == 403:
                    self._pause_f2()
                    print(f"[抖音解析] F2 请求被抖音拒绝（HTTP 403），暂停该来源 15 分钟{next_source}")
                else:
                    print(f"[抖音解析] {label} 未成功：{message}{next_source}")

        details = "；".join(f"{name}: {error}" for name, error in self.last_errors.items())
        raise DouyinProviderError(f"当前可用抖音解析源均未成功，尚未下载文件。{details}")
