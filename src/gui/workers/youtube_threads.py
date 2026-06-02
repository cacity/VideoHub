"""
YouTube 字幕相关线程
"""

import os
from PyQt6.QtCore import QThread, pyqtSignal


class GetLanguagesThread(QThread):
    """获取 YouTube 视频可用字幕语言线程"""
    languages_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        """获取YouTube视频的可用字幕语言"""
        try:
            import yt_dlp

            # 尝试多种配置
            proxy_configs = []

            # 配置1：使用系统代理
            proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if proxy:
                proxy_configs.append({
                    'quiet': True,
                    'no_warnings': True,
                    'proxy': proxy
                })

            # 配置2：不使用代理
            proxy_configs.append({
                'quiet': True,
                'no_warnings': True,
            })

            info = None
            for ydl_opts in proxy_configs:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.url, download=False)
                        break  # 成功则退出循环
                except Exception as e:
                    if "proxy" in ydl_opts:
                        print(f"使用代理失败，尝试直连: {str(e)}")
                    else:
                        raise e  # 如果直连也失败，抛出异常

            if not info:
                self.error_signal.emit("无法获取视频信息")
                return

            # 获取可用字幕
            subtitles = info.get('subtitles', {})
            automatic_captions = info.get('automatic_captions', {})

            # 构建语言列表
            languages = {}

            # 手动字幕
            for lang_code, lang_info in subtitles.items():
                lang_name = lang_info[0].get('name', lang_code) if lang_info else lang_code
                languages[lang_code] = {
                    'name': lang_name,
                    'type': 'manual'
                }

            # 自动字幕
            for lang_code, lang_info in automatic_captions.items():
                if lang_code not in languages:
                    lang_name = lang_info[0].get('name', lang_code) if lang_info else lang_code
                    languages[lang_code] = {
                        'name': lang_name,
                        'type': 'auto'
                    }

            self.languages_signal.emit(languages)

        except Exception as e:
            self.error_signal.emit(f"获取语言列表失败: {str(e)}")


class DownloadSubtitleThread(QThread):
    """下载 YouTube 字幕线程"""
    download_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, url, language):
        super().__init__()
        self.url = url
        self.language = language

    def run(self):
        """下载YouTube字幕"""
        try:
            # 确保导入路径正确
            import sys
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)

            from youtube_transcriber import download_youtube_subtitles
            from paths_config import NATIVE_SUBTITLES_DIR

            # 创建输出目录（统一使用 workspace/native_subtitles）
            output_dir = NATIVE_SUBTITLES_DIR
            os.makedirs(output_dir, exist_ok=True)

            print(f"开始下载字幕: URL={self.url}, 语言={self.language}")

            # 下载字幕
            downloaded_files = download_youtube_subtitles(
                self.url,
                output_dir=output_dir,
                languages=[self.language],
                download_auto=True
            )

            print(f"下载结果: {downloaded_files}")

            if downloaded_files:
                # 验证文件是否真实存在并标准化路径
                valid_files = []
                for f in downloaded_files:
                    # 标准化路径分隔符
                    normalized_path = os.path.normpath(f)
                    if os.path.exists(normalized_path):
                        # 转换为绝对路径
                        abs_path = os.path.abspath(normalized_path)
                        valid_files.append(abs_path)

                if valid_files:
                    self.download_signal.emit(valid_files[0])
                else:
                    self.error_signal.emit(f"字幕文件下载后未找到: {downloaded_files}")
            else:
                self.error_signal.emit("没有找到可下载的字幕文件，可能的原因：\n1. 该视频没有此语言的字幕\n2. 字幕不可下载\n3. 网络连接问题")

        except ImportError as e:
            self.error_signal.emit(f"导入模块失败: {str(e)}")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.error_signal.emit(f"下载失败: {str(e)}\n\n详细错误信息:\n{error_details}")
