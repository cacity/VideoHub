#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
高级视频提取器
参考先进项目实现无水印视频下载
"""

import re
import json
import time
import random
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, parse_qs
from .advanced_signer import AdvancedSigner
from .utils import DouyinUtils

class VideoExtractor:
    """高级视频提取器"""
    
    def __init__(self):
        """初始化提取器"""
        self.signer = AdvancedSigner()
        self.session = requests.Session()
        # 禁用SSL验证
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def extract_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        提取视频信息
        :param url: 抖音视频链接
        :return: 视频信息
        """
        try:
            print("🔍 使用高级提取器获取视频信息...")
            
            # 提取视频ID
            video_id = DouyinUtils.extract_video_id(url)
            if not video_id:
                print("❌ 无法提取视频ID")
                return None
            
            print(f"📹 视频ID: {video_id}")
            
            # 尝试多种方法获取视频信息
            methods = [
                self._method_api_with_advanced_signature,
                self._method_web_page_analysis,
                self._method_mobile_api,
            ]
            
            for i, method in enumerate(methods, 1):
                try:
                    print(f"🔄 尝试方法 {i}...")
                    result = method(video_id, url)
                    if result:
                        print(f"✅ 方法 {i} 成功获取视频信息")
                        return result
                except Exception as e:
                    print(f"❌ 方法 {i} 失败: {e}")
                    continue
            
            print("❌ 所有方法都失败了")
            return None
            
        except Exception as e:
            print(f"❌ 视频信息提取失败: {e}")
            return None
    
    def _method_api_with_advanced_signature(self, video_id: str, url: str) -> Optional[Dict[str, Any]]:
        """
        方法1: 使用高级签名的API调用
        """
        try:
            # 生成高级参数
            params = self.signer.generate_advanced_params(video_id)
            headers = self.signer.generate_headers()
            
            # API调用
            api_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
            
            print(f"🌐 发送高级API请求...")
            print(f"   X-Bogus: {params.get('X-Bogus', '')[:20]}...")
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=15)
            
            print(f"📊 响应状态: {response.status_code}")
            
            if response.status_code == 200 and response.text.strip():
                data = response.json()
                if data.get('status_code') == 0:
                    aweme_detail = data.get('aweme_detail')
                    if aweme_detail:
                        return self._parse_aweme_detail(aweme_detail)
            
            return None
            
        except Exception as e:
            print(f"❌ 高级API方法失败: {e}")
            return None
    
    def _method_web_page_analysis(self, video_id: str, url: str) -> Optional[Dict[str, Any]]:
        """
        方法2: 高级网页分析
        """
        try:
            # 确保使用完整URL
            if 'v.douyin.com' in url:
                expanded_url = DouyinUtils.expand_short_url(url)
                if expanded_url:
                    url = expanded_url
            
            headers = self.signer.generate_headers()
            headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
            })
            
            print(f"🌐 分析网页: {url}")
            response = self.session.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                return None
            
            html_content = response.text
            
            # 高级网页解析
            video_info = self._advanced_html_parse(html_content, video_id)
            if video_info:
                return video_info
            
            return None
            
        except Exception as e:
            print(f"❌ 网页分析方法失败: {e}")
            return None
    
    def _method_mobile_api(self, video_id: str, url: str) -> Optional[Dict[str, Any]]:
        """
        方法3: 移动端API
        """
        try:
            mobile_headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://www.douyin.com/',
                'Origin': 'https://www.douyin.com',
            }
            
            # 移动端API参数
            mobile_params = {
                'aweme_id': video_id,
                'aid': '1128',
                'version_name': '23.5.0',
                'device_platform': 'webapp',
                'device_type': 'mobile',
                'os': 'ios',
                'browser_name': 'Safari',
                'channel': 'channel_mobile_web',
            }
            
            api_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
            response = self.session.get(api_url, params=mobile_params, headers=mobile_headers, timeout=10)
            
            if response.status_code == 200 and response.text.strip():
                data = response.json()
                if data.get('status_code') == 0:
                    aweme_detail = data.get('aweme_detail')
                    if aweme_detail:
                        return self._parse_aweme_detail(aweme_detail)
            
            return None
            
        except Exception as e:
            print(f"❌ 移动端API方法失败: {e}")
            return None
    
    def _advanced_html_parse(self, html_content: str, video_id: str) -> Optional[Dict[str, Any]]:
        """
        高级HTML解析
        """
        try:
            # 方式1: 查找RENDER_DATA
            render_data_match = re.search(r'window\._RENDER_DATA\s*=\s*({.*?});', html_content, re.DOTALL)
            if render_data_match:
                try:
                    render_data = json.loads(render_data_match.group(1))
                    video_info = self._extract_from_render_data(render_data, video_id)
                    if video_info:
                        return video_info
                except json.JSONDecodeError:
                    pass
            
            # 方式2: 查找SSR_HYDRATED_DATA
            ssr_data_match = re.search(r'window\._SSR_HYDRATED_DATA\s*=\s*({.*?});', html_content, re.DOTALL)
            if ssr_data_match:
                try:
                    ssr_data = json.loads(ssr_data_match.group(1))
                    video_info = self._extract_from_ssr_data(ssr_data, video_id)
                    if video_info:
                        return video_info
                except json.JSONDecodeError:
                    pass
            
            # 方式3: 查找INITIAL_STATE
            initial_state_match = re.search(r'window\.INITIAL_STATE\s*=\s*({.*?});', html_content, re.DOTALL)
            if initial_state_match:
                try:
                    initial_state = json.loads(initial_state_match.group(1))
                    video_info = self._extract_from_initial_state(initial_state, video_id)
                    if video_info:
                        return video_info
                except json.JSONDecodeError:
                    pass
            
            # 方式4: 基础信息提取
            return self._extract_basic_info(html_content, video_id)
            
        except Exception as e:
            print(f"❌ HTML解析失败: {e}")
            return None
    
    def _extract_from_render_data(self, data: Dict[str, Any], video_id: str) -> Optional[Dict[str, Any]]:
        """从RENDER_DATA提取视频信息"""
        try:
            # 递归搜索视频信息
            def find_aweme(obj, target_id):
                if isinstance(obj, dict):
                    if obj.get('aweme_id') == target_id or str(obj.get('aweme_id', '')) == target_id:
                        return obj
                    for value in obj.values():
                        result = find_aweme(value, target_id)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_aweme(item, target_id)
                        if result:
                            return result
                return None
            
            aweme_detail = find_aweme(data, video_id)
            if aweme_detail:
                return self._parse_aweme_detail(aweme_detail)
            
            return None
        except Exception:
            return None
    
    def _extract_from_ssr_data(self, data: Dict[str, Any], video_id: str) -> Optional[Dict[str, Any]]:
        """从SSR_HYDRATED_DATA提取视频信息"""
        return self._extract_from_render_data(data, video_id)
    
    def _extract_from_initial_state(self, data: Dict[str, Any], video_id: str) -> Optional[Dict[str, Any]]:
        """从INITIAL_STATE提取视频信息"""
        return self._extract_from_render_data(data, video_id)
    
    def _extract_basic_info(self, html_content: str, video_id: str) -> Optional[Dict[str, Any]]:
        """提取基础信息"""
        try:
            # 提取标题
            title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
            title = title_match.group(1) if title_match else "未知标题"
            title = title.replace(' - 抖音', '').replace(' | 抖音', '').strip()
            
            # 提取描述
            desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html_content, re.IGNORECASE)
            if desc_match:
                desc = desc_match.group(1).strip()
                if desc and len(desc) > len(title):
                    title = desc
            
            return {
                'aweme_id': video_id,
                'desc': title,
                'author': {
                    'nickname': '未知用户',
                    'unique_id': '',
                    'uid': ''
                },
                'video': {
                    'play_url': None,
                    'play_url_no_watermark': None,
                    'cover_url': None,
                    'duration': 0,
                    'width': 0,
                    'height': 0,
                },
                'music': {
                    'play_url': None,
                    'title': '',
                    'author': '',
                },
                'statistics': {
                    'digg_count': 0,
                    'comment_count': 0,
                    'share_count': 0,
                    'play_count': 0,
                },
                'create_time': 0,
                'from_web_parse': True,
                'extraction_method': 'basic_html_parse'
            }
        except Exception:
            return None
    
    def _parse_aweme_detail(self, aweme_detail: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析aweme详情，重点提取无水印视频链接
        """
        try:
            # 基本信息
            aweme_id = aweme_detail.get('aweme_id', '')
            desc = aweme_detail.get('desc', '')
            create_time = aweme_detail.get('create_time', 0)
            
            # 作者信息
            author_info = aweme_detail.get('author', {})
            author = {
                'uid': author_info.get('uid', ''),
                'nickname': author_info.get('nickname', ''),
                'unique_id': author_info.get('unique_id', ''),
                'avatar_url': self._extract_avatar_url(author_info),
            }
            
            # 视频信息 - 重点提取无水印链接
            video_data = aweme_detail.get('video', {})
            video = self._extract_video_urls(video_data)
            
            # 音频信息
            music_info = aweme_detail.get('music', {})
            music = {
                'play_url': self._extract_music_url(music_info),
                'title': music_info.get('title', ''),
                'author': music_info.get('author', ''),
            }
            
            # 统计信息
            statistics = aweme_detail.get('statistics', {})
            stats = {
                'digg_count': statistics.get('digg_count', 0),
                'comment_count': statistics.get('comment_count', 0),
                'share_count': statistics.get('share_count', 0),
                'play_count': statistics.get('play_count', 0),
            }
            
            return {
                'aweme_id': aweme_id,
                'desc': desc,
                'create_time': create_time,
                'duration': video.get('duration', 0),
                'author': author,
                'video': video,
                'music': music,
                'statistics': stats,
                'raw_data': aweme_detail,
                'extraction_method': 'api_parse'
            }
            
        except Exception as e:
            print(f"❌ 解析aweme详情失败: {e}")
            return None
    
    def _extract_video_urls(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取视频URL，包括无水印版本
        """
        try:
            video_info = {
                'play_url': None,
                'play_url_no_watermark': None,
                'cover_url': None,
                'duration': 0,
                'width': 0,
                'height': 0,
            }
            
            # 提取时长
            duration = video_data.get('duration', 0)
            if isinstance(duration, str):
                duration = int(duration) if duration.isdigit() else 0
            video_info['duration'] = duration // 1000 if duration > 1000 else duration
            
            # 提取尺寸
            video_info['width'] = video_data.get('width', 0)
            video_info['height'] = video_data.get('height', 0)
            
            # 提取封面
            video_info['cover_url'] = self._extract_cover_url(video_data)
            
            # 提取播放链接 - 优先无水印版本
            play_addr = video_data.get('play_addr', {})
            url_list = play_addr.get('url_list', [])
            
            if url_list:
                # 选择最佳质量的链接
                best_url = url_list[0]
                video_info['play_url'] = best_url
                
                # 尝试转换为无水印链接
                no_watermark_url = self._convert_to_no_watermark(best_url)
                if no_watermark_url:
                    video_info['play_url_no_watermark'] = no_watermark_url
                    print("✅ 成功获取无水印视频链接")
                else:
                    print("⚠️ 无法生成无水印链接，使用原始链接")
            
            # 备用方法：从bit_rate中提取
            if not video_info['play_url']:
                bit_rate = video_data.get('bit_rate', [])
                if bit_rate:
                    # 选择最高质量
                    highest_quality = max(bit_rate, key=lambda x: x.get('bit_rate', 0))
                    play_addr = highest_quality.get('play_addr', {})
                    url_list = play_addr.get('url_list', [])
                    if url_list:
                        video_info['play_url'] = url_list[0]
                        video_info['play_url_no_watermark'] = self._convert_to_no_watermark(url_list[0])
            
            return video_info
            
        except Exception as e:
            print(f"❌ 提取视频URL失败: {e}")
            return {
                'play_url': None,
                'play_url_no_watermark': None,
                'cover_url': None,
                'duration': 0,
                'width': 0,
                'height': 0,
            }
    
    def _convert_to_no_watermark(self, original_url: str) -> Optional[str]:
        """
        转换为无水印链接
        参考先进项目的无水印处理方法
        """
        try:
            if not original_url:
                return None
            
            # 方法1: 替换wm为nwm (no watermark)
            if '/video/tos/' in original_url:
                no_watermark_url = original_url.replace('/video/tos/', '/obj/')
                if 'watermark=1' in no_watermark_url:
                    no_watermark_url = no_watermark_url.replace('watermark=1', 'watermark=0')
                elif 'wm' in no_watermark_url:
                    no_watermark_url = no_watermark_url.replace('wm', 'nwm')
                return no_watermark_url
            
            # 方法2: 修改URL参数
            if '?' in original_url:
                base_url, params = original_url.split('?', 1)
                if 'watermark' not in params:
                    no_watermark_url = f"{base_url}?{params}&watermark=0"
                else:
                    no_watermark_url = original_url.replace('watermark=1', 'watermark=0')
                return no_watermark_url
            
            return None
            
        except Exception:
            return None
    
    def _extract_cover_url(self, video_data: Dict[str, Any]) -> Optional[str]:
        """提取封面URL"""
        try:
            cover = video_data.get('origin_cover', {}) or video_data.get('cover', {})
            url_list = cover.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None
    
    def _extract_avatar_url(self, author_info: Dict[str, Any]) -> Optional[str]:
        """提取头像URL"""
        try:
            avatar = author_info.get('avatar_larger', {}) or author_info.get('avatar_medium', {})
            url_list = avatar.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None
    
    def _extract_music_url(self, music_info: Dict[str, Any]) -> Optional[str]:
        """提取音乐URL"""
        try:
            play_url = music_info.get('play_url', {})
            url_list = play_url.get('url_list', [])
            return url_list[0] if url_list else None
        except Exception:
            return None