# -*- coding: utf-8 -*-
"""
FFmpeg Manager - 统一管理FFmpeg的使用方式
支持ffmpeg-python库和ffmpeg.exe两种方式，可灵活切换
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    from live_recorder.logger import logger
except ImportError:
    class SimpleLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
    logger = SimpleLogger()


class FFmpegManager:
    """FFmpeg管理器，根据配置选择使用Python库或exe"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化FFmpeg管理器

        Args:
            config_path: 配置文件路径，默认为当前目录下的ffmpeg_config.json
        """
        self.execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
        self.config_path = config_path or os.path.join(self.execute_dir, 'ffmpeg_config.json')
        self.config = self._load_config()
        self.mode = None  # 实际使用的模式
        self.ffmpeg_exe = None  # ffmpeg可执行文件路径
        self._initialize()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "ffmpeg_mode": "auto",
            "ffmpeg_exe_path": "",
            "download_on_missing": True,
            "prefer_exe": False
        }

        if not os.path.exists(self.config_path):
            logger.warning(f"配置文件 {self.config_path} 不存在，使用默认配置")
            return default_config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 移除description字段（仅供用户参考）
                config.pop('description', None)
                return {**default_config, **config}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return default_config

    def _save_config(self):
        """保存配置文件"""
        try:
            # 读取现有配置（包含description）
            existing_config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    existing_config = json.load(f)

            # 更新配置但保留description
            existing_config.update(self.config)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到 {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    def _initialize(self):
        """初始化FFmpeg环境"""
        mode = self.config['ffmpeg_mode'].lower()

        if mode == 'python':
            self._setup_python_mode()
        elif mode == 'exe':
            self._setup_exe_mode()
        elif mode == 'auto':
            self._setup_auto_mode()
        else:
            logger.error(f"不支持的ffmpeg_mode: {mode}，使用auto模式")
            self._setup_auto_mode()

    def _setup_python_mode(self):
        """设置为Python库模式"""
        try:
            import ffmpeg
            self.mode = 'python'
            logger.info("FFmpeg模式: Python库 (ffmpeg-python)")
        except ImportError:
            logger.error("无法导入ffmpeg-python库，请安装: pip install ffmpeg-python")
            if self.config.get('download_on_missing', True):
                logger.info("尝试切换到exe模式...")
                self._setup_exe_mode()
            else:
                raise RuntimeError("ffmpeg-python库未安装")

    def _setup_exe_mode(self):
        """设置为exe模式"""
        ffmpeg_exe = self._find_ffmpeg_exe()

        if ffmpeg_exe:
            self.ffmpeg_exe = ffmpeg_exe
            self.mode = 'exe'
            logger.info(f"FFmpeg模式: 可执行文件 ({ffmpeg_exe})")
        else:
            if self.config.get('download_on_missing', True):
                logger.info("未找到ffmpeg.exe，尝试下载...")
                if self._download_ffmpeg():
                    self.ffmpeg_exe = self._find_ffmpeg_exe()
                    self.mode = 'exe'
                    logger.info(f"FFmpeg模式: 可执行文件 (已下载)")
                else:
                    raise RuntimeError("无法找到或下载ffmpeg.exe")
            else:
                raise RuntimeError("未找到ffmpeg.exe，且download_on_missing为false")

    def _setup_auto_mode(self):
        """自动模式：根据prefer_exe配置选择"""
        prefer_exe = self.config.get('prefer_exe', False)

        if prefer_exe:
            # 优先尝试exe
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
            # 优先尝试Python库
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

        raise RuntimeError("无法初始化FFmpeg（Python库和exe都不可用）")

    def _find_ffmpeg_exe(self) -> Optional[str]:
        """查找ffmpeg可执行文件"""
        # 1. 检查配置中指定的路径
        config_path = self.config.get('ffmpeg_exe_path', '').strip()
        if config_path and os.path.isfile(config_path):
            if self._test_ffmpeg_exe(config_path):
                return config_path

        # 2. 检查项目目录下的ffmpeg文件夹
        local_ffmpeg_dir = os.path.join(self.execute_dir, 'ffmpeg')
        if os.path.isdir(local_ffmpeg_dir):
            # Windows
            ffmpeg_exe = os.path.join(local_ffmpeg_dir, 'ffmpeg.exe')
            if os.path.isfile(ffmpeg_exe) and self._test_ffmpeg_exe(ffmpeg_exe):
                return ffmpeg_exe
            # Linux/Mac
            ffmpeg_exe = os.path.join(local_ffmpeg_dir, 'ffmpeg')
            if os.path.isfile(ffmpeg_exe) and self._test_ffmpeg_exe(ffmpeg_exe):
                return ffmpeg_exe

        # 3. 检查系统PATH
        ffmpeg_exe = shutil.which('ffmpeg')
        if ffmpeg_exe and self._test_ffmpeg_exe(ffmpeg_exe):
            return ffmpeg_exe

        return None

    def _test_ffmpeg_exe(self, path: str) -> bool:
        """测试ffmpeg可执行文件是否可用"""
        try:
            result = subprocess.run(
                [path, '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def _download_ffmpeg(self) -> bool:
        """下载ffmpeg（调用ffmpeg_install.py）"""
        try:
            from ffmpeg_install import install_ffmpeg
            return install_ffmpeg() or False
        except Exception as e:
            logger.error(f"下载ffmpeg失败: {e}")
            return False

    def get_mode(self) -> str:
        """获取当前使用的FFmpeg模式"""
        return self.mode

    def get_ffmpeg_exe(self) -> Optional[str]:
        """获取ffmpeg可执行文件路径（仅在exe模式下有效）"""
        return self.ffmpeg_exe

    def set_mode(self, mode: str):
        """
        设置FFmpeg模式

        Args:
            mode: 'python', 'exe', 或 'auto'
        """
        self.config['ffmpeg_mode'] = mode
        self._save_config()
        self._initialize()

    def set_ffmpeg_exe_path(self, path: str):
        """
        设置ffmpeg可执行文件路径

        Args:
            path: ffmpeg.exe的完整路径
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"文件不存在: {path}")

        if not self._test_ffmpeg_exe(path):
            raise RuntimeError(f"指定的文件不是有效的ffmpeg可执行文件: {path}")

        self.config['ffmpeg_exe_path'] = path
        self._save_config()

        if self.config['ffmpeg_mode'] in ['exe', 'auto']:
            self._initialize()

    def run_ffmpeg_command(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """
        运行ffmpeg命令（仅在exe模式下可用）

        Args:
            *args: ffmpeg命令参数
            **kwargs: subprocess.run的关键字参数

        Returns:
            subprocess.CompletedProcess
        """
        if self.mode != 'exe':
            raise RuntimeError("run_ffmpeg_command仅在exe模式下可用")

        if not self.ffmpeg_exe:
            raise RuntimeError("ffmpeg可执行文件未找到")

        return subprocess.run([self.ffmpeg_exe] + list(args), **kwargs)

    def get_ffmpeg_python(self):
        """
        获取ffmpeg-python模块（仅在python模式下可用）

        Returns:
            ffmpeg模块
        """
        if self.mode != 'python':
            raise RuntimeError("get_ffmpeg_python仅在python模式下可用")

        import ffmpeg
        return ffmpeg

    def probe(self, filename: str, **kwargs) -> Dict[str, Any]:
        """
        探测媒体文件信息（兼容两种模式）

        Args:
            filename: 媒体文件路径
            **kwargs: 额外参数

        Returns:
            媒体信息字典
        """
        if self.mode == 'python':
            import ffmpeg
            return ffmpeg.probe(filename, **kwargs)
        elif self.mode == 'exe':
            result = self.run_ffmpeg_command(
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                filename,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {result.stderr}")
            return json.loads(result.stdout)
        else:
            raise RuntimeError(f"不支持的模式: {self.mode}")

    def extract_audio(self, video_path: str, audio_path: str, **kwargs) -> bool:
        """
        从视频中提取音频（兼容两种模式）

        Args:
            video_path: 视频文件路径
            audio_path: 输出音频文件路径
            **kwargs: 额外参数（如 audio_bitrate, audio_codec等）

        Returns:
            是否成功
        """
        try:
            if self.mode == 'python':
                import ffmpeg
                stream = ffmpeg.input(video_path)
                audio = stream.audio

                output_kwargs = {'acodec': 'pcm_s16le', 'ac': 1, 'ar': '16k'}
                output_kwargs.update(kwargs)

                audio = ffmpeg.output(audio, audio_path, **output_kwargs)
                ffmpeg.run(audio, overwrite_output=True, capture_stdout=True, capture_stderr=True)
                return True

            elif self.mode == 'exe':
                cmd = [
                    self.ffmpeg_exe,
                    '-i', video_path,
                    '-vn',  # 不处理视频
                    '-acodec', kwargs.get('acodec', 'pcm_s16le'),
                    '-ac', str(kwargs.get('ac', 1)),
                    '-ar', kwargs.get('ar', '16k'),
                    '-y',  # 覆盖输出文件
                    audio_path
                ]

                result = subprocess.run(cmd, capture_output=True)
                return result.returncode == 0
            else:
                raise RuntimeError(f"不支持的模式: {self.mode}")
        except Exception as e:
            logger.error(f"提取音频失败: {e}")
            return False

    def get_version(self) -> str:
        """获取FFmpeg版本信息"""
        if self.mode == 'python':
            try:
                result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
                return result.stdout.split('\n')[0] if result.returncode == 0 else "Unknown"
            except:
                return "Unknown"
        elif self.mode == 'exe':
            try:
                result = self.run_ffmpeg_command('-version', capture_output=True, text=True)
                return result.stdout.split('\n')[0] if result.returncode == 0 else "Unknown"
            except:
                return "Unknown"
        return "Unknown"


# 全局单例
_ffmpeg_manager_instance = None


def get_ffmpeg_manager() -> FFmpegManager:
    """获取FFmpeg管理器单例"""
    global _ffmpeg_manager_instance
    if _ffmpeg_manager_instance is None:
        _ffmpeg_manager_instance = FFmpegManager()
    return _ffmpeg_manager_instance


if __name__ == "__main__":
    # 测试代码
    manager = get_ffmpeg_manager()
    print(f"FFmpeg模式: {manager.get_mode()}")
    print(f"FFmpeg版本: {manager.get_version()}")
    if manager.mode == 'exe':
        print(f"FFmpeg路径: {manager.get_ffmpeg_exe()}")
