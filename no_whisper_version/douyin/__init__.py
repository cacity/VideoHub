#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载模块
基于新douyin.py的简化实现
"""

__version__ = "2.0.0"
__author__ = "YouTube Reader Team"
__description__ = "抖音视频下载工具（使用douyin.py）"

from .downloader import DouyinDownloader
from .config import DouyinConfig
from .utils import DouyinUtils
from .douyinvd_extractor import DouyinVdExtractor

__all__ = [
    'DouyinDownloader',
    'DouyinConfig',
    'DouyinUtils',
    'DouyinVdExtractor'
]