#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载配置管理
"""

import os
from typing import Dict, Any, Optional

class DouyinConfig:
    """抖音下载配置类"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        # 基础配置
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "timeout": 30,
        "max_retries": 3,
        "retry_delay": 1,
        
        # 下载配置
        "download_dir": "douyin_downloads",
        "video_quality": "high",  # high, medium, low
        "download_cover": True,
        "download_music": True,
        "remove_watermark": True,
        
        # API配置
        "api_version": "v1",
        "chunk_size": 1024 * 1024,  # 1MB
        
        # 文件命名
        "filename_template": "{title}",
        "max_filename_length": 100,
        
        # 并发设置
        "max_workers": 4,
        "concurrent_downloads": 3,
        
        # 代理设置
        "proxy": None,
        "proxy_type": "http",
        
        # Cookie设置
        "cookie": None,
        "auto_cookie": True,
        
        # 过滤设置
        "min_duration": 1,  # 最小时长(秒)
        "max_duration": 600,  # 最大时长(秒)
        "filter_ads": True,
        
        # 输出设置
        "save_metadata": True,
        "metadata_format": "json",
        "log_level": "INFO",
        
        # 转录和摘要设置
        "enable_transcription": True,
        "generate_article": True,
    }
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """
        初始化配置
        :param config_dict: 自定义配置字典
        """
        self.config = self.DEFAULT_CONFIG.copy()
        if config_dict:
            self.config.update(config_dict)
            
        # 确保下载目录存在
        os.makedirs(self.get("download_dir"), exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        self.config[key] = value
    
    def update(self, config_dict: Dict[str, Any]) -> None:
        """批量更新配置"""
        self.config.update(config_dict)
    
    def get_headers(self) -> Dict[str, str]:
        """获取请求头 - 参考开源项目优化"""
        headers = {
            "User-Agent": self.get("user_agent"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
            # 添加更多反爬虫头部
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            # 抖音特定头部
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
        }
        
        # 添加Cookie
        cookie = self.get("cookie")
        if cookie:
            headers["Cookie"] = cookie
        else:
            # 添加基础cookie以提高成功率
            headers["Cookie"] = self._generate_basic_cookies()
            
        return headers
    
    def _generate_basic_cookies(self) -> str:
        """生成基础Cookie"""
        import random
        import time
        
        # 基础cookie参数，参考开源项目
        cookies = [
            f"ttwid=1%7C{int(time.time())}%7C{random.randint(100000000, 999999999)}",
            "s_v_web_id=verify_" + ''.join(random.choices('abcdef0123456789', k=32)),
            f"passport_csrf_token={''.join(random.choices('abcdef0123456789', k=32))}",
            f"passport_csrf_token_default={''.join(random.choices('abcdef0123456789', k=32))}",
        ]
        
        return "; ".join(cookies)
    
    def get_proxies(self) -> Optional[Dict[str, str]]:
        """获取代理配置"""
        proxy = self.get("proxy")
        if not proxy:
            return None
            
        proxy_type = self.get("proxy_type", "http")
        return {
            "http": f"{proxy_type}://{proxy}",
            "https": f"{proxy_type}://{proxy}"
        }
    
    def validate(self) -> bool:
        """验证配置有效性"""
        try:
            # 检查下载目录权限
            download_dir = self.get("download_dir")
            if not os.path.exists(download_dir):
                os.makedirs(download_dir, exist_ok=True)
                
            # 检查数值范围
            timeout = self.get("timeout")
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                return False
                
            max_retries = self.get("max_retries")
            if not isinstance(max_retries, int) or max_retries < 0:
                return False
                
            return True
        except Exception:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.config.copy()
    
    @classmethod
    def from_file(cls, config_path: str) -> 'DouyinConfig':
        """从文件加载配置"""
        import json
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            return cls(config_dict)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return cls()
    
    def save_to_file(self, config_path: str) -> bool:
        """保存配置到文件"""
        import json
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False