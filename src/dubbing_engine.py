"""
视频配音引擎 - 协调整个配音流程
整合下载、转录、翻译、TTS、合成等模块
"""

import os
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import shutil
import time

# 导入相关模块
try:
    from src.chinese_tts import ChineseTTS, check_kokoro_available
    from src.audio_utils import (
        extract_audio,
        combine_video_audio,
        get_audio_duration,
        get_video_duration
    )
except ImportError:
    # 相对导入备用
    from .chinese_tts import ChineseTTS, check_kokoro_available
    from .audio_utils import (
        extract_audio,
        combine_video_audio,
        get_audio_duration,
        get_video_duration
    )


class DubbingTask:
    """配音任务配置类"""

    def __init__(
        self,
        video_path: Optional[str] = None,
        youtube_url: Optional[str] = None,
        subtitle_path: Optional[str] = None,
        output_path: Optional[str] = None,
        voice: str = 'xiaobei',
        speed: float = 1.0,
        tts_backend: str = 'kokoro',
        cosyvoice_url: str = 'http://127.0.0.1:8877',
        cosyvoice_mode: str = 'sft',
        cosyvoice_speaker: str = '中文女',
        cosyvoice_instruction: str = '',
        keep_background_audio: bool = False,
        background_volume: float = 0.1,
        enable_translation: bool = True,
        enable_transcription: bool = True
    ):
        """
        初始化配音任务

        Args:
            video_path: 本地视频文件路径（与 youtube_url 二选一）
            youtube_url: YouTube 链接（与 video_path 二选一）
            subtitle_path: 字幕文件路径（可选，不提供则自动转录/翻译）
            output_path: 输出视频路径（可选，默认自动生成）
            voice: 配音音色
            speed: 语速
            tts_backend: TTS 后端，kokoro/cosyvoice
            cosyvoice_url: CosyVoice 本地服务地址
            cosyvoice_mode: CosyVoice 模式，sft/instruct
            cosyvoice_speaker: CosyVoice 音色
            cosyvoice_instruction: CosyVoice Instruct 指令
            keep_background_audio: 是否保留背景音
            background_volume: 背景音音量
            enable_translation: 是否启用字幕翻译
            enable_transcription: 是否启用自动转录
        """
        self.video_path = video_path
        self.youtube_url = youtube_url
        self.subtitle_path = subtitle_path
        self.output_path = output_path
        self.voice = voice
        self.speed = speed
        self.tts_backend = tts_backend
        self.cosyvoice_url = cosyvoice_url
        self.cosyvoice_mode = cosyvoice_mode
        self.cosyvoice_speaker = cosyvoice_speaker
        self.cosyvoice_instruction = cosyvoice_instruction
        self.keep_background_audio = keep_background_audio
        self.background_volume = background_volume
        self.enable_translation = enable_translation
        self.enable_transcription = enable_transcription

        # 内部状态
        self.temp_files: list = []
        self.downloaded_video: Optional[str] = None
        self.generated_subtitle: Optional[str] = None
        self.translated_subtitle: Optional[str] = None
        self.dubbing_audio: Optional[str] = None


