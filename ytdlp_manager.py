# -*- coding: utf-8 -*-
"""
yt-dlp Manager - 统一管理yt-dlp的使用方式
支持yt-dlp库和yt-dlp.exe两种方式，可灵活切换
"""

import os
import sys
import json
import subprocess
import shutil
import requests
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from live_recorder.logger import logger
except ImportError:
    class SimpleLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
    logger = SimpleLogger()


class YtDlpManager:
    """yt-dlp管理器，根据配置选择使用Python库或exe"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化yt-dlp管理器

        Args:
            config_path: 配置文件路径，默认为当前目录下的ytdlp_config.json
        """
        self.execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
        self.config_path = config_path or os.path.join(self.execute_dir, 'ytdlp_config.json')
        self.config = self._load_config()
        self.mode = None  # 实际使用的模式
        self.ytdlp_exe = None  # yt-dlp可执行文件路径
        self._initialize()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "ytdlp_mode": "auto",
            "ytdlp_exe_path": "",
            "download_on_missing": True,
            "prefer_exe": False
        }

        if not os.path.exists(self.config_path):
            logger.warning(f"配置文件 {self.config_path} 不存在，使用默认配置")
            return default_config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                config.pop('description', None)
                return {**default_config, **config}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return default_config

    def _save_config(self):
        """保存配置文件"""
        try:
            existing_config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    existing_config = json.load(f)

            existing_config.update(self.config)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到 {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    def _initialize(self):
        """初始化yt-dlp环境"""
        mode = self.config['ytdlp_mode'].lower()

        if mode == 'python':
            self._setup_python_mode()
        elif mode == 'exe':
            self._setup_exe_mode()
        elif mode == 'auto':
            self._setup_auto_mode()
        else:
            logger.error(f"不支持的ytdlp_mode: {mode}，使用auto模式")
            self._setup_auto_mode()

    def _setup_python_mode(self):
        """设置为Python库模式"""
        try:
            import yt_dlp
            self.mode = 'python'
            logger.info("yt-dlp模式: Python库")
        except ImportError:
            logger.error("无法导入yt-dlp库，请安装: pip install yt-dlp")
            if self.config.get('download_on_missing', True):
                logger.info("尝试切换到exe模式...")
                self._setup_exe_mode()
            else:
                raise RuntimeError("yt-dlp库未安装")

    def _setup_exe_mode(self):
        """设置为exe模式"""
        ytdlp_exe = self._find_ytdlp_exe()

        if ytdlp_exe:
            self.ytdlp_exe = ytdlp_exe
            self.mode = 'exe'
            logger.info(f"yt-dlp模式: 可执行文件 ({ytdlp_exe})")
        else:
            if self.config.get('download_on_missing', True):
                logger.info("未找到yt-dlp.exe，尝试下载...")
                downloaded_path = self._download_ytdlp()
                if downloaded_path:
                    self.ytdlp_exe = downloaded_path
                    self.mode = 'exe'
                    logger.info(f"yt-dlp模式: 可执行文件 (已下载)")
                else:
                    raise RuntimeError("无法找到或下载yt-dlp.exe")
            else:
                raise RuntimeError("未找到yt-dlp.exe，且download_on_missing为false")

    def _setup_auto_mode(self):
        """自动模式：根据prefer_exe配置选择"""
        prefer_exe = self.config.get('prefer_exe', False)

        if prefer_exe:
            try:
                self._setup_exe_mode()
                return
            except:
                logger.info("exe模式不可用，尝试Python库模式...")
                try:
                    self._setup_python_mode()
                    return
                except:
                    pass
        else:
            try:
                self._setup_python_mode()
                return
            except:
                logger.info("Python库模式不可用，尝试exe模式...")
                try:
                    self._setup_exe_mode()
                    return
                except:
                    pass

        raise RuntimeError("无法初始化yt-dlp（Python库和exe都不可用）")

    def _find_ytdlp_exe(self) -> Optional[str]:
        """查找yt-dlp可执行文件"""
        # 1. 检查配置中指定的路径
        config_path = self.config.get('ytdlp_exe_path', '').strip()
        if config_path and os.path.isfile(config_path):
            if self._test_ytdlp_exe(config_path):
                return config_path

        # 2. 检查项目目录下的ytdlp文件夹
        local_ytdlp_dir = os.path.join(self.execute_dir, 'ytdlp')
        if os.path.isdir(local_ytdlp_dir):
            ytdlp_exe = os.path.join(local_ytdlp_dir, 'yt-dlp.exe')
            if os.path.isfile(ytdlp_exe) and self._test_ytdlp_exe(ytdlp_exe):
                return ytdlp_exe
            ytdlp_exe = os.path.join(local_ytdlp_dir, 'yt-dlp')
            if os.path.isfile(ytdlp_exe) and self._test_ytdlp_exe(ytdlp_exe):
                return ytdlp_exe

        # 3. 检查系统PATH
        ytdlp_exe = shutil.which('yt-dlp')
        if ytdlp_exe and self._test_ytdlp_exe(ytdlp_exe):
            return ytdlp_exe

        return None

    def _test_ytdlp_exe(self, path: str) -> bool:
        """测试yt-dlp可执行文件是否可用"""
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def _download_ytdlp(self) -> Optional[str]:
        """
        下载yt-dlp.exe

        Returns:
            下载成功返回文件路径，失败返回None
        """
        try:
            import platform
            system = platform.system()

            if system == "Windows":
                url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            elif system == "Darwin":  # macOS
                url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
            else:  # Linux
                url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

            logger.info(f"正在从 {url} 下载yt-dlp...")

            # 创建ytdlp目录
            ytdlp_dir = os.path.join(self.execute_dir, 'ytdlp')
            if not os.path.exists(ytdlp_dir):
                os.makedirs(ytdlp_dir)

            # 确定文件名
            if system == "Windows":
                filename = "yt-dlp.exe"
            else:
                filename = "yt-dlp"

            file_path = os.path.join(ytdlp_dir, filename)

            # 下载文件
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Linux/macOS需要添加执行权限
            if system != "Windows":
                os.chmod(file_path, 0o755)

            logger.info(f"yt-dlp下载成功: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"下载yt-dlp失败: {e}")
            return None

    def get_mode(self) -> str:
        """获取当前使用的yt-dlp模式"""
        return self.mode

    def get_ytdlp_exe(self) -> Optional[str]:
        """获取yt-dlp可执行文件路径（仅在exe模式下有效）"""
        return self.ytdlp_exe

    def set_mode(self, mode: str):
        """设置yt-dlp模式"""
        self.config['ytdlp_mode'] = mode
        self._save_config()
        self._initialize()

    def set_ytdlp_exe_path(self, path: str):
        """设置yt-dlp可执行文件路径"""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"文件不存在: {path}")

        if not self._test_ytdlp_exe(path):
            raise RuntimeError(f"指定的文件不是有效的yt-dlp可执行文件: {path}")

        self.config['ytdlp_exe_path'] = path
        self._save_config()

        if self.config['ytdlp_mode'] in ['exe', 'auto']:
            self._initialize()

    def run_ytdlp_command(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """
        运行yt-dlp命令（仅在exe模式下可用）
        """
        if self.mode != 'exe':
            raise RuntimeError("run_ytdlp_command仅在exe模式下可用")

        if not self.ytdlp_exe:
            raise RuntimeError("yt-dlp可执行文件未找到")

        return subprocess.run([self.ytdlp_exe] + list(args), **kwargs)

    def get_ytdlp_module(self):
        """
        获取yt-dlp模块（仅在python模式下可用）
        """
        if self.mode != 'python':
            raise RuntimeError("get_ytdlp_module仅在python模式下可用")

        import yt_dlp
        return yt_dlp

    def get_YoutubeDL(self):
        """
        获取YoutubeDL类（兼容两种模式）
        """
        if self.mode == 'python':
            import yt_dlp
            return yt_dlp.YoutubeDL
        else:
            # exe模式下返回一个包装类
            return self._YoutubeDLWrapper

    class _YoutubeDLWrapper:
        """yt-dlp.exe的包装类，提供类似YoutubeDL的接口"""
        def __init__(self, params=None, manager=None):
            self.params = params or {}
            self.manager = manager

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, url_list):
            """下载视频"""
            # 构建命令行参数
            cmd = []
            for key, value in self.params.items():
                if isinstance(value, bool):
                    if value:
                        cmd.append(f'--{key.replace("_", "-")}')
                else:
                    cmd.append(f'--{key.replace("_", "-")}')
                    cmd.append(str(value))

            if isinstance(url_list, str):
                url_list = [url_list]

            cmd.extend(url_list)

            result = self.manager.run_ytdlp_command(*cmd, capture_output=True)
            return result.returncode

    def get_version(self) -> str:
        """获取yt-dlp版本信息"""
        if self.mode == 'python':
            try:
                import yt_dlp
                return yt_dlp.version.__version__
            except:
                return "Unknown"
        elif self.mode == 'exe':
            try:
                result = self.run_ytdlp_command('--version', capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else "Unknown"
            except:
                return "Unknown"
        return "Unknown"


# 全局单例
_ytdlp_manager_instance = None


def get_ytdlp_manager() -> YtDlpManager:
    """获取yt-dlp管理器单例"""
    global _ytdlp_manager_instance
    if _ytdlp_manager_instance is None:
        _ytdlp_manager_instance = YtDlpManager()
    return _ytdlp_manager_instance


if __name__ == "__main__":
    # 测试代码
    manager = get_ytdlp_manager()
    print(f"yt-dlp模式: {manager.get_mode()}")
    print(f"yt-dlp版本: {manager.get_version()}")
    if manager.mode == 'exe':
        print(f"yt-dlp路径: {manager.get_ytdlp_exe()}")
