"""
GUI 模块公共常量
从 main.py 提取的常量定义
"""

import os
from pathlib import Path

# ===== 路径常量 =====

# 项目根目录（main.py 所在目录）
# constants.py 在 src/gui/ 下，需要向上3层才能到达项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .env 文件路径
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# 模板目录
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")

# 日志目录
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# 日志文件路径
COMMAND_LOG_FILE = os.path.join(LOGS_DIR, "command_history.log")
VIDEO_LIST_FILE = os.path.join(LOGS_DIR, "downloaded_videos.json")

# 闲时队列文件
IDLE_QUEUE_FILE = os.path.join(PROJECT_ROOT, "idle_queue.json")

# ===== 默认模板 =====

DEFAULT_TEMPLATE = """请将以下文本改写成一篇完整、连贯、专业的文章。

要求：
1. 你是一名资深科技领域编辑，同时具备优秀的文笔，文本转为一篇文章，确保段落清晰，文字连贯，可读性强，必要修改调整段落结构，确保内容具备良好的逻辑性。
2. 添加适当的小标题来组织内容
3. 以markdown格式输出，充分利用标题、列表、引用等格式元素
4. 如果原文有技术内容，确保准确表达并提供必要的解释

原文内容：
{content}
"""

# 默认模板文件路径
DEFAULT_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "default.txt")

# ===== 默认配置值 =====

# 闲时设置
IDLE_START_TIME = "23:00"
IDLE_END_TIME = "07:00"
IDLE_CHECK_INTERVAL_MS = 60000  # 60秒检查一次

# Whisper 模型
DEFAULT_WHISPER_MODEL = "small"

# LLM 模型
DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

# UI 默认值
DEFAULT_WINDOW_WIDTH = 900
DEFAULT_WINDOW_HEIGHT = 700

# API 服务器
API_SERVER_PORT = 8765

# 配音默认值
DEFAULT_DUBBING_VOICE = "xiaobei"
DEFAULT_DUBBING_SPEED = 1.0

# ===== 配色方案 =====

# 主色调
PRIMARY_COLOR = "#2c5aa0"
SECONDARY_COLOR = "#f0f0f0"
ACCENT_COLOR = "#e74c3c"
SUCCESS_COLOR = "#27ae60"
WARNING_COLOR = "#f39c12"
ERROR_COLOR = "#c0392b"

# 文字颜色
TEXT_PRIMARY = "#333333"
TEXT_SECONDARY = "#666666"
TEXT_LIGHT = "#999999"

# ===== API 配置 =====

# API 超时设置
API_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 300

# ===== 字幕颜色预设 =====

SUBTITLE_COLOR_PRESETS = [
    "#FFFFFF",  # 白色
    "#FFFF00",  # 黄色
    "#00FFFF",  # 青色
    "#FF00FF",  # 紫色
    "#00FF00",  # 绿色
    "#FF8800",  # 橙色
]