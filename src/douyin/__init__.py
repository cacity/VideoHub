#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载模块
单视频使用 F2 主解析与 DLPanda 回退
"""

__version__ = "2.0.0"
__author__ = "YouTube Reader Team"
__description__ = "抖音视频下载工具（F2 主解析 + DLPanda 回退）"

from .downloader import DouyinDownloader
from .config import DouyinConfig
from .utils import DouyinUtils
from .douyinvd_extractor import DouyinVdExtractor
from .providers import DLPandaProvider, DouyinProviderChain, F2Provider

__all__ = [
    'DouyinDownloader',
    'DouyinConfig',
    'DouyinUtils',
    'DouyinVdExtractor',
    'DouyinProviderChain',
    'F2Provider',
    'DLPandaProvider',
]