class VideoDubbingEngine:
    """视频中文配音引擎"""

    # 处理步骤定义
    STEPS = [
        'download',      # 下载视频
        'transcribe',    # 生成英文字幕
        'translate',     # 翻译中文字幕
        'tts',           # 合成中文音频
        'combine',       # 合并最终视频
    ]

    # 临时文件保留模式（True=保留，False=清理）
    KEEP_TEMP_FILES = True

    def _get_temp_dir(self) -> str:
        """获取临时工作目录，使用 workspace/dubbing_temp/"""
        from .paths_config import DUBBING_TEMP_DIR
        temp_dir = DUBBING_TEMP_DIR
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def _get_timestamp(self) -> str:
        """获取时间戳用于生成唯一文件名"""
        return str(int(time.time() * 1000))

    def __init__(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        step_callback: Optional[Callable[[str, int], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        初始化配音引擎

        Args:
            progress_callback: 进度回调(percent, message)
            step_callback: 步骤回调(step_name, step_index)
            log_callback: 日志回调(message)
        """
        self.progress_callback = progress_callback
        self.step_callback = step_callback
        self.log_callback = log_callback

        # 检查依赖
        self.kokoro_available = check_kokoro_available()

    def _log(self, message: str):
        """输出日志"""
        if self.log_callback:
            self.log_callback(message)
        print(f"[Dubbing] {message}")

    def _report_progress(self, percent: int, message: str):
        """报告进度"""
        if self.progress_callback:
            self.progress_callback(percent, message)
        self._log(f"[{percent}%] {message}")

    def _report_step(self, step_name: str, step_index: int):
        """报告当前步骤"""
        if self.step_callback:
            self.step_callback(step_name, step_index)
        self._log(f"步骤 {step_index + 1}/{len(self.STEPS)}: {step_name}")

    def dub_video(self, task: DubbingTask) -> str:
        """
        执行完整配音流程

        Args:
            task: 配音任务配置

        Returns:
            输出视频路径
        """
        self._log("=" * 50)
        self._log("开始配音流程")
        self._log("=" * 50)

        try:
            # 步骤 1: 获取视频
            if task.youtube_url:
                self._report_step('download', 0)
                task.video_path = self._download_video(task.youtube_url)
                task.downloaded_video = task.video_path

            if not task.video_path or not os.path.exists(task.video_path):
                raise ValueError("视频文件不存在")

            # 步骤 2: 生成字幕（如果需要）
            if task.enable_transcription and not task.subtitle_path:
                self._report_step('transcribe', 1)
                task.generated_subtitle = self._transcribe_video(task.video_path)
                task.subtitle_path = task.generated_subtitle

            # 步骤 3: 翻译字幕（如果需要）
            if task.enable_translation and task.subtitle_path:
                self._report_step('translate', 2)
                task.translated_subtitle = self._translate_subtitle(
                    task.subtitle_path
                )
                task.subtitle_path = task.translated_subtitle

            # 检查字幕文件
            if not task.subtitle_path or not os.path.exists(task.subtitle_path):
                raise ValueError("字幕文件不存在")

            # 步骤 4: 合成中文音频
            self._report_step('tts', 3)
            task.dubbing_audio = self._synthesize_audio(
                task.subtitle_path,
                task.voice,
                task.speed,
                task.video_path,
                task.tts_backend,
                task.cosyvoice_url,
                task.cosyvoice_mode,
                task.cosyvoice_speaker,
                task.cosyvoice_instruction,
            )

            # 步骤 5: 合并最终视频
            self._report_step('combine', 4)
            output_path = self._combine_video(
                task.video_path,
                task.dubbing_audio,
                task.output_path,
                task.keep_background_audio,
                task.background_volume
            )

            # 清理临时文件
            self._cleanup_temp_files(task)

            self._log("=" * 50)
            self._log(f"配音完成: {output_path}")
            self._log("=" * 50)

            return output_path

        except Exception as e:
            self._log(f"[ERROR] 配音失败: {e}")
            # 失败时也尝试清理临时文件
            self._cleanup_temp_files(task)
            raise

    def _download_video(self, youtube_url: str) -> str:
        """下载 YouTube 视频"""
        from .youtube_transcriber import download_youtube_video

        self._report_progress(0, "开始下载视频...")

        # 使用 workspace/dubbing_temp/ 作为临时目录
        temp_dir = self._get_temp_dir()
        download_dir = os.path.join(temp_dir, f"download_{self._get_timestamp()}")
        os.makedirs(download_dir, exist_ok=True)

        # 下载视频
        self._report_progress(10, "开始下载视频...")
        video_path = download_youtube_video(
            youtube_url,
            output_dir=download_dir,
            audio_only=False  # 需要视频
        )

        self._report_progress(100, "视频下载完成")
        return video_path

    def _transcribe_video(self, video_path: str) -> str:
        """转录视频生成字幕"""
        from .youtube_transcriber import transcribe_audio_unified

        self._report_progress(0, "开始转录音频...")

        # 使用 workspace/dubbing_temp/ 作为临时目录
        temp_dir = self._get_temp_dir()
        audio_path = extract_audio(
            video_path,
            output_audio=os.path.join(temp_dir, f"audio_{self._get_timestamp()}.wav")
        )

        self._report_progress(30, "音频提取完成，开始转录...")

        # 转录 - 函数返回 (text_path, subtitle_path) 元组
        text_path, subtitle_path = transcribe_audio_unified(
            audio_path=audio_path,
            model_size="small",  # 使用小模型提升速度
            generate_subtitles=True,
            translate_to_chinese=False,  # 仅生成英文字幕
            source_language="en"
        )

        self._report_progress(100, f"转录完成: {subtitle_path}")
        return subtitle_path

    def _translate_subtitle(
        self,
        subtitle_path: str
    ) -> str:
        """翻译字幕为中文"""
        from .youtube_transcriber import translate_subtitle_file

        self._report_progress(0, "开始翻译字幕...")

        # 检查是否已经是中文
        # 简单检查：如果文件名包含 .zh. 或 _zh. 则跳过翻译
        if '.zh.' in subtitle_path or '_zh.' in subtitle_path:
            self._log("字幕似乎已经是中文，跳过翻译")
            self._report_progress(100, "跳过翻译")
            return subtitle_path

        # 翻译字幕
        translated_path = translate_subtitle_file(
            subtitle_path,
            target_language='zh-CN'
        )

        self._report_progress(100, f"翻译完成: {translated_path}")
        return translated_path

    def _synthesize_audio(
        self,
        subtitle_path: str,
        voice: str,
        speed: float,
        video_path: str = None,
        tts_backend: str = 'kokoro',
        cosyvoice_url: str = 'http://127.0.0.1:8877',
        cosyvoice_mode: str = 'sft',
        cosyvoice_speaker: str = '中文女',
        cosyvoice_instruction: str = '',
    ) -> str:
        """合成中文音频"""
        if tts_backend == 'cosyvoice':
            return self._synthesize_audio_cosyvoice(
                subtitle_path,
                cosyvoice_url,
                cosyvoice_mode,
                cosyvoice_speaker,
                cosyvoice_instruction,
            )

        if not self.kokoro_available:
            raise RuntimeError("Kokoro TTS 不可用，无法合成音频")

        self._report_progress(0, "初始化 TTS 引擎...")

        # 使用 workspace/dubbing_temp/ 作为临时音频目录
        temp_dir = self._get_temp_dir()
        temp_audio_path = os.path.join(temp_dir, f"dubbing_audio_{self._get_timestamp()}.wav")

        # 导入TTS相关库
        from .chinese_tts import ChineseTTS as CTTS
        import numpy as np
        import soundfile as sf

        # 创建TTS实例
        tts_instance = CTTS(voice=voice, speed=speed)

        # 解析字幕并合成
        segments = tts_instance._parse_srt(subtitle_path)
        sample_rate = 24000
        all_audio = []
        current_time = 0.0

        total_segments = len(segments)
        self._log(f"字幕解析完成，共 {total_segments} 段")

        for idx, seg in enumerate(segments):
            if idx < 3:  # 只显示前3段
                self._log(f"  段落 {idx+1}: {seg['start']:.2f}s - {seg['end']:.2f}s | {seg['text'][:30]}...")

        for idx, seg in enumerate(segments):
            if self.progress_callback:
                progress = int((idx / max(total_segments, 1)) * 100)
                self._report_progress(progress, f"合成第 {idx + 1}/{total_segments} 句...")

            # 添加静音填充（模拟自然停顿）
            if current_time < seg['start']:
                base_silence = seg['start'] - current_time
                # 根据句子类型调整停顿时长
                sent_type = tts_instance._analyze_sentence_type(seg['text'])
                if sent_type == 'question':
                    pause_multiplier = 1.5  # 问句后停顿稍长
                elif sent_type == 'ellipsis':
                    pause_multiplier = 2.0  # 省略号后停顿更长
                elif sent_type == 'exclamation':
                    pause_multiplier = 1.3  # 感叹句后中等停顿
                else:
                    pause_multiplier = 1.0
                silence_duration = base_silence * pause_multiplier
                silence_samples = int(silence_duration * sample_rate)
                if silence_samples > 0:
                    all_audio.append(np.zeros(silence_samples))
                current_time = seg['start']

            # 跳过空文本
            if not seg['text'].strip():
                self._log(f"  跳过空文本段落 {idx+1}")
                continue

            # 合成这段文本
            try:
                # 语气优化：问句稍慢，感叹句正常，陈述句正常
                sent_type = tts_instance._analyze_sentence_type(seg['text'])
                enhanced_text = tts_instance._enhance_text_for_tts(seg['text'], sent_type)

                if sent_type == 'question':
                    seg_speed = max(speed * 0.95, 0.8)  # 问句稍慢
                elif sent_type == 'statement':
                    seg_speed = speed
                elif sent_type == 'exclamation':
                    seg_speed = max(speed * 0.92, 0.8)  # 感叹句稍慢，突出情感
                elif sent_type == 'imperative':
                    seg_speed = max(speed * 0.95, 0.8)
                else:
                    seg_speed = speed

                generator = tts_instance.pipeline(enhanced_text, voice=tts_instance.voice_name, speed=seg_speed)
                seg_audios = []
                for _, _, audio in generator:
                    seg_audios.append(audio)

                if seg_audios:
                    seg_audio = np.concatenate(seg_audios)
                    all_audio.append(seg_audio)
                    current_time = seg['start'] + len(seg_audio) / sample_rate
            except Exception as e:
                self._log(f"  段落 {idx+1} 合成失败: {e}")
                continue

        # 保存音频文件
        self._log(f"合成完成，共 {len(all_audio)} 个音频片段")
        if all_audio:
            final_audio = np.concatenate(all_audio)
            self._log(f"最终音频长度: {len(final_audio)/sample_rate:.2f}秒")
            sf.write(temp_audio_path, final_audio, sample_rate)
            self._log(f"音频已保存到: {temp_audio_path}")
            # 验证文件
            if os.path.exists(temp_audio_path):
                file_size = os.path.getsize(temp_audio_path)
                self._log(f"文件大小: {file_size} bytes")
            else:
                raise RuntimeError(f"音频文件写入失败: {temp_audio_path}")
        else:
            raise RuntimeError("没有生成任何音频数据")

        self._report_progress(100, "音频合成完成")
        return temp_audio_path

    def _synthesize_audio_cosyvoice(
        self,
        subtitle_path: str,
        cosyvoice_url: str,
        cosyvoice_mode: str,
        cosyvoice_speaker: str,
        cosyvoice_instruction: str,
    ) -> str:
        """通过本地 CosyVoice TTS 服务合成中文音频。"""
        self._report_progress(0, "初始化 CosyVoice TTS 服务...")

        try:
            from .chinese_tts import ChineseTTS as CTTS
            from .cosyvoice_tts_client import CosyVoiceTTSClient
            import numpy as np
            import soundfile as sf
        except ImportError:
            from src.chinese_tts import ChineseTTS as CTTS
            from src.cosyvoice_tts_client import CosyVoiceTTSClient
            import numpy as np
            import soundfile as sf

        mode = 'instruct' if cosyvoice_mode == 'instruct' else 'sft'
        client = CosyVoiceTTSClient(
            base_url=cosyvoice_url,
            mode=mode,
            speaker=cosyvoice_speaker,
            instruction=cosyvoice_instruction,
        )
        try:
            health = client.check_health()
            self._log(f"CosyVoice 服务可用: {health.get('models_loaded', {})}")
        except Exception as exc:
            raise RuntimeError(f"CosyVoice 服务不可用，请先启动 tts_service.py: {exc}") from exc

        temp_dir = self._get_temp_dir()
        temp_audio_path = os.path.join(temp_dir, f"dubbing_audio_cosyvoice_{self._get_timestamp()}.wav")
        parser = CTTS.__new__(CTTS)
        segments = parser._parse_srt(subtitle_path)
        sample_rate = None
        all_audio = []
        current_time = 0.0

        total_segments = len(segments)
        self._log(f"字幕解析完成，共 {total_segments} 段")
        self._log(f"CosyVoice 模式: {mode}, speaker={cosyvoice_speaker}")

        for idx, seg in enumerate(segments):
            progress = int((idx / max(total_segments, 1)) * 100)
            self._report_progress(progress, f"CosyVoice 合成第 {idx + 1}/{total_segments} 句...")

            text = seg.get('text', '').strip()
            if not text:
                self._log(f"  跳过空文本段落 {idx + 1}")
                continue

            if sample_rate is not None and current_time < seg['start']:
                silence_duration = seg['start'] - current_time
                silence_samples = int(silence_duration * sample_rate)
                if silence_samples > 0:
                    all_audio.append(np.zeros(silence_samples, dtype=np.float32))
                current_time = seg['start']

            try:
                audio_path = client.synthesize(text)
                audio, sr = sf.read(audio_path, always_2d=False)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = audio.astype(np.float32)
                if sample_rate is None:
                    sample_rate = sr
                elif sr != sample_rate:
                    import librosa
                    audio = librosa.resample(audio, orig_sr=sr, target_sr=sample_rate).astype(np.float32)

                if current_time < seg['start']:
                    silence_duration = seg['start'] - current_time
                    silence_samples = int(silence_duration * sample_rate)
                    if silence_samples > 0:
                        all_audio.append(np.zeros(silence_samples, dtype=np.float32))
                    current_time = seg['start']

                all_audio.append(audio)
                current_time = seg['start'] + len(audio) / sample_rate
            except Exception as exc:
                self._log(f"  段落 {idx + 1} CosyVoice 合成失败: {exc}")
                continue

        if not all_audio or sample_rate is None:
            raise RuntimeError("CosyVoice 没有生成任何音频数据")

        final_audio = np.concatenate(all_audio)
        sf.write(temp_audio_path, final_audio, sample_rate)
        self._log(f"CosyVoice 音频已保存到: {temp_audio_path}")
        self._log(f"最终音频长度: {len(final_audio) / sample_rate:.2f}秒")

        self._report_progress(100, "CosyVoice 音频合成完成")
        return temp_audio_path

    def _combine_video(
        self,
        video_path: str,
        audio_path: str,
        output_path: Optional[str],
        keep_background: bool,
        bg_volume: float
    ) -> str:
        """合并视频和音频"""
        self._report_progress(50, "合成最终视频...")

        if output_path is None:
            # 自动生成输出路径
            base = Path(video_path).stem
            output_dir = Path(video_path).parent
            output_path = str(output_dir / f"{base}_中文配音.mp4")

        # 合并
        combine_video_audio(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            keep_original_audio=keep_background,
            original_audio_volume=bg_volume
        )

        self._report_progress(100, "视频合成完成")
        return output_path

    def _cleanup_temp_files(self, task: DubbingTask):
        """
        处理临时文件

        默认保留所有临时文件在 workspace/dubbing_temp/ 目录中，
        以便后续使用或调试。如果需要清理，可调用 purge_temp_files()。
        """
        self._log("临时文件保留在 workspace/dubbing_temp/ 目录中")
        self._log(f"  - 配音音频: {task.dubbing_audio}")
        if task.generated_subtitle:
            self._log(f"  - 原始字幕: {task.generated_subtitle}")
        if task.translated_subtitle:
            self._log(f"  - 翻译字幕: {task.translated_subtitle}")
        if task.downloaded_video:
            self._log(f"  - 下载视频: {task.downloaded_video}")

    def purge_temp_files(self, older_than_days: int = 7):
        """
        清理旧的临时文件（可选功能）

        Args:
            older_than_days: 清理多少天前的文件
        """
        import datetime

        temp_dir = self._get_temp_dir()
        if not os.path.exists(temp_dir):
            return

        cutoff_time = time.time() - (older_than_days * 24 * 60 * 60)
        removed_count = 0

        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isfile(item_path):
                if os.path.getmtime(item_path) < cutoff_time:
                    try:
                        os.unlink(item_path)
                        removed_count += 1
                        self._log(f"已清理: {item}")
                    except Exception as e:
                        self._log(f"清理失败 {item}: {e}")
            elif os.path.isdir(item_path):
                if 'download_' in item and os.path.getmtime(item_path) < cutoff_time:
                    try:
                        shutil.rmtree(item_path)
                        removed_count += 1
                        self._log(f"已清理目录: {item}")
                    except Exception as e:
                        self._log(f"清理目录失败 {item}: {e}")

        self._log(f"清理完成，共移除 {removed_count} 个项目")


def create_dubbed_video(
    video_path: str,
    subtitle_path: Optional[str] = None,
    output_path: Optional[str] = None,
    voice: str = 'xiaobei',
    speed: float = 1.0,
    **kwargs
) -> str:
    """
    快速为视频配音的便捷函数

    Args:
        video_path: 视频文件路径
        subtitle_path: 字幕文件路径（可选）
        output_path: 输出路径（可选）
        voice: 配音音色
        speed: 语速
        **kwargs: 其他参数

    Returns:
        输出视频路径
    """
    task = DubbingTask(
        video_path=video_path,
        subtitle_path=subtitle_path,
        output_path=output_path,
        voice=voice,
        speed=speed,
        **kwargs
    )

    engine = VideoDubbingEngine()
    return engine.dub_video(task)


if __name__ == '__main__':
    # 测试代码
    print("[INFO] 测试 VideoDubbingEngine...")

    if not check_kokoro_available():
        print("[ERROR] Kokoro 未安装")
        exit(1)

    # 这里需要实际的测试文件
    print("[OK] 配音引擎模块加载成功")
