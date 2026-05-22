"""
音频和视频处理工具模块
提供 ffmpeg 相关的音频提取、视频合成功能
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def extract_audio(
    video_path: str,
    output_audio: str = None,
    sample_rate: int = 24000,
    channels: int = 1
) -> str:
    """
    从视频提取音频

    Args:
        video_path: 输入视频路径
        output_audio: 输出音频路径，默认自动生成
        sample_rate: 采样率，默认24kHz（匹配Kokoro输出）
        channels: 声道数，默认单声道

    Returns:
        输出音频文件路径
    """
    if output_audio is None:
        base = Path(video_path).stem
        output_audio = f"{base}_audio.wav"

    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn',  # 禁用视频
        '-acodec', 'pcm_s16le',  # PCM 16-bit 小端
        '-ar', str(sample_rate),
        '-ac', str(channels),
        output_audio
    ]

    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True
    )

    return output_audio


def combine_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    keep_original_audio: bool = False,
    original_audio_volume: float = 0.1
) -> str:
    """
    合并视频和新的音频

    Args:
        video_path: 原视频路径
        audio_path: 新音频路径（中文配音）
        output_path: 输出视频路径
        keep_original_audio: 是否保留原音频作为背景音
        original_audio_volume: 原音频音量（0.0-1.0）

    Returns:
        输出视频路径
    """
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if keep_original_audio:
        # 混音模式：新音频 + 降低音量的原音频
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-filter_complex',
            f'[0:a]volume={original_audio_volume}[bg];[bg][1:a]amix=inputs=2:duration=first[aout]',
            '-map', '0:v:0',
            '-map', '[aout]',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            output_path
        ]
    else:
        # 替换音轨模式
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',  # 复制视频流
            '-map', '0:v:0',  # 使用第一个输入的视频
            '-map', '1:a:0',  # 使用第二个输入的音频
            '-c:a', 'aac',  # AAC 编码
            '-b:a', '192k',
            '-shortest',  # 以较短者为准
            output_path
        ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        error_msg = f"ffmpeg 失败 (exit code {e.returncode})\n"
        error_msg += f"stdout: {e.stdout}\n"
        error_msg += f"stderr: {e.stderr}"
        raise RuntimeError(error_msg)

    return output_path


def get_audio_duration(audio_path: str) -> float:
    """
    获取音频时长（秒）

    Args:
        audio_path: 音频文件路径

    Returns:
        音频时长（秒）
    """
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def get_video_duration(video_path: str) -> float:
    """
    获取视频时长（秒）

    Args:
        video_path: 视频文件路径

    Returns:
        视频时长（秒）
    """
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def mix_audios(
    audio_paths: list,
    output_path: str,
    volumes: list = None
) -> str:
    """
    混合多个音频文件

    Args:
        audio_paths: 音频文件路径列表
        output_path: 输出路径
        volumes: 每个音频的音量列表（0.0-1.0），默认全部1.0

    Returns:
        输出音频路径
    """
    if not audio_paths:
        raise ValueError("至少需要提供一个音频文件")

    if volumes is None:
        volumes = [1.0] * len(audio_paths)

    # 构建输入和过滤器
    inputs = []
    filters = []
    for i, (path, vol) in enumerate(zip(audio_paths, volumes)):
        inputs.extend(['-i', path])
        filters.append(f'[{i}:a]volume={vol}[a{i}]')

    mix_filter = ''.join([f'[a{i}]' for i in range(len(audio_paths))])
    mix_filter += f'amix=inputs={len(audio_paths)}:duration=longest[aout]'
    filters.append(mix_filter)

    cmd = [
        'ffmpeg', '-y',
        *inputs,
        '-filter_complex', ';'.join(filters),
        '-map', '[aout]',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def trim_audio(
    audio_path: str,
    output_path: str,
    start: float = 0,
    end: float = None
) -> str:
    """
    裁剪音频

    Args:
        audio_path: 输入音频路径
        output_path: 输出音频路径
        start: 开始时间（秒）
        end: 结束时间（秒），默认到结尾

    Returns:
        输出音频路径
    """
    cmd = [
        'ffmpeg', '-y',
        '-i', audio_path,
        '-ss', str(start),
    ]

    if end is not None:
        cmd.extend(['-t', str(end - start)])

    cmd.extend([
        '-c:a', 'copy',
        output_path
    ])

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def add_silence(
    audio_path: str,
    output_path: str,
    position: str = 'start',
    duration: float = 1.0
) -> str:
    """
    在音频开头或结尾添加静音

    Args:
        audio_path: 输入音频路径
        output_path: 输出音频路径
        position: 'start' 或 'end'
        duration: 静音时长（秒）

    Returns:
        输出音频路径
    """
    # 创建静音文件
    silence_file = tempfile.mktemp(suffix='.wav')

    # 生成静音
    subprocess.run([
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', f'anullsrc=r=24000:cl=mono',
        '-t', str(duration),
        '-acodec', 'pcm_s16le',
        silence_file
    ], check=True, capture_output=True)

    # 合并
    if position == 'start':
        mix_audios([silence_file, audio_path], output_path)
    else:
        mix_audios([audio_path, silence_file], output_path)

    # 清理临时文件
    os.unlink(silence_file)

    return output_path


def check_ffmpeg_available() -> bool:
    """检查 ffmpeg 是否可用"""
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_ffprobe_available() -> bool:
    """检查 ffprobe 是否可用"""
    try:
        subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


if __name__ == '__main__':
    # 测试代码
    print("[INFO] 测试 audio_utils...")

    # 检查 ffmpeg
    if not check_ffmpeg_available():
        print("[ERROR] ffmpeg 不可用")
        exit(1)

    print("[OK] ffmpeg 可用")
    print(f"[OK] ffprobe 可用: {check_ffprobe_available()}")
