#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基于新 douyin.py 的抖音视频提取器
使用直接HTTP请求获取抖音视频信息和下载链接
"""

import os
import json
import sys
from typing import Dict, Any, Optional
from pathlib import Path

# 导入新的 douyin.py 模块（从项目根目录）
_root_path = Path(__file__).parent.parent
if str(_root_path) not in sys.path:
    sys.path.insert(0, str(_root_path))

# 使用 importlib 避免循环导入
import importlib.util
spec = importlib.util.spec_from_file_location("douyin_core", _root_path / "douyin.py")
douyin_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(douyin_core)

douyin_get_video_info = douyin_core.get_video_info
DouyinVideoInfo = douyin_core.DouyinVideoInfo

class DouyinVdExtractor:
    """使用新 douyin.py 的抖音视频提取器"""
    
    def __init__(self, port: str = "8080"):
        self.port = port
        
    def start_server(self) -> bool:
        """启动服务器（新版本不需要服务器）"""
        return True
    
    def stop_server(self):
        """停止服务器（新版本不需要服务器）"""
        pass
    
    def is_server_running(self) -> bool:
        """检查服务器是否运行中（新版本始终返回True）"""
        return True
    
    def get_video_url(self, douyin_url: str) -> Optional[str]:
        """
        获取无水印视频下载链接
        :param douyin_url: 抖音分享链接
        :return: 无水印视频下载链接
        """
        try:
            video_info = douyin_get_video_info(douyin_url)
            if video_info and video_info.video_url:
                print(f"获取到视频下载链接: {video_info.video_url[:50]}...")
                return video_info.video_url
            else:
                print("获取视频链接失败")
                return None
                
        except Exception as e:
            print(f"获取视频链接异常: {e}")
            return None
    
    def get_video_info(self, douyin_url: str) -> Optional[Dict[str, Any]]:
        """
        获取详细视频信息
        :param douyin_url: 抖音分享链接
        :return: 视频详细信息
        """
        try:
            video_info = douyin_get_video_info(douyin_url)
            if video_info:
                print("获取到视频详细信息")
                return self._normalize_video_info(video_info)
            else:
                print("获取视频信息失败")
                return None
                
        except Exception as e:
            print(f"获取视频信息异常: {e}")
            return None
    
    def _normalize_video_info(self, video_info: DouyinVideoInfo) -> Dict[str, Any]:
        """
        标准化视频信息格式，使其与现有系统兼容
        :param video_info: DouyinVideoInfo 对象
        :return: 标准化后的视频信息
        """
        try:
            info_dict = video_info.to_dict()
            
            # 标准化格式
            normalized_info = {
                "aweme_id": info_dict.get("aweme_id", "unknown"),
                "desc": info_dict.get("desc", "未知标题"),
                "create_time": info_dict.get("create_time", ""),
                "author": {
                    "uid": "unknown",
                    "short_id": "unknown",
                    "nickname": info_dict.get("nickname", "未知用户"),
                    "signature": info_dict.get("signature", ""),
                    "avatar_thumb": ""
                },
                "music": {
                    "id": "",
                    "title": "",
                    "author": "",
                    "play_url": ""
                },
                "video": {
                    "play_url": info_dict.get("video_url", ""),
                    "play_url_no_watermark": info_dict.get("video_url", ""),
                    "cover_url": "",
                    "duration": 0,
                    "width": 0,
                    "height": 0
                },
                "statistics": {
                    "digg_count": info_dict.get("digg_count", 0),
                    "comment_count": info_dict.get("comment_count", 0),
                    "share_count": info_dict.get("share_count", 0),
                    "collect_count": info_dict.get("collect_count", 0)
                },
                "from_douyinpy": True,
                "raw_data": info_dict
            }
            
            # 处理图片类型
            if info_dict.get("type") == "img" and info_dict.get("image_url_list"):
                normalized_info["images"] = info_dict["image_url_list"]
                normalized_info["type"] = "image"
            
            return normalized_info
            
        except Exception as e:
            print(f"标准化视频信息失败: {e}")
            return video_info.to_dict() if hasattr(video_info, 'to_dict') else {}
    
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
            import requests
            print(f"开始下载视频: {filename}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36",
                "Referer": "https://www.douyin.com/"
            }
            response = requests.get(video_url, headers=headers, stream=True, timeout=60)
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
            
            print(f"\n视频下载完成: {filepath}")
            
            # 保存元数据
            metadata_path = os.path.join(download_dir, f"{base_filename}_metadata.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, ensure_ascii=False, indent=2)
            
            print(f"元数据保存完成: {metadata_path}")
            
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
            print(f"下载视频失败: {e}")
            return {"success": False, "error": str(e)}
    
    def __del__(self):
        """析构函数（新版本不需要清理）"""
        pass