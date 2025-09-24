#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载模块
基于TikTokDownload项目的核心技术实现
"""

__version__ = "1.0.0"
__author__ = "YouTube Reader Team"
__description__ = "抖音视频下载工具"

from .downloader import DouyinDownloader
from .parser import DouyinParser  
from .config import DouyinConfig
from .utils import DouyinUtils
from .douyinvd_extractor import DouyinVdExtractor

__all__ = [
    'DouyinDownloader',
    'DouyinParser', 
    'DouyinConfig',
    'DouyinUtils',
    'DouyinVdExtractor'
]