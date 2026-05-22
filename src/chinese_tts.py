"""
中文 TTS 模块 - 基于 Kokoro
用于将中文字幕合成为语音
"""

import os
import re
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple

# 尝试导入 Kokoro，如果失败则标记不可用
try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    print("[WARNING] Kokoro 未安装，中文配音功能不可用。请运行: pip install kokoro>=0.9.4 soundfile")


class ChineseTTS:
    """中文语音合成器 - 基于 Kokoro TTS"""

    # 可用音色映射表
    VOICES = {
        'xiaobei': 'zf_xiaobei',      # 女声 - 小贝
        'xiaoxiao': 'zf_xiaoxiao',    # 女声 - 晓晓
        'xiaoyi': 'zf_xiaoyi',        # 女声 - 小艺
        'yunjian': 'zm_yunjian',      # 男声 - 云健
        'yunyang': 'zm_yunyang',      # 男声 - 云扬
    }

    # 音色显示名称映射
    VOICE_DISPLAY_NAMES = {
        'xiaobei': '晓贝 (女声)',
        'xiaoxiao': '晓晓 (女声)',
        'xiaoyi': '晓艺 (女声)',
        'yunjian': '云健 (男声)',
        'yunyang': '云扬 (男声)',
    }

    def __init__(self, voice: str = 'xiaobei', speed: float = 1.0):
        """
        初始化 TTS

        Args:
            voice: 音色名称，可选 xiaobei/xiaoxiao/xiaoyi/yunjian/yunyang
            speed: 语速，1.0 为正常，0.8 稍慢，1.2 稍快
        """
        if not KOKORO_AVAILABLE:
            raise RuntimeError("Kokoro 未安装，无法使用中文TTS功能")

        self.voice_name = self.VOICES.get(voice, 'zf_xiaobei')
        self.speed = speed
        self.pipeline = KPipeline(lang_code='z')  # 'z' = 中文普通话

    def _get_temp_audio_path(self) -> str:
        """获取临时音频文件路径，使用 workspace/dubbing_temp/"""
        try:
            from .paths_config import WORKSPACE_DIR
        except ImportError:
            from src.paths_config import WORKSPACE_DIR

        temp_dir = os.path.join(WORKSPACE_DIR, "dubbing_temp")
        os.makedirs(temp_dir, exist_ok=True)
        return os.path.join(temp_dir, f"tts_audio_{int(time.time() * 1000)}.wav")

    def synthesize(self, text: str, output_path: str = None) -> str:
        """
        合成单段文本

        Args:
            text: 要合成的中文文本
            output_path: 输出音频路径，默认创建临时文件

        Returns:
            输出音频文件路径
        """
        if output_path is None:
            output_path = self._get_temp_audio_path()

        # 清理文本
        text = self._clean_text(text)

        if not text:
            # 空文本生成静音
            silence = np.zeros(24000)  # 1秒静音
            sf.write(output_path, silence, 24000)
            return output_path

        generator = self.pipeline(
            text,
            voice=self.voice_name,
            speed=self.speed
        )

        # 收集所有音频片段
        audios = []
        for _, _, audio in generator:
            audios.append(audio)

        if audios:
            full_audio = np.concatenate(audios)
            sf.write(output_path, full_audio, 24000)  # 24kHz

        return output_path

    def synthesize_from_subtitle(
        self,
        subtitle_path: str,
        output_path: str = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, List[Dict]]:
        """
        按字幕时间轴合成音频

        Args:
            subtitle_path: SRT 字幕文件路径
            output_path: 输出音频路径
            progress_callback: 进度回调函数(percent, message)

        Returns:
            (音频文件路径, 调整后的时间轴列表)
        """
        if output_path is None:
            output_path = self._get_temp_audio_path()

        # 解析字幕
        segments = self._parse_srt(subtitle_path)
        total_segments = len(segments)

        # 按时间轴生成音频
        sample_rate = 24000
        all_audio = []
        current_time = 0.0
        adjusted_segments = []

        for idx, seg in enumerate(segments):
            # 报告进度
            if progress_callback:
                progress = int((idx / total_segments) * 100)
                progress_callback(progress, f"合成第 {idx + 1}/{total_segments} 句...")

            # 如果当前时间小于片段开始时间，添加静音
            if current_time < seg['start']:
                silence_duration = seg['start'] - current_time
                silence_samples = int(silence_duration * sample_rate)
                if silence_samples > 0:
                    all_audio.append(np.zeros(silence_samples))
                current_time = seg['start']

            # 生成这段文本的音频
            text = seg['text']
            sent_type = self._analyze_sentence_type(text)
            enhanced_text = self._enhance_text_for_tts(text, sent_type)
            generator = self.pipeline(enhanced_text, voice=self.voice_name, speed=self.speed)

            seg_audios = []
            for _, _, audio in generator:
                seg_audios.append(audio)

            if seg_audios:
                seg_audio = np.concatenate(seg_audios)
                all_audio.append(seg_audio)

                # 记录实际音频时长
                actual_duration = len(seg_audio) / sample_rate
                adjusted_segments.append({
                    **seg,
                    'actual_duration': actual_duration,
                    'audio_samples': len(seg_audio)
                })

                # 更新当前时间
                current_time = seg['start'] + actual_duration
            else:
                # 合成失败，添加静音
                adjusted_segments.append({
                    **seg,
                    'actual_duration': 0,
                    'audio_samples': 0
                })

        # 合并所有音频
        if all_audio:
            final_audio = np.concatenate(all_audio)
            sf.write(output_path, final_audio, sample_rate)

        if progress_callback:
            progress_callback(100, "音频合成完成")

        return output_path, adjusted_segments

    def _clean_text(self, text: str) -> str:
        """清理文本，移除不必要的符号"""
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除多余空格
        text = ' '.join(text.split())
        # 保留中英文、数字和常用标点（包括！？？等影响语气的）
        text = re.sub(r'[^一-龥a-zA-Z0-9，。！？、：；""''（）【】\[()].!?,:\s]', '', text)
        return text.strip()

    def _analyze_sentence_type(self, text: str) -> str:
        """
        分析句子类型，用于语气优化

        Returns:
            'question' - 疑问句
            'exclamation' - 感叹句
            'ellipsis' - 省略号/留白
            'statement' - 普通陈述句
            'imperative' - 祈使句
        """
        text = text.strip()
        if not text:
            return 'statement'

        # 句末标点判断
        if text.endswith('?') or text.endswith('？'):
            return 'question'
        elif text.endswith('!') or text.endswith('！'):
            return 'exclamation'
        elif '…' in text or '......' in text or '——' in text:
            return 'ellipsis'
        elif text.endswith('.') or text.endswith('。') or text.endswith('；') or text.endswith('；'):
            return 'statement'
        elif any(kw in text for kw in ['请', '让', '不要', '必须', '应该', '可以']):
            return 'imperative'
        return 'statement'

    def _split_into_sentences(self, text: str) -> List[Dict]:
        """
        将一段字幕文本按句子拆分，保留语气信息

        Returns:
            List of dicts with 'text', 'type', 'pause_before', 'pause_after'
        """
        results = []
        text = text.strip()
        if not text:
            return results

        # 句子分隔符
        sentence_enders = r'([。！？；])'

        parts = re.split(sentence_enders, text)
        # parts 类似: ['今天天气很好', '，', '我们一起出去', '！', '吧', '。']

        i = 0
        while i < len(parts):
            chunk = parts[i]
            if not chunk.strip():
                i += 1
                continue

            # 合并标点到上一个句子
            sentence_text = chunk
            if i + 1 < len(parts) and re.match(r'^[,，、；：]$', parts[i + 1]):
                i += 1  # 跳过这些中间标点

            # 收集后面的完整句子标点
            while i + 1 < len(parts):
                next_chunk = parts[i + 1]
                if re.match(r'^[。！？；]$', next_chunk):
                    sentence_text += next_chunk
                    i += 1
                    break
                elif re.match(r'^[,，、：]$', next_chunk):
                    # 内部标点，合并但不作为结束
                    sentence_text += next_chunk
                    i += 1
                    i += 1  # 跳过对应的空部分
                    break
                else:
                    break

            if sentence_text.strip():
                sent_type = self._analyze_sentence_type(sentence_text)
                results.append({
                    'text': sentence_text.strip(),
                    'type': sent_type
                })
            i += 1

        return results

    def _enhance_text_for_tts(self, text: str, sentence_type: str = 'statement') -> str:
        """
        为 TTS 优化文本，添加语气提示

        虽然 Kokoro 不直接支持情感标签，但文本预处理可以让合成更自然：
        1. 问句句尾语调上扬暗示
        2. 感叹句适当强调
        3. 省略号用空格模拟停顿
        """
        text = text.strip()
        if not text:
            return text

        if sentence_type == 'question':
            # 问句：句末添加轻微延长，让语调自然过渡
            text = re.sub(r'[？\?]+$', '', text).strip()
            text += '……'  # 用省略号暗示语调变化
        elif sentence_type == 'ellipsis':
            # 省略号：用空格模拟自然停顿感
            text = re.sub(r'…+', '……', text)
            text = re.sub(r'\.{3,}', '……', text)
        elif sentence_type == 'exclamation':
            # 感叹句：适当重复强调词
            text = re.sub(r'！+$', '', text).strip()
            # 不做额外处理，保持原有强度

        return text

    def _parse_srt(self, subtitle_path: str) -> List[Dict]:
        """解析 SRT 字幕文件"""
        segments = []

        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 按空行分割块
        blocks = re.split(r'\n\s*\n', content.strip())

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                # 第1行: 序号
                # 第2行: 时间码
                # 第3行+: 文本
                time_line = lines[1]
                text = '\n'.join(lines[2:])

                # 解析时间码 00:00:01,000 --> 00:00:04,000
                match = re.match(
                    r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})',
                    time_line
                )
                if match:
                    start_str = match.group(1)
                    end_str = match.group(2)
                    start = self._time_to_seconds(start_str)
                    end = self._time_to_seconds(end_str)

                    segments.append({
                        'text': text.strip(),
                        'start': start,
                        'end': end,
                        'duration': end - start
                    })

        return segments

    def _time_to_seconds(self, time_str: str) -> float:
        """将时间字符串转换为秒"""
        time_str = time_str.replace(',', '.')
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds


