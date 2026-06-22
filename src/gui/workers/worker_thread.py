"""
工作线程模块
包含所有 QThread 子类，用于执行耗时操作避免界面卡顿
"""

from PyQt6.QtCore import QThread, pyqtSignal, QTimer


class WorkerThread(QThread):
    """主工作线程，用于执行各种视频处理任务"""
    update_signal = pyqtSignal(str)  # 更新信息信号
    progress_signal = pyqtSignal(int)  # 进度信号
    finished_signal = pyqtSignal(str, bool)  # 完成信号，参数：结果路径，是否成功

    def __init__(self, task_type, params):
        """
        初始化工作线程
        :param task_type: 任务类型
        :param params: 任务参数
        """
        super().__init__()
        self.task_type = task_type
        self.params = params
        self.is_running = True
        self.stopped = False

    def run(self):
        """执行任务"""
        try:
            # 根据任务类型执行不同的操作
            if not self.stopped and self.task_type == "youtube":
                self.process_youtube()
            elif not self.stopped and self.task_type == "twitter":
                self.process_twitter()
            elif not self.stopped and self.task_type == "bilibili":
                self.process_bilibili()
            elif not self.stopped and self.task_type == "instagram":
                self.process_instagram()
            elif not self.stopped and self.task_type == "koushare":
                self.process_koushare()
            elif not self.stopped and self.task_type == "local_audio":
                self.process_local_audio()
            elif not self.stopped and self.task_type == "local_video":
                self.process_local_video()
            elif not self.stopped and self.task_type == "local_video_batch":
                self.process_local_video_batch()
            elif not self.stopped and self.task_type == "local_text":
                self.process_local_text()
            elif not self.stopped and self.task_type == "batch":
                self.process_batch()
            elif not self.stopped and self.task_type == "dubbing":
                self.process_dubbing()
        except Exception as e:
            if not self.stopped:  # 只有在非停止状态下才报告错误
                import traceback
                error_msg = f"执行任务时出错: {str(e)}\n{traceback.format_exc()}"
                self.update_signal.emit(error_msg)
                self.finished_signal.emit("", False)

    def process_youtube(self):
        """处理YouTube视频"""
        from youtube_transcriber import (
            process_youtube_video,
            process_youtube_playlist,
            is_youtube_playlist_url,
            set_translation_verbose,
        )
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始处理YouTube视频...")

        # 从参数中获取值
        youtube_url = self.params.get("youtube_url", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        download_video = self.params.get("download_video", False)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        cookies_file = self.params.get("cookies_file", None)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        os.environ["TRANSLATION_POLISH_DEEPSEEK"] = "true" if enable_translation_polish else "false"
        prefer_native_subtitles = self.params.get("prefer_native_subtitles", True)
        show_translation_logs = self.params.get("show_translation_logs", True)
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        os.environ["TRANSLATION_POLISH_DEEPSEEK"] = "true" if enable_translation_polish else "false"

        # 重定向print输出到信号
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        # 替换全局print函数
        import builtins
        builtins.print = custom_print

        # 控制翻译日志详细程度
        try:
            set_translation_verbose(show_translation_logs)
        except Exception:
            pass

        try:
            # 检查是否为抖音URL
            try:
                from douyin import DouyinUtils, DouyinDownloader
                DOUYIN_AVAILABLE = True
            except ImportError:
                DOUYIN_AVAILABLE = False

            if DOUYIN_AVAILABLE and DouyinUtils.validate_url(youtube_url):
                self.update_signal.emit(f"检测到抖音视频，开始下载...")

                # 使用抖音下载器处理
                try:
                    # 创建下载器
                    downloader = DouyinDownloader()

                    # 检查是否为用户主页链接
                    self.update_signal.emit("正在判断链接类型...")
                    is_user_profile = self.params.get("is_user_profile", False) or DouyinUtils.is_user_profile_url(youtube_url)

                    if is_user_profile:
                        self.update_signal.emit("检测到用户主页链接，开始批量下载...")
                        def user_progress(message, progress):
                            self.update_signal.emit(f"[{progress}%] {message}")
                        result = downloader.download_user_videos(youtube_url, progress_callback=user_progress)
                        if result.get("success"):
                            s = result.get("successful_count", 0)
                            f = result.get("failed_count", 0)
                            self.update_signal.emit(f"✅ 批量下载完成：成功 {s} 个，失败 {f} 个")
                            self.finished_signal.emit("", True)
                        else:
                            self.update_signal.emit(f"❌ 批量下载失败: {result.get('error', '未知错误')}")
                            self.finished_signal.emit("", False)
                        return

                    # 单视频：获取视频信息
                    self.update_signal.emit("正在获取视频信息...")
                    video_info = downloader.get_video_info(youtube_url)

                    if not video_info:
                        self.update_signal.emit("❌ 无法获取抖音视频信息")
                        self.update_signal.emit("可能原因：")
                        self.update_signal.emit("1. 视频链接已失效或被删除")
                        self.update_signal.emit("2. douyinVd 服务器暂时不可用")
                        self.update_signal.emit("3. 网络连接问题")
                        self.update_signal.emit("建议：尝试使用其他抖音链接或稍后重试")
                        self.finished_signal.emit("抖音视频信息获取失败", False)
                        return

                    # 显示视频信息
                    summary = DouyinUtils.get_video_info_summary(video_info)
                    self.update_signal.emit(f"视频信息:\n{summary}")

                    # 下载视频
                    self.update_signal.emit("开始下载抖音视频...")
                    def progress_callback(message, progress):
                        self.update_signal.emit(f"[{progress}%] {message}")

                    result = downloader.download_video(youtube_url, progress_callback=progress_callback)

                    if result.get("success"):
                        downloaded_files = result.get("downloaded_files", [])
                        if downloaded_files:
                            video_file = None
                            for file_info in downloaded_files:
                                if file_info.get("type") == "video":
                                    video_file = file_info.get("path")
                                    break

                            if video_file:
                                self.update_signal.emit(f"✅ 抖音视频下载完成: {video_file}")

                                # 检查是否需要执行转录和摘要
                                if enable_transcription or generate_article:
                                    self._process_douyin_transcription_and_summary(
                                        video_file, model, api_key, base_url, whisper_model_size,
                                        stream, summary_dir, custom_prompt, template_path,
                                        generate_subtitles, translate_to_chinese, embed_subtitles,
                                        enable_transcription, generate_article
                                    )
                                else:
                                    self.finished_signal.emit(video_file, True)
                            else:
                                self.update_signal.emit("✅ 抖音视频处理完成")
                                self.finished_signal.emit("", True)
                        else:
                            self.update_signal.emit("✅ 抖音视频处理完成")
                            self.finished_signal.emit("", True)
                    else:
                        error_msg = result.get("error", "未知错误")
                        self.update_signal.emit(f"❌ 抖音视频下载失败: {error_msg}")
                        self.finished_signal.emit("", False)

                    return

                except Exception as e:
                    self.update_signal.emit(f"❌ 抖音视频处理异常: {str(e)}")
                    self.finished_signal.emit("", False)
                    return

            # 检查是否为播放列表URL
            elif is_youtube_playlist_url(youtube_url):
                self.update_signal.emit(f"检测到YouTube播放列表，开始批量处理...")
                # 调用播放列表处理函数
                results = process_youtube_playlist(
                    youtube_url, model, api_key, base_url, whisper_model_size,
                    stream, summary_dir, download_video, custom_prompt,
                    template_path, generate_subtitles, translate_to_chinese,
                    embed_subtitles, cookies_file, enable_transcription, generate_article,
                    prefer_native_subtitles, enable_translation_polish
                )

                if results:
                    success_count = sum(1 for result in results.values() if result.get("status") == "success")
                    total_count = len(results)
                    self.update_signal.emit(f"播放列表处理完成! 成功处理 {success_count}/{total_count} 个视频")

                    # 返回第一个成功的结果作为主要结果
                    first_success = None
                    for result in results.values():
                        if result.get("status") == "success":
                            first_success = result.get("summary_path")
                            break

                    self.finished_signal.emit(first_success or "", success_count > 0)
                else:
                    self.update_signal.emit("播放列表处理失败，请检查错误信息。")
                    self.finished_signal.emit("", False)
            else:
                # 调用原始代码中的处理函数
                result = process_youtube_video(
                    youtube_url, model, api_key, base_url, whisper_model_size,
                    stream, summary_dir, download_video, custom_prompt,
                    template_path, generate_subtitles, translate_to_chinese,
                    embed_subtitles, cookies_file, enable_transcription, generate_article,
                    prefer_native_subtitles, enable_translation_polish
                )

                if result:
                    self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                    self.finished_signal.emit(result, True)
                else:
                    self.update_signal.emit("处理失败，请检查错误信息。")
                    self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            # 恢复原始print函数
            builtins.print = original_print

    def _process_douyin_transcription_and_summary(self, video_file, model, api_key, base_url,
                                                   whisper_model_size, stream, summary_dir,
                                                   custom_prompt, template_path, generate_subtitles,
                                                   translate_to_chinese, embed_subtitles,
                                                   enable_transcription, generate_article):
        """处理抖音视频的转录和摘要"""
        try:
            from youtube_transcriber import process_local_video

            self.update_signal.emit("开始处理抖音视频转录和摘要...")

            # 执行转录和摘要处理
            result = process_local_video(
                video_file, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, None  # source_language
            )

            if result:
                self.update_signal.emit(f"✅ 抖音视频转录和摘要完成！结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("⚠️ 转录和摘要处理失败，但视频下载成功")
                self.finished_signal.emit(video_file, True)

        except Exception as e:
            self.update_signal.emit(f"❌ 转录处理失败: {str(e)}")
            # 即使转录失败，视频下载成功也算成功
            self.finished_signal.emit(video_file, True)

    def process_twitter(self):
        """处理Twitter视频 - 使用yt-dlp下载"""
        from paths_config import TWITTER_DOWNLOADS_DIR

        self.update_signal.emit("开始处理Twitter视频...")

        # 从参数中获取Twitter URL
        twitter_url = self.params.get("url", "")
        if not twitter_url:
            self.update_signal.emit("错误: 未提供Twitter URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"Twitter URL: {twitter_url}")

        try:
            import yt_dlp
            import os

            # 创建下载目录
            download_dir = TWITTER_DOWNLOADS_DIR
            os.makedirs(download_dir, exist_ok=True)

            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': False,
            }

            self.update_signal.emit("正在下载Twitter视频...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(twitter_url, download=True)
                video_title = info.get('title', 'twitter_video')
                video_ext = info.get('ext', 'mp4')
                video_file = os.path.join(download_dir, f"{video_title}.{video_ext}")

                self.update_signal.emit(f"✓ Twitter视频下载完成!")
                self.update_signal.emit(f"保存位置: {video_file}")
                self.finished_signal.emit(video_file, True)

        except Exception as e:
            import traceback
            error_msg = f"Twitter视频下载失败: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(error_msg)
            self.finished_signal.emit("", False)

    def process_bilibili(self):
        """处理Bilibili视频 - 使用yt-dlp下载"""
        from paths_config import BILIBILI_DOWNLOADS_DIR

        self.update_signal.emit("开始处理Bilibili视频...")

        # 从参数中获取Bilibili URL
        bilibili_url = self.params.get("url", "")
        if not bilibili_url:
            self.update_signal.emit("错误: 未提供Bilibili URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"Bilibili URL: {bilibili_url}")

        try:
            import yt_dlp
            import os

            # 创建下载目录
            download_dir = BILIBILI_DOWNLOADS_DIR
            os.makedirs(download_dir, exist_ok=True)

            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': False,
            }

            self.update_signal.emit("正在下载Bilibili视频...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(bilibili_url, download=True)
                video_title = info.get('title', 'bilibili_video')
                video_ext = info.get('ext', 'mp4')
                video_file = os.path.join(download_dir, f"{video_title}.{video_ext}")

                self.update_signal.emit(f"✓ Bilibili视频下载完成!")
                self.update_signal.emit(f"保存位置: {video_file}")
                self.finished_signal.emit(video_file, True)

        except Exception as e:
            import traceback
            error_msg = f"Bilibili视频下载失败: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(error_msg)
            self.finished_signal.emit("", False)

    def process_instagram(self):
        """Download Instagram video with yt-dlp."""
        from paths_config import INSTAGRAM_DOWNLOADS_DIR

        self.update_signal.emit("开始处理Instagram视频...")

        instagram_url = self.params.get("url", "")
        if not instagram_url:
            self.update_signal.emit("错误: 未提供Instagram URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"Instagram URL: {instagram_url}")

        try:
            import os
            import time
            from pathlib import Path
            import yt_dlp

            download_dir = INSTAGRAM_DOWNLOADS_DIR
            os.makedirs(download_dir, exist_ok=True)
            before = {p.resolve() for p in Path(download_dir).glob("*") if p.is_file()}
            started_at = time.time()

            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": os.path.join(download_dir, "%(title).180B_%(id)s.%(ext)s"),
                "quiet": False,
                "no_warnings": False,
                "noplaylist": True,
            }
            cookies_file = self.params.get("cookies_file")
            if cookies_file:
                ydl_opts["cookiefile"] = cookies_file

            self.update_signal.emit("正在下载Instagram视频...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(instagram_url, download=True)
                candidates = []
                for item in info.get("requested_downloads") or []:
                    filepath = item.get("filepath")
                    if filepath:
                        candidates.append(Path(filepath))
                candidates.append(Path(ydl.prepare_filename(info)))

            existing = [p for p in candidates if p.exists()]
            if not existing:
                after = [p for p in Path(download_dir).glob("*") if p.is_file()]
                existing = [
                    p for p in after
                    if p.resolve() not in before and p.stat().st_mtime >= started_at - 2
                ]

            if not existing:
                raise RuntimeError("Instagram视频下载完成但未找到输出文件")

            video_file = str(max(existing, key=lambda p: p.stat().st_mtime))
            self.update_signal.emit("✓ Instagram视频下载完成!")
            self.update_signal.emit(f"保存位置: {video_file}")
            self.finished_signal.emit(video_file, True)

        except Exception as e:
            import traceback
            error_msg = f"Instagram视频下载失败: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(error_msg)
            self.finished_signal.emit("", False)

    def process_koushare(self):
        """处理寇享视频 - 使用自定义下载器"""
        from paths_config import KOUSHARE_DOWNLOADS_DIR

        self.update_signal.emit("开始处理寇享视频...")

        url = self.params.get("url", "")
        if not url:
            self.update_signal.emit("错误: 未提供寇享视频 URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"寇享 URL: {url}")

        try:
            import koushare_downloader

            def progress_callback(message, percent):
                if not self.stopped:
                    self.update_signal.emit(f"[{percent}%] {message}")

            result = koushare_downloader.download(
                url,
                output_dir=KOUSHARE_DOWNLOADS_DIR,
                progress_callback=progress_callback,
            )

            if self.stopped:
                return

            if result.get("success"):
                file_path = result.get("file_path", "")
                title = result.get("title", "")
                self.update_signal.emit(f"✅ 寇享视频下载完成: {title}")
                self.update_signal.emit(f"保存位置: {file_path}")
                self.finished_signal.emit(file_path, True)
            else:
                error = result.get("error", "未知错误")
                self.update_signal.emit(f"❌ 寇享视频下载失败: {error}")
                self.finished_signal.emit("", False)

        except Exception as e:
            import traceback
            self.update_signal.emit(f"❌ 寇享视频下载异常: {str(e)}\n{traceback.format_exc()}")
            self.finished_signal.emit("", False)

    def process_local_audio(self):
        """处理本地音频文件"""
        from youtube_transcriber import process_local_audio
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始处理本地音频文件...")

        # 从参数中获取值
        audio_path = self.params.get("audio_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        os.environ["TRANSLATION_POLISH_DEEPSEEK"] = "true" if enable_translation_polish else "false"

        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        import builtins
        builtins.print = custom_print

        try:
            # 调用原始代码中的处理函数
            result = process_local_audio(
                audio_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, enable_transcription, generate_article,
                enable_translation_polish
            )

            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print

    def process_local_video(self):
        """处理本地视频文件"""
        from youtube_transcriber import process_local_video
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始处理本地视频文件...")

        # 从参数中获取值
        video_path = self.params.get("video_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        source_language = self.params.get("source_language", None)
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        os.environ["TRANSLATION_POLISH_DEEPSEEK"] = "true" if enable_translation_polish else "false"

        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        import builtins
        builtins.print = custom_print

        try:
            # 调用原始代码中的处理函数
            result = process_local_video(
                video_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language, enable_translation_polish
            )

            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print

    def process_local_video_batch(self):
        """批量处理本地视频文件"""
        from youtube_transcriber import process_local_videos_batch
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始批量处理本地视频文件...")

        # 从参数中获取值
        input_path = self.params.get("video_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        source_language = self.params.get("source_language", None)
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        os.environ["TRANSLATION_POLISH_DEEPSEEK"] = "true" if enable_translation_polish else "false"

        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        import builtins
        builtins.print = custom_print

        try:
            # 调用批量处理函数
            results = process_local_videos_batch(
                input_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language, enable_translation_polish
            )

            if results:
                # 统计成功和失败的数量
                success_count = sum(1 for result in results if result.get("status") == "success")
                failed_count = sum(1 for result in results if result.get("status") in ["failed", "error"])
                skipped_count = sum(1 for result in results if result.get("status") == "skipped")

                self.update_signal.emit(f"\n批量处理完成!")
                self.update_signal.emit(f"成功: {success_count} 个，失败: {failed_count} 个，跳过: {skipped_count} 个")

                # 如果有成功的文件，返回第一个成功的结果路径
                success_results = [r for r in results if r.get("status") == "success"]
                if success_results:
                    self.finished_signal.emit(success_results[0].get("result_path", ""), True)
                else:
                    self.finished_signal.emit("", len(results) > 0)
            else:
                self.update_signal.emit("批量处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"批量处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print

    def process_local_text(self):
        """处理本地文本文件"""
        from youtube_transcriber import process_local_text
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始处理本地文本文件...")

        # 从参数中获取值
        text_path = self.params.get("text_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)

        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        import builtins
        builtins.print = custom_print

        try:
            # 调用原始代码中的处理函数
            result = process_local_text(
                text_path, model, api_key, base_url, stream,
                summary_dir, custom_prompt, template_path
            )

            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print

    def process_batch(self):
        """批量处理YouTube视频"""
        from youtube_transcriber import process_youtube_videos_batch
        from paths_config import DEFAULT_SUMMARY_DIR

        self.update_signal.emit("开始批量处理YouTube视频...")

        # 从参数中获取值
        youtube_urls = self.params.get("youtube_urls", [])
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        download_video = self.params.get("download_video", False)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        cookies_file = self.params.get("cookies_file", None)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)

        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)

        import builtins
        builtins.print = custom_print

        try:
            # 调用原始代码中的处理函数
            results = process_youtube_videos_batch(
                youtube_urls, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, download_video, custom_prompt,
                template_path, generate_subtitles, translate_to_chinese,
                embed_subtitles, cookies_file, enable_transcription, generate_article,
                True, enable_translation_polish
            )

            # 统计成功和失败的数量
            success_count = sum(1 for result in results.values() if result.get("status") == "success")
            failed_count = sum(1 for result in results.values() if result.get("status") == "failed")

            self.update_signal.emit(f"\n批量处理完成!")
            self.update_signal.emit(f"总计: {len(youtube_urls)} 个视频")
            self.update_signal.emit(f"成功: {success_count} 个视频")
            self.update_signal.emit(f"失败: {failed_count} 个视频")

            if failed_count > 0:
                self.update_signal.emit("\n失败的视频:")
                for url, result in results.items():
                    if result.get("status") == "failed":
                        self.update_signal.emit(f"- {url}: {result.get('error', '未知错误')}")

            # 返回结果
            self.finished_signal.emit(str(results), success_count > 0)
        except Exception as e:
            self.update_signal.emit(f"批量处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print

    def process_dubbing(self):
        """处理中文配音任务"""
        from src.dubbing_engine import VideoDubbingEngine, DubbingTask
        from src.chinese_tts import check_kokoro_available
        from src.audio_utils import combine_video_audio
        from src.paths_config import DUBBING_OUTPUT_DIR

        self.update_signal.emit("🎙️ 开始中文配音流程...")

        # 获取参数
        video_path = self.params.get("video_path", "")
        youtube_url = self.params.get("youtube_url", "")
        subtitle_path = self.params.get("subtitle_path", "")
        output_path = self.params.get("output_path", "")
        voice = self.params.get("voice", "xiaobei")
        speed = self.params.get("speed", 1.0)
        tts_backend = self.params.get("tts_backend", "kokoro")
        cosyvoice_url = self.params.get("cosyvoice_url", "http://127.0.0.1:8877")
        cosyvoice_mode = self.params.get("cosyvoice_mode", "sft")
        cosyvoice_speaker = self.params.get("cosyvoice_speaker", "中文女")
        cosyvoice_instruction = self.params.get("cosyvoice_instruction", "")
        subtitle_burn_mode = self.params.get("subtitle_burn_mode", "none")
        enable_translation_polish = self.params.get("enable_translation_polish", False)
        enable_transcription = self.params.get("enable_transcription", True)
        enable_translation = self.params.get("enable_translation", True)
        audio_only_mode = self.params.get("audio_only_mode", False)
        dubbing_audio_path = self.params.get("dubbing_audio_path", "")

        # 音频+字幕模式：仅合成，不转录翻译
        if audio_only_mode and dubbing_audio_path and video_path:
            self.update_signal.emit("📦 音频+字幕模式：直接合成音频到视频")
            self.update_signal.emit(f"  配音音频: {dubbing_audio_path}")
            self.update_signal.emit(f"  目标视频: {video_path}")

            try:
                import os
                import time

                output_dir = DUBBING_OUTPUT_DIR
                os.makedirs(output_dir, exist_ok=True)

                # 生成输出文件名
                timestamp = int(time.time() * 1000)
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                output_path = os.path.join(output_dir, f"{base_name}_配音_{timestamp}.mp4")

                # 直接合成音频到视频
                self.update_signal.emit("🎬 开始合成...")
                combine_video_audio(
                    video_path=video_path,
                    audio_path=dubbing_audio_path,
                    output_path=output_path,
                    keep_original_audio=False,
                    original_audio_volume=0.1
                )

                self.update_signal.emit("=" * 50)
                self.update_signal.emit("✅ 合成完成！")
                self.update_signal.emit(f"📁 输出文件: {output_path}")
                self.update_signal.emit("=" * 50)

                self.finished_signal.emit(output_path, True)
                return

            except Exception as e:
                import traceback
                self.update_signal.emit(f"[ERROR] 合成失败: {str(e)}")
                self.update_signal.emit(traceback.format_exc())
                self.finished_signal.emit("", False)
                return

        # 检查 TTS 后端是否可用（非音频模式）
        if tts_backend != "cosyvoice" and not check_kokoro_available():
            self.update_signal.emit("[ERROR] Kokoro TTS 未安装，请先运行: pip install kokoro>=0.9.4 soundfile")
            self.finished_signal.emit("", False)
            return
        if tts_backend == "cosyvoice":
            self.update_signal.emit(f"🔊 使用 CosyVoice TTS: {cosyvoice_mode}, speaker={cosyvoice_speaker}")
            self.update_signal.emit(f"   服务地址: {cosyvoice_url}")
        if subtitle_burn_mode != "none":
            self.update_signal.emit(f"📝 配音完成后烧录字幕: {subtitle_burn_mode}")

        # 创建配音任务
        task = DubbingTask(
            video_path=video_path if video_path else None,
            youtube_url=youtube_url if youtube_url else None,
            subtitle_path=subtitle_path if subtitle_path else None,
            output_path=output_path if output_path else None,
            voice=voice,
            speed=speed,
            tts_backend=tts_backend,
            cosyvoice_url=cosyvoice_url,
            cosyvoice_mode=cosyvoice_mode,
            cosyvoice_speaker=cosyvoice_speaker,
            cosyvoice_instruction=cosyvoice_instruction,
            subtitle_burn_mode=subtitle_burn_mode,
            enable_translation_polish=enable_translation_polish,
            enable_transcription=enable_transcription,
            enable_translation=enable_translation
        )

        # 创建引擎并设置回调
        def progress_callback(percent, message):
            self.update_signal.emit(f"[{percent}%] {message}")
            self.progress_signal.emit(percent)

        def step_callback(step_name, step_index):
            total_steps = 6 if subtitle_burn_mode != "none" else 5
            step_names = {
                'download': '📥 下载视频',
                'transcribe': '📝 生成英文字幕',
                'translate': '🌐 翻译中文字幕',
                'tts': '🔊 合成中文音频',
                'combine': '🎬 合成最终视频',
                'subtitle': '📝 烧录字幕'
            }
            display_name = step_names.get(step_name, step_name)
            self.update_signal.emit(f"步骤 {step_index + 1}/{total_steps}: {display_name}")

        def log_callback(message):
            self.update_signal.emit(message)

        engine = VideoDubbingEngine(
            progress_callback=progress_callback,
            step_callback=step_callback,
            log_callback=log_callback
        )

        try:
            # 执行配音
            result_path = engine.dub_video(task)

            self.update_signal.emit("=" * 50)
            self.update_signal.emit(f"✅ 配音完成！")
            self.update_signal.emit(f"📁 输出文件: {result_path}")
            self.update_signal.emit("=" * 50)

            self.finished_signal.emit(result_path, True)

        except Exception as e:
            import traceback
            self.update_signal.emit(f"[ERROR] 配音失败: {str(e)}")
            self.update_signal.emit(traceback.format_exc())
            self.finished_signal.emit("", False)

    def stop(self):
        """停止线程"""
        self.stopped = True
        self.is_running = False
        self.update_signal.emit("正在停止任务...")
        # 等待一小段时间，给线程一个优雅停止的机会
        QTimer.singleShot(500, self.terminate)
