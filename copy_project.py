#!/usr/bin/env python3
"""
项目文件复制工具
将核心代码和必需文件复制到新目录
"""

import os
import shutil
from pathlib import Path
import sys

# 当前目录
SOURCE_DIR = Path(__file__).parent

# 必需的核心 Python 文件
CORE_PYTHON_FILES = [
    "main.py",
    "api_server.py",
    "youtube_transcriber.py",
    "douyin.py",
    "douyin_cli.py",
    "live_recorder_adapter.py",
    "msg_push.py",
    "ffmpeg_install.py",
]

# 必需的文档文件
DOC_FILES = [
    "README.md",
    "PROJECT_STATUS.md",
    "DOUYIN_USAGE_GUIDE.md",
    "PASTE_FEATURE_GUIDE.md",
    "SELENIUM_SETUP_GUIDE.md",
]

# 必需的配置文件
CONFIG_FILES = [
    "requirements.txt",
    "run.bat",
    ".env",  # 如果存在
    ".gitignore",  # 如果存在
]

# 可选的启动脚本
OPTIONAL_FILES = [
    "idle_queue.json",  # 闲时队列配置（如果有）
    "sync_and_push.bat",
    "sync_from_remote.bat",
    "带时间戳Tag.bat",
]

# 必需的目录（包含代码）
CODE_DIRECTORIES = [
    "chrome_extension",     # Chrome 插件
    "douyin",               # 抖音模块
    "live_recorder",        # 直播录制
    "live_config",          # 直播配置
]

# 资源目录
RESOURCE_DIRECTORIES = [
    "icons",                # 应用图标
    "templates",            # 文章模板
]

# 输出目录（空目录，需要创建）
OUTPUT_DIRECTORIES = [
    "downloads",            # 音频下载
    "videos",               # 视频下载
    "youtube_downloads",    # YouTube 视频
    "twitter_downloads",    # Twitter 视频
    "bilibili_downloads",   # Bilibili 视频
    "douyin_downloads",     # 抖音视频
    "transcripts",          # 转录文本
    "subtitles",            # 字幕文件
    "native_subtitles",     # 原生字幕
    "summaries",            # 摘要文章
    "videos_with_subtitles",# 嵌入字幕的视频
    "logs",                 # 日志文件
    "live_downloads",       # 直播录制文件
]

# 不需要复制的目录
EXCLUDE_DIRECTORIES = [
    "_archive",             # 归档文件
    "__pycache__",          # Python 缓存
    ".git",                 # Git 仓库
    "venv",                 # 虚拟环境
    ".venv",
    "env",
    ".env_backup",
    "douyinVd",             # 外部项目（应该独立克隆）
]


def copy_file(src, dest, create_dirs=True):
    """复制单个文件"""
    src_path = SOURCE_DIR / src
    dest_path = dest / src

    if not src_path.exists():
        print(f"  ⚠ 跳过（不存在）: {src}")
        return False

    if create_dirs:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(src_path, dest_path)
        print(f"  ✓ 复制: {src}")
        return True
    except Exception as e:
        print(f"  ✗ 失败: {src} - {e}")
        return False


def copy_directory(src, dest, exclude_patterns=None):
    """复制整个目录"""
    src_path = SOURCE_DIR / src
    dest_path = dest / src

    if not src_path.exists():
        print(f"  ⚠ 跳过（不存在）: {src}")
        return False

    try:
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(
            src_path,
            dest_path,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store') if exclude_patterns is None else exclude_patterns
        )
        file_count = sum(1 for _ in dest_path.rglob('*') if _.is_file())
        print(f"  ✓ 复制目录: {src} ({file_count} 个文件)")
        return True
    except Exception as e:
        print(f"  ✗ 失败: {src} - {e}")
        return False


def create_directory(dest, dirname):
    """创建空目录"""
    dir_path = dest / dirname
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ 创建目录: {dirname}")
        return True
    except Exception as e:
        print(f"  ✗ 失败: {dirname} - {e}")
        return False


