#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基于 douyinVd 项目的抖音视频提取器
使用本地 douyinVd 服务来获取抖音视频信息和下载链接
"""

import os
import json
import requests
import subprocess
import time
import threading
from typing import Dict, Any, Optional
from pathlib import Path

class DouyinVdExtractor:
    """使用 douyinVd 项目的抖音视频提取器"""
    
    def __init__(self, port: str = "8080"):
        self.port = port
        self.base_url = f"http://localhost:{port}"
        self.douyinvd_path = Path(__file__).parent.parent / "douyinVd"
        self.server_process = None
        self._server_running = False
        
    def start_server(self) -> bool:
        """启动 douyinVd 服务器"""
        try:
            if self.is_server_running():
                print("✅ douyinVd 服务器已经在运行")
                return True
                
            print("🚀 启动 douyinVd 服务器...")
            
            # 检查 douyinVd 目录是否存在
            if not self.douyinvd_path.exists():
                print(f"❌ douyinVd 目录不存在: {self.douyinvd_path}")
                return False
            
            # 检查 deno 是否可用
            try:
                subprocess.run(["deno", "--version"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("❌ deno 未安装或不在 PATH 中")
                return False
            
            # 启动服务器进程
            env = os.environ.copy()
            env['DENO_DIR'] = str(self.douyinvd_path / ".deno")
            
            # 使用指定端口启动服务
            self.server_process = subprocess.Popen(
                ["deno", "run", "--allow-net", "--allow-read", f"--port={self.port}", "main.ts"],
                cwd=self.douyinvd_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 等待服务器启动
            max_wait = 10  # 最多等待10秒
            for i in range(max_wait):
                if self.is_server_running():
                    print("✅ douyinVd 服务器启动成功")
                    self._server_running = True
                    return True
                time.sleep(1)
                print(f"⏳ 等待服务器启动... ({i+1}/{max_wait})")
            
            print("❌ douyinVd 服务器启动超时")
            if self.server_process:
                self.server_process.terminate()
                self.server_process = None
            return False
            
        except Exception as e:
            print(f"❌ 启动 douyinVd 服务器失败: {e}")
            return False
    
    def stop_server(self):
        """停止 douyinVd 服务器"""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                print("✅ douyinVd 服务器已停止")
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                print("🔪 强制停止 douyinVd 服务器")
            finally:
                self.server_process = None
                self._server_running = False
    
    def is_server_running(self) -> bool:
        """检查服务器是否运行中"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_video_url(self, douyin_url: str) -> Optional[str]:
        """
        获取无水印视频下载链接
        :param douyin_url: 抖音分享链接
        :return: 无水印视频下载链接
        """
        try:
            if not self.is_server_running():
                if not self.start_server():
                    return None
            
            params = {"url": douyin_url}
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                video_url = response.text.strip()
                if video_url and not video_url.startswith("请提供url参数"):
                    print(f"✅ 获取到视频下载链接: {video_url[:50]}...")
                    return video_url
                else:
                    print("❌ 获取视频链接失败，服务器返回错误信息")
                    return None
            else:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ 获取视频链接异常: {e}")
            return None
    
    def get_video_info(self, douyin_url: str) -> Optional[Dict[str, Any]]:
        """
        获取详细视频信息
        :param douyin_url: 抖音分享链接
        :return: 视频详细信息
        """
        try:
            if not self.is_server_running():
                if not self.start_server():
                    return None
            
            params = {"url": douyin_url, "data": "true"}
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                try:
                    video_info = response.json()
                    print(f"✅ 获取到视频详细信息")
                    return self._normalize_video_info(video_info)
                except json.JSONDecodeError:
                    print("❌ 解析视频信息JSON失败")
                    return None
            else:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ 获取视频信息异常: {e}")
            return None
    
    def _normalize_video_info(self, raw_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化视频信息格式，使其与现有系统兼容
        :param raw_info: 原始视频信息
        :return: 标准化后的视频信息
        """
        try:
            # 基本信息
            video_id = raw_info.get("aweme_id", "unknown")
            title = raw_info.get("desc", "未知标题")
            
            # 作者信息
            author_info = raw_info.get("author", {})
            author_name = author_info.get("nickname", "未知用户")
            author_id = author_info.get("unique_id", "unknown")
            
            # 统计信息
            statistics = raw_info.get("statistics", {})
            digg_count = statistics.get("digg_count", 0)
            comment_count = statistics.get("comment_count", 0)
            share_count = statistics.get("share_count", 0)
            collect_count = statistics.get("collect_count", 0)
            
            # 视频信息
            video_info = raw_info.get("video", {})
            cover_url = video_info.get("cover", {}).get("url_list", [""])[0] if video_info.get("cover") else ""
            
            # 音乐信息
            music_info = raw_info.get("music", {})
            music_title = music_info.get("title", "")
            music_author = music_info.get("author", "")
            
            # 获取无水印视频链接
            play_url_no_watermark = raw_info.get("video_url", "")
            
            # 创建时间
            create_time = raw_info.get("create_time", 0)
            
            # 标准化格式
            normalized_info = {
                "aweme_id": video_id,
                "desc": title,
                "create_time": create_time,
                "author": {
                    "uid": author_id,
                    "short_id": author_id,
                    "nickname": author_name,
                    "signature": author_info.get("signature", ""),
                    "avatar_thumb": author_info.get("avatar_thumb", {}).get("url_list", [""])[0] if author_info.get("avatar_thumb") else ""
                },
                "music": {
                    "id": music_info.get("id", ""),
                    "title": music_title,
                    "author": music_author,
                    "play_url": music_info.get("play_url", {}).get("uri", "") if music_info.get("play_url") else ""
                },
                "video": {
                    "play_url": raw_info.get("video_url", ""),
                    "play_url_no_watermark": play_url_no_watermark,
                    "cover_url": cover_url,
                    "duration": video_info.get("duration", 0),
                    "width": video_info.get("width", 0),
                    "height": video_info.get("height", 0)
                },
                "statistics": {
                    "digg_count": digg_count,
                    "comment_count": comment_count,
                    "share_count": share_count,
                    "collect_count": collect_count
                },
                "from_douyinvd": True,  # 标记来源
                "raw_data": raw_info  # 保存原始数据
            }
            
            return normalized_info
            
        except Exception as e:
            print(f"❌ 标准化视频信息失败: {e}")
            return raw_info
    
    def download_video(self, douyin_url: str, download_dir: str = "douyin_downloads") -> Dict[str, Any]:
        """
        下载抖音视频
        :param douyin_url: 抖音分享链接
        :param download_dir: 下载目录
        :return: 下载结果
        """
        try:
            # 获取视频信息
            video_info = self.get_video_info(douyin_url)
            if not video_info:
                return {"success": False, "error": "无法获取视频信息"}
            
            # 获取下载链接
            video_url = self.get_video_url(douyin_url)
            if not video_url:
                return {"success": False, "error": "无法获取视频下载链接"}
            
            # 创建下载目录
            os.makedirs(download_dir, exist_ok=True)
            
            # 生成文件名，使用配置的模板
            from .utils import DouyinUtils
            from .config import DouyinConfig
            
            # 获取配置文件名模板
            config = DouyinConfig()
            filename_template = config.get("filename_template")
            
            # 使用统一的文件名格式化方法
            base_filename = DouyinUtils.format_filename(filename_template, video_info)
            filename = f"{base_filename}_no_watermark.mp4"
            filepath = os.path.join(download_dir, filename)
            
            # 下载视频文件
            print(f"🎬 开始下载视频: {filename}")
            response = requests.get(video_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            print(f"\r下载进度: {progress:.1f}%", end="", flush=True)
            
            print(f"\n✅ 视频下载完成: {filepath}")
            
            # 保存元数据
            metadata_path = os.path.join(download_dir, f"{base_filename}_metadata.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 元数据保存完成: {metadata_path}")
            
            return {
                "success": True,
                "video_info": video_info,
                "downloaded_files": [
                    {
                        "type": "video",
                        "path": filepath,
                        "size": os.path.getsize(filepath),
                        "is_no_watermark": True
                    },
                    {
                        "type": "metadata",
                        "path": metadata_path,
                        "size": os.path.getsize(metadata_path)
                    }
                ],
                "errors": []
            }
            
        except Exception as e:
            print(f"❌ 下载视频失败: {e}")
            return {"success": False, "error": str(e)}
    
    def __del__(self):
        """析构函数，确保服务器进程被清理"""
        if hasattr(self, 'server_process') and self.server_process:
            self.stop_server()