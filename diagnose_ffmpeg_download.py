#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FFmpeg下载诊断脚本
检查各个下载源的可用性
"""

import requests
import sys

def check_url(name, url, timeout=10):
    """检查URL是否可访问"""
    print(f"\n检查 {name}...")
    print(f"  URL: {url}")
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            print(f"  ✓ 可访问 (状态码: {response.status_code})")
            if 'Content-Length' in response.headers:
                size = int(response.headers['Content-Length'])
                print(f"  文件大小: {size / (1024*1024):.2f} MB")
            return True
        elif response.status_code == 405:  # Method Not Allowed
            # 有些服务器不支持HEAD，尝试GET
            print(f"  HEAD请求不支持，尝试GET...")
            response = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                print(f"  ✓ 可访问 (状态码: {response.status_code})")
                if 'Content-Length' in response.headers:
                    size = int(response.headers['Content-Length'])
                    print(f"  文件大小: {size / (1024*1024):.2f} MB")
                return True
        else:
            print(f"  ✗ 无法访问 (状态码: {response.status_code})")
            return False
    except requests.exceptions.Timeout:
        print(f"  ✗ 连接超时 (>{timeout}秒)")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"  ✗ 连接错误: {e}")
        return False
    except Exception as e:
        print(f"  ✗ 错误: {type(e).__name__}: {e}")
        return False


def main():
    print("="*70)
    print("FFmpeg下载源诊断工具")
    print("="*70)

    # 检查网络连接
    print("\n1. 检查基本网络连接...")
    print("-"*70)

    test_urls = [
        ("百度", "https://www.baidu.com"),
        ("Google", "https://www.google.com"),
    ]

    for name, url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {name}: 可访问")
            else:
                print(f"  ? {name}: 状态码 {response.status_code}")
        except:
            print(f"  ✗ {name}: 无法访问")

    # 检查FFmpeg下载源
    print("\n2. 检查FFmpeg下载源...")
    print("-"*70)

    sources = [
        ("Gyan.dev (推荐)", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"),
        ("GitHub", "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"),
        ("蓝奏云", "https://wweb.lanzouv.com/iHAc22ly3r3g"),
    ]

    available_sources = []
    for name, url in sources:
        if check_url(name, url):
            available_sources.append(name)

    # 总结
    print("\n" + "="*70)
    print("诊断总结")
    print("="*70)

    if available_sources:
        print(f"\n✓ 发现 {len(available_sources)} 个可用的下载源:")
        for source in available_sources:
            print(f"  - {source}")
        print("\n建议: 使用程序中的'下载FFmpeg'按钮，系统会自动尝试这些源")
    else:
        print("\n✗ 所有下载源都无法访问")
        print("\n可能的原因:")
        print("  1. 网络连接问题")
        print("  2. 防火墙拦截")
        print("  3. 需要代理/VPN")
        print("  4. DNS解析问题")
        print("\n建议:")
        print("  1. 检查网络连接")
        print("  2. 尝试关闭防火墙")
        print("  3. 使用VPN或代理")
        print("  4. 手动下载: https://www.gyan.dev/ffmpeg/builds/")
        print("     下载后在程序中使用'浏览'按钮指定路径")

    print("\n" + "="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
