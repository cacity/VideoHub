#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Compatibility facade for the F2 -> DLPanda Douyin provider chain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import requests

from paths_config import DOUYIN_DOWNLOADS_DIR

from .config import DouyinConfig
from .providers import DouyinProviderChain, DouyinProviderError
from .utils import DouyinUtils


class DouyinVdExtractor:
    """Resolve through F2 first and DLPanda second, then download media."""

    def __init__(
        self,
        port: str = "8080",
        config: Optional[DouyinConfig] = None,
        provider_chain: Optional[DouyinProviderChain] = None,
    ):
        self.port = port  # compatibility only
        self.config = config or DouyinConfig()
        self.provider_chain = provider_chain or DouyinProviderChain(self.config)
        self.last_error = ""

    def start_server(self) -> bool:
        """Compatibility method; the provider chain needs no local server."""
        return True

    def stop_server(self):
        return None

    def is_server_running(self) -> bool:
        return True

    def get_video_info(self, douyin_url: str) -> Optional[Dict[str, Any]]:
        try:
            info = self.provider_chain.get_video_info(douyin_url)
            self.last_error = ""
            return info
        except Exception as exc:
            self.last_error = str(exc)
            print(f"获取视频信息异常: {self.last_error}")
            return None

    def get_video_url(
        self,
        douyin_url: str,
        video_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        info = video_info or self.get_video_info(douyin_url)
        if not info:
            return None
        video = info.get("video") or {}
        return video.get("play_url_no_watermark") or video.get("play_url") or None

    def _request_headers(self, provider: str, media_url: str) -> Dict[str, str]:
        headers = {
            "User-Agent": self.config.get("user_agent"),
            "Accept": "*/*",
        }
        # DLPanda currently renders its player with referrerpolicy="no-referrer".
        # Its signed CDN URLs return 403 when a DLPanda Referer is supplied.
        if provider != "dlpanda":
            headers["Referer"] = "https://www.douyin.com/"

        # Never send a user's Douyin Cookie to DLPanda or an unrelated CDN.
        host = (urlparse(media_url).hostname or "").lower()
        is_douyin_host = (
            host == "douyin.com"
            or host.endswith(".douyin.com")
            or host.endswith(".iesdouyin.com")
        )
        if is_douyin_host:
            cookie = self.config.get_cookie()
            if cookie:
                headers["Cookie"] = cookie
        return headers

    def _download_media(
        self,
        media_url: str,
        output_path: Path,
        provider: str,
        progress_callback: Optional[Callable],
        progress_start: int,
        progress_end: int,
    ) -> Path:
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = output_path.with_suffix(output_path.suffix + ".part")
        if part_path.exists():
            part_path.unlink()

        try:
            with requests.get(
                media_url,
                headers=self._request_headers(provider, media_url),
                stream=True,
                timeout=max(self.config.get("timeout", 30), 60),
                allow_redirects=True,
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0) or 0)
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "text/html" in content_type:
                    raise DouyinProviderError("媒体地址返回了 HTML 页面，链接可能已过期")

                downloaded = 0
                first_chunk = True
                with part_path.open("wb") as handle:
                    for chunk in response.iter_content(
                        chunk_size=self.config.get("chunk_size", 1024 * 1024)
                    ):
                        if not chunk:
                            continue
                        if first_chunk:
                            first_chunk = False
                            prefix = chunk[:64].lstrip().lower()
                            if prefix.startswith(b"<html") or prefix.startswith(b"<!doctype html"):
                                raise DouyinProviderError("媒体地址返回了网页而不是媒体文件")
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            ratio = min(downloaded / total_size, 1.0)
                            progress = progress_start + int(ratio * (progress_end - progress_start))
                            progress_callback(f"下载 {output_path.name}: {int(ratio * 100)}%", progress)

            if not part_path.exists() or part_path.stat().st_size == 0:
                raise DouyinProviderError("下载结果为空")
            part_path.replace(output_path)
            return output_path
        except Exception:
            if part_path.exists():
                part_path.unlink()
            raise

    def download_video(
        self,
        douyin_url: str,
        download_dir: str = DOUYIN_DOWNLOADS_DIR,
        save_metadata: bool = False,
        video_info: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        try:
            info = video_info or self.get_video_info(douyin_url)
            if not info:
                return {"success": False, "error": self.last_error or "无法获取视频信息"}

            provider = info.get("provider", "unknown")
            base_filename = DouyinUtils.format_filename(
                self.config.get("filename_template"), info
            )
            output_dir = Path(download_dir)
            downloaded_files = []
            files = {"video": [], "image": [], "cover": [], "music": [], "metadata": []}

            video_url = self.get_video_url(douyin_url, info)
            images = info.get("images") or []
            if video_url:
                video_path = self._download_media(
                    video_url,
                    output_dir / f"{base_filename}_no_watermark.mp4",
                    provider,
                    progress_callback,
                    15,
                    85,
                )
                files["video"].append(str(video_path))
                downloaded_files.append(
                    {
                        "type": "video",
                        "path": str(video_path),
                        "size": video_path.stat().st_size,
                        "is_no_watermark": True,
                    }
                )
            elif images:
                span = max(70 // len(images), 1)
                for index, image_url in enumerate(images, start=1):
                    image_path = self._download_media(
                        image_url,
                        output_dir / f"{base_filename}_{index:02d}.jpg",
                        provider,
                        progress_callback,
                        15 + (index - 1) * span,
                        min(15 + index * span, 85),
                    )
                    files["image"].append(str(image_path))
                    downloaded_files.append(
                        {
                            "type": "image",
                            "path": str(image_path),
                            "size": image_path.stat().st_size,
                        }
                    )
            else:
                raise DouyinProviderError("解析结果中没有可下载的媒体地址")

            cover_url = (info.get("video") or {}).get("cover_url")
            if self.config.get("download_cover", True) and cover_url:
                try:
                    cover_path = self._download_media(
                        cover_url,
                        output_dir / f"{base_filename}_cover.jpg",
                        provider,
                        progress_callback,
                        86,
                        91,
                    )
                    files["cover"].append(str(cover_path))
                    downloaded_files.append(
                        {"type": "cover", "path": str(cover_path), "size": cover_path.stat().st_size}
                    )
                except Exception as exc:
                    print(f"封面下载失败，已跳过: {exc}")

            music_url = (info.get("music") or {}).get("play_url")
            if self.config.get("download_music", False) and music_url:
                try:
                    music_path = self._download_media(
                        music_url,
                        output_dir / f"{base_filename}_music.mp3",
                        provider,
                        progress_callback,
                        91,
                        96,
                    )
                    files["music"].append(str(music_path))
                    downloaded_files.append(
                        {"type": "music", "path": str(music_path), "size": music_path.stat().st_size}
                    )
                except Exception as exc:
                    print(f"原声下载失败，已跳过: {exc}")

            if save_metadata:
                metadata_path = output_dir / f"{base_filename}_metadata.json"
                metadata_path.write_text(
                    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                files["metadata"].append(str(metadata_path))
                downloaded_files.append(
                    {
                        "type": "metadata",
                        "path": str(metadata_path),
                        "size": metadata_path.stat().st_size,
                    }
                )

            if progress_callback:
                progress_callback(f"下载完成（解析源：{provider}）", 100)
            return {
                "success": True,
                "provider": provider,
                "video_info": info,
                "downloaded_files": downloaded_files,
                "files": files,
                "errors": [],
            }
        except Exception as exc:
            self.last_error = str(exc)
            print(f"下载视频失败: {self.last_error}")
            return {"success": False, "error": self.last_error}


__all__ = ["DouyinVdExtractor", "DouyinProviderChain", "DouyinProviderError"]
