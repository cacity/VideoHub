#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频信息解析器
基于TikTokDownload项目的API分析技术
"""

import re
import json
import time
import random
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode, urlparse
from .utils import DouyinUtils
from .config import DouyinConfig
from .video_extractor import VideoExtractor
from .ytdlp_wrapper import YtDlpWrapper
from .selenium_extractor import SeleniumExtractor
from .dlpanda_extractor import DLPandaExtractor

class DouyinParser:
    """抖音视频解析器"""
    
    def __init__(self, config: Optional[DouyinConfig] = None):
        """
        初始化解析器
        :param config: 配置对象
        """
        self.config = config or DouyinConfig()
        self.session = requests.Session()
        self.session.headers.update(self.config.get_headers())
        
        # 设置代理
        proxies = self.config.get_proxies()
        if proxies:
            self.session.proxies.update(proxies)
        
        # 初始化高级提取器
        self.video_extractor = VideoExtractor()
        
        # 初始化yt-dlp包装器
        self.ytdlp_wrapper = YtDlpWrapper()
        
        # 初始化Selenium提取器
        self.selenium_extractor = SeleniumExtractor()
        
        # 初始化DLPanda提取器
        self.dlpanda_extractor = DLPandaExtractor()
    
    def parse_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        解析视频信息 - 优先使用DLPanda，备用Selenium
        :param url: 抖音视频链接
        :return: 视频信息字典
        """
        try:
            # 验证URL
            if not DouyinUtils.validate_url(url):
                raise ValueError("无效的抖音URL")
            
            # 方法1: 优先尝试DLPanda
            print("🐼 优先使用 DLPanda 提取器解析视频...")
            try:
                if self.dlpanda_extractor.is_available():
                    video_info = self.dlpanda_extractor.extract_video_info(url)
                    if video_info:
                        # 检查是否获取到完整的下载链接
                        play_url = video_info.get('video', {}).get('play_url')
                        if play_url and play_url.strip() and not video_info.get('_dlpanda_incomplete'):
                            print("✅ DLPanda 成功提取完整视频信息")
                            print(f"📋 准备返回视频信息: {video_info.get('desc', 'N/A')[:50]}...")
                            return video_info
                        else:
                            print("⚠️ DLPanda 提取的信息不完整，尝试其他方法")
                    else:
                        print("⚠️ DLPanda 未返回视频信息")
                else:
                    print("❌ DLPanda 服务不可用")
            except Exception as e:
                print(f"❌ DLPanda 提取失败: {e}")
            
            # 方法2: 备用Selenium提取器（不显示浏览器，减少被检测）
            print("🔧 使用 Selenium 提取器解析视频...")
            video_info = self.selenium_extractor.extract_video_info(url)
            if video_info:
                print("✅ Selenium 成功提取视频信息")
                print(f"📋 准备返回视频信息: {video_info.get('desc', 'N/A')[:50]}...")
                return video_info
            else:
                print("❌ Selenium 提取失败")
                return None
            
        except Exception as e:
            print(f"解析视频信息失败: {e}")
            return None
    
    def _try_ytdlp_extraction(self, url: str) -> Optional[Dict[str, Any]]:
        """
        尝试使用yt-dlp提取视频信息
        """
        try:
            if not self.ytdlp_wrapper.ytdlp_available:
                print("📦 yt-dlp 不可用，尝试安装...")
                if not self.ytdlp_wrapper.install_ytdlp():
                    print("❌ yt-dlp 安装失败")
                    return None
            
            # 检查URL是否被支持
            if not self.ytdlp_wrapper.is_supported(url):
                print("❌ yt-dlp 不支持此URL")
                return None
            
            # 获取视频信息
            video_info = self.ytdlp_wrapper.get_video_info(url)
            return video_info
            
        except Exception as e:
            print(f"❌ yt-dlp 提取失败: {e}")
            return None
    
    def _get_video_detail(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        获取视频详细信息
        :param video_id: 视频ID
        :return: 原始视频信息
        """
        try:
            # 构建API请求参数
            params = self._build_api_params(video_id)
            
            # 发送请求
            api_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
            print(f"发送API请求: {api_url}")
            print(f"请求参数: {params}")
            
            response = self.session.get(api_url, params=params, timeout=self.config.get("timeout"))
            
            print(f"响应状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            
            if response.status_code != 200:
                print(f"API请求失败: {response.status_code}")
                print(f"响应内容: {response.text[:500]}")
                return None
            
            # 检查响应内容
            response_text = response.text
            print(f"响应内容长度: {len(response_text)}")
            print(f"响应内容前500字符: {response_text[:500]}")
            
            if not response_text or response_text.strip() == "":
                print("API响应为空")
                return None
            
            # 解析响应
            try:
                data = response.json()
            except ValueError as json_error:
                print(f"JSON解析失败: {json_error}")
                print(f"响应不是有效的JSON格式")
                return None
            
            if data.get('status_code') != 0:
                print(f"API返回错误: {data.get('status_msg', '未知错误')}")
                return None
            
            return data.get('aweme_detail')
            
        except Exception as e:
            print(f"获取视频详细信息失败: {e}")
            return None
    
    def _get_video_detail_from_web(self, url: str) -> Optional[Dict[str, Any]]:
        """
        从网页获取视频详细信息（备用方案）
        :param url: 视频URL
        :return: 简化的视频信息
        """
        try:
            print("尝试从网页获取视频信息...")
            
            # 确保使用完整的网页URL
            if 'v.douyin.com' in url:
                # 先展开短链接
                expanded_url = DouyinUtils.expand_short_url(url)
                if expanded_url:
                    url = expanded_url
                else:
                    # 如果展开失败，尝试从短链接提取ID并构造URL
                    video_id = DouyinUtils.extract_video_id(url)
                    if video_id:
                        url = f"https://www.douyin.com/video/{video_id}"
                        print(f"从短链接构造完整URL: {url}")
            
            # 创建session with better configuration
            session = requests.Session()
            session.verify = False  # 忽略SSL验证
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
            }
            
            # 禁用SSL警告
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = session.get(url, headers=headers, timeout=self.config.get("timeout", 15))
            
            if response.status_code != 200:
                print(f"网页请求失败: {response.status_code}")
                return None
            
            # 解析网页内容获取基本信息
            html_content = response.text
            print(f"网页内容长度: {len(html_content)}")
            
            # 提取视频ID
            video_id = DouyinUtils.extract_video_id(url)
            
            # 多种方式提取标题
            title = "未知标题"
            author_name = "未知用户"
            
            # 方式1: 从title标签提取
            title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
            if title_match:
                raw_title = title_match.group(1).strip()
                # 清理标题
                title = raw_title.replace(' - 抖音', '').replace(' | 抖音', '').replace('抖音 - ', '').strip()
                if title and title != '抖音' and len(title) > 1:
                    print(f"从title标签提取标题: {title}")
            
            # 方式2: 从meta description提取
            if title == "未知标题" or not title:
                desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html_content, re.IGNORECASE)
                if desc_match:
                    title = desc_match.group(1).strip()
                    print(f"从meta description提取标题: {title}")
            
            # 方式3: 从JSON数据提取（如果存在）
            if title == "未知标题" or not title:
                # 查找内嵌的JSON数据
                json_matches = re.findall(r'window\._SSR_HYDRATED_DATA\s*=\s*({.*?});', html_content, re.DOTALL)
                if not json_matches:
                    json_matches = re.findall(r'window\.INITIAL_STATE\s*=\s*({.*?});', html_content, re.DOTALL)
                
                for json_match in json_matches:
                    try:
                        json_data = json.loads(json_match)
                        # 尝试从JSON中提取信息
                        if isinstance(json_data, dict):
                            # 递归查找视频信息
                            video_info_from_json = self._extract_info_from_json(json_data, video_id)
                            if video_info_from_json:
                                title = video_info_from_json.get('desc', title)
                                author_name = video_info_from_json.get('author', {}).get('nickname', author_name)
                                print(f"从JSON数据提取信息: 标题={title}, 作者={author_name}")
                                break
                    except json.JSONDecodeError:
                        continue
            
            # 最后清理标题
            if title and title != "未知标题":
                # 移除常见的无用字符和文本
                title = re.sub(r'[\\n\\r\\t]+', ' ', title)
                title = re.sub(r'\s+', ' ', title)
                title = title.strip()
                
                # 如果标题过短或是页面错误信息，重置为未知
                if len(title) < 2 or any(keyword in title.lower() for keyword in ['error', '404', '403', '验证', 'challenge']):
                    title = "未知标题"
            
            # 构造简化的视频信息
            video_info = {
                'aweme_id': video_id,
                'desc': title,
                'author': {
                    'nickname': author_name,
                    'unique_id': '',
                    'uid': ''
                },
                'video': {
                    'play_url': '',  # 无法从网页直接获取
                    'cover_url': '',
                    'duration': 0,
                    'ratio': '16:9'
                },
                'statistics': {
                    'digg_count': 0,
                    'comment_count': 0,
                    'share_count': 0,
                    'play_count': 0
                },
                'create_time': 0,
                'from_web_parse': True  # 标记来源
            }
            
            print(f"从网页解析获得信息: 标题={title}, 作者={author_name}")
            return video_info
            
        except Exception as e:
            print(f"从网页获取视频信息失败: {e}")
            return None
    
    def _extract_info_from_json(self, data: Any, target_video_id: str) -> Optional[Dict[str, Any]]:
        """
        从JSON数据中递归提取视频信息
        :param data: JSON数据
        :param target_video_id: 目标视频ID
        :return: 视频信息
        """
        try:
            if isinstance(data, dict):
                # 检查当前字典是否包含目标视频信息
                if data.get('aweme_id') == target_video_id or str(data.get('aweme_id', '')) == target_video_id:
                    return data
                
                # 递归搜索所有字典值
                for key, value in data.items():
                    result = self._extract_info_from_json(value, target_video_id)
                    if result:
                        return result
                        
            elif isinstance(data, list):
                # 递归搜索列表中的每个元素
                for item in data:
                    result = self._extract_info_from_json(item, target_video_id)
                    if result:
                        return result
                        
            return None
        except Exception:
            return None
    
    def _build_api_params(self, video_id: str) -> Dict[str, Any]:
        """
        构建API请求参数 - 参考开源项目改进
        :param video_id: 视频ID
        :return: 请求参数
        """
        # 生成必要的签名参数
        current_time = int(time.time())
        webid = self._generate_webid()
        ms_token = self._generate_ms_token()
        
        # 基础参数 - 参考TikTokDownload项目的参数设置
        params = {
            'aweme_id': video_id,
            'aid': '1128',
            'version_name': '31.2.0',  # 更新版本
            'device_platform': 'webapp',
            'os': 'windows',
            'browser_name': 'Chrome',
            'browser_version': '120.0.0.0',
            'channel': 'channel_pc_web',
            'device_type': 'pc',
            'pc_client_type': '1',
            'version_code': '170400',
            'app_name': 'douyin_web',
            'app_version': '1.0.0',
            'cookie_enabled': 'true',
            'screen_width': '1920',
            'screen_height': '1080',
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_online': 'true',
            'engine_name': 'Blink',
            'engine_version': '120.0.0.0',
            'os_version': '10',
            'cpu_core_num': '8',
            'device_memory': '8',
            'platform': 'PC',
            'downlink': '10',
            'effective_type': '4g',
            'round_trip_time': '150',
            # 关键签名参数
            'webid': webid,
            'msToken': ms_token,
            'verifyFp': self._generate_verify_fp(),
            'fp': self._generate_verify_fp(),
            'biz_trace_id': f"{current_time}{random.randint(10000, 99999)}",
            'X-Bogus': self._generate_x_bogus(),
            # 添加更多参数提高成功率
            'from_page': 'web_code_link',
            'loc_mode': 'web',
            'loc_time': str(current_time),
            'req_from': 'web_detail',
            'ts': str(current_time),
        }
        
        return params
    
    def _generate_webid(self) -> str:
        """生成webid - 参考开源项目改进"""
        # 更符合抖音格式的webid生成
        timestamp = int(time.time() * 1000)
        # 确保webid格式正确
        webid = f"{timestamp}{random.randint(100000, 999999)}"
        return webid[:19]  # 限制长度
    
    def _generate_ms_token(self) -> str:
        """生成msToken - 参考TikTokDownload项目改进"""
        # 更接近真实的msToken格式
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
        length = 107 + random.randint(0, 20)  # 随机长度
        return ''.join(random.choices(chars, k=length))
    
    def _generate_x_bogus(self) -> str:
        """生成X-Bogus参数 - 参考开源项目的更复杂实现"""
        # 基于时间戳和随机数生成更真实的X-Bogus
        timestamp = str(int(time.time()))
        random_part = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=32))
        
        # 构造X-Bogus格式 (这是简化版本，实际算法更复杂)
        x_bogus = f"DFSzswVLkmSLNS{random_part[:8]}{timestamp[-6:]}{random_part[8:16]}"
        return x_bogus[:40]
    
    def _generate_verify_fp(self) -> str:
        """生成verifyFp参数"""
        chars = 'verify_' + ''.join(random.choices('abcdef0123456789', k=8))
        chars += '_' + ''.join(random.choices('abcdef0123456789', k=8))
        chars += '_' + ''.join(random.choices('abcdef0123456789', k=8))
        return chars
    
    def _generate_ttwid(self) -> str:
        """生成ttwid参数"""
        # 类似Cookie中的ttwid格式
        part1 = '1%7C' + str(int(time.time()))
        part2 = '%7C' + str(random.randint(100000000, 999999999))
        return part1 + part2
    
    def _parse_video_detail(self, video_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析并标准化视频信息
        :param video_info: 原始视频信息
        :return: 标准化后的视频信息
        """
        try:
            # 检查是否来自网页解析
            from_web_parse = video_info.get('from_web_parse', False)
            
            # 基本信息
            aweme_id = video_info.get('aweme_id', '')
            desc = video_info.get('desc', '')
            create_time = video_info.get('create_time', 0)
            
            # 对于网页解析的数据，时长可能在video字段中
            if from_web_parse:
                duration = video_info.get('video', {}).get('duration', 0)
                if isinstance(duration, str):
                    try:
                        duration = int(duration)
                    except:
                        duration = 0
            else:
                duration = video_info.get('duration', 0) // 1000  # API数据转换为秒
            
            # 作者信息
            author_info = video_info.get('author', {})
            author = {
                'uid': author_info.get('uid', ''),
                'nickname': author_info.get('nickname', ''),
                'unique_id': author_info.get('unique_id', ''),
                'avatar_url': self._extract_avatar_url(author_info),
                'follower_count': author_info.get('follower_count', 0),
                'following_count': author_info.get('following_count', 0),
                'aweme_count': author_info.get('aweme_count', 0),
            }
            
            # 统计信息
            statistics = video_info.get('statistics', {})
            stats = {
                'digg_count': statistics.get('digg_count', 0),  # 点赞数
                'comment_count': statistics.get('comment_count', 0),  # 评论数
                'share_count': statistics.get('share_count', 0),  # 分享数
                'play_count': statistics.get('play_count', 0),  # 播放数
                'collect_count': statistics.get('collect_count', 0),  # 收藏数
            }
            
            # 视频信息
            video_data = video_info.get('video', {})
            video = {
                'play_url': self._extract_play_url(video_data),
                'cover_url': self._extract_cover_url(video_data),
                'width': video_data.get('width', 0),
                'height': video_data.get('height', 0),
                'format': video_data.get('format', 'mp4'),
                'size': video_data.get('data_size', 0),
            }
            
            # 音频信息
            music_info = video_info.get('music', {})
            music = {
                'id': music_info.get('id', ''),
                'title': music_info.get('title', ''),
                'author': music_info.get('author', ''),
                'play_url': self._extract_music_url(music_info),
                'duration': music_info.get('duration', 0) // 1000,
                'cover_url': music_info.get('cover_large', {}).get('url_list', [None])[0],
            }
            
            # 构建标准化信息
            parsed_info = {
                'aweme_id': aweme_id,
                'desc': desc,
                'create_time': create_time,
                'duration': duration,
                'author': author,
                'statistics': stats,
                'video': video,
                'music': music,
                'raw_data': video_info,  # 保留原始数据
            }
            
            return parsed_info
            
        except Exception as e:
            print(f"解析视频详细信息失败: {e}")
            return None
    
    def _extract_play_url(self, video_data: Dict[str, Any]) -> Optional[str]:
        """提取播放链接"""
        try:
            # 尝试多个可能的字段
            play_addr = video_data.get('play_addr', {})
            url_list = play_addr.get('url_list', [])
            
            if url_list:
                return url_list[0]
            
            # 备用字段
            bit_rate = video_data.get('bit_rate', [])
            if bit_rate:
                # 选择最高质量
                highest_quality = max(bit_rate, key=lambda x: x.get('bit_rate', 0))
                play_addr = highest_quality.get('play_addr', {})
                url_list = play_addr.get('url_list', [])
                if url_list:
                    return url_list[0]
            
            return None
        except Exception:
            return None
    
    def _extract_cover_url(self, video_data: Dict[str, Any]) -> Optional[str]:
        """提取封面链接"""
        try:
            cover = video_data.get('origin_cover', {}) or video_data.get('cover', {})
            url_list = cover.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None
    
    def _extract_avatar_url(self, author_info: Dict[str, Any]) -> Optional[str]:
        """提取头像链接"""
        try:
            avatar = author_info.get('avatar_larger', {}) or author_info.get('avatar_medium', {})
            url_list = avatar.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None
    
    def _extract_music_url(self, music_info: Dict[str, Any]) -> Optional[str]:
        """提取音乐链接"""
        try:
            play_url = music_info.get('play_url', {})
            url_list = play_url.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None
    
    def parse_user_info(self, user_url: str) -> Optional[Dict[str, Any]]:
        """
        解析用户信息
        :param user_url: 用户主页链接
        :return: 用户信息
        """
        try:
            # 提取用户ID
            user_id = self._extract_user_id(user_url)
            if not user_id:
                return None
            
            # 获取用户详细信息
            user_info = self._get_user_detail(user_id)
            return user_info
            
        except Exception as e:
            print(f"解析用户信息失败: {e}")
            return None
    
    def _extract_user_id(self, user_url: str) -> Optional[str]:
        """从用户链接中提取用户ID"""
        try:
            # 匹配用户ID的正则表达式
            patterns = [
                r'user/([^/?]+)',
                r'@([^/?]+)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, user_url)
                if match:
                    return match.group(1)
            
            return None
        except Exception:
            return None
    
    def _get_user_detail(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户详细信息"""
        # 这里可以实现用户信息获取的API调用
        # 由于复杂性，暂时返回None
        return None
    
    def _try_selenium_extraction(self, url: str) -> Optional[Dict[str, Any]]:
        """
        尝试使用Selenium提取视频信息
        :param url: 视频URL
        :return: 视频信息字典
        """
        try:
            if not self.selenium_extractor.is_available():
                print("❌ Selenium 不可用，尝试安装...")
                if not self.selenium_extractor.install_selenium():
                    print("❌ Selenium 安装失败")
                    return None
            
            # 使用Selenium提取
            video_info = self.selenium_extractor.extract_video_info(url)
            
            if video_info:
                print("✅ Selenium 成功提取视频信息")
                return video_info
            else:
                print("❌ Selenium 提取失败")
                return None
                
        except Exception as e:
            print(f"❌ Selenium 提取异常: {e}")
            return None

    def _try_windows_selenium_extraction(self, url: str) -> Optional[Dict[str, Any]]:
        """
        尝试使用Windows Selenium提取视频信息
        :param url: 视频URL
        :return: 视频信息字典
        """
        try:
            import platform
            if platform.system() != "Windows":
                print("❌ 非Windows系统，跳过Windows Selenium方案")
                return None
            
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            import os
            import time
            import re
            
            # 检查ChromeDriver
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            chromedriver_path = os.path.join(current_dir, "chromedriver.exe")
            
            if not os.path.exists(chromedriver_path):
                print(f"❌ ChromeDriver未找到: {chromedriver_path}")
                return None
            
            # 配置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-images')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # 启动浏览器
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)
            
            try:
                # 访问页面
                driver.get(url)
                time.sleep(8)
                
                current_url = driver.current_url
                title = driver.title
                page_source = driver.page_source
                
                # 提取视频ID
                video_id_match = re.search(r'/video/(\d+)', current_url)
                video_id = video_id_match.group(1) if video_id_match else "unknown"
                
                # 获取视频URL
                video_urls = driver.execute_script("""
                    var videos = document.querySelectorAll('video');
                    var urls = [];
                    for (var i = 0; i < videos.length; i++) {
                        if (videos[i].src) {
                            urls.push(videos[i].src);
                        }
                        if (videos[i].currentSrc) {
                            urls.push(videos[i].currentSrc);
                        }
                    }
                    return urls;
                """)
                
                video_url = None
                if video_urls:
                    for url_candidate in video_urls:
                        if url_candidate and 'douyinvod.com' in url_candidate:
                            video_url = url_candidate
                            break
                
                if not video_url:
                    print("❌ 未找到有效视频URL")
                    return None
                
                # 构建视频信息
                video_info = {
                    'aweme_id': video_id,
                    'desc': title.replace(' - 抖音', '').strip() if title else '未知标题',
                    'duration': 0,
                    'create_time': int(time.time()),
                    'author': {
                        'uid': '',
                        'nickname': '未知用户',
                        'unique_id': '',
                        'avatar_url': '',
                    },
                    'video': {
                        'play_url': video_url,
                        'play_url_no_watermark': video_url,
                        'cover_url': '',
                        'width': 0,
                        'height': 0,
                        'duration': 0,
                    },
                    'statistics': {
                        'digg_count': 0,
                        'comment_count': 0,
                        'share_count': 0,
                        'play_count': 0,
                    },
                    'music': {
                        'id': '',
                        'title': '',
                        'author': '',
                        'play_url': '',
                    },
                    'extraction_method': 'windows_selenium',
                    'from_selenium': True
                }
                
                print(f"✅ Windows Selenium 成功提取: {video_url[:80]}...")
                return video_info
                
            finally:
                driver.quit()
                
        except Exception as e:
            print(f"❌ Windows Selenium 提取异常: {e}")
            return None