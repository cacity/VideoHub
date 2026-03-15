#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载器
基于TikTokDownload项目的核心下载技术
"""

import os
import time
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
import requests
from .config import DouyinConfig
from .utils import DouyinUtils
from .douyinvd_extractor import DouyinVdExtractor

class DouyinDownloader:
    """抖音视频下载器"""
    
    def __init__(self, config: Optional[DouyinConfig] = None, port: str = "8080"):
        """
        初始化下载器
        :param config: 配置对象
        :param port: 端口（保留兼容性，实际未使用）
        """
        self.config = config or DouyinConfig()
        self.session = requests.Session()
        self.session.headers.update(self.config.get_headers())
        
        # 设置代理
        proxies = self.config.get_proxies()
        if proxies:
            self.session.proxies.update(proxies)
        
        # 创建下载目录
        download_dir = self.config.get("download_dir")
        os.makedirs(download_dir, exist_ok=True)
        
        # 初始化新的提取器（使用douyin.py）
        self.douyinvd_extractor = DouyinVdExtractor(port=port)
    
    def download_video(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        下载单个视频
        :param url: 抖音视频链接
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            # 使用新的 douyin.py 下载
            print("🚀 使用新douyin.py下载...")
            if progress_callback:
                progress_callback("正在下载抖音视频...", 5)
            
            douyinvd_result = self._download_with_douyinvd(url, progress_callback)
            if douyinvd_result.get("success"):
                print("✅ 下载成功")
                return douyinvd_result
            else:
                error = douyinvd_result.get('error', '未知错误')
                print(f"❌ 下载失败: {error}")
                return {"success": False, "error": error}
            
        except Exception as e:
            print(f"下载视频失败: {e}")
            return {"success": False, "error": str(e)}
    
    def download_videos_batch(self, urls: List[str], progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        批量下载视频
        :param urls: 视频链接列表
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            total_count = len(urls)
            results = []
            successful_count = 0
            failed_count = 0
            
            print(f"开始批量下载 {total_count} 个视频...")
            
            for i, url in enumerate(urls):
                print(f"下载进度: {i+1}/{total_count}")
                if progress_callback:
                    overall_progress = int((i / total_count) * 100)
                    progress_callback(f"正在下载第 {i+1}/{total_count} 个视频", overall_progress)
                
                # 单个视频下载进度回调
                def single_progress(msg, progress):
                    if progress_callback:
                        # 将单个视频的进度映射到总进度
                        base_progress = int((i / total_count) * 100)
                        current_progress = base_progress + int((progress / 100) * (100 / total_count))
                        progress_callback(f"第 {i+1}/{total_count} 个视频: {msg}", current_progress)
                
                result = self.download_video(url, single_progress)
                results.append(result)
                
                if result["success"]:
                    successful_count += 1
                else:
                    failed_count += 1
                
                # 添加延迟避免请求过快
                time.sleep(self.config.get("retry_delay", 1))
            
            batch_result = {
                "success": True,
                "total_count": total_count,
                "successful_count": successful_count,
                "failed_count": failed_count,
                "results": results
            }
            
            if progress_callback:
                progress_callback("批量下载完成", 100)
            
            return batch_result
            
        except Exception as e:
            print(f"批量下载失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _download_file(self, url: str, filename: str, progress_callback: Optional[Callable] = None, 
                      progress_start: int = 0, progress_end: int = 100) -> Optional[str]:
        """
        下载文件
        :param url: 文件URL
        :param filename: 文件名
        :param progress_callback: 进度回调
        :param progress_start: 进度起始点
        :param progress_end: 进度结束点
        :return: 下载后的文件路径
        """
        try:
            # 构建文件路径
            file_path = os.path.join(self.config.get("download_dir"), filename)
            
            # 检查文件是否已存在
            if os.path.exists(file_path):
                print(f"文件已存在: {filename}")
                return file_path
            
            # 发送请求
            headers = self.config.get_headers()
            headers.update({
                'Referer': 'https://www.douyin.com/',
                'Range': 'bytes=0-'  # 支持断点续传
            })
            
            response = self.session.get(url, headers=headers, stream=True, timeout=self.config.get("timeout"))
            response.raise_for_status()
            
            # 获取文件大小
            total_size = int(response.headers.get('Content-Length', 0))
            chunk_size = self.config.get("chunk_size", 1024 * 1024)
            downloaded_size = 0
            
            print(f"开始下载: {filename} ({DouyinUtils.format_file_size(total_size)})")
            
            # 写入文件
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 更新进度
                        if progress_callback and total_size > 0:
                            file_progress = int((downloaded_size / total_size) * 100)
                            overall_progress = progress_start + int((file_progress / 100) * (progress_end - progress_start))
                            progress_callback(f"下载 {filename}: {file_progress}%", overall_progress)
            
            print(f"下载完成: {filename}")
            return file_path
            
        except Exception as e:
            print(f"下载文件失败 {filename}: {e}")
            return None
    
    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        获取视频信息（不下载）
        :param url: 抖音视频链接
        :return: 视频信息
        """
        try:
            print("🚀 获取视频信息...")
            video_info = self.douyinvd_extractor.get_video_info(url)
            
            if video_info:
                print("✅ 获取视频信息成功")
                return video_info
            else:
                print("❌ 获取视频信息失败")
                return None
                
        except Exception as e:
            print(f"❌ 获取视频信息异常: {e}")
            return None
    
    def download_user_videos(self, user_url: str, limit: int = 0, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        使用 f2 库批量下载用户主页所有视频
        :param user_url: 用户主页链接（支持短链和长链）
        :param limit: 最多下载数量，0 表示全部
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            import asyncio
            from f2.apps.douyin.handler import DouyinHandler
            from f2.apps.douyin.utils import SecUserIdFetcher
            from f2.utils.utils import extract_valid_urls
        except ImportError as e:
            return {"success": False, "error": f"需要安装 f2 库: pip install f2\n({e})"}

        cookie = self.config.get("cookie") or ""
        kwargs = {
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
                "Referer": "https://www.douyin.com/",
            },
            "proxies": {"http://": None, "https://": None},
            "timeout": 10,
            "cookie": cookie,
        }

        async def _fetch_aweme_ids():
            urls = extract_valid_urls([user_url])
            if not urls:
                return []
            sec_user_id = await SecUserIdFetcher.get_sec_user_id(urls[0])
            if not sec_user_id:
                return []
            all_ids = []
            async for page_data in DouyinHandler(kwargs).fetch_user_post_videos(
                sec_user_id=sec_user_id,
                page_counts=20,
                max_counts=limit if limit > 0 else None,
            ):
                for item in page_data._to_list():
                    aweme_id = item.get("aweme_id")
                    if aweme_id:
                        all_ids.append(str(aweme_id))
            return all_ids

        try:
            if progress_callback:
                progress_callback("正在解析用户主页，获取视频列表...", 5)

            aweme_ids = asyncio.run(_fetch_aweme_ids())
            if not aweme_ids:
                return {"success": False, "error": "未找到视频，请确认链接为用户主页，或提供有效 Cookie"}

            total = len(aweme_ids)
            if progress_callback:
                progress_callback(f"共找到 {total} 个视频，开始下载...", 10)

            success_count = 0
            fail_count = 0

            for i, aweme_id in enumerate(aweme_ids):
                pct = 10 + int((i / total) * 88)
                if progress_callback:
                    progress_callback(f"[{i+1}/{total}] 正在下载 {aweme_id}...", pct)

                video_url = f"https://www.douyin.com/video/{aweme_id}"
                result = self._download_with_douyinvd(video_url)
                if result.get("success"):
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"下载失败 {aweme_id}: {result.get('error')}")

                time.sleep(self.config.get("retry_delay", 1))

            if progress_callback:
                progress_callback(f"批量下载完成：成功 {success_count} 个，失败 {fail_count} 个", 100)

            return {
                "success": True,
                "total_count": total,
                "successful_count": success_count,
                "failed_count": fail_count,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
    

    def cleanup_downloads(self, days_old: int = 7) -> Dict[str, Any]:
        """
        清理下载文件
        :param days_old: 清理多少天前的文件
        :return: 清理结果
        """
        try:
            download_dir = Path(self.config.get("download_dir"))
            current_time = time.time()
            cutoff_time = current_time - (days_old * 24 * 60 * 60)
            
            cleaned_files = []
            cleaned_size = 0
            
            for file_path in download_dir.iterdir():
                if file_path.is_file():
                    file_stat = file_path.stat()
                    if file_stat.st_mtime < cutoff_time:
                        file_size = file_stat.st_size
                        file_path.unlink()
                        cleaned_files.append(str(file_path))
                        cleaned_size += file_size
            
            result = {
                "success": True,
                "cleaned_count": len(cleaned_files),
                "cleaned_size": cleaned_size,
                "cleaned_files": cleaned_files
            }
            
            print(f"清理完成: 删除了 {len(cleaned_files)} 个文件，释放了 {DouyinUtils.format_file_size(cleaned_size)} 空间")
            return result
            
        except Exception as e:
            print(f"清理文件失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _download_with_douyinvd(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        使用 douyinVd 下载视频
        :param url: 视频URL
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            print("🚀 使用 douyinVd 下载模式")
            if progress_callback:
                progress_callback("使用 douyinVd 下载...", 10)
            
            # 使用 douyinVd 下载
            download_dir = self.config.get("download_dir")
            result = self.douyinvd_extractor.download_video(url, download_dir)
            
            if result.get("success"):
                print("✅ douyinVd 下载成功")
                if progress_callback:
                    progress_callback("douyinVd 下载完成", 100)
                return result
            else:
                error_msg = result.get("error", "douyinVd 下载失败")
                print(f"❌ douyinVd 下载失败: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"douyinVd 下载异常: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}