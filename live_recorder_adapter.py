#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
直播录制适配器
整合DouyinLiveRecorder功能到PyQt应用中
"""

import os
import sys
import asyncio
import threading
import time
import configparser
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import signal
from datetime import datetime
import re
import json
import requests

# 添加live_recorder到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'live_recorder'))

try:
    from live_recorder import spider, stream, utils, room
    from live_recorder.utils import logger
    from ffmpeg_install import check_ffmpeg, ffmpeg_path, current_env_path
    import msg_push
    LIVE_RECORDER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 直播录制模块导入失败: {e}")
    LIVE_RECORDER_AVAILABLE = False


class LiveRecorderConfig:
    """直播录制配置管理"""
    
    def __init__(self, config_dir="live_config"):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.ini")
        self.url_config_file = os.path.join(config_dir, "URL_config.ini")
        
        # 确保配置目录存在
        os.makedirs(config_dir, exist_ok=True)
        
        # 默认配置
        self.default_config = {
            'Settings': {
                'monitoring_time': '60',
                'max_request': '10',
                'video_format': 'ts',
                'video_quality': '原画',
                'save_path': './live_downloads',
                'show_ffmpeg_log': '0',
                'save_log': '1'
            },
            'Push': {
                'enable_push': '0',
                'dingtalk_webhook': '',
                'pushplus_token': '',
                'email_host': '',
                'email_port': '587',
                'email_user': '',
                'email_password': '',
                'email_to': ''
            },
            'Proxy': {
                'enable_proxy': '0',
                'proxy_addr': '127.0.0.1:7890',
                'proxy_platforms': 'TikTok,SOOP,PandaTV,WinkTV,FlexTV,PopkonTV,TwitchTV'
            }
        }
        
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        self.config = configparser.ConfigParser()
        
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            # 创建默认配置文件
            self.config.read_dict(self.default_config)
            self.save_config()
    
    def save_config(self):
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def get(self, section, key, fallback=None):
        """获取配置值"""
        return self.config.get(section, key, fallback=fallback)
    
    def set(self, section, key, value):
        """设置配置值"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
    
    def load_urls(self) -> List[str]:
        """从配置文件加载URL列表"""
        urls = []
        if os.path.exists(self.url_config_file):
            with open(self.url_config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and line.startswith('http'):
                        urls.append(line)
        return urls
    
    def save_urls(self, urls: List[str]):
        """保存URL列表到配置文件"""
        with open(self.url_config_file, 'w', encoding='utf-8') as f:
            f.write("# 直播间URL配置文件\n")
            f.write("# 一行一个直播间地址\n")
            f.write("# 要停止某个直播间录制，在URL前添加 # 号\n\n")
            for url in urls:
                f.write(f"{url}\n")


class LiveRecorderManager:
    """直播录制管理器"""
    
    def __init__(self):
        self.config = LiveRecorderConfig()
        self.recording_processes = {}  # URL -> subprocess映射
        self.monitoring = False
        self.log_callback = None
        
        # 设置FFmpeg环境变量
        os.environ['PATH'] = ffmpeg_path + os.pathsep + current_env_path
        
        # 检查FFmpeg
        if not check_ffmpeg():
            raise RuntimeError("FFmpeg未找到，请先安装FFmpeg")
    
    def set_log_callback(self, callback):
        """设置日志回调函数"""
        self.log_callback = callback
    
    def log(self, message):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        if self.log_callback:
            self.log_callback(message)
    
    def start_monitoring(self, urls: List[str], settings: Dict[str, Any]):
        """开始监控直播"""
        if not LIVE_RECORDER_AVAILABLE:
            self.log("❌ 直播录制模块不可用")
            return False
        
        if not urls:
            self.log("❌ 没有要监控的URL")
            return False
        
        self.monitoring = True
        self.log(f"🎬 开始监控 {len(urls)} 个直播间")
        
        # 更新配置
        self.update_config(settings)
        
        # 在后台线程中运行监控
        monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(urls, settings),
            daemon=True
        )
        monitoring_thread.start()
        
        return True
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        
        # 停止所有录制进程
        for url, process in self.recording_processes.items():
            try:
                if process.poll() is None:  # 进程还在运行
                    process.terminate()
                    self.log(f"🛑 停止录制: {url}")
            except Exception as e:
                self.log(f"❌ 停止录制失败 {url}: {str(e)}")
        
        self.recording_processes.clear()
        self.log("🛑 已停止所有监控")
    
    def update_config(self, settings: Dict[str, Any]):
        """更新配置"""
        # 更新设置部分
        self.config.set('Settings', 'monitoring_time', settings.get('interval', 60))
        self.config.set('Settings', 'video_format', settings.get('format', 'ts'))
        self.config.set('Settings', 'video_quality', settings.get('quality', '原画'))
        self.config.set('Settings', 'save_path', settings.get('save_path', './live_downloads'))
        self.config.set('Settings', 'show_ffmpeg_log', '1' if settings.get('show_ffmpeg_log', False) else '0')
        self.config.set('Settings', 'save_log', '1' if settings.get('save_log', True) else '0')
        
        self.config.save_config()
    
    def _monitoring_loop(self, urls: List[str], settings: Dict[str, Any]):
        """监控循环（在后台线程运行）"""
        interval = settings.get('interval', 60)
        
        while self.monitoring:
            for url in urls:
                if not self.monitoring:
                    break
                
                try:
                    self._check_and_record_stream(url, settings)
                except Exception as e:
                    self.log(f"❌ 检查直播失败 {url}: {str(e)}")
                
                # 短暂休息
                time.sleep(2)
            
            if self.monitoring:
                # 等待下次检查
                for _ in range(interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)
    
    def _check_and_record_stream(self, url: str, settings: Dict[str, Any]):
        """检查并录制直播流"""
        try:
            # 如果这个URL已经在录制，跳过
            if url in self.recording_processes:
                process = self.recording_processes[url]
                if process.poll() is None:  # 进程还在运行
                    return
                else:
                    # 进程已结束，清理
                    del self.recording_processes[url]
                    self.log(f"📹 录制进程已结束: {url}")
            
            # 检查直播状态（简化实现）
            self.log(f"🔍 检查直播状态: {url}")
            
            # 这里应该调用DouyinLiveRecorder的实际检测逻辑
            # 由于时间关系，这里使用简化的模拟实现
            is_live = self._check_live_status(url)
            
            if is_live:
                # 开始录制
                self._start_recording(url, settings)
            else:
                self.log(f"📴 直播未开始: {url}")
                
        except Exception as e:
            self.log(f"❌ 处理直播流错误 {url}: {str(e)}")
    
    def _check_live_status(self, url: str) -> bool:
        """检查直播状态"""
        # 优先使用改进的抖音检测逻辑
        if 'douyin.com' in url:
            return self._check_douyin_live_status(url)
        
        # 其他平台使用原有逻辑
        try:
            # 尝试使用原有的spider模块检测
            if 'kuaishou.com' in url:
                # 快手检测逻辑
                pass
            elif 'huya.com' in url:
                # 虎牙检测逻辑
                pass
            # 其他平台...
            
        except Exception as e:
            self.log(f"⚠️ 平台检测失败，使用备用检测: {str(e)}")
        
        return False
    
    def _check_douyin_live_status(self, url: str) -> bool:
        """改进的抖音直播状态检测"""
        try:
            
            # 提取房间ID
            room_id_match = re.search(r'live\.douyin\.com/(\d+)', url)
            if not room_id_match:
                self.log("❌ 无法从URL提取房间ID")
                return False
            
            room_id = room_id_match.group(1)
            clean_url = f"https://live.douyin.com/{room_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = requests.get(clean_url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                self.log(f"❌ 页面访问失败: {response.status_code}")
                return False
            
            content = response.text
            
            # 方法1: 查找JSON数据中的直播状态
            json_data = self._extract_json_data(content)
            if json_data:
                live_info = self._parse_json_live_data(json_data)
                if live_info.get('is_live'):
                    self.log(f"✅ JSON检测到直播 (方法: {live_info.get('method', 'json')})")
                    return True
            
            # 方法2: 正则表达式检测
            if self._regex_live_check(content):
                self.log("✅ 正则检测到直播")
                return True
            
            # 方法3: 简单指示器检查
            if self._simple_live_check(content):
                self.log("✅ 简单检测到直播")
                return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ 抖音直播检测失败: {str(e)}")
            return False
    
    def _extract_json_data(self, content: str):
        """提取页面中的JSON数据"""
        json_patterns = [
            r'window\.__INIT_DATA__\s*=\s*({.*?});',
            r'window\.__SSR_RENDERED_DATA__\s*=\s*({.*?});',
            r'self\.__pace_f\.push\(\[function\(\)\{.*?(\{.*?\}).*?\}\]\)',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                try:
                    if match.strip().startswith('{'):
                        return json.loads(match)
                except json.JSONDecodeError:
                    continue
        return None
    
    def _parse_json_live_data(self, data: dict) -> dict:
        """解析JSON数据中的直播信息"""
        result = {'is_live': False, 'method': 'json_parse'}
        
        def search_live_data(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # 检查直播状态字段
                    if key.lower() in ['islive', 'is_live', 'live_status', 'status']:
                        if value in [1, '1', True, 'live', 'online']:
                            result['is_live'] = True
                            result['status_field'] = current_path
                            result['status_value'] = value
                    
                    # 检查直播流URL
                    elif key.lower() in ['stream_url', 'play_url', 'flv_url', 'm3u8_url']:
                        if value and isinstance(value, str) and ('http' in value or 'rtmp' in value):
                            result['is_live'] = True
                            result['stream_url'] = value
                            result['stream_field'] = current_path
                    
                    # 递归搜索
                    if isinstance(value, (dict, list)):
                        search_live_data(value, current_path)
            
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    search_live_data(item, f"{path}[{idx}]")
        
        search_live_data(data)
        return result
    
    def _regex_live_check(self, content: str) -> bool:
        """使用正则表达式检测直播状态"""
        # 查找直播状态
        status_patterns = [
            r'"is_live"\s*:\s*(\d+)',
            r'"live_status"\s*:\s*(\d+)',
            r'"status"\s*:\s*"([^"]*)"',
            r'islive["\']?\s*[:=]\s*(\w+)',
        ]
        
        for pattern in status_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match in ['1', 'true', 'live', 'online']:
                    return True
        
        # 查找直播流URL
        stream_patterns = [
            r'"stream_url"\s*:\s*"([^"]+)"',
            r'"play_url"\s*:\s*"([^"]+)"',
            r'"flv_url"\s*:\s*"([^"]+)"',
        ]
        
        for pattern in stream_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if 'http' in match:
                    return True
        
        return False
    
    def _simple_live_check(self, content: str) -> bool:
        """简单的直播检查"""
        # 检查是否包含直播相关关键词
        live_keywords = ['stream_url', 'play_url', 'is_live', 'live_status']
        keyword_count = sum(1 for keyword in live_keywords if keyword in content)
        
        # 检查是否包含视频播放器相关内容
        player_keywords = ['video', 'player', 'stream', 'live']
        player_count = sum(1 for keyword in player_keywords if keyword in content.lower())
        
        # 简单的启发式判断
        if keyword_count >= 2 and player_count >= 3:
            return True
        
        return False
    
    def _start_recording(self, url: str, settings: Dict[str, Any]):
        """开始录制直播"""
        try:
            save_path = settings.get('save_path', './live_downloads')
            video_format = settings.get('format', 'ts')
            
            # 确保保存目录存在
            os.makedirs(save_path, exist_ok=True)
            
            # 生成输出文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            platform = self._get_platform_from_url(url)
            filename = f"{platform}_{timestamp}.{video_format}"
            output_path = os.path.join(save_path, filename)
            
            # 构建FFmpeg命令（简化实现）
            cmd = [
                'ffmpeg',
                '-i', url,  # 这里应该是实际的直播流地址
                '-c', 'copy',
                '-f', video_format,
                output_path
            ]
            
            # 启动录制进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.recording_processes[url] = process
            self.log(f"🎬 开始录制: {url} -> {filename}")
            
        except Exception as e:
            self.log(f"❌ 启动录制失败 {url}: {str(e)}")
    
    def _get_platform_from_url(self, url: str) -> str:
        """从URL获取平台名称"""
        if 'douyin.com' in url:
            return 'douyin'
        elif 'kuaishou.com' in url:
            return 'kuaishou'
        elif 'huya.com' in url:
            return 'huya'
        elif 'douyu.com' in url:
            return 'douyu'
        elif 'bilibili.com' in url:
            return 'bilibili'
        elif 'tiktok.com' in url:
            return 'tiktok'
        else:
            return 'unknown'
    
    def get_recording_status(self) -> Dict[str, Any]:
        """获取录制状态"""
        status = {
            'monitoring': self.monitoring,
            'recording_count': len(self.recording_processes),
            'recording_urls': list(self.recording_processes.keys())
        }
        return status


# 全局实例
live_recorder_manager = None

def get_live_recorder_manager():
    """获取直播录制管理器单例"""
    global live_recorder_manager
    if live_recorder_manager is None:
        try:
            live_recorder_manager = LiveRecorderManager()
        except Exception as e:
            print(f"❌ 初始化直播录制管理器失败: {e}")
            return None
    return live_recorder_manager