import os

"""
为多平台下载模块提供统一的下载目录配置。

目前用于抖音下载模块（douyin.config），以后可以扩展到其他平台。
"""

from paths_config import WORKSPACE_DIR


class VideoDownloadConfig:
    """统一管理各平台下载目录的工具类。"""

    @staticmethod
    def get_douyin_dir() -> str:
        """
        返回抖音下载目录（统一放在 workspace/douyin_downloads 下）。
        """
        download_dir = os.path.join(WORKSPACE_DIR, "douyin_downloads")
        os.makedirs(download_dir, exist_ok=True)
        return download_dir

