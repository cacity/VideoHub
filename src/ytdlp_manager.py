"""
yt-dlp 管理器 - 支持 Python 库模式和本地可执行文件模式
"""

import os
import subprocess
import tempfile
from typing import Optional, Dict, Any

import yt_dlp


class YtDlpManager:
    """yt-dlp 管理器"""

    def __init__(self, mode: str = None, exe_path: str = None):
        """
        初始化 yt-dlp 管理器

        Args:
            mode: 运行模式，"python" (默认) 或 "exe"
            exe_path: 本地可执行文件路径（仅 exe 模式使用）
        """
        self.mode = mode or os.getenv("YT_DLP_MODE", "python")
        self.exe_path = exe_path or os.getenv("YT_DLP_EXE_PATH", "")

    def is_exe_mode(self) -> bool:
        """检查是否为本地可执行文件模式"""
        return self.mode == "exe" and self.exe_path and os.path.exists(self.exe_path)

    def get_exe_path(self) -> Optional[str]:
        """获取可执行文件路径"""
        if self.is_exe_mode():
            return self.exe_path
        return None

    def run(self, url: str, ydl_opts: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """
        运行 yt-dlp 下载

        Args:
            url: 视频 URL
            ydl_opts: yt-dlp 选项
            progress_callback: 进度回调函数

        Returns:
            下载结果字典
        """
        if self.is_exe_mode():
            return self._run_exe(url, ydl_opts, progress_callback)
        else:
            return self._run_python(url, ydl_opts, progress_callback)

    def _run_python(self, url: str, ydl_opts: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """使用 Python 库模式运行"""
        def progress_hook(d):
            if progress_callback and d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = downloaded / total * 100
                    progress_callback(percent, f"下载中: {percent:.1f}%")

        ydl_opts['progress_hooks'] = [progress_hook] if progress_callback else []

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)

    def _run_exe(self, url: str, ydl_opts: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """使用本地可执行文件模式运行"""
        # 将 ydl_opts 转换为命令行参数
        cmd_args = [self.exe_path]

        # 基本选项
        if ydl_opts.get('outtmpl'):
            outtmpl = ydl_opts['outtmpl']
            if isinstance(outtmpl, str):
                cmd_args.extend(['-o', outtmpl])

        if ydl_opts.get('format'):
            cmd_args.extend(['-f', ydl_opts['format']])

        if ydl_opts.get('cookiesfile'):
            cmd_args.extend(['--cookies', ydl_opts['cookiesfile']])

        # 添加其他常用选项
        if ydl_opts.get('proxy'):
            cmd_args.extend(['--proxy', ydl_opts['proxy']])

        if ydl_opts.get('user_agent'):
            cmd_args.extend(['--user-agent', ydl_opts['user_agent']])

        if ydl_opts.get('nocheckcertificate', False):
            cmd_args.append('--no-check-certificate')

        # 添加下载选项
        if not ydl_opts.get('skip_download', False):
            if ydl_opts.get('writesubtitles', False):
                cmd_args.append('--write-subs')
            if ydl_opts.get('writeautomaticsub', False):
                cmd_args.append('--write-auto-subs')
            if ydl_opts.get('subtitleslangs'):
                langs = ydl_opts['subtitleslangs']
                if isinstance(langs, list):
                    cmd_args.extend(['--sub-langs', ','.join(langs)])

        # 输出信息 JSON
        cmd_args.append('--dump-json')
        cmd_args.append(url)

        # 执行命令
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"yt-dlp.exe 执行失败: {result.stderr}")

        # 解析 JSON 输出
        import json
        return json.loads(result.stdout)

    def download_video(
        self,
        url: str,
        output_dir: str = None,
        audio_only: bool = False,
        cookies_file: str = None,
        progress_callback=None
    ) -> Optional[str]:
        """
        下载视频

        Args:
            url: 视频 URL
            output_dir: 输出目录
            audio_only: 是否仅下载音频
            cookies_file: Cookies 文件路径
            progress_callback: 进度回调

        Returns:
            下载的文件路径
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        if output_dir:
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
        else:
            ydl_opts['outtmpl'] = '%(title)s.%(ext)s'

        if audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }]
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'

        if cookies_file and os.path.exists(cookies_file):
            ydl_opts['cookiefile'] = cookies_file

        try:
            info = self.run(url, ydl_opts, progress_callback)
            if info and 'requested_downloads' in info:
                return info['requested_downloads'][0].get('filepath')
            return None
        except Exception as e:
            print(f"[ERROR] 下载失败: {e}")
            return None


def get_ytdlp_manager() -> YtDlpManager:
    """获取 yt-dlp 管理器实例"""
    mode = os.getenv("YT_DLP_MODE", "python")
    exe_path = os.getenv("YT_DLP_EXE_PATH", "")
    return YtDlpManager(mode=mode, exe_path=exe_path)


def get_ytdlp_options(
    cookies_file: str = None,
    proxy: str = None,
    output_template: str = None,
    format_spec: str = "bestvideo+bestaudio/best"
) -> Dict[str, Any]:
    """
    获取 yt-dlp 选项（适用于 Python 库模式）

    Args:
        cookies_file: Cookies 文件路径
        proxy: 代理服务器
        output_template: 输出模板
        format_spec: 格式规格

    Returns:
        yt-dlp 选项字典
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_spec,
    }

    if output_template:
        ydl_opts['outtmpl'] = output_template

    if cookies_file and os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file

    if proxy:
        ydl_opts['proxy'] = proxy

    # 从环境变量读取代理
    env_proxy = os.getenv("PROXY", "")
    if env_proxy and not proxy:
        ydl_opts['proxy'] = env_proxy

    return ydl_opts


def check_ytdlp_version() -> Optional[str]:
    """检查 yt-dlp 版本"""
    try:
        # 先尝试 Python 库版本
        import yt_dlp
        return yt_dlp.version.__version__
    except:
        pass

    try:
        # 再尝试本地 exe
        mode = os.getenv("YT_DLP_MODE", "python")
        exe_path = os.getenv("YT_DLP_EXE_PATH", "")

        if mode == "exe" and exe_path and os.path.exists(exe_path):
            result = subprocess.run([exe_path, "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
    except:
        pass

    return None


if __name__ == '__main__':
    # 测试代码
    version = check_ytdlp_version()
    print(f"yt-dlp 版本: {version or '未找到'}")

    manager = get_ytdlp_manager()
    print(f"运行模式: {manager.mode}")
    print(f"可执行文件模式: {manager.is_exe_mode()}")
    if manager.is_exe_mode():
        print(f"可执行文件路径: {manager.exe_path}")
