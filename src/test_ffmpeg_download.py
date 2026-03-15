#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FFmpeg下载测试脚本
用于测试和调试FFmpeg下载功能
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("="*60)
    print("FFmpeg下载测试脚本")
    print("="*60)
    print()

    try:
        from ffmpeg_install import install_ffmpeg
        print("✓ 成功导入ffmpeg_install模块")
        print()

        print("开始测试FFmpeg下载...")
        print("-"*60)

        result = install_ffmpeg()

        print()
        print("="*60)
        if result:
            print(f"✓ 下载成功!")
            print(f"FFmpeg路径: {result}")
            print()
            print("你可以在程序的设置中看到这个路径已被自动配置")
        else:
            print("✗ 下载失败")
            print()
            print("可能的原因:")
            print("1. 网络问题 - 无法访问下载源")
            print("2. 防火墙阻止")
            print("3. 代理设置问题")
            print()
            print("建议:")
            print("- 检查网络连接")
            print("- 尝试使用VPN")
            print("- 查看上面的详细日志找出具体错误")
            print("- 或使用手动下载方式")
        print("="*60)

    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        print("请确保在项目根目录运行此脚本")
    except KeyboardInterrupt:
        print("\n\n用户中断下载")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
