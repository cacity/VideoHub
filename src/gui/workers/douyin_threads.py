"""
抖音下载相关线程
"""

import os
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication


class DouyinParseThread(QThread):
    """抖音视频信息解析线程"""
    update_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, is_user_profile=False):
        super().__init__()
        self.url = url
        self.is_user_profile = is_user_profile
        self.stopped = False

    def stop(self):
        """停止解析"""
        self.stopped = True

    def run(self):
        """执行视频信息解析"""
        try:
            self.update_signal.emit("正在解析视频信息...")

            # 安全获取 DouyinUtils 并验证URL
            try:
                from douyin.utils import DouyinUtils
                if not DouyinUtils.validate_url(self.url):
                    self.finished_signal.emit(False, "无效的抖音URL")
                    return
            except ImportError:
                self.finished_signal.emit(False, "抖音模块不可用")
                return

            # 粘贴时已识别为用户主页分享，直接走用户主页分支
            if self.is_user_profile:
                self.update_signal.emit("检测到用户主页分享链接...")
                user_profile = {
                    "_type": "user_profile",
                    "url": self.url,
                    "original_url": self.url,
                    "nickname": "抖音用户",
                }
                self.result_signal.emit(user_profile)
                self.finished_signal.emit(True, "检测到用户主页")
                return

            # 展开短链接，判断是否为用户主页
            resolved_url = self.url
            if 'v.douyin.com' in self.url or 'iesdouyin.com' in self.url:
                self.update_signal.emit("正在解析短链接跳转目标...")
                expanded = DouyinUtils.expand_short_url(self.url)
                if expanded:
                    resolved_url = expanded

            if '/user/' in resolved_url:
                self.update_signal.emit("检测到用户主页链接...")
                user_profile = {
                    "_type": "user_profile",
                    "url": resolved_url,
                    "original_url": self.url,
                    "nickname": "抖音用户",
                }
                self.result_signal.emit(user_profile)
                self.finished_signal.emit(True, "检测到用户主页")
                return

            # 创建下载器，使用默认端口8080
            from douyin import DouyinDownloader
            downloader = DouyinDownloader(port="8080")

            # 解析视频信息
            print(f"[线程] 调用 downloader.get_video_info({self.url})")
            video_info = downloader.get_video_info(self.url)
            print(f"[线程] get_video_info 返回: {type(video_info)}")

            if self.stopped:
                return

            if video_info:
                print(f"[线程] 成功获取视频信息，发出 result_signal")
                self.result_signal.emit(video_info)
                print(f"[线程] 发出 finished_signal(True)")
                self.finished_signal.emit(True, "解析完成")
                print(f"[线程] 信号发送完成，等待处理...")
                # 强制刷新事件循环
                QApplication.processEvents()
                print(f"[线程] 事件循环处理完成")
            else:
                print(f"[线程] 视频信息为空，发出失败信号")
                self.finished_signal.emit(False, "无法解析视频信息")

        except Exception as e:
            if not self.stopped:
                self.update_signal.emit(f"解析失败: {str(e)}")
                self.finished_signal.emit(False, f"解析失败: {str(e)}")
        finally:
            print(f"[线程] DouyinParseThread.run() 结束")


