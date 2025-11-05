# -*- coding: utf-8 -*-
"""
FFmpeg使用示例
演示如何在项目中使用FFmpeg管理器
"""

from ffmpeg_manager import get_ffmpeg_manager, FFmpegManager


def example_1_basic_usage():
    """示例1: 基础使用"""
    print("\n" + "="*60)
    print("示例1: 基础使用")
    print("="*60)

    # 获取FFmpeg管理器（单例）
    manager = get_ffmpeg_manager()

    # 查看当前配置
    print(f"当前模式: {manager.get_mode()}")
    print(f"FFmpeg版本: {manager.get_version()}")

    if manager.mode == 'exe':
        print(f"可执行文件路径: {manager.get_ffmpeg_exe()}")


def example_2_probe_video():
    """示例2: 探测视频信息"""
    print("\n" + "="*60)
    print("示例2: 探测视频信息（兼容两种模式）")
    print("="*60)

    manager = get_ffmpeg_manager()

    # 假设你有一个视频文件
    video_file = "test_video.mp4"

    try:
        # 这个方法在两种模式下都可用
        probe_data = manager.probe(video_file)

        # 打印视频信息
        print(f"格式: {probe_data['format']['format_name']}")
        print(f"时长: {probe_data['format']['duration']}秒")

        # 打印视频流信息
        for stream in probe_data['streams']:
            if stream['codec_type'] == 'video':
                print(f"视频编码: {stream['codec_name']}")
                print(f"分辨率: {stream['width']}x{stream['height']}")
            elif stream['codec_type'] == 'audio':
                print(f"音频编码: {stream['codec_name']}")
                print(f"采样率: {stream['sample_rate']}Hz")
    except Exception as e:
        print(f"探测视频失败: {e}")
        print("请确保有test_video.mp4文件，或修改video_file变量")


def example_3_extract_audio():
    """示例3: 提取音频"""
    print("\n" + "="*60)
    print("示例3: 从视频提取音频（兼容两种模式）")
    print("="*60)

    manager = get_ffmpeg_manager()

    video_file = "test_video.mp4"
    audio_file = "output_audio.wav"

    try:
        # 这个方法在两种模式下都可用
        success = manager.extract_audio(
            video_path=video_file,
            audio_path=audio_file,
            acodec="pcm_s16le",  # 音频编码
            ac=1,                 # 单声道
            ar="16k"              # 采样率16kHz
        )

        if success:
            print(f"✓ 音频提取成功: {audio_file}")
        else:
            print("✗ 音频提取失败")
    except Exception as e:
        print(f"提取音频时出错: {e}")
        print("请确保有test_video.mp4文件，或修改video_file变量")


def example_4_python_mode_advanced():
    """示例4: Python库模式高级用法"""
    print("\n" + "="*60)
    print("示例4: Python库模式高级用法")
    print("="*60)

    manager = get_ffmpeg_manager()

    if manager.get_mode() != 'python':
        print("当前不是Python库模式，跳过此示例")
        print(f"当前模式: {manager.get_mode()}")
        print("提示: 使用 'python ffmpeg_config_cli.py mode python' 切换到Python库模式")
        return

    try:
        # 获取原始的ffmpeg-python模块
        ffmpeg = manager.get_ffmpeg_python()

        # 使用ffmpeg-python的完整功能
        input_file = "test_video.mp4"
        output_file = "output_converted.mp4"

        print(f"使用ffmpeg-python转换视频: {input_file} -> {output_file}")

        stream = ffmpeg.input(input_file)
        stream = ffmpeg.output(stream, output_file, vcodec='libx264', acodec='aac')

        # 注意：这里不实际运行，只是演示
        print("提示: 要实际运行，请取消下面一行的注释")
        # ffmpeg.run(stream, overwrite_output=True)

        print("✓ 命令准备完成（未实际执行）")
    except Exception as e:
        print(f"Python库模式示例失败: {e}")