def create_readme(dest):
    """创建复制说明文件"""
    import datetime
    readme_content = f"""# 项目文件复制说明

**复制时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**源目录**: {SOURCE_DIR}

## 已复制内容

### 核心代码文件
{chr(10).join(f'- {f}' for f in CORE_PYTHON_FILES)}

### 文档文件
{chr(10).join(f'- {f}' for f in DOC_FILES)}

### 代码目录
{chr(10).join(f'- {d}/' for d in CODE_DIRECTORIES)}

### 资源目录
{chr(10).join(f'- {d}/' for d in RESOURCE_DIRECTORIES)}

## 输出目录

以下空目录已创建，程序运行时会自动填充：
{chr(10).join(f'- {d}/' for d in OUTPUT_DIRECTORIES)}

## 使用说明

1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

2. **配置 API 密钥**:
   - 复制 `.env.example` 为 `.env`（如果有）
   - 或在 GUI 的"设置"页面配置

3. **运行应用**:
   ```bash
   python main.py
   ```

4. **安装 Chrome 插件**（可选）:
   - 访问 `chrome://extensions/`
   - 启用"开发者模式"
   - 加载 `chrome_extension` 目录

## 注意事项

- ⚠️ `.env` 文件可能未复制（包含密钥），需要重新配置
- ⚠️ `douyinVd` 目录未复制（外部依赖），如需要请单独克隆
- ⚠️ 归档文件 `_archive/` 未复制（仅测试和调试文件）

## 参考文档

详细使用说明请查看 `README.md`
"""

    readme_path = dest / "COPY_INFO.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  ✓ 创建说明文件: COPY_INFO.md")


def main():
    """主函数"""
    print("=" * 70)
    print("项目文件复制工具")
    print("=" * 70)
    print()

    # 获取目标目录
    if len(sys.argv) < 2:
        print("使用方法: python copy_project.py <目标目录>")
        print()
        print("示例:")
        print("  python copy_project.py /path/to/new/directory")
        print("  python copy_project.py D:\\Projects\\video_transcriber_copy")
        return

    dest_path = Path(sys.argv[1])

    # 确认操作
    print(f"源目录: {SOURCE_DIR}")
    print(f"目标目录: {dest_path}")
    print()

    if dest_path.exists():
        response = input(f"⚠️  目标目录已存在，是否继续？(y/N): ")
        if response.lower() != 'y':
            print("操作已取消")
            return

    print()
    print("开始复制...")
    print()

    # 创建目标目录
    dest_path.mkdir(parents=True, exist_ok=True)

    # 1. 复制核心 Python 文件
    print("[1/7] 复制核心 Python 文件")
    copied_py = 0
    for filename in CORE_PYTHON_FILES:
        if copy_file(filename, dest_path):
            copied_py += 1
    print(f"  ✓ 已复制 {copied_py}/{len(CORE_PYTHON_FILES)} 个 Python 文件")
    print()

    # 2. 复制文档文件
    print("[2/7] 复制文档文件")
    copied_docs = 0
    for filename in DOC_FILES:
        if copy_file(filename, dest_path):
            copied_docs += 1
    print(f"  ✓ 已复制 {copied_docs}/{len(DOC_FILES)} 个文档")
    print()

    # 3. 复制配置文件
    print("[3/7] 复制配置文件")
    copied_config = 0
    for filename in CONFIG_FILES:
        if copy_file(filename, dest_path):
            copied_config += 1
    print(f"  ✓ 已复制 {copied_config}/{len(CONFIG_FILES)} 个配置文件")
    print()

    # 4. 复制代码目录
    print("[4/7] 复制代码目录")
    copied_code_dirs = 0
    for dirname in CODE_DIRECTORIES:
        if copy_directory(dirname, dest_path):
            copied_code_dirs += 1
    print(f"  ✓ 已复制 {copied_code_dirs}/{len(CODE_DIRECTORIES)} 个代码目录")
    print()

    # 5. 复制资源目录
    print("[5/7] 复制资源目录")
    copied_res_dirs = 0
    for dirname in RESOURCE_DIRECTORIES:
        if copy_directory(dirname, dest_path):
            copied_res_dirs += 1
    print(f"  ✓ 已复制 {copied_res_dirs}/{len(RESOURCE_DIRECTORIES)} 个资源目录")
    print()

    # 6. 创建输出目录
    print("[6/7] 创建输出目录")
    created_dirs = 0
    for dirname in OUTPUT_DIRECTORIES:
        if create_directory(dest_path, dirname):
            created_dirs += 1
    print(f"  ✓ 已创建 {created_dirs}/{len(OUTPUT_DIRECTORIES)} 个输出目录")
    print()

    # 7. 创建说明文件
    print("[7/7] 创建复制说明")
    create_readme(dest_path)
    print()

    # 完成总结
    print("=" * 70)
    print("复制完成！")
    print("=" * 70)
    print()
    print(f"目标位置: {dest_path}")
    print()
    print("文件统计:")
    py_files = len(list(dest_path.glob('*.py')))
    md_files = len(list(dest_path.glob('*.md')))
    dirs = len([d for d in dest_path.iterdir() if d.is_dir()])
    print(f"  - Python 文件: {py_files}")
    print(f"  - Markdown 文档: {md_files}")
    print(f"  - 目录: {dirs}")
    print()
    print("下一步:")
    print("  1. cd " + str(dest_path))
    print("  2. pip install -r requirements.txt")
    print("  3. python main.py")
    print()
    print("📖 详细说明请查看目标目录中的 COPY_INFO.md")


if __name__ == "__main__":
    main()
