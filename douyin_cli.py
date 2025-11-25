#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载命令行工具
使用集成的 douyinVd 功能下载抖音视频
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from douyin import DouyinDownloader, DouyinConfig

def download_douyin_video(url, output_dir="douyin_downloads"):
    """下载抖音视频"""
    
    print("=" * 60)
    print("🎬 抖音视频下载工具（基于 douyinVd）")
    print("=" * 60)
    
    # 配置下载器
    config = DouyinConfig()
    config.set("download_dir", output_dir)
    config.set("save_metadata", True)
    config.set("download_cover", True)
    config.set("download_music", False)  # 可选
    
    downloader = DouyinDownloader(config)
    
    print(f"🔗 下载链接: {url}")
    print(f"📁 下载目录: {output_dir}")
    print()
    
    # 进度回调函数
    def progress_callback(message, progress):
        # 创建进度条
        bar_length = 30
        filled_length = int(bar_length * progress // 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r📊 [{bar}] {progress:3.0f}% - {message}", end="", flush=True)
    
    try:
        # 开始下载
        result = downloader.download_video(url, progress_callback)
        print("\n")  # 换行
        
        # 显示结果
        print("=" * 60)
        print("📋 下载结果:")
        print("=" * 60)
        
        if result.get("success"):
            print("✅ 下载成功!")
            
            downloaded_files = result.get("downloaded_files", [])
            print(f"\n📄 下载文件 ({len(downloaded_files)} 个):")
            
            for i, file_info in enumerate(downloaded_files, 1):
                file_type = file_info.get("type", "unknown")
                file_path = file_info.get("path", "")
                file_size = file_info.get("size", 0)
                size_mb = file_size / (1024 * 1024)
                
                type_icons = {
                    "video": "🎬",
                    "metadata": "📝",
                    "cover": "🖼️",
                    "music": "🎵"
                }
                icon = type_icons.get(file_type, "📄")
                
                print(f"  {i}. {icon} {file_type}: {os.path.basename(file_path)}")
                print(f"     大小: {size_mb:.1f} MB")
                print(f"     路径: {file_path}")
                
                if file_type == "video" and file_info.get("is_no_watermark"):
                    print("     ✨ 无水印版本")
                print()
            
            # 显示警告
            errors = result.get("errors", [])
            if errors:
                print(f"⚠️ 警告 ({len(errors)} 个):")
                for error in errors:
                    print(f"  - {error}")
                print()
            
            print("🎉 所有文件下载完成!")
            
        else:
            print("❌ 下载失败!")
            error = result.get("error", "未知错误")
            print(f"错误信息: {error}")
            
            # 提供建议
            print("\n💡 建议:")
            print("1. 检查抖音链接是否有效")
            print("2. 确保 douyinVd 服务器正在运行")
            print("3. 检查网络连接")
            
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户取消下载")
    except Exception as e:
        print(f"\n\n❌ 下载异常: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="抖音视频下载工具（基于 douyinVd）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python douyin_cli.py "https://v.douyin.com/Rd4EHcN/"
  python douyin_cli.py "https://v.douyin.com/Rd4EHcN/" -o my_downloads
  
支持的链接格式:
  - https://v.douyin.com/xxxxx/
  - https://www.douyin.com/video/xxxxx
  
注意:
  - 需要先启动 douyinVd 服务器: cd douyinVd && deno task dev
  - 下载的是无水印版本
  - 同时保存视频信息的 JSON 元数据
        """
    )
    
    parser.add_argument("url", help="抖音视频链接")
    parser.add_argument("-o", "--output", default="douyin_downloads", 
                       help="下载目录 (默认: douyin_downloads)")
    
    args = parser.parse_args()
    
    # 验证URL
    if not ("douyin.com" in args.url or "dy.tt" in args.url):
        print("❌ 错误: 请提供有效的抖音链接")
        print("支持的格式: https://v.douyin.com/xxxxx/ 或 https://www.douyin.com/video/xxxxx")
        sys.exit(1)
    
    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)
    
    # 下载视频
    download_douyin_video(args.url, args.output)

if __name__ == "__main__":
    main()