class DouyinDownloadThread(QThread):
    """抖音视频下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, config):
        super().__init__()
        self.url = url
        self.config = config
        self.stopped = False

    def stop(self):
        """停止下载"""
        self.stopped = True

    def process_transcription_and_summary(self, download_result):
        """处理转录和摘要生成"""
        try:
            # 获取下载的视频文件路径
            video_files = download_result.get("files", {}).get("video", [])
            if not video_files:
                self.result_signal.emit(download_result)
                self.finished_signal.emit(True, "下载完成（未找到视频文件进行转录）")
                return

            # 使用第一个视频文件
            video_path = video_files[0]
            if not os.path.exists(video_path):
                self.result_signal.emit(download_result)
                self.finished_signal.emit(True, "下载完成（视频文件不存在）")
                return

            self.update_signal.emit("开始处理转录和摘要...")
            self.progress_signal.emit(80, "开始转录处理...")

            # 导入必要的模块
            from youtube_transcriber import process_local_video

            # 设置处理参数（使用默认值）
            model = "gpt-4o-mini"
            api_key = os.getenv('OPENAI_API_KEY')
            base_url = os.getenv('OPENAI_BASE_URL')
            whisper_model_size = "medium"
            stream = True
            summary_dir = "summaries"
            custom_prompt = None
            template_path = None
            generate_subtitles = True
            translate_to_chinese = True
            embed_subtitles = False
            enable_transcription = self.config.get("enable_transcription", True)
            generate_article = self.config.get("generate_article", True)
            source_language = None

            # 执行转录和摘要处理
            result = process_local_video(
                video_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language
            )

            if result:
                self.update_signal.emit(f"✅ 转录和摘要处理完成: {result}")
                download_result["transcription_result"] = result
            else:
                self.update_signal.emit("⚠️ 转录和摘要处理失败")

            self.result_signal.emit(download_result)
            self.finished_signal.emit(True, "下载和处理完成")

        except Exception as e:
            self.update_signal.emit(f"❌ 转录处理失败: {str(e)}")
            self.result_signal.emit(download_result)
            self.finished_signal.emit(True, "下载完成，但转录处理失败")

    def run(self):
        """执行视频下载"""
        try:
            self.update_signal.emit("开始下载抖音视频...")
            self.progress_signal.emit(0, "初始化下载...")

            from douyin import DouyinDownloader

            # 创建下载器
            downloader = DouyinDownloader(self.config, port="8080")

            # 进度回调函数
            def progress_callback(message, progress):
                if not self.stopped:
                    self.update_signal.emit(message)
                    self.progress_signal.emit(progress, message)

            # 下载视频
            result = downloader.download_video(self.url, progress_callback=progress_callback)

            if self.stopped:
                return

            if result and result.get("success"):
                self.progress_signal.emit(70, "下载完成，处理结果...")

                # 检查是否需要转录和摘要
                if self.config.get("enable_transcription", True) or self.config.get("generate_article", True):
                    self.process_transcription_and_summary(result)
                else:
                    self.result_signal.emit(result)
                    self.finished_signal.emit(True, "下载完成")
            else:
                error_msg = result.get("error", "下载失败") if result else "下载失败"
                self.update_signal.emit(f"❌ {error_msg}")
                self.finished_signal.emit(False, error_msg)

        except Exception as e:
            if not self.stopped:
                import traceback
                error_msg = f"下载失败: {str(e)}"
                self.update_signal.emit(f"❌ {error_msg}\n{traceback.format_exc()}")
                self.finished_signal.emit(False, error_msg)


class DouyinBatchDownloadThread(QThread):
    """抖音批量下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, urls, config):
        super().__init__()
        self.urls = urls
        self.config = config
        self.stopped = False

    def stop(self):
        """停止下载"""
        self.stopped = True

    def run(self):
        """执行批量下载"""
        try:
            total_count = len(self.urls)
            self.update_signal.emit(f"开始批量下载 {total_count} 个视频...")
            self.progress_signal.emit(0, "初始化批量下载...")

            from douyin import DouyinDownloader

            # 创建下载器
            downloader = DouyinDownloader(self.config, port="8080")

            # 进度回调函数
            def progress_callback(message, progress):
                if not self.stopped:
                    self.update_signal.emit(message)
                    self.progress_signal.emit(progress, message)

            # 批量下载
            result = downloader.download_videos_batch(self.urls, progress_callback)

            if self.stopped:
                return

            if result and result.get("success"):
                successful_count = result.get("successful_count", 0)
                failed_count = result.get("failed_count", 0)

                result_message = f"批量下载完成\n成功: {successful_count} 个\n失败: {failed_count} 个"

                self.result_signal.emit(result)
                self.finished_signal.emit(True, result_message)
            else:
                error_msg = result.get("error", "批量下载失败") if result else "批量下载失败"
                self.finished_signal.emit(False, error_msg)

        except Exception as e:
            if not self.stopped:
                self.update_signal.emit(f"批量下载失败: {str(e)}")
                self.finished_signal.emit(False, f"批量下载失败: {str(e)}")


class DouyinUserDownloadThread(QThread):
    """抖音用户主页批量下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, config, limit=0):
        super().__init__()
        self.url = url
        self.config = config
        self.limit = limit
        self.stopped = False

    def stop(self):
        self.stopped = True

    def run(self):
        try:
            self.update_signal.emit("开始批量下载用户视频...")
            self.progress_signal.emit(0, "初始化...")

            from douyin import DouyinDownloader

            downloader = DouyinDownloader(self.config)

            def progress_callback(message, progress):
                if not self.stopped:
                    self.update_signal.emit(message)
                    self.progress_signal.emit(progress, message)

            result = downloader.download_user_videos(self.url, self.limit, progress_callback)

            if self.stopped:
                return

            if result and result.get("success"):
                s = result.get("successful_count", 0)
                f = result.get("failed_count", 0)
                self.result_signal.emit(result)
                self.finished_signal.emit(True, f"批量下载完成：成功 {s} 个，失败 {f} 个")
            else:
                error = result.get("error", "下载失败") if result else "下载失败"
                self.finished_signal.emit(False, error)

        except Exception as e:
            if not self.stopped:
                self.finished_signal.emit(False, f"批量下载失败: {str(e)}")
