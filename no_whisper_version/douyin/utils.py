#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载工具函数
"""

import re
import os
import time
import json
import hashlib
import random
import string
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, parse_qs, unquote
import requests

class DouyinUtils:
    """抖音工具类"""
    
    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """
        从抖音URL中提取视频ID
        :param url: 抖音视频链接
        :return: 视频ID
        """
        try:
            # 常见的抖音URL格式
            patterns = [
                r'video/(\d+)',  # https://www.douyin.com/video/7xxxxx
                r'share/video/(\d+)',  # 分享链接
                r'/(\d+)',  # 短链接
                r'modal_id=(\d+)',  # 模态框链接
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            
            # 处理短链接需要展开
            if 'v.douyin.com' in url or 'iesdouyin.com' in url:
                expanded_url = DouyinUtils.expand_short_url(url)
                if expanded_url and expanded_url != url:
                    return DouyinUtils.extract_video_id(expanded_url)
            
            return None
        except Exception as e:
            print(f"提取视频ID失败: {e}")
            return None
    
    @staticmethod
    def expand_short_url(short_url: str) -> Optional[str]:
        """
        展开短链接
        :param short_url: 短链接
        :return: 展开后的链接
        """
        try:
            print(f"正在展开短链接: {short_url}")
            
            # 创建session with SSL configuration
            session = requests.Session()
            session.verify = False  # 忽略SSL验证问题
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.3',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # 禁用SSL警告
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # 多次尝试不同的方法
            methods = [
                lambda: session.head(short_url, headers=headers, allow_redirects=True, timeout=15),
                lambda: session.get(short_url, headers=headers, allow_redirects=True, timeout=15, stream=True),
            ]
            
            for i, method in enumerate(methods):
                try:
                    print(f"尝试方法 {i+1}...")
                    response = method()
                    expanded_url = response.url
                    print(f"短链接展开结果: {expanded_url}")
                    
                    # 验证URL是否有效
                    if expanded_url and expanded_url != short_url and 'douyin.com' in expanded_url:
                        return expanded_url
                        
                except Exception as method_error:
                    print(f"方法 {i+1} 失败: {method_error}")
                    continue
            
            # 如果所有方法都失败，尝试从短链接直接提取ID
            print("尝试从短链接直接提取视频ID...")
            video_id_match = re.search(r'/([A-Za-z0-9]+)/?$', short_url)
            if video_id_match:
                video_id = video_id_match.group(1)
                constructed_url = f"https://www.douyin.com/video/{video_id}"
                print(f"构造的URL: {constructed_url}")
                return constructed_url
            
            return None
            
        except Exception as e:
            print(f"展开短链接失败: {e}")
            return None
    
    @staticmethod
    def clean_filename(filename: str, max_length: int = 100) -> str:
        """
        清理文件名，移除非法字符
        :param filename: 原始文件名
        :param max_length: 最大长度
        :return: 清理后的文件名
        """
        # 移除非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '_', filename)
        
        # 将所有空白字符折叠为一个下划线，避免文件名中出现空格
        # 这样可以与 YouTube 下载部分使用的 sanitize_filename 行为保持一致
        filename = re.sub(r'\s+', '_', filename).strip('_')
        
        # 限制长度
        if len(filename) > max_length:
            filename = filename[:max_length]
        
        return filename
    
    @staticmethod
    def format_filename(template: str, video_info: Dict[str, Any]) -> str:
        """
        格式化文件名
        :param template: 文件名模板
        :param video_info: 视频信息
        :return: 格式化后的文件名
        """
        try:
            # 提取常用字段
            author = video_info.get('author', {}).get('nickname', 'unknown')
            title = video_info.get('desc', 'untitled')
            aweme_id = video_info.get('aweme_id', 'unknown')
            create_time = video_info.get('create_time', 0)
            
            # 处理时间戳（支持字符串和数字格式）
            if isinstance(create_time, str):
                # 如果是字符串时间格式，转换为时间戳
                try:
                    import datetime
                    dt = datetime.datetime.strptime(create_time, '%Y-%m-%d %H:%M:%S')
                    create_time = int(dt.timestamp())
                except ValueError:
                    # 如果解析失败，使用当前时间
                    create_time = int(time.time())
            elif not isinstance(create_time, (int, float)) or create_time <= 0:
                create_time = int(time.time())
            
            # 格式化时间
            try:
                create_date = time.strftime('%Y%m%d', time.localtime(create_time))
            except (OSError, ValueError):
                # 时间戳无效时使用当前时间
                create_date = time.strftime('%Y%m%d', time.localtime())
            
            # 替换模板变量
            filename = template.format(
                author=author,
                title=title,
                aweme_id=aweme_id,
                create_time=create_time,
                create_date=create_date
            )
            
            return DouyinUtils.clean_filename(filename)
        except Exception as e:
            print(f"格式化文件名失败: {e}")
            return f"douyin_{int(time.time())}"
    
    @staticmethod
    def generate_sign(params: Dict[str, Any]) -> str:
        """
        生成签名（简化版本）
        :param params: 参数字典
        :return: 签名字符串
        """
        try:
            # 排序参数
            sorted_params = sorted(params.items())
            
            # 拼接字符串
            param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
            
            # 计算MD5
            md5_hash = hashlib.md5(param_str.encode('utf-8')).hexdigest()
            
            return md5_hash[:16]  # 取前16位
        except Exception:
            return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    
    @staticmethod
    def get_timestamp() -> int:
        """获取当前时间戳"""
        return int(time.time())
    
    @staticmethod
    def get_random_string(length: int = 8) -> str:
        """生成随机字符串"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))
    
    @staticmethod
    def format_duration(seconds: int) -> str:
        """
        格式化时长
        :param seconds: 秒数
        :return: 格式化字符串
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    @staticmethod
    def format_file_size(size: int) -> str:
        """
        格式化文件大小
        :param size: 文件大小（字节）
        :return: 格式化字符串
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    @staticmethod
    def extract_urls_from_text(text: str) -> List[str]:
        """
        从分享文本中提取抖音链接
        :param text: 分享文本内容
        :return: 提取到的URL列表
        """
        if not text:
            return []
        
        urls = []
        
        # 抖音URL的正则表达式模式
        url_patterns = [
            # 标准抖音链接
            r'https?://(?:www\.)?douyin\.com/[^\s]+',
            # 短链接
            r'https?://v\.douyin\.com/[^\s]+',
            # 其他抖音域名
            r'https?://(?:www\.)?iesdouyin\.com/[^\s]+',
            r'https?://(?:www\.)?amemv\.com/[^\s]+',
        ]
        
        try:
            for pattern in url_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    # 清理URL末尾的标点符号，保持更宽松的清理策略
                    # 移除末尾的常见标点符号但保留URL必要字符
                    cleaned_url = re.sub(r'[，。！？；""''（）【】\\s]+$', '', match.strip())
                    
                    # 确保URL以/结尾（如果原本就有）或保持原样
                    if cleaned_url and cleaned_url not in urls:
                        urls.append(cleaned_url)
            
            return urls
        except Exception as e:
            print(f"从文本提取URL失败: {e}")
            return []
    
    @staticmethod
    def parse_share_text(share_text: str) -> Optional[str]:
        """
        解析抖音分享文本，提取有效的视频链接
        :param share_text: 分享文本
        :return: 第一个有效的视频链接
        """
        try:
            # 提取所有可能的URL
            urls = DouyinUtils.extract_urls_from_text(share_text)
            
            # 验证并返回第一个有效的URL
            for url in urls:
                if DouyinUtils.validate_url(url):
                    return url
            
            return None
        except Exception as e:
            print(f"解析分享文本失败: {e}")
            return None
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        验证抖音URL是否有效
        :param url: URL字符串
        :return: 是否有效
        """
        if not url:
            return False
            
        # 抖音域名列表
        douyin_domains = [
            'douyin.com',
            'v.douyin.com', 
            'iesdouyin.com',
            'amemv.com'
        ]
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # 检查是否是抖音域名
            for douyin_domain in douyin_domains:
                if douyin_domain in domain:
                    return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def save_metadata(video_info: Dict[str, Any], file_path: str) -> bool:
        """
        保存视频元数据
        :param video_info: 视频信息
        :param file_path: 保存路径
        :return: 是否成功
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存元数据失败: {e}")
            return False
    
    @staticmethod
    def load_metadata(file_path: str) -> Optional[Dict[str, Any]]:
        """
        加载视频元数据
        :param file_path: 文件路径
        :return: 视频信息
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载元数据失败: {e}")
            return None
    
    @staticmethod
    def get_video_info_summary(video_info: Dict[str, Any]) -> str:
        """
        获取视频信息摘要
        :param video_info: 视频信息
        :return: 摘要字符串
        """
        try:
            author = video_info.get('author', {}).get('nickname', '未知')
            title = video_info.get('desc', '无标题')[:50]
            duration = video_info.get('duration', 0)
            create_time = video_info.get('create_time', 0)
            
            # 格式化时间
            create_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(create_time))
            duration_str = DouyinUtils.format_duration(duration)
            
            summary = f"""
作者: {author}
标题: {title}
时长: {duration_str}
发布时间: {create_date}
            """.strip()
            
            return summary
        except Exception:
            return "无法获取视频信息摘要"
