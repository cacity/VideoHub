#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
VideoHub 无音频版入口（No-Whisper Edition）

特点：
- 通过本目录下的 `whisper` / `torch` stub 模块，避免真实依赖 Whisper / Torch，
  方便打包一个“无音频转字幕”的轻量版本。
- 图形界面与原版基本一致，但涉及语音转文字 / Whisper 的功能不会产出真实结果。

使用方式：
    python no_whisper_version/main_no_whisper.py

打包时可直接以本文件为入口。
"""

from pathlib import Path
import sys


def main() -> None:
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent

    # 确保 stub 模块路径在最前面（覆盖系统已安装的 whisper / torch）
    sys.path.insert(0, str(current_dir))

    # 确保项目根目录可被导入（main.py、youtube_transcriber.py 等）
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    # 延迟导入主程序，使用原来的 GUI 入口
    from main import youtuber

    youtuber()


if __name__ == "__main__":
    main()