def text_to_speech(
    text: str,
    output_path: str = None,
    voice: str = 'xiaobei',
    speed: float = 1.0
) -> str:
    """快速合成单段文本的便捷函数"""
    tts = ChineseTTS(voice=voice, speed=speed)
    return tts.synthesize(text, output_path)


def check_kokoro_available() -> bool:
    """检查 Kokoro 是否可用"""
    return KOKORO_AVAILABLE


if __name__ == '__main__':
    # 测试代码
    if not KOKORO_AVAILABLE:
        print("[ERROR] Kokoro 未安装，请运行: pip install kokoro>=0.9.4 soundfile")
        exit(1)

    print("[INFO] 测试 ChineseTTS...")
    tts = ChineseTTS(voice='xiaobei', speed=1.0)

    # 测试单句合成
    test_text = "你好，这是一个中文语音合成测试。"
    output = tts.synthesize(test_text, "test_output.wav")
    print(f"[OK] 单句合成完成: {output}")

    # 测试字幕文件合成（如果有测试字幕）
    test_srt = "test_subtitle.srt"
    if Path(test_srt).exists():
        def progress(p, m):
            print(f"  [{p}%] {m}")
        output2, _ = tts.synthesize_from_subtitle(test_srt, "test_dubbing.wav", progress)
        print(f"[OK] 字幕合成完成: {output2}")