def example_5_exe_mode_advanced():
    """示例5: 可执行文件模式高级用法"""
    print("\n" + "="*60)
    print("示例5: 可执行文件模式高级用法")
    print("="*60)

    manager = get_ffmpeg_manager()

    if manager.get_mode() != 'exe':
        print("当前不是可执行文件模式，跳过此示例")
        print(f"当前模式: {manager.get_mode()}")
        print("提示: 使用 'python ffmpeg_config_cli.py mode exe' 切换到exe模式")
        return

    try:
        input_file = "test_video.mp4"
        output_file = "output_converted.mp4"

        print(f"使用ffmpeg.exe转换视频: {input_file} -> {output_file}")

        # 直接运行ffmpeg命令
        result = manager.run_ffmpeg_command(
            '-i', input_file,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-y',  # 覆盖输出文件
            output_file,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("✓ 转换成功")
        else:
            print("✗ 转换失败")
            print(f"错误信息: {result.stderr}")
    except Exception as e:
        print(f"可执行文件模式示例失败: {e}")


def example_6_mode_switching():
    """示例6: 动态切换模式"""
    print("\n" + "="*60)
    print("示例6: 动态切换模式")
    print("="*60)

    manager = get_ffmpeg_manager()

    print(f"初始模式: {manager.get_mode()}")

    # 注意：实际切换需要相应的环境支持
    print("\n可用的切换命令:")
    print("  manager.set_mode('python')  # 切换到Python库模式")
    print("  manager.set_mode('exe')     # 切换到可执行文件模式")
    print("  manager.set_mode('auto')    # 切换到自动模式")

    print("\n或使用CLI工具:")
    print("  python ffmpeg_config_cli.py mode python")
    print("  python ffmpeg_config_cli.py mode exe")
    print("  python ffmpeg_config_cli.py mode auto")


def example_7_custom_ffmpeg_path():
    """示例7: 使用自定义ffmpeg路径"""
    print("\n" + "="*60)
    print("示例7: 使用自定义ffmpeg路径")
    print("="*60)

    manager = get_ffmpeg_manager()

    print("设置自定义ffmpeg路径的方法:")
    print("\n方法1: 使用Python代码")
    print("  manager.set_ffmpeg_exe_path('/path/to/ffmpeg.exe')")

    print("\n方法2: 使用CLI工具")
    print("  python ffmpeg_config_cli.py path '/path/to/ffmpeg.exe'")

    print("\n方法3: 直接编辑配置文件")
    print("  编辑 ffmpeg_config.json，设置 ffmpeg_exe_path 字段")

    print(f"\n当前配置的路径: {manager.config.get('ffmpeg_exe_path') or '(未设置)'}")


def example_8_check_availability():
    """示例8: 检查FFmpeg可用性"""
    print("\n" + "="*60)
    print("示例8: 检查FFmpeg可用性")
    print("="*60)

    try:
        manager = get_ffmpeg_manager()
        print("✓ FFmpeg可用")
        print(f"  模式: {manager.get_mode()}")
        print(f"  版本: {manager.get_version()}")

        if manager.mode == 'exe':
            print(f"  路径: {manager.get_ffmpeg_exe()}")

        # 检查配置
        print("\n当前配置:")
        for key, value in manager.config.items():
            print(f"  {key}: {value}")

    except Exception as e:
        print(f"✗ FFmpeg不可用: {e}")
        print("\n建议:")
        print("1. 安装ffmpeg-python: pip install ffmpeg-python")
        print("2. 或下载ffmpeg.exe: python ffmpeg_config_cli.py download")
        print("3. 或指定已有的ffmpeg: python ffmpeg_config_cli.py path <路径>")


def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("FFmpeg管理器使用示例")
    print("="*60)

    examples = [
        ("基础使用", example_1_basic_usage),
        ("探测视频信息", example_2_probe_video),
        ("提取音频", example_3_extract_audio),
        ("Python库模式高级用法", example_4_python_mode_advanced),
        ("可执行文件模式高级用法", example_5_exe_mode_advanced),
        ("动态切换模式", example_6_mode_switching),
        ("自定义ffmpeg路径", example_7_custom_ffmpeg_path),
        ("检查FFmpeg可用性", example_8_check_availability),
    ]

    print("\n可用示例:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"{i}. {name}")

    print("\n" + "-"*60)
    choice = input("\n请选择要运行的示例 (1-8, 或按Enter运行所有): ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(examples):
        name, func = examples[int(choice) - 1]
        func()
    else:
        for name, func in examples:
            try:
                func()
            except Exception as e:
                print(f"\n示例 '{name}' 执行出错: {e}")

    print("\n" + "="*60)
    print("示例结束")
    print("="*60)
    print("\n更多信息请查看 FFMPEG_USAGE.md")


if __name__ == "__main__":
    main()
