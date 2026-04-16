#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载命令行工具
使用集成的 douyinVd 功能下载抖音视频或用户主页作品
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from douyin import DouyinDownloader, DouyinConfig
from douyin.utils import DouyinUtils

from paths_config import DOUYIN_DOWNLOADS_DIR


def build_downloader(output_dir=DOUYIN_DOWNLOADS_DIR, cookie=None):
    """创建下载器"""
    config = DouyinConfig()
    config.set("download_dir", output_dir)
    config.set("save_metadata", True)
    config.set("download_cover", True)
    config.set("download_music", False)
    if cookie:
        config.set("cookie", cookie.strip())
    return DouyinDownloader(config)


def download_douyin_video(url, output_dir=DOUYIN_DOWNLOADS_DIR, cookie=None):
    """下载单个视频"""

    print("=" * 60)
    print("抖音视频下载工具（基于 douyinVd）")
    print("=" * 60)

    downloader = build_downloader(output_dir, cookie)

    print(f"下载链接: {url}")
    print(f"下载目录: {output_dir}")
    print()

    def progress_callback(message, progress):
        bar_length = 30
        filled_length = int(bar_length * progress // 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r[{bar}] {progress:3.0f}% - {message}", end="", flush=True)

    try:
        result = downloader.download_video(url, progress_callback)
        print("\n")

        print("=" * 60)
        print("单视频下载结果:")
        print("=" * 60)

        if result.get("success"):
            print("下载成功!")

            downloaded_files = result.get("downloaded_files", [])
            print(f"\n下载文件 ({len(downloaded_files)} 个):")

            for i, file_info in enumerate(downloaded_files, 1):
                file_type = file_info.get("type", "unknown")
                file_path = file_info.get("path", "")
                file_size = file_info.get("size", 0)
                size_mb = file_size / (1024 * 1024)

                type_icons = {
                    "video": "[video]",
                    "metadata": "[metadata]",
                    "cover": "[cover]",
                    "music": "[music]"
                }
                icon = type_icons.get(file_type, "[file]")

                print(f"  {i}. {icon} {file_type}: {os.path.basename(file_path)}")
                print(f"     大小: {size_mb:.1f} MB")
                print(f"     路径: {file_path}")

                if file_type == "video" and file_info.get("is_no_watermark"):
                    print("     无水印版本")
                print()

            errors = result.get("errors", [])
            if errors:
                print(f"警告 ({len(errors)} 个):")
                for error in errors:
                    print(f"  - {error}")
                print()

            print("所有文件下载完成!")
            return 0

        print("下载失败!")
        error = result.get("error", "未知错误")
        print(f"错误信息: {error}")
        print("\n建议:")
        print("1. 检查抖音链接是否有效")
        print("2. 确保 douyinVd 服务器正在运行")
        print("3. 检查网络连接")
        return 1

    except KeyboardInterrupt:
        print("\n\n用户取消下载")
        return 130
    except Exception as e:
        print(f"\n\n下载异常: {e}")
        return 1


def download_douyin_profile(url, output_dir=DOUYIN_DOWNLOADS_DIR, limit=0, cookie=None):
    """批量下载用户主页视频"""

    print("=" * 60)
    print("抖音用户主页批量下载工具")
    print("=" * 60)

    downloader = build_downloader(output_dir, cookie)

    print(f"主页链接: {url}")
    print(f"下载目录: {output_dir}")
    print(f"下载数量: {'全部' if limit == 0 else limit}")
    print()

    def progress_callback(message, progress):
        bar_length = 30
        filled_length = int(bar_length * progress // 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r[{bar}] {progress:3.0f}% - {message}", end="", flush=True)

    try:
        result = downloader.download_user_videos(url, limit=limit, progress_callback=progress_callback)
        print("\n")

        print("=" * 60)
        print("主页批量下载结果:")
        print("=" * 60)

        if result.get("success"):
            total_count = result.get("total_count", 0)
            successful_count = result.get("successful_count", 0)
            failed_count = result.get("failed_count", 0)
            print("批量下载完成!")
            print(f"总计: {total_count}")
            print(f"成功: {successful_count}")
            print(f"失败: {failed_count}")
            return 0

        print("批量下载失败!")
        print(f"错误信息: {result.get('error', '未知错误')}")
        return 1

    except KeyboardInterrupt:
        print("\n\n用户取消批量下载")
        return 130
    except Exception as e:
        print(f"\n\n批量下载异常: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="抖音下载工具（支持单视频和用户主页批量下载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python douyin_cli.py "https://v.douyin.com/Rd4EHcN/"
  python douyin_cli.py "https://v.douyin.com/Rd4EHcN/" -o my_downloads
  python douyin_cli.py "https://www.douyin.com/user/MS4wLjABAAAA..." --cookie "your_cookie"
  python douyin_cli.py "https://www.douyin.com/user/MS4wLjABAAAA..." --cookie "your_cookie" --limit 3

支持的链接格式:
  - 单视频: https://v.douyin.com/xxxxx/ 或 https://www.douyin.com/video/xxxxx
  - 用户主页: https://www.douyin.com/user/xxxxx 或可展开为主页的分享短链

注意:
  - 主页批量下载通常需要提供有效 Cookie
  - 需要先启动 douyinVd 服务器: cd douyinVd && deno task dev
  - 单视频下载默认尝试无水印版本，并保存 JSON 元数据
        """
    )

    parser.add_argument("url", help="抖音视频链接或用户主页链接")
    parser.add_argument("-o", "--output", default=DOUYIN_DOWNLOADS_DIR,
                       help="下载目录 (默认: workspace/douyin_downloads)")
    parser.add_argument("--limit", type=int, default=0,
                       help="用户主页批量下载数量限制，0 表示全部")
    parser.add_argument("--cookie", default=None,
                       help="手动传入抖音 Cookie，用户主页批量下载建议提供")

    args = parser.parse_args()

    if not ("douyin.com" in args.url or "dy.tt" in args.url or "iesdouyin.com" in args.url):
        print("错误: 请提供有效的抖音链接")
        print("支持的格式: 单视频链接或用户主页链接")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    if DouyinUtils.is_user_profile_url(args.url):
        exit_code = download_douyin_profile(args.url, args.output, args.limit, args.cookie)
    else:
        exit_code = download_douyin_video(args.url, args.output, args.cookie)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
