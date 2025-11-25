#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
yt-dlp包装器 - 更实用的抖音视频下载方案
"""

import os
import sys
import json
import subprocess
import tempfile
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

class YtDlpWrapper:
    """yt-dlp包装器，提供更可靠的抖音视频下载"""
    
    def __init__(self, download_dir: str = "downloads"):
        """
        初始化yt-dlp包装器
        :param download_dir: 下载目录
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        
        # 检查yt-dlp是否可用
        self.ytdlp_available = self._check_ytdlp()
    
    def _check_ytdlp(self) -> bool:
        """检查yt-dlp是否可用"""
        try:
            result = subprocess.run(['yt-dlp', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✅ yt-dlp 可用，版本: {result.stdout.strip()}")
                return True
            else:
                print("❌ yt-dlp 不可用")
                return False
        except Exception as e:
            print(f"❌ yt-dlp 检查失败: {e}")
            return False
    
    def install_ytdlp(self) -> bool:
        """尝试安装yt-dlp"""
        try:
            print("📦 正在安装 yt-dlp...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], 
                                  capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                print("✅ yt-dlp 安装成功")
                self.ytdlp_available = self._check_ytdlp()
                return self.ytdlp_available
            else:
                print(f"❌ yt-dlp 安装失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ yt-dlp 安装异常: {e}")
            return False
    
    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        获取视频信息
        :param url: 视频URL
        :return: 视频信息字典
        """
        if not self.ytdlp_available:
            print("❌ yt-dlp 不可用，无法获取视频信息")
            return None
        
        try:
            print(f"🔍 使用 yt-dlp 获取视频信息: {url}")
            
            # yt-dlp命令参数
            cmd = [
                'yt-dlp',
                '--dump-json',  # 只输出JSON信息，不下载
                '--no-warnings',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                try:
                    video_info = json.loads(result.stdout)
                    print("✅ yt-dlp 成功获取视频信息")
                    return self._normalize_video_info(video_info)
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    return None
            else:
                print(f"❌ yt-dlp 获取信息失败: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ yt-dlp 获取信息超时")
            return None
        except Exception as e:
            print(f"❌ yt-dlp 获取信息异常: {e}")
            return None
    
    def download_video(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        下载视频
        :param url: 视频URL
        :param progress_callback: 进度回调函数
        :return: 下载结果
        """
        if not self.ytdlp_available:
            return {"success": False, "error": "yt-dlp 不可用"}
        
        try:
            print(f"📥 使用 yt-dlp 下载视频: {url}")
            
            if progress_callback:
                progress_callback("开始下载...", 0)
            
            # 生成输出文件名模板
            output_template = str(self.download_dir / "%(uploader)s_%(title)s_%(id)s.%(ext)s")
            
            # yt-dlp命令参数
            cmd = [
                'yt-dlp',
                '--format', 'best[height<=720]',  # 选择720p以下最佳质量
                '--output', output_template,
                '--write-info-json',  # 保存元数据
                '--write-thumbnail',  # 保存缩略图
                '--no-warnings',
                url
            ]
            
            if progress_callback:
                progress_callback("正在下载视频...", 20)
            
            # 执行下载
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                if progress_callback:
                    progress_callback("下载完成", 100)
                
                # 查找下载的文件
                downloaded_files = self._find_downloaded_files(url)
                
                return {
                    "success": True,
                    "downloaded_files": downloaded_files,
                    "ytdlp_output": result.stdout,
                    "errors": []
                }
            else:
                error_msg = result.stderr or "下载失败"
                print(f"❌ yt-dlp 下载失败: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except subprocess.TimeoutExpired:
            error_msg = "下载超时"
            print(f"❌ yt-dlp 下载超时")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"下载异常: {str(e)}"
            print(f"❌ yt-dlp 下载异常: {e}")
            return {"success": False, "error": error_msg}
    
    def _normalize_video_info(self, ytdlp_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化yt-dlp的视频信息格式
        """
        try:
            # 提取关键信息
            video_id = ytdlp_info.get('id', '')
            title = ytdlp_info.get('title', '未知标题')
            uploader = ytdlp_info.get('uploader', '未知用户')
            duration = ytdlp_info.get('duration', 0)
            view_count = ytdlp_info.get('view_count', 0)
            like_count = ytdlp_info.get('like_count', 0)
            
            # 视频URL信息
            url = ytdlp_info.get('url', '')
            thumbnail = ytdlp_info.get('thumbnail', '')
            
            # 标准化格式
            normalized_info = {
                'aweme_id': video_id,
                'desc': title,
                'duration': duration,
                'create_time': ytdlp_info.get('timestamp', 0),
                'author': {
                    'nickname': uploader,
                    'unique_id': ytdlp_info.get('uploader_id', ''),
                    'uid': ytdlp_info.get('uploader_id', ''),
                    'avatar_url': ytdlp_info.get('uploader_url', ''),
                },
                'video': {
                    'play_url': url,
                    'play_url_no_watermark': url,  # yt-dlp通常提供无水印版本
                    'cover_url': thumbnail,
                    'width': ytdlp_info.get('width', 0),
                    'height': ytdlp_info.get('height', 0),
                    'duration': duration,
                },
                'statistics': {
                    'play_count': view_count,
                    'digg_count': like_count,
                    'comment_count': 0,
                    'share_count': 0,
                },
                'raw_data': ytdlp_info,
                'extraction_method': 'yt-dlp',
                'from_ytdlp': True
            }
            
            return normalized_info
            
        except Exception as e:
            print(f"❌ 标准化视频信息失败: {e}")
            return None
    
    def _find_downloaded_files(self, url: str) -> List[Dict[str, Any]]:
        """
        查找下载的文件
        """
        downloaded_files = []
        
        try:
            # 查找最近下载的文件
            for file_path in self.download_dir.iterdir():
                if file_path.is_file():
                    # 检查文件修改时间（最近1分钟内）
                    import time
                    if time.time() - file_path.stat().st_mtime < 60:
                        file_info = {
                            "path": str(file_path),
                            "size": file_path.stat().st_size,
                            "type": self._get_file_type(file_path),
                        }
                        downloaded_files.append(file_info)
            
            return downloaded_files
            
        except Exception as e:
            print(f"❌ 查找下载文件失败: {e}")
            return []
    
    def _get_file_type(self, file_path: Path) -> str:
        """
        根据文件扩展名确定文件类型
        """
        suffix = file_path.suffix.lower()
        
        if suffix in ['.mp4', '.avi', '.mkv', '.webm']:
            return 'video'
        elif suffix in ['.jpg', '.jpeg', '.png', '.webp']:
            return 'thumbnail'
        elif suffix in ['.json']:
            return 'metadata'
        elif suffix in ['.mp3', '.m4a', '.wav']:
            return 'audio'
        else:
            return 'unknown'
    
    def get_supported_sites(self) -> List[str]:
        """
        获取yt-dlp支持的网站列表
        """
        if not self.ytdlp_available:
            return []
        
        try:
            result = subprocess.run(['yt-dlp', '--list-extractors'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                sites = result.stdout.split('\n')
                return [site.strip() for site in sites if site.strip()]
            else:
                return []
        except Exception:
            return []
    
    def is_supported(self, url: str) -> bool:
        """
        检查URL是否被yt-dlp支持
        """
        if not self.ytdlp_available:
            return False
        
        try:
            # 检查是否包含抖音相关的域名
            if any(domain in url.lower() for domain in ['douyin.com', 'tiktok.com']):
                return True
            
            # 使用yt-dlp检查
            result = subprocess.run(['yt-dlp', '--simulate', '--quiet', url], 
                                  capture_output=True, text=True, timeout=15)
            return result.returncode == 0
            
        except Exception:
            return False