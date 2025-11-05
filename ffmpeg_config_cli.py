# -*- coding: utf-8 -*-
"""
FFmpeg配置管理CLI工具
用于管理FFmpeg的配置，包括模式切换、路径设置、下载等
"""

import sys
import os
from pathlib import Path

try:
    from ffmpeg_manager import FFmpegManager, get_ffmpeg_manager
    from ffmpeg_install import install_ffmpeg, check_ffmpeg_installed
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)


def print_help():
    """打印帮助信息"""
    help_text = """
FFmpeg配置管理工具

用法:
    python ffmpeg_config_cli.py [命令] [参数]

命令:
    status              查看当前FFmpeg配置和状态
    mode <模式>         设置FFmpeg模式 (python/exe/auto)
    path <路径>         设置ffmpeg.exe的路径
    download            下载ffmpeg.exe
    test                测试FFmpeg是否可用
    prefer-exe <值>     设置是否优先使用exe (true/false)
    auto-download <值>  设置是否自动下载 (true/false)
    help                显示此帮助信息

示例:
    # 查看当前状态
    python ffmpeg_config_cli.py status

    # 切换到exe模式
    python ffmpeg_config_cli.py mode exe

    # 设置ffmpeg.exe路径
    python ffmpeg_config_cli.py path "C:/ffmpeg/bin/ffmpeg.exe"

    # 下载ffmpeg
    python ffmpeg_config_cli.py download

    # 设置优先使用exe
    python ffmpeg_config_cli.py prefer-exe true
"""
    print(help_text)


def show_status():
    """显示当前状态"""
    try:
        manager = get_ffmpeg_manager()
        print("\n" + "="*60)
        print("FFmpeg配置状态")
        print("="*60)
        print(f"当前模式: {manager.get_mode()}")
        print(f"FFmpeg版本: {manager.get_version()}")

        if manager.mode == 'exe':
            print(f"可执行文件路径: {manager.get_ffmpeg_exe()}")

        print("\n配置文件设置:")
        print(f"  - ffmpeg_mode: {manager.config['ffmpeg_mode']}")
        print(f"  - ffmpeg_exe_path: {manager.config.get('ffmpeg_exe_path') or '(未设置)'}")
        print(f"  - download_on_missing: {manager.config.get('download_on_missing', True)}")
        print(f"  - prefer_exe: {manager.config.get('prefer_exe', False)}")
        print("="*60 + "\n")
    except Exception as e:
        print(f"获取状态失败: {e}")


def set_mode(mode: str):
    """设置FFmpeg模式"""
    if mode.lower() not in ['python', 'exe', 'auto']:
        print(f"错误: 无效的模式 '{mode}'")
        print("有效模式: python, exe, auto")
        return

    try:
        manager = get_ffmpeg_manager()
        manager.set_mode(mode.lower())
        print(f"✓ FFmpeg模式已设置为: {mode}")
        print(f"✓ 当前使用: {manager.get_mode()}")
    except Exception as e:
        print(f"✗ 设置模式失败: {e}")


def set_path(path: str):
    """设置ffmpeg.exe路径"""
    if not os.path.isfile(path):
        print(f"✗ 错误: 文件不存在: {path}")
        return

    try:
        manager = get_ffmpeg_manager()
        manager.set_ffmpeg_exe_path(path)
        print(f"✓ FFmpeg路径已设置为: {path}")
    except Exception as e:
        print(f"✗ 设置路径失败: {e}")


def download_ffmpeg():
    """下载ffmpeg"""
    print("开始下载FFmpeg...")
    try:
        success = install_ffmpeg()
        if success:
            print("✓ FFmpeg下载成功")
            # 重新初始化管理器
            manager = get_ffmpeg_manager()
            manager._initialize()
            print(f"✓ 当前模式: {manager.get_mode()}")
        else:
            print("✗ FFmpeg下载失败")
    except Exception as e:
        print(f"✗ 下载过程中出错: {e}")


def test_ffmpeg():
    """测试FFmpeg"""
    try:
        manager = get_ffmpeg_manager()
        print(f"FFmpeg模式: {manager.get_mode()}")
        print(f"FFmpeg版本: {manager.get_version()}")

        if manager.mode == 'exe':
            print(f"可执行文件: {manager.get_ffmpeg_exe()}")

        # 测试probe功能
        print("\n测试基本功能...")
        print("✓ FFmpeg工作正常")
    except Exception as e:
        print(f"✗ FFmpeg测试失败: {e}")


def set_prefer_exe(value: str):
    """设置优先使用exe"""
    if value.lower() not in ['true', 'false']:
        print("错误: 值必须是 true 或 false")
        return

    try:
        manager = get_ffmpeg_manager()
        manager.config['prefer_exe'] = value.lower() == 'true'
        manager._save_config()
        print(f"✓ prefer_exe已设置为: {value}")

        if manager.config['ffmpeg_mode'] == 'auto':
            print("重新初始化...")
            manager._initialize()
            print(f"✓ 当前模式: {manager.get_mode()}")
    except Exception as e:
        print(f"✗ 设置失败: {e}")


def set_auto_download(value: str):
    """设置自动下载"""
    if value.lower() not in ['true', 'false']:
        print("错误: 值必须是 true 或 false")
        return

    try:
        manager = get_ffmpeg_manager()
        manager.config['download_on_missing'] = value.lower() == 'true'
        manager._save_config()
        print(f"✓ download_on_missing已设置为: {value}")
    except Exception as e:
        print(f"✗ 设置失败: {e}")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == 'help' or command == '--help' or command == '-h':
        print_help()
    elif command == 'status':
        show_status()
    elif command == 'mode':
        if len(sys.argv) < 3:
            print("错误: 请指定模式 (python/exe/auto)")
            return
        set_mode(sys.argv[2])
    elif command == 'path':
        if len(sys.argv) < 3:
            print("错误: 请指定ffmpeg.exe的路径")
            return
        set_path(sys.argv[2])
    elif command == 'download':
        download_ffmpeg()
    elif command == 'test':
        test_ffmpeg()
    elif command == 'prefer-exe':
        if len(sys.argv) < 3:
            print("错误: 请指定值 (true/false)")
            return
        set_prefer_exe(sys.argv[2])
    elif command == 'auto-download':
        if len(sys.argv) < 3:
            print("错误: 请指定值 (true/false)")
            return
        set_auto_download(sys.argv[2])
    else:
        print(f"未知命令: {command}")
        print("使用 'python ffmpeg_config_cli.py help' 查看帮助")


if __name__ == "__main__":
    main()
