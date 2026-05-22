"""
VideoHub 核心模块包
"""

from .chinese_tts import ChineseTTS, text_to_speech, check_kokoro_available
from .dubbing_engine import VideoDubbingEngine, DubbingTask, create_dubbed_video
from .audio_utils import (
    extract_audio,
    combine_video_audio,
    get_audio_duration,
    get_video_duration,
    check_ffmpeg_available
)

__all__ = [
    'ChineseTTS',
    'text_to_speech',
    'check_kokoro_available',
    'VideoDubbingEngine',
    'DubbingTask',
    'create_dubbed_video',
    'extract_audio',
    'combine_video_audio',
    'get_audio_duration',
    'get_video_duration',
    'check_ffmpeg_available'
]
