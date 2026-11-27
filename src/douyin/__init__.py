#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音视频下载模块
视频与图集使用 F2、DLPanda、HelloTik、PeanutDL 顺序回退
"""

__version__ = "2.0.0"
__author__ = "YouTube Reader Team"
__description__ = "抖音视频与图集下载工具（F2 → DLPanda → HelloTik → PeanutDL）"

from .downloader import DouyinDownloader
from .config import DouyinConfig
from .utils import DouyinUtils
from .douyinvd_extractor import DouyinVdExtractor
from .providers import DLPandaProvider, DouyinProviderChain, F2Provider
from .hellotik import HelloTikProvider
from .peanutdl import PeanutDLProvider

__all__ = [
    'DouyinDownloader',
    'DouyinConfig',
    'DouyinUtils',
    'DouyinVdExtractor',
    'DouyinProviderChain',
    'F2Provider',
    'DLPandaProvider',
    'HelloTikProvider',
    'PeanutDLProvider',
]
