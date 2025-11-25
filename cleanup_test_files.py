#!/usr/bin/env python3
"""
清理测试和调试文件
将测试文件移动到 _archive/test_files/ 目录，保持项目整洁
"""

import os
import shutil
from pathlib import Path

# 当前目录
BASE_DIR = Path(__file__).parent

# 归档目录
ARCHIVE_DIR = BASE_DIR / "_archive"
TEST_DIR = ARCHIVE_DIR / "test_files"
DEBUG_DOCS_DIR = ARCHIVE_DIR / "debug_docs"

# 需要移除的测试文件（Python）
TEST_FILES = [
    "test_chrome_extension_api.py",
    "test_douyin_detection.py",
    "test_douyin_live.py",
    "test_douyin_recording.py",
    "test_full_integration.py",
    "test_gui_detection.py",
    "test_improved_detection.py",
    "test_integration.py",
    "test_live_recorder.py",
    "test_method_order.py",
    "test_real_douyin_api.py",
    "test_simple_tab.py",
    "test_tab_creation.py",
    "debug_douyin_live_detection.py",
    "debug_live_tab.py",
    "check_extension_ready.py",
    "verify_tabs.py",
    "fix_douyin_detection.py",
]

# 需要移除的调试文档（Markdown）
DEBUG_DOCS = [
    "CHECK_SERVICE_WORKER.md",
    "CHROME_EXTENSION_DEBUG_GUIDE.md",
    "DEBUG_TWITTER_BUTTON.md",
    "FINAL_UPDATE_INSTRUCTIONS.md",
    "FIX_TWITTER_BUTTON_NOW.md",
    "QUICK_FIX_GUIDE.md",
    "TEST_TWITTER_NOW.md",
    "TWITTER_DEBUG_GUIDE.md",
    "TWITTER_DOWNLOAD_FIX.md",
    "URGENT_FIX_GUIDE.md",
    "extension_checklist.md",
]

# 需要移除的临时/重复文档
TEMP_DOCS = [
    "CLEANUP_SUMMARY.md",      # 清理总结（临时）
    "DOUYIN_USAGE_NEW.md",     # 与 DOUYIN_USAGE_GUIDE.md 重复
    "wechat_article.md",       # 微信公众号文章（非用户文档）
]

# 保留的核心文件（不移动）
KEEP_FILES = [
    "main.py",
    "api_server.py",
    "youtube_transcriber.py",
    "douyin_cli.py",
    "douyin.py",
    "ffmpeg_install.py",
    "live_recorder_adapter.py",
    "msg_push.py",
    "README.md",
    "DOUYIN_USAGE_GUIDE.md",
    "DOUYIN_USAGE_NEW.md",
    "PASTE_FEATURE_GUIDE.md",
    "SELENIUM_SETUP_GUIDE.md",
    "wechat_article.md",
]

def create_directories():
    """创建归档目录"""
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✓ 创建归档目录: {ARCHIVE_DIR}")

def move_file(source, dest_dir):
    """移动文件到目标目录"""
    source_path = BASE_DIR / source
    if not source_path.exists():
        print(f"  ⚠ 文件不存在，跳过: {source}")
        return False

    dest_path = dest_dir / source
    try:
        shutil.move(str(source_path), str(dest_path))
        print(f"  ✓ 移动: {source} -> {dest_dir.name}/{source}")
        return True
    except Exception as e:
        print(f"  ✗ 移动失败 {source}: {e}")
        return False

def create_readme():
    """在归档目录创建说明文件"""
    readme_content = """# 测试和调试文件归档

此目录包含项目开发过程中的测试和调试文件。

## 目录结构

- `test_files/` - Python 测试脚本
- `debug_docs/` - 调试和修复文档

## 说明

这些文件在项目开发和调试时使用，已归档以保持主目录整洁。

如果需要查看调试历史或测试代码，可以在此目录中找到。

**注意**: 这些文件不是核心功能的一部分，删除它们不会影响项目运行。

归档时间: 由 cleanup_test_files.py 自动生成
"""

    readme_path = ARCHIVE_DIR / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"✓ 创建说明文件: {readme_path}")

def main():
    """主函数"""
    print("=" * 60)
    print("清理测试和调试文件")
    print("=" * 60)
    print()

    # 创建目录
    create_directories()
    print()

    # 移动测试文件
    print(f"正在移动 {len(TEST_FILES)} 个测试文件到 {TEST_DIR.name}/")
    moved_tests = 0
    for filename in TEST_FILES:
        if move_file(filename, TEST_DIR):
            moved_tests += 1
    print(f"✓ 已移动 {moved_tests}/{len(TEST_FILES)} 个测试文件")
    print()

    # 移动调试文档
    print(f"正在移动 {len(DEBUG_DOCS)} 个调试文档到 {DEBUG_DOCS_DIR.name}/")
    moved_docs = 0
    for filename in DEBUG_DOCS:
        if move_file(filename, DEBUG_DOCS_DIR):
            moved_docs += 1
    print(f"✓ 已移动 {moved_docs}/{len(DEBUG_DOCS)} 个调试文档")
    print()

    # 移动临时文档
    print(f"正在移动 {len(TEMP_DOCS)} 个临时/重复文档到 {DEBUG_DOCS_DIR.name}/")
    moved_temp = 0
    for filename in TEMP_DOCS:
        if move_file(filename, DEBUG_DOCS_DIR):
            moved_temp += 1
    print(f"✓ 已移动 {moved_temp}/{len(TEMP_DOCS)} 个临时文档")
    print()

    # 创建说明文件
    create_readme()
    print()

    # 显示保留的文件
    print("=" * 60)
    print("清理完成！")
    print("=" * 60)
    print()
    print(f"归档位置: {ARCHIVE_DIR}")
    print(f"  - 测试文件: {TEST_DIR}")
    print(f"  - 调试文档: {DEBUG_DOCS_DIR}")
    print()

    # 列出当前目录的 Python 文件
    print("当前目录中的核心 Python 文件:")
    py_files = sorted(BASE_DIR.glob("*.py"))
    for f in py_files:
        if f.name != "cleanup_test_files.py":  # 排除清理脚本本身
            print(f"  - {f.name}")
    print()

    print("当前目录中的核心文档文件:")
    md_files = sorted(BASE_DIR.glob("*.md"))
    for f in md_files:
        print(f"  - {f.name}")
    print()

    print("✓ 项目目录已整理完毕！")

if __name__ == "__main__":
    main()
