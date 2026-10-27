"""
VideoHub 核心模块包
"""

from importlib import import_module

# Importing a lightweight local web service must not load Torch/Kokoro/Whisper.
# Preserve the public package exports, loading their original modules on use.
_MODULES = {
    **dict.fromkeys(['ChineseTTS', 'text_to_speech', 'check_kokoro_available'], '.chinese_tts'),
    **dict.fromkeys(['VideoDubbingEngine', 'DubbingTask', 'create_dubbed_video'], '.dubbing_engine'),
    **dict.fromkeys(['extract_audio', 'combine_video_audio', 'get_audio_duration',
                     'get_video_duration', 'check_ffmpeg_available'], '.audio_utils'),
}


def __getattr__(name):
    if name not in _MODULES:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(_MODULES[name], __name__), name)
    globals()[name] = value
    return value

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
