#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载器
基于TikTokDownload项目的核心下载技术
"""

import os
import time
import asyncio
import aiohttp
import aiofiles
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
import requests
from .parser import DouyinParser
from .config import DouyinConfig
from .utils import DouyinUtils
from .ytdlp_wrapper import YtDlpWrapper
from .douyinvd_extractor import DouyinVdExtractor

class DouyinDownloader:
    """抖音视频下载器"""
    
    def __init__(self, config: Optional[DouyinConfig] = None, port: str = "8080"):
        """
        初始化下载器
        :param config: 配置对象
        :param port: douyinVd服务端口
        """
        self.config = config or DouyinConfig()
        self.parser = DouyinParser(self.config)
        self.session = requests.Session()
        self.session.headers.update(self.config.get_headers())
        
        # 设置代理
        proxies = self.config.get_proxies()
        if proxies:
            self.session.proxies.update(proxies)
        
        # 创建下载目录
        download_dir = self.config.get("download_dir")
        os.makedirs(download_dir, exist_ok=True)
        
        # 初始化yt-dlp包装器
        self.ytdlp_wrapper = YtDlpWrapper(download_dir)
        
        # 初始化douyinVd提取器，使用指定端口
        self.douyinvd_extractor = DouyinVdExtractor(port=port)
    
    def download_video(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        下载单个视频
        :param url: 抖音视频链接
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            # 优先尝试使用 douyinVd 下载
            print("🚀 尝试使用 douyinVd 下载...")
            if progress_callback:
                progress_callback("尝试使用 douyinVd 下载...", 5)
            
            douyinvd_result = self._download_with_douyinvd(url, progress_callback)
            if douyinvd_result.get("success"):
                print("✅ douyinVd 下载成功")
                return douyinvd_result
            else:
                print(f"⚠️ douyinVd 下载失败: {douyinvd_result.get('error', '未知错误')}")
                print("🔄 回退到传统解析方法...")
            
            # 解析视频信息
            print("正在解析视频信息...")
            if progress_callback:
                progress_callback("正在解析视频信息...", 10)
            
            video_info = self.parser.parse_video_info(url)
            if not video_info:
                return {"success": False, "error": "无法解析视频信息"}
            
            # 检查是否是来自yt-dlp的信息
            if video_info.get('from_ytdlp'):
                print("🚀 检测到 yt-dlp 视频信息，使用 yt-dlp 下载")
                return self._download_with_ytdlp(url, progress_callback)
            
            # 生成文件名
            filename_template = self.config.get("filename_template")
            print(f"文件名模板: {filename_template}")
            base_filename = DouyinUtils.format_filename(filename_template, video_info)
            print(f"生成的基础文件名: {base_filename}")
            print(f"下载目录: {self.config.get('download_dir')}")
            
            # 下载结果
            result = {
                "success": True,
                "video_info": video_info,
                "downloaded_files": [],
                "errors": []
            }
            
            # 下载视频 - 优先下载无水印版本
            video_data = video_info.get("video", {})
            
            # 优先使用无水印链接
            no_watermark_url = video_data.get("play_url_no_watermark")
            video_url = video_data.get("play_url")
            
            download_url = None
            video_type = ""
            
            if no_watermark_url and no_watermark_url.strip():
                download_url = no_watermark_url
                video_type = "无水印视频"
                print("🎬 发现无水印视频链接，优先下载")
            elif video_url and video_url.strip():
                download_url = video_url
                video_type = "标准视频"
                print("📹 使用标准视频链接下载")
            
            if download_url:
                print(f"正在下载{video_type}...")
                if progress_callback:
                    progress_callback(f"正在下载{video_type}...", 20)
                
                video_filename = f"{base_filename}{'_no_watermark' if no_watermark_url else ''}.mp4"
                video_path = self._download_file(
                    download_url, 
                    video_filename,
                    progress_callback,
                    20, 70  # 进度范围：20% - 70%
                )
                
                if video_path:
                    result["downloaded_files"].append({
                        "type": "video",
                        "path": video_path,
                        "size": os.path.getsize(video_path),
                        "is_no_watermark": bool(no_watermark_url)
                    })
                    print(f"✅ {video_type}下载成功")
                else:
                    result["errors"].append(f"{video_type}下载失败")
            else:
                print("⚠️ 无法获取视频下载链接（来自网页解析）")
                if progress_callback:
                    progress_callback("跳过视频下载（无下载链接）", 70)
                result["errors"].append("无法获取视频下载链接")
            
            # 下载封面
            if self.config.get("download_cover"):
                cover_url = video_info.get("video", {}).get("cover_url")
                if cover_url and cover_url.strip():
                    print("正在下载封面...")
                    if progress_callback:
                        progress_callback("正在下载封面...", 75)
                    
                    cover_path = self._download_file(cover_url, f"{base_filename}_cover.jpg")
                    if cover_path:
                        result["downloaded_files"].append({
                            "type": "cover",
                            "path": cover_path,
                            "size": os.path.getsize(cover_path)
                        })
                else:
                    print("⚠️ 无法获取封面下载链接")
                    if progress_callback:
                        progress_callback("跳过封面下载（无下载链接）", 75)
            
            # 下载音频
            if self.config.get("download_music"):
                music_url = video_info.get("music", {}).get("play_url")
                if music_url and music_url.strip():
                    print("正在下载音频...")
                    if progress_callback:
                        progress_callback("正在下载音频...", 85)
                    
                    music_path = self._download_file(music_url, f"{base_filename}_music.mp3")
                    if music_path:
                        result["downloaded_files"].append({
                            "type": "music",
                            "path": music_path,
                            "size": os.path.getsize(music_path)
                        })
                else:
                    print("⚠️ 无法获取音频下载链接")
                    if progress_callback:
                        progress_callback("跳过音频下载（无下载链接）", 85)
            
            # 保存元数据
            if self.config.get("save_metadata"):
                print("正在保存元数据...")
                if progress_callback:
                    progress_callback("正在保存元数据...", 95)
                
                try:
                    metadata_path = os.path.join(
                        self.config.get("download_dir"),
                        f"{base_filename}_metadata.json"
                    )
                    print(f"元数据保存路径: {metadata_path}")
                    
                    if DouyinUtils.save_metadata(video_info, metadata_path):
                        result["downloaded_files"].append({
                            "type": "metadata",
                            "path": metadata_path,
                            "size": os.path.getsize(metadata_path)
                        })
                        print("✅ 元数据保存成功")
                    else:
                        print("❌ 元数据保存失败")
                        result["errors"].append("元数据保存失败")
                        
                except Exception as metadata_error:
                    print(f"❌ 元数据保存异常: {metadata_error}")
                    result["errors"].append(f"元数据保存异常: {metadata_error}")
            
            if progress_callback:
                progress_callback("下载完成", 100)
            
            # 优化结果消息
            if result["success"]:
                downloaded_count = len(result["downloaded_files"])
                error_count = len(result["errors"])
                
                if downloaded_count > 0:
                    print(f"✅ 下载成功：共下载 {downloaded_count} 个文件")
                    if error_count > 0:
                        print(f"⚠️ 注意：有 {error_count} 个警告")
                        for error in result["errors"]:
                            print(f"   - {error}")
                else:
                    print("⚠️ 下载完成但没有文件被下载")
                    if error_count > 0:
                        for error in result["errors"]:
                            print(f"   - {error}")
                    
                    # 如果只是因为网页解析无法获取下载链接，给出友好提示
                    if "无法获取视频下载链接" in result["errors"]:
                        print("💡 提示：当前使用网页解析模式，只能获取基本信息")
                        print("   - 视频信息已保存到元数据文件")
                        print("   - 如需下载视频文件，请确保链接有效或尝试其他方法")
            
            return result
            
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
            # 优先尝试使用 douyinVd 获取视频信息
            print("🚀 尝试使用 douyinVd 获取视频信息...")
            video_info = self.douyinvd_extractor.get_video_info(url)
            
            if video_info:
                print("✅ douyinVd 获取视频信息成功")
                return video_info
            else:
                print("⚠️ douyinVd 获取视频信息失败，回退到传统解析方法...")
                
        except Exception as e:
            print(f"❌ douyinVd 获取视频信息异常: {e}")
            print("🔄 回退到传统解析方法...")
        
        # 回退到传统解析方法
        return self.parser.parse_video_info(url)
    
    def download_user_videos(self, user_url: str, limit: int = 20, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        下载用户的视频
        :param user_url: 用户主页链接
        :param limit: 下载数量限制
        :param progress_callback: 进度回调
        :return: 下载结果
        """
        try:
            # 解析用户信息
            print("正在解析用户信息...")
            if progress_callback:
                progress_callback("正在解析用户信息...", 5)
            
            user_info = self.parser.parse_user_info(user_url)
            if not user_info:
                return {"success": False, "error": "无法解析用户信息"}
            
            # 获取用户视频列表
            print("正在获取用户视频列表...")
            if progress_callback:
                progress_callback("正在获取用户视频列表...", 15)
            
            # 这里需要实现获取用户视频列表的逻辑
            # 由于复杂性，暂时返回空列表
            video_urls = []
            
            if not video_urls:
                return {"success": False, "error": "无法获取用户视频列表"}
            
            # 限制下载数量
            video_urls = video_urls[:limit]
            
            # 批量下载
            def batch_progress(msg, progress):
                if progress_callback:
                    # 将批量下载进度映射到总进度的85%
                    mapped_progress = 15 + int((progress / 100) * 85)
                    progress_callback(msg, mapped_progress)
            
            result = self.download_videos_batch(video_urls, batch_progress)
            result["user_info"] = user_info
            
            return result
            
        except Exception as e:
            print(f"下载用户视频失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _download_with_ytdlp(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        使用yt-dlp下载视频
        :param url: 视频URL
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        try:
            print("🚀 使用 yt-dlp 下载模式")
            if progress_callback:
                progress_callback(10, "使用 yt-dlp 下载...")
            
            # 使用yt-dlp下载
            result = self.ytdlp_wrapper.download_video(url, progress_callback)
            
            if result.get("success"):
                print("✅ yt-dlp 下载成功")
                if progress_callback:
                    progress_callback(100, "yt-dlp 下载完成")
                
                # 转换为标准格式
                return {
                    "success": True,
                    "video_info": {"extraction_method": "yt-dlp"},
                    "downloaded_files": result.get("downloaded_files", []),
                    "errors": []
                }
            else:
                error_msg = result.get("error", "yt-dlp 下载失败")
                print(f"❌ yt-dlp 下载失败: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"yt-dlp 下载异常: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

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