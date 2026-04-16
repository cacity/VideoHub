import yt_dlp
import whisper
import torch
from pathlib import Path
import openai
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
import shutil
import requests
import html
import subprocess
import json
import time
from urllib.parse import urlparse, parse_qs

# 统一的工作目录和各类子目录（videos/downloads/subtitles/...）
from paths_config import (
    WORKSPACE_DIR,
    VIDEOS_DIR,
    DOWNLOADS_DIR,
    SUBTITLES_DIR,
    TRANSCRIPTS_DIR,
    SUMMARIES_DIR,
    VIDEOS_WITH_SUBTITLES_DIR,
    NATIVE_SUBTITLES_DIR,
    DIRECTORY_MAP,
    DEFAULT_SUMMARY_DIR,
)

# Load environment variables from .env file
load_dotenv()

# 创建模板目录（模板通常较小，仍然放在项目根目录下）
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# 创建日志目录（日志体积较小，保留在项目根目录下）
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# 日志文件路径
COMMAND_LOG_FILE = os.path.join(LOGS_DIR, "command_history.log")
VIDEO_LIST_FILE = os.path.join(LOGS_DIR, "downloaded_videos.json")

# 翻译日志开关：默认开启详细日志，GUI 可通过 set_translation_verbose 控制
TRANSLATION_VERBOSE = True

def set_translation_verbose(verbose: bool):
    """
    控制是否输出详细的翻译日志。
    :param verbose: True 显示详细日志，False 仅显示简要进度
    """
    global TRANSLATION_VERBOSE
    TRANSLATION_VERBOSE = bool(verbose)

def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default

_SUBTITLE_FONT_DEFAULTS = {
    "zh": ("思源黑体 CN", 16),
    "en": ("Fira Code", 10),
    "ja": ("思源黑体 JP", 16),
}

# 字幕样式默认值
_SUBTITLE_STYLE_DEFAULTS = {
    "primary_color": "#FFFFFF",      # 原文字幕颜色（白色）
    "secondary_color": "#FFD700",    # 译文字幕颜色（金色）
    "outline_color": "#000000",      # 边框颜色（黑色）
    "back_color": "#000000",         # 背景颜色（黑色）
    "outline_width": 0.5,            # 边框宽度
    "shadow_depth": 0,               # 阴影深度
    "bold": False,                   # 粗体
    "italic": False,                 # 斜体
}

def rgb_to_ass_color(rgb_hex: str, alpha: int = 0) -> str:
    """
    将RGB十六进制颜色转换为ASS颜色格式 &HAABBGGRR

    Args:
        rgb_hex: RGB颜色，格式如 "#FFFFFF" 或 "FFFFFF"
        alpha: 透明度 (0-255)，0为完全不透明

    Returns:
        ASS颜色字符串，如 "&H00FFFFFF"
    """
    rgb_hex = rgb_hex.lstrip('#')
    if len(rgb_hex) != 6:
        rgb_hex = "FFFFFF"  # 默认白色

    try:
        r = int(rgb_hex[0:2], 16)
        g = int(rgb_hex[2:4], 16)
        b = int(rgb_hex[4:6], 16)
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"
    except ValueError:
        return "&H00FFFFFF"  # 默认白色

def _normalize_lang_key(lang_code: str) -> str:
    if not lang_code:
        return "en"
    code = str(lang_code).strip().lower()
    if code.startswith("zh") or code in {"chi", "zho"}:
        return "zh"
    if code.startswith("ja") or code in {"jpn"}:
        return "ja"
    if code.startswith("en"):
        return "en"
    return "en"

def _detect_text_lang_key(text: str) -> str:
    # 日文：优先检测假名（平假名/片假名）；其余 CJK 统一按中文处理
    if not text:
        return "en"
    import re
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", text):
        return "ja"
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh"
    return "en"

def get_subtitle_font_settings():
    """
    读取双语 ASS 字幕的字体设置（来自环境变量/设置页）。
    返回: {"zh": {"font": str, "size": int}, "en": {...}, "ja": {...}}
    """
    settings = {}
    for key, (default_font, default_size) in _SUBTITLE_FONT_DEFAULTS.items():
        font = os.getenv(f"SUBTITLE_FONT_{key.upper()}", default_font) or default_font
        # ASS 的 Fontname 不能包含逗号，否则会破坏字段分隔
        font = str(font).replace(",", " ").strip() or default_font
        size = _safe_int(os.getenv(f"SUBTITLE_FONT_{key.upper()}_SIZE", str(default_size)), default_size)
        settings[key] = {"font": font, "size": size}
    return settings

def get_subtitle_style_settings():
    """
    读取双语 ASS 字幕的样式设置（来自环境变量/设置页）。
    返回字典包含原文和译文的样式配置。
    """
    def get_color(env_key: str, default: str) -> str:
        color = os.getenv(env_key, default)
        return rgb_to_ass_color(color)

    def get_float(env_key: str, default: float) -> float:
        try:
            return float(os.getenv(env_key, str(default)))
        except:
            return default

    def get_bool(env_key: str, default: bool) -> int:
        value = os.getenv(env_key, str(default)).lower()
        return 1 if value in ("true", "1", "yes") else 0

    return {
        "primary": {
            "color": get_color("SUBTITLE_PRIMARY_COLOR", _SUBTITLE_STYLE_DEFAULTS["primary_color"]),
            "outline_color": get_color("SUBTITLE_PRIMARY_OUTLINE_COLOR", _SUBTITLE_STYLE_DEFAULTS["outline_color"]),
            "back_color": get_color("SUBTITLE_PRIMARY_BACK_COLOR", _SUBTITLE_STYLE_DEFAULTS["back_color"]),
            "outline_width": get_float("SUBTITLE_PRIMARY_OUTLINE_WIDTH", _SUBTITLE_STYLE_DEFAULTS["outline_width"]),
            "shadow_depth": get_float("SUBTITLE_PRIMARY_SHADOW_DEPTH", _SUBTITLE_STYLE_DEFAULTS["shadow_depth"]),
            "bold": get_bool("SUBTITLE_PRIMARY_BOLD", _SUBTITLE_STYLE_DEFAULTS["bold"]),
            "italic": get_bool("SUBTITLE_PRIMARY_ITALIC", _SUBTITLE_STYLE_DEFAULTS["italic"]),
        },
        "secondary": {
            "color": get_color("SUBTITLE_SECONDARY_COLOR", _SUBTITLE_STYLE_DEFAULTS["secondary_color"]),
            "outline_color": get_color("SUBTITLE_SECONDARY_OUTLINE_COLOR", _SUBTITLE_STYLE_DEFAULTS["outline_color"]),
            "back_color": get_color("SUBTITLE_SECONDARY_BACK_COLOR", _SUBTITLE_STYLE_DEFAULTS["back_color"]),
            "outline_width": get_float("SUBTITLE_SECONDARY_OUTLINE_WIDTH", _SUBTITLE_STYLE_DEFAULTS["outline_width"]),
            "shadow_depth": get_float("SUBTITLE_SECONDARY_SHADOW_DEPTH", _SUBTITLE_STYLE_DEFAULTS["shadow_depth"]),
            "bold": get_bool("SUBTITLE_SECONDARY_BOLD", _SUBTITLE_STYLE_DEFAULTS["bold"]),
            "italic": get_bool("SUBTITLE_SECONDARY_ITALIC", _SUBTITLE_STYLE_DEFAULTS["italic"]),
        }
    }

# 默认模板
DEFAULT_TEMPLATE = """请将以下文本改写成一篇完整、连贯、专业的文章。

要求：
1. 你是一名资深科技领域编辑，同时具备优秀的文笔，文本转为一篇文章，确保段落清晰，文字连贯，可读性强，必要修改调整段落结构，确保内容具备良好的逻辑性。
2. 添加适当的小标题来组织内容
3. 以markdown格式输出，充分利用标题、列表、引用等格式元素
4. 如果原文有技术内容，确保准确表达并提供必要的解释

原文内容：
{content}
"""

# 创建默认模板文件
DEFAULT_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "default.txt")
if not os.path.exists(DEFAULT_TEMPLATE_PATH):
    with open(DEFAULT_TEMPLATE_PATH, "w", encoding="utf-8") as f:
        f.write(DEFAULT_TEMPLATE)

def configure_cuda_for_whisper():
    """
    配置CUDA环境以获得最佳Whisper性能
    :return: 设备名称 ("cuda" 或 "cpu")
    """
    try:
        # 设置环境变量，避免某些CUDA相关问题
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
        os.environ['CUDA_LAUNCH_BLOCKING'] = '0'  # 非阻塞CUDA调用
        
        # 检测CUDA可用性
        if torch.cuda.is_available():
            device = "cuda"
            print(f"✓ CUDA 可用，将使用 GPU 加速")
            print(f"  - CUDA 版本: {torch.version.cuda}")
            print(f"  - GPU 数量: {torch.cuda.device_count()}")
            print(f"  - 当前 GPU: {torch.cuda.get_device_name(0)}")
            print(f"  - GPU 内存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print("  - GPU 缓存已清理")
            
            # 设置内存分配策略
            try:
                torch.cuda.set_per_process_memory_fraction(0.8)  # 使用80%的GPU内存
                print("  - GPU 内存分配限制设置为 80%")
            except:
                pass
                
        else:
            device = "cpu"
            print("⚠ CUDA 不可用，将使用 CPU 处理")
            print("  - 建议安装支持CUDA的PyTorch版本以获得更好性能")
            
            # CPU优化设置
            torch.set_num_threads(os.cpu_count())
            print(f"  - CPU 线程数设置为: {os.cpu_count()}")
            
        return device
    except Exception as e:
        print(f"配置CUDA环境时出错: {str(e)}")
        return "cpu"

def get_optimal_whisper_params(device="cpu"):
    """
    获取针对不同设备优化的Whisper参数
    :param device: 设备类型 ("cuda" 或 "cpu")
    :return: 参数字典
    """
    if device == "cuda":
        return {
            "fp16": True,  # 使用半精度浮点数加速
            "verbose": True,
            "temperature": 0,  # 使用确定性输出
            "compression_ratio_threshold": 2.4,  # 压缩比阈值
            "logprob_threshold": -1.0,  # 对数概率阈值
            "no_speech_threshold": 0.6,  # 无语音阈值
        }
    else:
        return {
            "fp16": False,  # CPU不支持FP16
            "verbose": True,
            "temperature": 0,
            "compression_ratio_threshold": 2.4,
            "logprob_threshold": -1.0,
            "no_speech_threshold": 0.6,
        }

def load_template(template_path=None):
    """
    加载模板文件
    :param template_path: 模板文件路径，如果为None则使用默认模板
    :return: 模板内容
    """
    if template_path is None:
        # 使用默认模板
        template_path = DEFAULT_TEMPLATE_PATH
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"加载模板文件失败: {str(e)}")
        print(f"使用内置默认模板")
        return DEFAULT_TEMPLATE

def sanitize_filename(filename):
    """
    清理文件名，移除或替换不安全的字符
    :param filename: 原始文件名
    :return: 清理后的文件名
    """
    # 替换不安全的字符
    # 扩展不安全字符列表，包含更多特殊符号
    unsafe_chars = [
        '<', '>', ':', '"', '/', '\\', '|', '?', '*',  # 基本不安全字符
        '【', '】', '｜', '：',  # 中文特殊字符
        '!', '@', '#', '$', '%', '^', '&', '(', ')', '+', '=',  # 其他特殊符号
        '[', ']', '{', '}', ';', "'", ',', '.', '`', '~',  # 更多特殊符号
        '—', '–', '…', '“', '”', '‘', '’',  # 破折号、引号等
        '©', '®', '™',  # 版权符号、商标符号
    ]
    
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # 替换空格为下划线
    filename = filename.replace(' ', '_')
    
    # 处理多个连续的下划线
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    # 移除前导和尾随的下划线和空格
    filename = filename.strip('_').strip()
    
    # 确保文件名不为空
    if not filename:
        filename = "video_file"
    
    # 限制文件名长度，避免路径过长
    if len(filename) > 100:
        filename = filename[:97] + '...'
    
    return filename

def translate_with_llm(text, target_language='zh-CN', source_language='auto'):
    """
    使用大模型API翻译文本
    :param text: 要翻译的文本
    :param target_language: 目标语言代码，默认为中文
    :param source_language: 源语言代码，默认为自动检测
    :return: 翻译后的文本
    """
    try:
        # 语言代码映射
        language_map = {
            'zh-CN': '简体中文',
            'zh-TW': '繁体中文',
            'en': '英语',
            'ja': '日语',
            'ko': '韩语',
            'fr': '法语',
            'de': '德语',
            'es': '西班牙语',
            'it': '意大利语',
            'ru': '俄语'
        }

        target_lang_name = language_map.get(target_language, '简体中文')

        # 优先使用DeepSeek API（更便宜），如果没有则使用OpenAI
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        proxy = os.getenv("PROXY", "")

        if not deepseek_api_key and not openai_api_key:
            if TRANSLATION_VERBOSE:
                print("警告: 未配置大模型API密钥，使用谷歌翻译作为后备")
            return translate_with_google(text, target_language, source_language)

        # 配置代理
        proxies = None
        if proxy:
            proxies = {
                "http": proxy,
                "https": proxy
            }

        # 使用DeepSeek或OpenAI
        if deepseek_api_key:
            client = OpenAI(
                api_key=deepseek_api_key,
                base_url="https://api.deepseek.com",
                http_client=None if not proxies else None  # DeepSeek通常不需要代理
            )
            model = "deepseek-chat"
        else:
            client = OpenAI(
                api_key=openai_api_key,
                http_client=None if not proxies else None
            )
            model = "gpt-3.5-turbo"

        # 构建提示词
        prompt = f"请将以下文本翻译成{target_lang_name}，只返回翻译结果，不要添加任何解释或额外内容：\n\n{text}"

        # 调用API
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"你是一个专业的翻译助手，专门将文本翻译成{target_lang_name}。你只返回翻译结果，不添加任何解释。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        translated_text = response.choices[0].message.content.strip()
        return translated_text

    except Exception as e:
        print(f"大模型翻译过程中出错: {str(e)}")
        print("尝试使用谷歌翻译作为后备...")
        return translate_with_google(text, target_language, source_language)


def translate_with_google(text, target_language='zh-CN', source_language='auto'):
    """
    使用Google翻译API翻译文本
    :param text: 要翻译的文本
    :param target_language: 目标语言代码，默认为中文
    :param source_language: 源语言代码，默认为自动检测
    :return: 翻译后的文本
    """
    try:
        # Google翻译API的URL
        url = "https://translate.googleapis.com/translate_a/single"

        # 请求参数
        params = {
            "client": "gtx",
            "sl": source_language,
            "tl": target_language,
            "dt": "t",
            "q": text
        }

        # 发送请求
        response = requests.get(url, params=params)

        if response.status_code == 200:
            # 解析响应
            result = response.json()

            # 提取翻译文本
            translated_text = ""
            for sentence in result[0]:
                if sentence[0]:
                    translated_text += sentence[0]

            return html.unescape(translated_text)
        else:
            print(f"翻译请求失败: {response.status_code}")
            return text
    except Exception as e:
        print(f"翻译过程中出错: {str(e)}")
        return text


def translate_text(text, target_language='zh-CN', source_language='auto'):
    """
    翻译文本，根据配置选择使用Google翻译或大模型翻译
    :param text: 要翻译的文本
    :param target_language: 目标语言代码，默认为中文
    :param source_language: 源语言代码，默认为自动检测
    :return: 翻译后的文本
    """
    # 从环境变量读取翻译方式配置
    translation_method = os.getenv("TRANSLATION_METHOD", "google")

    if translation_method == "llm":
        if TRANSLATION_VERBOSE:
            print(f"使用大模型翻译: {text[:50]}...")
        return translate_with_llm(text, target_language, source_language)
    else:
        if TRANSLATION_VERBOSE:
            print(f"使用谷歌翻译: {text[:50]}...")
        return translate_with_google(text, target_language, source_language)

def format_timestamp(seconds):
    """
    将秒数格式化为SRT时间戳格式 (HH:MM:SS,mmm)
    :param seconds: 秒数
    :return: 格式化的时间戳
    """
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def format_timestamp_vtt(seconds):
    """
    将秒数格式化为WebVTT时间戳格式 (HH:MM:SS.mmm)
    :param seconds: 秒数
    :return: 格式化的时间戳
    """
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = seconds % 60
    milliseconds = int((secs - int(secs)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(secs):02d}.{milliseconds:03d}"

def format_timestamp_ass(seconds):
    """
    将秒数格式化为ASS时间戳格式 (H:MM:SS.CC)
    :param seconds: 秒数
    :return: 格式化的时间戳
    """
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = seconds % 60
    centiseconds = int((secs - int(secs)) * 100)
    return f"{hours:01d}:{minutes:02d}:{int(secs):02d}.{centiseconds:02d}"

def log_command(command_args):
    """
    记录执行的命令到日志文件
    :param command_args: 命令行参数
    """
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        command_str = " ".join(command_args)
        log_entry = f"[{timestamp}] {command_str}\n"
        
        with open(COMMAND_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"记录命令日志时出错: {str(e)}")

def log_downloaded_video(youtube_url, file_path, video_info=None):
    """
    记录下载的视频信息到JSON文件
    :param youtube_url: YouTube视频链接
    :param file_path: 下载文件的路径
    :param video_info: 视频信息字典
    """
    try:
        # 读取现有记录
        video_list = []
        if os.path.exists(VIDEO_LIST_FILE):
            try:
                with open(VIDEO_LIST_FILE, "r", encoding="utf-8") as f:
                    video_list = json.load(f)
            except json.JSONDecodeError:
                # 如果文件格式不正确，创建新的列表
                video_list = []
        
        # 检查URL是否已存在
        for video in video_list:
            if video.get("url") == youtube_url:
                # 更新现有记录
                video["last_download_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                video["file_path"] = file_path
                if video_info:
                    video["title"] = video_info.get("title", "")
                    video["duration"] = video_info.get("duration", 0)
                    video["upload_date"] = video_info.get("upload_date", "")
                break
        else:
            # 添加新记录
            new_entry = {
                "url": youtube_url,
                "file_path": file_path,
                "first_download_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_download_time": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            if video_info:
                new_entry["title"] = video_info.get("title", "")
                new_entry["duration"] = video_info.get("duration", 0)
                new_entry["upload_date"] = video_info.get("upload_date", "")
            video_list.append(new_entry)
        
        # 保存更新后的列表
        with open(VIDEO_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(video_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"记录下载视频信息时出错: {str(e)}")

def list_downloaded_videos():
    """
    列出所有下载过的视频
    :return: 视频列表
    """
    try:
        if os.path.exists(VIDEO_LIST_FILE):
            with open(VIDEO_LIST_FILE, "r", encoding="utf-8") as f:
                video_list = json.load(f)
            return video_list
        return []
    except Exception as e:
        print(f"读取下载视频列表时出错: {str(e)}")
        return []

def check_youtube_subtitles(youtube_url, cookies_file=None):
    """
    检查YouTube视频是否有原生字幕
    :param youtube_url: YouTube视频链接
    :param cookies_file: cookies文件路径
    :return: 字幕信息字典
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    # 设置cookies
    if cookies_file:
        if cookies_file.startswith("browser:"):
            browser_name = cookies_file.replace("browser:", "")
            ydl_opts['cookiesfrombrowser'] = (browser_name, None, None, None)
        elif os.path.exists(cookies_file):
            ydl_opts['cookiefile'] = cookies_file
    
    proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        ydl_opts['proxy'] = proxy
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            # 检查是否成功获取视频信息
            if not info:
                return {'error': 'unable_to_access'}
            
            subtitles = info.get('subtitles', {})
            auto_subtitles = info.get('automatic_captions', {})
            
            manual_languages = list(subtitles.keys())
            auto_languages = list(auto_subtitles.keys())
            all_languages = list(set(manual_languages + auto_languages))

            result = {
                'title': info.get('title', 'Unknown'),
                'has_manual_subtitles': bool(subtitles),
                'has_auto_subtitles': bool(auto_subtitles),
                'manual_languages': manual_languages,
                'auto_languages': auto_languages,
                'all_languages': all_languages,
                'preferred_languages': [],
                # 下面几个字段用于在上层快速选择“最佳”字幕语言
                'best_manual_language': None,
                'best_auto_language': None,
                'best_overall_language': None,
                'best_is_auto': False,
            }
            
            # 通用语言优先级（越靠前优先级越高）
            # 主要用于手动字幕，自动字幕会单独再做一层优先级处理
            priority_groups = [
                ['zh-CN', 'zh-Hans', 'zh'],
                ['zh-TW', 'zh-Hant'],
                ['en-US', 'en-GB', 'en'],
            ]

            def pick_best_manual(langs):
                """从手动字幕语言列表中挑选最合适的语言"""
                if not langs:
                    return None
                # 先按通用优先组匹配（支持前缀/包含匹配）
                for group in priority_groups:
                    for target in group:
                        for lang in langs:
                            if lang == target:
                                return lang
                            # 处理类似 zh-Hans, en-US 这种前缀/后缀情况
                            if lang.startswith(target) or target.startswith(lang.split('-')[0]):
                                return lang
                # 如果没有命中优先组，就返回列表中的第一个
                return langs[0]

            def pick_best_auto(langs):
                """
                从自动字幕语言列表中挑选最合适的语言
                为了避免 YouTube 对机器翻译字幕(如 zh-Hans) 的 429 限流，
                这里优先选择英文原始轨道(en-orig/en)，再考虑中文等其他语言。
                """
                if not langs:
                    return None

                # 1) 优先使用英文原始/英文自动字幕
                for key in ['en-orig', 'en', 'en-US', 'en-GB']:
                    if key in langs:
                        return key

                # 2) 其次考虑中文自动字幕（如果真的没有英文轨道）
                for key in ['zh-CN', 'zh-Hans', 'zh', 'zh-TW', 'zh-Hant']:
                    if key in langs:
                        return key

                # 3) 其他语言按原有优先规则挑选
                for group in priority_groups:
                    for target in group:
                        for lang in langs:
                            if lang == target:
                                return lang
                            if lang.startswith(target) or target.startswith(lang.split('-')[0]):
                                return lang

                # 4) 仍然没命中就返回第一个
                return langs[0]

            best_manual = pick_best_manual(manual_languages)
            best_auto = pick_best_auto(auto_languages)

            # 组装 preferred_languages（旧字段，保持兼容）
            # 先按优先级放入中文/英文，再放入其他语言
            priority_langs = ['zh', 'zh-Hans', 'zh-CN', 'zh-TW', 'zh-Hant', 'en', 'en-US', 'en-GB']
            for lang in priority_langs:
                if lang in all_languages and lang not in result['preferred_languages']:
                    result['preferred_languages'].append(lang)
            for lang in all_languages:
                if lang not in result['preferred_languages']:
                    result['preferred_languages'].append(lang)

            # 记录最佳语言信息，供上层逻辑直接使用
            result['best_manual_language'] = best_manual
            result['best_auto_language'] = best_auto

            # 整体最佳：优先手动字幕，如果没有再用自动字幕
            if best_manual:
                result['best_overall_language'] = best_manual
                result['best_is_auto'] = False
            elif best_auto:
                result['best_overall_language'] = best_auto
                result['best_is_auto'] = True

            return result
            
    except Exception as e:
        return {'error': str(e)}

def download_youtube_subtitles(youtube_url, output_dir=NATIVE_SUBTITLES_DIR,
                             languages=['zh', 'en'], download_auto=True, cookies_file=None):
    """
    下载YouTube视频的原生字幕
    :param youtube_url: YouTube视频链接
    :param output_dir: 输出目录
    :param languages: 要下载的语言列表
    :param download_auto: 是否下载自动生成的字幕
    :param cookies_file: cookies文件路径
    :return: 下载的字幕文件列表
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    base_ydl_opts = {
        'writesubtitles': True,
        'writeautomaticsub': download_auto,
        'skip_download': True,
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'subtitlesformat': 'srt',
        'quiet': False,
    }

    # 设置cookies
    if cookies_file:
        if cookies_file.startswith("browser:"):
            browser_name = cookies_file.replace("browser:", "")
            base_ydl_opts['cookiesfrombrowser'] = (browser_name, None, None, None)
        elif os.path.exists(cookies_file):
            base_ydl_opts['cookiefile'] = cookies_file

    proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        base_ydl_opts['proxy'] = proxy

    subtitle_extensions = ['srt', 'vtt', 'ttml', 'srv3', 'srv2', 'srv1', 'json3']
    downloaded_files = []

    def find_downloaded_files(title, target_languages, existing_files=None):
        found_files = []
        existing_files = existing_files or set()
        for lang in target_languages:
            for ext in subtitle_extensions:
                manual_file = os.path.join(output_dir, f"{title}.{lang}.{ext}")
                auto_file = os.path.join(output_dir, f"{title}.{lang}.auto.{ext}")
                for candidate in [manual_file, auto_file]:
                    if os.path.exists(candidate) and candidate not in existing_files and candidate not in found_files:
                        found_files.append(candidate)
        return found_files

    try:
        # 尝试多种配置
        proxy_configs = []

        # 配置1：使用系统代理
        proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        if proxy:
            proxy_config = base_ydl_opts.copy()
            proxy_config['proxy'] = proxy
            proxy_configs.append(proxy_config)

        # 配置2：不使用代理
        no_proxy_config = base_ydl_opts.copy()
        if 'proxy' in no_proxy_config:
            del no_proxy_config['proxy']
        proxy_configs.append(no_proxy_config)

        info = None
        successful_config = None
        for config in proxy_configs:
            try:
                with yt_dlp.YoutubeDL(config) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    successful_config = config
                    break  # 成功则退出循环
            except Exception as e:
                if "proxy" in config:
                    print(f"使用代理失败，尝试直连: {str(e)}")
                else:
                    raise e  # 如果直连也失败，抛出异常

        # 检查是否成功获取视频信息
        if not info:
            print("无法获取视频信息，可能需要Cookies文件或网络问题")
            return []

        title = sanitize_filename(info.get('title', 'Unknown'))

        print(f"视频标题: {title}")

        # 检查可用字幕
        subtitles = info.get('subtitles', {})
        auto_subtitles = info.get('automatic_captions', {})

        print(f"手动字幕语言: {list(subtitles.keys())}")
        print(f"自动字幕语言: {list(auto_subtitles.keys())}")

        # 下载字幕
        if subtitles or auto_subtitles:
            print("开始下载字幕...")
            print(f"查找字幕文件，标题: '{title}', 语言: {languages}")

            download_errors = []
            existing_files = {
                str(path)
                for path in Path(output_dir).glob('*')
                if path.is_file()
            }
            for lang in languages:
                lang_config = successful_config.copy()
                lang_config['subtitleslangs'] = [lang]
                print(f"尝试下载字幕语言: {lang}")
                try:
                    with yt_dlp.YoutubeDL(lang_config) as ydl:
                        ydl.download([youtube_url])
                except Exception as e:
                    error_message = str(e)
                    download_errors.append((lang, error_message))
                    print(f"下载字幕语言 {lang} 失败: {error_message}")
                    continue

                lang_files = find_downloaded_files(title, [lang], existing_files)
                if lang_files:
                    downloaded_files.extend([f for f in lang_files if f not in downloaded_files])
                    print(f"已下载字幕语言 {lang}: {lang_files}")
                    break

                print(f"字幕语言 {lang} 下载完成，但未找到对应文件")

            if not downloaded_files:
                if download_errors:
                    print("所有候选字幕语言下载均失败:")
                    for lang, error_message in download_errors:
                        print(f"- {lang}: {error_message}")
                else:
                    print(f"在目录 {output_dir} 中未找到任何新下载的字幕文件")
        else:
            print("该视频没有可用的字幕")

        return downloaded_files

    except Exception as e:
        print(f"下载字幕时出错: {str(e)}")
        return []

def translate_subtitle_file(subtitle_path, target_language='zh-CN', base_name=None, output_dir=None, keep_lang_suffix=True):
    """
    翻译字幕文件
    :param subtitle_path: 字幕文件路径
    :param target_language: 目标语言代码
    :return: 翻译后的文件路径
    """
    try:
        import re
        
        if TRANSLATION_VERBOSE:
            print(f"开始翻译字幕文件: {subtitle_path}")
            print(f"目标语言: {target_language}")
        
        # 验证文件存在
        if not os.path.exists(subtitle_path):
            print(f"字幕文件不存在: {subtitle_path}")
            return None
        
        # 读取字幕文件
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 生成输出文件名
        # 默认输出到原字幕同目录；如果指定了 output_dir，则优先使用
        file_dir = output_dir if output_dir else os.path.dirname(subtitle_path)
        os.makedirs(file_dir, exist_ok=True)

        file_name = os.path.basename(subtitle_path)
        original_name, ext = os.path.splitext(file_name)

        # 如果指定了基准名称（通常是视频文件名），则优先使用它作为输出文件的基础名
        # 这样可以保证“视频名”和“字幕名”完全一致，只是扩展名不同
        if base_name:
            # base_name 既可以是完整路径，也可以是裸文件名；统一取 stem 再做一次清理
            base_stem = Path(base_name).stem
            name = sanitize_filename(base_stem)
        else:
            name = original_name

        # 是否在文件名中保留语言后缀（例如 _zh_CN）
        lang_suffix = target_language.replace('-', '_')
        if keep_lang_suffix:
            filename_base = f"{name}_{lang_suffix}"
        else:
            filename_base = name

        output_path = os.path.join(file_dir, f"{filename_base}{ext}")
        
        # 解析SRT格式
        if ext.lower() == '.srt':
            # SRT格式: 序号 -> 时间轴 -> 文本 -> 空行
            blocks = re.split(r'\n\s*\n', content.strip())
            translated_blocks = []
            # 收集用于生成ASS样式字幕的数据: (timestamp_line, original_text, translated_text)
            ass_segments = []
            
            for i, block in enumerate(blocks):
                if not block.strip():
                    continue
                    
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 第一行是序号
                    seq_num = lines[0]
                    # 第二行是时间轴
                    timestamp = lines[1]
                    # 剩余行是文本（去掉块内的强制换行，合并成一句，避免一大堆很短的行）
                    subtitle_text = ' '.join(l.strip() for l in lines[2:] if l.strip())
                    
                    # 翻译文本
                    # 日志：详细模式下显示前50个字符；非详细模式下，定期输出进度
                    if TRANSLATION_VERBOSE:
                        print(f"翻译字幕 {i+1}/{len(blocks)}: {subtitle_text[:50]}...")
                    elif i % 50 == 0:
                        # 每隔约 50 条输出一次简要进度，避免刷屏
                        print(f"翻译进度: {i+1}/{len(blocks)}")
                    translated_text = translate_text(subtitle_text, target_language)
                    # 去掉翻译结果中的换行，避免同一时间段出现多行超短句
                    translated_text = translated_text.replace('\n', ' ').strip()
                    
                    # 重新组合
                    translated_block = f"{seq_num}\n{timestamp}\n{translated_text}"
                    translated_blocks.append(translated_block)
                    
                    # 记录用于ASS的双语内容
                    ass_segments.append((timestamp, subtitle_text, translated_text))
            
            # 写入翻译后的文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(translated_blocks))
                f.write('\n')

            # 额外生成带样式的ASS字幕（中英双语）
            if ass_segments:
                font_settings = get_subtitle_font_settings()
                target_key = _normalize_lang_key(target_language)

                # 估算源语言：统计原文片段里中/英/日出现频率
                source_counts = {"en": 0, "zh": 0, "ja": 0}
                for _ts, original_text, _tt in ass_segments[:200]:
                    source_counts[_detect_text_lang_key(original_text)] += 1
                source_key = max(source_counts.items(), key=lambda x: x[1])[0] if any(source_counts.values()) else "en"

                source_font = font_settings[source_key]["font"]
                source_size = font_settings[source_key]["size"]
                target_font = font_settings[target_key]["font"]
                target_size = font_settings[target_key]["size"]

                def srt_time_to_ass(ts: str) -> str:
                    """将 SRT 时间戳 HH:MM:SS,mmm 转为 ASS 时间戳 H:MM:SS.cc"""
                    ts = ts.strip()
                    hms, ms = ts.split(',')
                    h, m, s = hms.split(':')
                    h = int(h)
                    m = int(m)
                    s = int(s)
                    ms = int(ms)
                    cs = int(ms / 10)  # 毫秒转厘秒
                    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

                ass_path = os.path.join(file_dir, f"{filename_base}.ass")
                with open(ass_path, 'w', encoding='utf-8') as ass_file:
                    # 获取字幕样式设置
                    style_settings = get_subtitle_style_settings()
                    primary_style = style_settings["primary"]
                    secondary_style = style_settings["secondary"]

                    # ASS 文件头和样式，尽量与 Whisper 转录生成的双语字幕保持一致
                    ass_file.write("[Script Info]\n")
                    ass_file.write("Title: 双语字幕\n")
                    ass_file.write("Original Script: MemoAI\n")
                    ass_file.write("Original Translation: MemoAI\n")
                    ass_file.write("WrapStyle: 0\n")
                    ass_file.write("Synch Point:1\n")
                    ass_file.write("Collisions:Normal\n")
                    ass_file.write("ScaledBorderAndShadow:Yes\n\n")
                    ass_file.write("[V4+ Styles]\n")
                    ass_file.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
                    ass_file.write(f"Style: Default, {source_font}, {source_size}, {primary_style['color']}, &H000000FF, {primary_style['outline_color']}, {primary_style['back_color']}, {primary_style['bold']}, {primary_style['italic']}, 0, 0, 100, 100, 0, 0, 1, {primary_style['outline_width']}, {primary_style['shadow_depth']}, 2, 10, 10, 5, 134\n")
                    ass_file.write(f"Style: Secondary, {target_font}, {target_size}, {secondary_style['color']}, &H000000FF, {secondary_style['outline_color']}, {secondary_style['back_color']}, {secondary_style['bold']}, {secondary_style['italic']}, 0, 0, 100, 100, 0, 0, 1, {secondary_style['outline_width']}, {secondary_style['shadow_depth']}, 2, 10, 10, 5, 134\n\n")
                    ass_file.write("[Events]\n")
                    ass_file.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

                    for timestamp, original_text, translated_text in ass_segments:
                        try:
                            start_str, end_str = timestamp.split('-->')
                            start_ass = srt_time_to_ass(start_str)
                            end_ass = srt_time_to_ass(end_str)
                        except Exception:
                            # 时间解析失败时跳过该条
                            continue

                        original_text = original_text or ""
                        translated_text = translated_text or ""

                        # 处理换行和特殊字符，避免ASS解析问题
                        def escape_ass(text: str) -> str:
                            return (
                                text.replace('\\', '\\\\')
                                .replace('{', '\\{')
                                .replace('}', '\\}')
                                .replace('\n', '\\N')
                            )

                        escaped_orig = escape_ass(original_text.strip())
                        escaped_trans = escape_ass(translated_text.strip())

                        # 原文使用 Default 样式
                        if escaped_orig:
                            ass_file.write(
                                f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{escaped_orig}\n"
                            )
                        # 翻译使用 Secondary 样式（中文）
                        if escaped_trans:
                            ass_file.write(
                                f"Dialogue: 0,{start_ass},{end_ass},Secondary,,0,0,0,,{escaped_trans}\n"
                            )
        
        else:
            # 对于其他格式，简单地翻译文本内容
            translated_content = translate_text(content, target_language)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)
        
        if TRANSLATION_VERBOSE:
            print(f"翻译完成，输出文件: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"翻译字幕文件时出错: {str(e)}")
        return None

def convert_subtitle_to_text(subtitle_path):
    """
    将字幕文件转换为纯文本
    :param subtitle_path: 字幕文件路径
    :return: 转换后的文本内容
    """
    try:
        import re
        
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 移除时间码和序号，只保留文本
        # 匹配SRT格式的时间码模式
        lines = content.split('\n')
        text_lines = []
        
        for line in lines:
            line = line.strip()
            # 跳过空行、序号和时间码
            if (line == '' or 
                line.isdigit() or 
                re.match(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', line)):
                continue
            text_lines.append(line)
        
        # 合并文本并清理
        text = ' '.join(text_lines)
        # 移除多余的空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
        
    except Exception as e:
        print(f"转换字幕文件失败: {str(e)}")
        return None

def get_youtube_video_title(youtube_url, cookies_file=None):
    """
    快速获取YouTube视频标题和基本信息
    :param youtube_url: YouTube视频链接
    :param cookies_file: cookies文件路径
    :return: 包含标题、时长等信息的字典
    """
    if not youtube_url or not youtube_url.strip():
        return None
        
    # 简单的URL验证
    if 'youtube.com/watch' not in youtube_url and 'youtu.be/' not in youtube_url:
        return None
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,  # 获取完整信息
    }
    
    # 设置cookies
    if cookies_file:
        if cookies_file.startswith("browser:"):
            browser_name = cookies_file.replace("browser:", "")
            ydl_opts['cookiesfrombrowser'] = (browser_name, None, None, None)
        elif os.path.exists(cookies_file):
            ydl_opts['cookiefile'] = cookies_file
    
    proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        ydl_opts['proxy'] = proxy
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            if not info:
                return None
            
            # 格式化时长
            duration = info.get('duration', 0)
            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes:02d}:{seconds:02d}"
            else:
                duration_str = "未知时长"
            
            # 格式化上传日期
            upload_date = info.get('upload_date', '')
            if upload_date and len(upload_date) == 8:
                formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            else:
                formatted_date = "未知日期"
            
            # 格式化观看次数
            view_count = info.get('view_count', 0)
            if view_count:
                if view_count >= 1000000:
                    view_str = f"{view_count/1000000:.1f}M"
                elif view_count >= 1000:
                    view_str = f"{view_count/1000:.1f}K"
                else:
                    view_str = str(view_count)
                view_str += " 次观看"
            else:
                view_str = "未知观看数"
            
            result = {
                'title': info.get('title', '未知标题'),
                'uploader': info.get('uploader', '未知UP主'),
                'duration': duration_str,
                'upload_date': formatted_date,
                'view_count': view_str,
                'description': info.get('description', '')[:200] + "..." if info.get('description', '') else "无描述",
                'has_subtitles': bool(info.get('subtitles', {})),
                'has_auto_subtitles': bool(info.get('automatic_captions', {}))
            }
            
            return result
            
    except Exception as e:
        error_msg = str(e).lower()
        
        # 检查是否是需要登录的错误
        if any(keyword in error_msg for keyword in [
            'sign in to confirm', 'not a bot', 'cookies', 'authentication'
        ]):
            return {
                'error': 'need_cookies',
                'error_msg': '🔐 YouTube需要验证身份才能访问此视频',
                'suggestion': '请设置Cookies文件以绕过机器人验证'
            }
        
        # 检查是否是地区限制
        elif any(keyword in error_msg for keyword in [
            'not available', 'blocked', 'restricted', 'region'
        ]):
            return {
                'error': 'region_blocked',
                'error_msg': '🌍 此视频在您的地区不可用',
                'suggestion': '可能需要使用代理或VPN'
            }
        
        # 检查是否是私有或删除的视频
        elif any(keyword in error_msg for keyword in [
            'private', 'deleted', 'unavailable', 'does not exist'
        ]):
            return {
                'error': 'video_unavailable',
                'error_msg': '📹 视频不存在或已设为私有',
                'suggestion': '请检查视频链接是否正确'
            }
        
        # 网络连接问题
        elif any(keyword in error_msg for keyword in [
            'network', 'connection', 'timeout', 'resolve'
        ]):
            return {
                'error': 'network_error',
                'error_msg': '🌐 网络连接问题',
                'suggestion': '请检查网络连接或稍后重试'
            }
        
        # 其他未知错误
        else:
            return {
                'error': 'unknown_error', 
                'error_msg': f'❌ 获取视频信息失败: {str(e)[:100]}',
                'suggestion': '可以尝试设置Cookies文件或检查网络连接'
            }

def format_video_tooltip(video_info):
    """
    格式化视频信息为工具提示文本
    :param video_info: 视频信息字典
    :return: 格式化的提示文本
    """
    if not video_info:
        return "无法获取视频信息"
    
    # 处理错误情况
    if 'error' in video_info:
        error_type = video_info.get('error')
        error_msg = video_info.get('error_msg', '未知错误')
        suggestion = video_info.get('suggestion', '')
        
        # 根据错误类型返回不同的提示
        if error_type == 'need_cookies':
            return f"""{error_msg}

💡 解决方案:
1. 在浏览器中登录YouTube
2. 导出cookies文件 (推荐使用浏览器插件)
3. 在"Cookies文件"字段中设置cookies路径

📚 详细教程:
• Chrome: 使用"Get cookies.txt"插件
• Firefox: 使用"cookies.txt"插件
• 手动导出: 开发者工具 > Application > Cookies

{suggestion}"""
        
        elif error_type == 'region_blocked':
            return f"""{error_msg}

💡 可能的解决方案:
• 使用VPN连接到视频允许的地区
• 设置代理服务器
• 检查视频是否真的在您的地区被屏蔽

{suggestion}"""
        
        elif error_type == 'video_unavailable':
            return f"""{error_msg}

💡 请检查:
• 视频链接是否完整和正确
• 视频是否被删除或设为私有
• 是否需要特殊权限访问

{suggestion}"""
        
        elif error_type == 'network_error':
            return f"""{error_msg}

💡 请尝试:
• 检查网络连接
• 稍后重试
• 检查防火墙设置
• 尝试使用代理

{suggestion}"""
        
        else:
            return f"""{error_msg}

💡 建议:
{suggestion}

🔧 通用解决方案:
• 确保网络连接正常
• 尝试设置Cookies文件
• 检查是否需要代理访问"""
    
    # 正常情况，显示视频信息
    subtitle_status = ""
    if video_info.get('has_subtitles'):
        subtitle_status = " ✅有人工字幕"
    elif video_info.get('has_auto_subtitles'):
        subtitle_status = " 🤖有自动字幕"
    else:
        subtitle_status = " ❌无字幕"
    
    tooltip = f"""🎬 {video_info.get('title', '未知标题')}
👤 UP主: {video_info.get('uploader', '未知')}
⏱️ 时长: {video_info.get('duration', '未知')}
📅 上传: {video_info.get('upload_date', '未知')}
👁️ 观看: {video_info.get('view_count', '未知')}
📝 字幕:{subtitle_status}

📖 简介: {video_info.get('description', '无描述')[:100]}..."""
    
    return tooltip

def download_youtube_video(youtube_url, output_dir=None, audio_only=True, cookies_file=None):
    """
    从YouTube下载视频或音频
    :param youtube_url: YouTube视频链接
    :param output_dir: 输出目录，如果为None，则根据audio_only自动选择目录
    :param audio_only: 是否只下载音频，如果为False则下载视频
    :param cookies_file: cookies文件路径，用于访问需要登录的内容
    :return: 下载文件的完整路径
    """
    # 根据下载类型选择默认输出目录（统一挂在 workspace/ 下）
    if output_dir is None:
        output_dir = DOWNLOADS_DIR if audio_only else VIDEOS_DIR

    # 在尝试下载前，先检查是否已经下载过同一URL对应的本地文件
    try:
        existing_list = list_downloaded_videos()
    except Exception:
        existing_list = []

    def _has_expected_type(path: str, audio_only_flag: bool) -> bool:
        """根据扩展名粗略判断文件类型是否匹配当前需求（视频/音频）。"""
        ext = os.path.splitext(path)[1].lower()
        if audio_only_flag:
            return ext in [".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"]
        else:
            return ext in [".mp4", ".mkv", ".webm", ".mov", ".flv", ".avi"]

    for item in existing_list:
        if item.get("url") != youtube_url:
            continue
        recorded_path = item.get("file_path")
        if not recorded_path:
            continue
        # 支持相对路径和绝对路径
        candidate_path = recorded_path
        if not os.path.isabs(candidate_path):
            candidate_path = os.path.abspath(candidate_path)
        if os.path.exists(candidate_path) and _has_expected_type(candidate_path, audio_only):
            # 如果有记录下来的标题，优先校验一下文件名与标题是否大致匹配，
            # 避免历史上因为回退逻辑把别的视频文件错误地记录到当前URL。
            title = item.get("title")
            if title:
                expected_stem = sanitize_filename(title)
                # 为了对比公平，当前文件名也先做一遍相同的清理。
                # 注意 file_path 可能是 Windows 风格路径（包含反斜杠），不能直接用 Path().stem。
                tmp = candidate_path.replace("/", "\\")
                basename = tmp.split("\\")[-1]
                current_stem = sanitize_filename(os.path.splitext(basename)[0])
                if expected_stem and current_stem and expected_stem != current_stem:
                    print(
                        "警告: 已有下载记录的文件名与标题不匹配，"
                        f"可能是旧版本逻辑造成的错误映射，忽略此记录并重新下载: {candidate_path}"
                    )
                    continue

            # 如果历史文件名中仍然包含空格或不安全字符，这里顺便做一次清理，
            # 保证后续使用的都是 sanitize_filename 规则下的“干净文件名”。
            dir_name = os.path.dirname(candidate_path)
            stem = Path(candidate_path).stem
            ext = os.path.splitext(candidate_path)[1]
            sanitized_stem = sanitize_filename(stem)
            final_path = candidate_path
            if sanitized_stem != stem:
                sanitized_path = os.path.join(dir_name, f"{sanitized_stem}{ext}")
                try:
                    os.rename(candidate_path, sanitized_path)
                    print(f"已清理已有下载文件名: {candidate_path} -> {sanitized_path}")
                    final_path = sanitized_path
                    try:
                        # 更新下载记录中的路径
                        log_downloaded_video(youtube_url, final_path)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"重命名已下载文件失败: {str(e)}")

            print(f"检测到本地已存在下载文件，跳过重新下载: {final_path}")
            return final_path
    
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {os.path.abspath(output_dir)}")

    # 记录下载前目录中已有的文件，后面回退时只在“新增文件”里查找，避免误把旧文件当成结果
    existing_files = {str(p) for p in Path(output_dir).glob("*.*")}

    # 设置yt-dlp的选项
    if audio_only:
        # 音频下载选项
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',  # 优先选择m4a格式的音频
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': False,  # 显示下载进度和错误信息
            'ignoreerrors': True,  # 忽略部分错误，尝试继续下载
            'noplaylist': True  # 确保只下载单个视频的音频而不是整个播放列表
        }
        expected_ext = "mp3"
    else:
        # 视频下载选项（最佳画质）
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',  # 使用更可靠的格式组合
            'merge_output_format': 'mp4',  # 确保输出为mp4
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': False,  # 显示下载进度和错误信息
            'ignoreerrors': True,  # 忽略部分错误，尝试继续下载
            'noplaylist': True  # 确保只下载单个视频而不是整个播放列表
        }
        expected_ext = "mp4"
    
    # 如果提供了cookies，添加到选项中
    if cookies_file:
        if cookies_file.startswith("browser:"):
            # 使用浏览器cookies
            browser_name = cookies_file.replace("browser:", "")
            print(f"使用 {browser_name.title()} 浏览器cookies")
            ydl_opts['cookiesfrombrowser'] = (browser_name, None, None, None)
        elif os.path.exists(cookies_file):
            # 使用cookies文件
            print(f"使用cookies文件: {cookies_file}")
            ydl_opts['cookiefile'] = cookies_file
        else:
            print(f"警告: cookies文件不存在: {cookies_file}")

    # 检查代理设置
    proxy = os.getenv("PROXY")
    if proxy:
        print(f"使用代理: {proxy}")
        ydl_opts['proxy'] = proxy
    
    try:
        print(f"开始{'音频' if audio_only else '视频'}下载: {youtube_url}")
        print(f"下载选项: {'仅音频' if audio_only else '完整视频'}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 获取视频信息
            print(f"正在获取视频信息...")
            info = ydl.extract_info(youtube_url, download=True)

            # 尝试从info中获取实际导出的文件扩展名，避免与预期扩展名不一致导致找不到文件
            try:
                info_ext = info.get("ext")
                if isinstance(info_ext, str) and info_ext:
                    expected_ext = info_ext.lower()
                    print(f"检测到实际文件扩展名: .{expected_ext}")
            except Exception:
                pass
            
            # 检查是否成功获取视频信息
            if not info:
                error_msg = "无法获取视频信息，可能的原因：\n"
                error_msg += "1. 视频需要登录才能访问 - 请设置Cookies文件\n"
                error_msg += "2. 视频被地区限制 - 可能需要VPN\n"
                error_msg += "3. 视频已被删除或设为私有\n"
                error_msg += "4. 网络连接问题\n"
                if not cookies_file:
                    error_msg += "\n💡 建议：尝试设置Cookies文件以解决访问限制问题"
                print(error_msg)
                raise Exception(error_msg)
            
            # 记录下载的视频信息
            try:
                log_downloaded_video(youtube_url, "未知路径", info)
            except Exception as e:
                print(f"记录视频信息时出错: {str(e)}")
            
            # 获取原始文件名并清理
            original_title = info.get('title', '未知视频')
            print(f"原始视频标题: {original_title}")
            sanitized_title = sanitize_filename(original_title)
            print(f"清理后的标题: {sanitized_title}")
            
            # 构建文件路径
            original_path = os.path.join(output_dir, f"{original_title}.{expected_ext}")
            sanitized_path = os.path.join(output_dir, f"{sanitized_title}.{expected_ext}")
            
            print(f"原始文件路径: {original_path}")
            print(f"清理后的文件路径: {sanitized_path}")
            
            # 如果文件名被清理了，需要重命名文件
            if original_path != sanitized_path and os.path.exists(original_path):
                try:
                    os.rename(original_path, sanitized_path)
                    print(f"文件已重命名: {original_title} -> {sanitized_title}")
                except Exception as e:
                    print(f"重命名文件失败: {str(e)}")
            
            # 检查文件是否存在
            if os.path.exists(sanitized_path):
                print(f"文件下载成功: {sanitized_path}")
                # 更新下载记录中的文件路径
                log_downloaded_video(youtube_url, sanitized_path, info)
                return sanitized_path
            elif os.path.exists(original_path):
                print(f"文件下载成功但未重命名: {original_path}")
                # 更新下载记录中的文件路径
                log_downloaded_video(youtube_url, original_path, info)
                return original_path
            else:
                # 回退：只在“本次下载新增”的文件中查找，避免误把旧文件当成下载结果
                all_files_after = list(Path(output_dir).glob("*.*"))
                new_files = [p for p in all_files_after if str(p) not in existing_files]

                newest_file = None
                if new_files:
                    # 优先选择与期望扩展名一致的新增文件
                    expected_files = [
                        p for p in new_files
                        if p.suffix.lower().lstrip(".") == expected_ext.lower()
                    ]
                    candidate_files = expected_files or new_files
                    newest_file = max(candidate_files, key=os.path.getctime)
                    print(f"找到可能的本次下载文件: {newest_file}")
                else:
                    print("未检测到本次下载产生的新文件，可能下载失败或输出目录被其他程序修改")

                if newest_file:
                    final_path = str(newest_file)
                    # 尝试将该文件重命名为清理后的标题，确保没有空格和不安全字符
                    try:
                        stem = Path(final_path).stem
                        ext = Path(final_path).suffix
                        sanitized_stem = sanitize_filename(stem)
                        sanitized_candidate = os.path.join(output_dir, f"{sanitized_stem}{ext}")
                        if sanitized_candidate != final_path:
                            os.rename(final_path, sanitized_candidate)
                            print(f"已重命名下载文件: {final_path} -> {sanitized_candidate}")
                            final_path = sanitized_candidate
                    except Exception as e:
                        print(f"重命名下载文件失败: {str(e)}")

                    # 更新下载记录中的文件路径
                    log_downloaded_video(youtube_url, final_path, info)
                    return final_path

                raise Exception(f"下载成功但找不到文件，请检查 {output_dir} 目录")
    except yt_dlp.utils.DownloadError as e:
        print(f"下载失败详细信息: {str(e)}")
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            if cookies_file:
                print(f"错误: 提供的cookies文件无效或已过期: {cookies_file}")
                print("请尝试使用最新的cookies文件或从浏览器中导出新的cookies")
            else:
                print("错误: YouTube要求登录验证，请使用--cookies参数提供有效的cookies文件")
                print("可以使用浏览器扩展如'Get cookies.txt'导出cookies文件")
        raise Exception(f"下载失败: {str(e)}")
    except Exception as e:
        print(f"下载失败详细信息: {str(e)}")
        raise Exception(f"下载失败: {str(e)}")

def download_youtube_audio(youtube_url, output_dir=DOWNLOADS_DIR, cookies_file=None):
    """
    从YouTube视频中下载音频
    :param youtube_url: YouTube视频链接
    :param output_dir: 输出目录
    :param cookies_file: cookies文件路径，用于访问需要登录的内容
    :return: 音频文件的完整路径
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 设置yt-dlp的选项
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True
    }
    
    # 如果提供了cookies文件，添加到选项中
    if cookies_file and os.path.exists(cookies_file):
        print(f"使用cookies文件: {cookies_file}")
        ydl_opts['cookiefile'] = cookies_file
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 获取视频信息
            info = ydl.extract_info(youtube_url, download=True)
            
            # 获取原始文件名并清理
            original_title = info['title']
            sanitized_title = sanitize_filename(original_title)
            
            # 如果文件名被清理了，需要重命名文件
            original_path = os.path.join(output_dir, f"{original_title}.mp3")
            sanitized_path = os.path.join(output_dir, f"{sanitized_title}.mp3")
            
            if original_path != sanitized_path and os.path.exists(original_path):
                try:
                    os.rename(original_path, sanitized_path)
                    print(f"文件已重命名: {original_title} -> {sanitized_title}")
                except Exception as e:
                    print(f"重命名文件失败: {str(e)}")
            
            # 返回清理后的文件路径
            return sanitized_path
    except Exception as e:
        raise Exception(f"下载音频失败: {str(e)}")

def extract_audio_from_video(video_path, output_dir=DOWNLOADS_DIR):
    """
    从视频文件中提取音频
    :param video_path: 视频文件路径
    :param output_dir: 输出目录，默认为downloads
    :return: 提取的音频文件路径
    """
    try:
        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 获取视频文件名（不含扩展名）
        video_name = Path(video_path).stem
        sanitized_name = sanitize_filename(video_name)
        
        # 设置输出音频路径
        audio_path = os.path.join(output_dir, f"{sanitized_name}.mp3")
        
        print(f"正在从视频提取音频: {video_path} -> {audio_path}")
        
        # 检查ffmpeg是否可用
        try:
            import subprocess
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode != 0:
                print("警告: ffmpeg命令不可用。请确保已安装ffmpeg并添加到系统PATH中。")
                print("您可以从 https://ffmpeg.org/download.html 下载ffmpeg。")
                raise Exception("ffmpeg命令不可用")
        except FileNotFoundError:
            print("错误: 找不到ffmpeg命令。请确保已安装ffmpeg并添加到系统PATH中。")
            print("您可以从 https://ffmpeg.org/download.html 下载ffmpeg。")
            raise Exception("找不到ffmpeg命令")
        
        # 首先检查视频文件是否包含音频流
        import subprocess
        probe_cmd = ["ffmpeg", "-i", video_path, "-hide_banner"]
        probe_process = subprocess.Popen(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = probe_process.communicate()
        stderr_text = stderr.decode('utf-8', errors='ignore')
        
        # 检查输出中是否包含音频流信息
        if "Stream" in stderr_text and "Audio" not in stderr_text:
            print("警告: 视频文件不包含音频流")
            print("错误详情:")
            print(stderr_text)
            raise Exception("视频文件不包含音频流，无法提取音频")
        
        # 使用ffmpeg-python库提取音频
        try:
            import ffmpeg
            # 使用ffmpeg-python库
            try:
                # 先获取视频信息
                probe = ffmpeg.probe(video_path)
                # 检查是否有音频流
                audio_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
                if not audio_streams:
                    raise Exception("视频文件不包含音频流，无法提取音频")
                
                # 有音频流，继续处理
                (
                    ffmpeg
                    .input(video_path)
                    .output(audio_path, acodec='libmp3lame', q=0)
                    .run(quiet=False, overwrite_output=True, capture_stdout=True, capture_stderr=True)
                )
                print(f"音频提取完成: {audio_path}")
            except ffmpeg._run.Error as e:
                print(f"ffmpeg错误: {str(e)}")
                print("尝试使用subprocess直接调用ffmpeg...")
                raise Exception("ffmpeg-python库调用失败，尝试使用subprocess")
        except (ImportError, Exception) as e:
            # 如果ffmpeg-python库不可用或调用失败，回退到subprocess
            print(f"使用subprocess调用ffmpeg: {str(e)}")
            import subprocess
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-q:a", "0",
                "-vn",
                "-y",  # 覆盖输出文件
                audio_path
            ]
            
            # 执行命令，捕获输出
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                stderr_text = stderr.decode('utf-8', errors='ignore')
                print(f"ffmpeg命令执行失败，返回代码: {process.returncode}")
                print(f"错误输出: {stderr_text}")
                
                # 检查是否是因为没有音频流
                if "Stream map 'a' matches no streams" in stderr_text or "does not contain any stream" in stderr_text:
                    raise Exception("视频文件不包含音频流，无法提取音频")
                else:
                    raise Exception(f"ffmpeg命令执行失败: {stderr_text}")
            
            print(f"音频提取完成: {audio_path}")
        
        # 检查生成的音频文件是否存在
        if not os.path.exists(audio_path):
            raise Exception(f"音频文件未生成: {audio_path}")
        
        # 检查音频文件大小
        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            raise Exception(f"生成的音频文件大小为0: {audio_path}")
        
        print(f"音频文件大小: {file_size} 字节")
        return audio_path
    except Exception as e:
        error_msg = f"从视频提取音频失败: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)

def transcribe_audio_unified(
    audio_path,
    output_dir=TRANSCRIPTS_DIR,
    subtitle_dir=SUBTITLES_DIR,
    model_size="small",
    generate_subtitles=False,
    translate_to_chinese=True,
    source_language=None,
    output_basename=None,
):
    """
    统一的音频转录函数：一次转录，同时生成文本和字幕文件
    :param audio_path: 音频文件路径
    :param output_dir: 转录文本保存目录
    :param subtitle_dir: 字幕文件保存目录
    :param model_size: Whisper模型大小
    :param generate_subtitles: 是否生成字幕文件
    :param translate_to_chinese: 是否翻译成中文
    :param source_language: 源语言
    :param output_basename: 输出文件基础名（可选，一般传入视频文件路径以保证字幕名与视频名一致）
    :return: (text_path, subtitle_path) 元组，如果不生成字幕则 subtitle_path 为 None
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if generate_subtitles:
        Path(subtitle_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # 配置CUDA环境
        device = configure_cuda_for_whisper()
        
        # 获取优化的参数
        whisper_params = get_optimal_whisper_params(device)
        whisper_params["task"] = "transcribe"
        
        # 如果指定了源语言，添加language参数
        if source_language and source_language != "auto":
            whisper_params["language"] = source_language
            print(f"使用指定的源语言: {source_language}")
        
        # 加载模型
        print(f"加载 {model_size} 模型...")
        start_time = time.time()
        model = whisper.load_model(model_size, device=device)
        load_time = time.time() - start_time
        print(f"模型加载完成，耗时: {load_time:.2f}秒")
        
        # 转录音频（一次性完成）
        print("开始转录音频...")
        transcribe_start = time.time()
        result = model.transcribe(audio_path, **whisper_params)
        transcribe_time = time.time() - transcribe_start
        print(f"转录完成，耗时: {transcribe_time:.2f}秒")
        
        # 显示性能信息
        if 'segments' in result:
            total_duration = result['segments'][-1]['end'] if result['segments'] else 0
            if total_duration > 0:
                speed_ratio = total_duration / transcribe_time
                print(f"转录速度: {speed_ratio:.1f}x 实时速度（{total_duration:.1f}秒音频用时{transcribe_time:.2f}秒）")
        
        # 生成输出文件路径
        # 默认以音频文件名为基础；如果指定了 output_basename（通常是视频文件路径），则优先使用，
        # 这样可以保证“视频文件名”和“字幕文件名”完全一致，只是扩展名不同。
        if output_basename:
            base_name = Path(output_basename).stem
        else:
            base_name = Path(audio_path).stem
        sanitized_name = sanitize_filename(base_name)
        
        # 保存转录文本
        text_path = os.path.join(output_dir, f"{sanitized_name}.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(result["text"])
        print(f"转录文本已保存到: {text_path}")
        
        subtitle_path = None
        if generate_subtitles and 'segments' in result and result['segments']:
            # 获取源语言
            detected_language = result.get("language", "en")
            if source_language and source_language != "auto":
                final_source_language = source_language
            else:
                final_source_language = detected_language
            print(f"检测到的语言: {final_source_language}")
            
            # 生成字幕文件路径（与视频同名，无额外后缀，便于播放器自动匹配）
            srt_path = os.path.join(subtitle_dir, f"{sanitized_name}.srt")
            vtt_path = os.path.join(subtitle_dir, f"{sanitized_name}.vtt")
            ass_path = os.path.join(subtitle_dir, f"{sanitized_name}.ass")
            
            # 创建SRT字幕文件
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                for i, segment in enumerate(result["segments"]):
                    start_time = segment["start"]
                    end_time = segment["end"]
                    original_text = segment["text"].strip()
                    
                    # 翻译处理
                    translated_text = ""
                    if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                        try:
                            translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                            if i < 3:  # 只显示前3个翻译示例
                                print(f"翻译示例: {original_text} -> {translated_text}")
                        except Exception as e:
                            print(f"翻译失败: {str(e)}")
                    
                    # 写入SRT格式
                    srt_file.write(f"{i+1}\n")
                    srt_file.write(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n")
                    srt_file.write(f"{original_text}\n")
                    if translated_text:
                        srt_file.write(f"{translated_text}\n")
                    srt_file.write("\n")
            
            # 创建VTT字幕文件  
            with open(vtt_path, "w", encoding="utf-8") as vtt_file:
                vtt_file.write("WEBVTT\n\n")
                for i, segment in enumerate(result["segments"]):
                    start_time = segment["start"]
                    end_time = segment["end"]
                    original_text = segment["text"].strip()
                    
                    translated_text = ""
                    if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                        try:
                            translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                        except:
                            pass
                    
                    vtt_file.write(f"{format_timestamp_vtt(start_time)} --> {format_timestamp_vtt(end_time)}\n")
                    vtt_file.write(f"{original_text}\n")
                    if translated_text:
                        vtt_file.write(f"{translated_text}\n")
                    vtt_file.write("\n")
            
            # 创建ASS字幕文件
            with open(ass_path, "w", encoding="utf-8") as ass_file:
                font_settings = get_subtitle_font_settings()
                source_key = _normalize_lang_key(final_source_language)
                target_key = "zh" if translate_to_chinese else source_key
                source_font = font_settings[source_key]["font"]
                source_size = font_settings[source_key]["size"]
                target_font = font_settings[target_key]["font"]
                target_size = font_settings[target_key]["size"]

                # 获取字幕样式设置
                style_settings = get_subtitle_style_settings()
                primary_style = style_settings["primary"]
                secondary_style = style_settings["secondary"]

                # ASS文件头
                ass_file.write("[Script Info]\n")
                ass_file.write("Title: Bilingual Subtitles\n")
                ass_file.write("ScriptType: v4.00+\n\n")
                ass_file.write("[V4+ Styles]\n")
                ass_file.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
                ass_file.write(f"Style: Default, {source_font}, {source_size}, {primary_style['color']}, &H000000FF, {primary_style['outline_color']}, {primary_style['back_color']}, {primary_style['bold']}, {primary_style['italic']}, 0, 0, 100, 100, 0, 0, 1, {primary_style['outline_width']}, {primary_style['shadow_depth']}, 2, 10, 10, 5, 134\n")
                ass_file.write(f"Style: Secondary, {target_font}, {target_size}, {secondary_style['color']}, &H000000FF, {secondary_style['outline_color']}, {secondary_style['back_color']}, {secondary_style['bold']}, {secondary_style['italic']}, 0, 0, 100, 100, 0, 0, 1, {secondary_style['outline_width']}, {secondary_style['shadow_depth']}, 2, 10, 10, 5, 134\n\n")
                ass_file.write("[Events]\n")
                ass_file.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
                
                for segment in result["segments"]:
                    start_time = segment["start"]
                    end_time = segment["end"]
                    original_text = segment["text"].strip()

                    translated_text = ""
                    if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                        try:
                            translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                        except:
                            pass

                    # 处理特殊字符，避免在ASS字幕中出现问题
                    escaped_text = original_text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')

                    # 写入原文（使用Default样式）
                    ass_file.write(f"Dialogue: 0,{format_timestamp_ass(start_time)},{format_timestamp_ass(end_time)},Default,,0,0,0,,{escaped_text}\n")

                    # 如果有翻译，写入翻译（使用Secondary样式，黄色）
                    if translated_text:
                        escaped_translated = translated_text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                        ass_file.write(f"Dialogue: 0,{format_timestamp_ass(start_time)},{format_timestamp_ass(end_time)},Secondary,,0,0,0,,{escaped_translated}\n")
            
            subtitle_path = srt_path  # 返回主要的字幕文件路径
            print(f"字幕文件已保存:")
            print(f"  SRT: {srt_path}")
            print(f"  VTT: {vtt_path}")
            print(f"  ASS: {ass_path}")
        
        # 清理CUDA缓存
        if device == "cuda":
            torch.cuda.empty_cache()
            
        return text_path, subtitle_path
        
    except Exception as e:
        # 清理CUDA缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise Exception(f"音频转录失败: {str(e)}")

def transcribe_audio_to_text(audio_path, output_dir=TRANSCRIPTS_DIR, model_size="small"):
    """
    使用Whisper将音频转换为文本（支持CUDA加速）
    :param audio_path: 音频文件路径
    :param output_dir: 输出目录
    :param model_size: 模型大小，可选 "tiny", "base", "small", "medium", "large"
    :return: 文本文件的路径
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # 配置CUDA环境
        device = configure_cuda_for_whisper()
        
        # 获取优化的参数
        whisper_params = get_optimal_whisper_params(device)
        
        # 加载模型
        print(f"加载 {model_size} 模型...")
        start_time = time.time()
        model = whisper.load_model(model_size, device=device)
        load_time = time.time() - start_time
        print(f"模型加载完成，耗时: {load_time:.2f}秒")
        
        # 转录音频
        print("开始转录音频...")
        transcribe_start = time.time()
        result = model.transcribe(audio_path, **whisper_params)
        transcribe_time = time.time() - transcribe_start
        print(f"转录完成，耗时: {transcribe_time:.2f}秒")
        
        # 显示性能信息
        if 'segments' in result:
            total_duration = result['segments'][-1]['end'] if result['segments'] else 0
            if total_duration > 0:
                speed_ratio = total_duration / transcribe_time
                print(f"转录速度: {speed_ratio:.1f}x 实时速度（{total_duration:.1f}秒音频用时{transcribe_time:.2f}秒）")
        
        # 生成输出文件路径
        base_name = Path(audio_path).stem
        sanitized_base_name = sanitize_filename(base_name)
        output_path = os.path.join(output_dir, f"{sanitized_base_name}_transcript.txt")
        
        # 保存转录文本
        with open(output_path, "w", encoding="utf-8") as f:
            # 如果result包含segments，按段落保存
            if 'segments' in result:
                for segment in result['segments']:
                    f.write(f"{segment['text'].strip()}\n\n")
            else:
                f.write(result['text'])
        
        # 清理GPU缓存
        if device == "cuda":
            torch.cuda.empty_cache()
        
        return output_path
    except Exception as e:
        # 清理GPU缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise Exception(f"音频转文字失败: {str(e)}")

def transcribe_only(audio_path, whisper_model_size="medium", output_dir=TRANSCRIPTS_DIR):
    """
    仅将音频转换为文本，不进行摘要生成
    
    参数:
        audio_path (str): 音频文件路径
        whisper_model_size (str): Whisper模型大小
        output_dir (str): 转录文本保存目录
    
    返回:
        str: 转录文本文件路径
    """
    print(f"正在将音频转换为文本: {audio_path}")
    
    # 检查文件是否存在
    if not os.path.exists(audio_path):
        print(f"错误: 文件 {audio_path} 不存在")
        return None
    
    # 转录音频
    text_path = transcribe_audio_to_text(audio_path, output_dir=output_dir, model_size=whisper_model_size)
    
    print(f"音频转文本完成，文本已保存至: {text_path}")
    return text_path

def create_bilingual_subtitles(audio_path, output_dir=SUBTITLES_DIR, model_size="tiny", translate_to_chinese=True, source_language=None):
    """
    创建双语字幕文件
    :param audio_path: 音频文件路径
    :param output_dir: 输出目录
    :param model_size: Whisper模型大小
    :param translate_to_chinese: 是否翻译成中文
    :param source_language: 指定源语言（可选），如果为None则自动检测
    :return: 字幕文件路径
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # 首先验证音频文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        print(f"准备从音频创建字幕: {audio_path}")
        
        # 配置CUDA环境
        device = configure_cuda_for_whisper()
        
        # 获取优化的参数
        whisper_params = get_optimal_whisper_params(device)
        whisper_params["task"] = "transcribe"  # 使用转录任务
        
        # 加载模型
        print(f"加载 {model_size} 模型...")
        start_time = time.time()
        try:
            model = whisper.load_model(model_size, device=device)
            load_time = time.time() - start_time
            print(f"模型加载成功，耗时: {load_time:.2f}秒")
        except Exception as e:
            print(f"模型加载失败: {str(e)}")
            raise
        
        # 如果指定了源语言，添加language参数
        if source_language and source_language != "auto":
            whisper_params["language"] = source_language
            print(f"使用指定的源语言: {source_language}")
        
        # 转录音频
        print("开始转录音频并生成字幕...")
        transcribe_start = time.time()
        result = model.transcribe(audio_path, **whisper_params)
        transcribe_time = time.time() - transcribe_start
        print(f"字幕转录完成，耗时: {transcribe_time:.2f}秒")
        
        # 显示性能信息
        if 'segments' in result and result['segments']:
            total_duration = result['segments'][-1]['end']
            speed_ratio = total_duration / transcribe_time
            print(f"转录速度: {speed_ratio:.1f}x 实时速度（{total_duration:.1f}秒音频用时{transcribe_time:.2f}秒）")
        
        # 获取源语言 - 如果已指定则使用指定的，否则使用检测到的
        detected_language = result.get("language", "en")
        if source_language and source_language != "auto":
            final_source_language = source_language
        else:
            final_source_language = detected_language
        print(f"最终使用的语言: {final_source_language}")
        
        # 生成输出文件路径
        base_name = Path(audio_path).stem
        sanitized_name = sanitize_filename(base_name)
        srt_path = os.path.join(output_dir, f"{sanitized_name}_bilingual.srt")
        vtt_path = os.path.join(output_dir, f"{sanitized_name}_bilingual.vtt")
        ass_path = os.path.join(output_dir, f"{sanitized_name}_bilingual.ass")
        
        # 创建SRT字幕文件
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            # 写入SRT文件
            for i, segment in enumerate(result["segments"]):
                # 获取时间戳
                start_time = segment["start"]
                end_time = segment["end"]
                
                # 获取文本
                original_text = segment["text"].strip()
                
                # 如果需要翻译且源语言不是中文
                translated_text = ""
                if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                    translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                    print(f"翻译: {original_text} -> {translated_text}")
                
                # 写入字幕索引
                srt_file.write(f"{i+1}\n")
                
                # 写入时间戳
                srt_file.write(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n")
                
                # 写入原文
                srt_file.write(f"{original_text}\n")
                
                # 如果有翻译，写入翻译
                if translated_text:
                    srt_file.write(f"{translated_text}\n")
                
                # 空行分隔
                srt_file.write("\n")
        
        # 创建WebVTT字幕文件
        with open(vtt_path, "w", encoding="utf-8") as vtt_file:
            # 写入WebVTT头
            vtt_file.write("WEBVTT\n\n")
            
            # 写入字幕
            for i, segment in enumerate(result["segments"]):
                # 获取时间戳
                start_time = segment["start"]
                end_time = segment["end"]
                
                # 格式化WebVTT时间戳 (HH:MM:SS.mmm)
                start_formatted = str(timedelta(seconds=start_time)).rjust(8, '0').replace(',', '.')
                end_formatted = str(timedelta(seconds=end_time)).rjust(8, '0').replace(',', '.')
                
                # 获取文本
                original_text = segment["text"].strip()
                
                # 如果需要翻译且源语言不是中文
                translated_text = ""
                if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                    # 使用缓存的翻译结果，避免重复翻译
                    if not hasattr(create_bilingual_subtitles, 'translation_cache'):
                        create_bilingual_subtitles.translation_cache = {}
                    
                    if original_text in create_bilingual_subtitles.translation_cache:
                        translated_text = create_bilingual_subtitles.translation_cache[original_text]
                    else:
                        translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                        create_bilingual_subtitles.translation_cache[original_text] = translated_text
                
                # 写入时间戳
                vtt_file.write(f"{start_formatted} --> {end_formatted}\n")
                
                # 写入原文
                vtt_file.write(f"{original_text}\n")
                
                # 如果有翻译，写入翻译
                if translated_text:
                    vtt_file.write(f"{translated_text}\n")
                
                # 空行分隔
                vtt_file.write("\n")
        
        # 创建ASS字幕文件（高级字幕格式，支持更多样式）
        with open(ass_path, "w", encoding="utf-8") as ass_file:
            font_settings = get_subtitle_font_settings()
            source_key = _normalize_lang_key(final_source_language)
            target_key = "zh" if translate_to_chinese else source_key
            source_font = font_settings[source_key]["font"]
            source_size = font_settings[source_key]["size"]
            target_font = font_settings[target_key]["font"]
            target_size = font_settings[target_key]["size"]

            # 写入ASS头部
            ass_file.write("[Script Info]\n")
            ass_file.write("Title: 双语字幕\n")
            ass_file.write("Original Script: MemoAI\n")
            ass_file.write("Original Translation: MemoAI\n")
            ass_file.write("WrapStyle: 0\n")
            ass_file.write("Synch Point:1\n")
            ass_file.write("Collisions:Normal\n")
            ass_file.write("ScaledBorderAndShadow:Yes\n\n")
            
            # 写入样式
            ass_file.write("[V4+ Styles]\n")
            ass_file.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            ass_file.write(f"Style: Default, {source_font}, {source_size}, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 0.5, 0, 2, 10, 10, 5, 134\n")
            ass_file.write(f"Style: Secondary, {target_font}, {target_size}, &H0000D7FF, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 0.5, 0, 2, 10, 10, 5, 134\n\n")
            
            # 写入事件
            ass_file.write("[Events]\n")
            ass_file.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            
            # 写入字幕
            for i, segment in enumerate(result["segments"]):
                # 获取时间戳
                start_time = segment["start"]
                end_time = segment["end"]
                
                # 格式化ASS时间戳 (H:MM:SS.cc)
                start_h = int(start_time / 3600)
                start_m = int((start_time % 3600) / 60)
                start_s = int(start_time % 60)
                start_cs = int((start_time % 1) * 100)
                start_formatted = f"{start_h}:{start_m:02d}:{start_s:02d}.{start_cs:02d}"
                
                end_h = int(end_time / 3600)
                end_m = int((end_time % 3600) / 60)
                end_s = int(end_time % 60)
                end_cs = int((end_time % 1) * 100)
                end_formatted = f"{end_h}:{end_m:02d}:{end_s:02d}.{end_cs:02d}"
                
                # 获取文本
                original_text = segment["text"].strip()
                
                # 写入原文
                # 处理特殊字符，避免在ASS字幕中出现问题
                escaped_text = original_text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                ass_file.write(f"Dialogue: 0,{start_formatted},{end_formatted},Default,,0,0,0,,{escaped_text}\n")
                
                # 如果需要翻译且源语言不是中文
                if translate_to_chinese and final_source_language != "zh" and final_source_language != "chi":
                    # 使用缓存的翻译结果
                    if not hasattr(create_bilingual_subtitles, 'translation_cache'):
                        create_bilingual_subtitles.translation_cache = {}
                    
                    if original_text in create_bilingual_subtitles.translation_cache:
                        translated_text = create_bilingual_subtitles.translation_cache[original_text]
                    else:
                        translated_text = translate_text(original_text, target_language="zh-CN", source_language=final_source_language)
                        create_bilingual_subtitles.translation_cache[original_text] = translated_text
                    
                    # 处理特殊字符，避免在ASS字幕中出现问题
                    escaped_translated = translated_text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                    # 写入翻译
                    ass_file.write(f"Dialogue: 0,{start_formatted},{end_formatted},Secondary,,0,0,0,,{escaped_translated}\n")
        
        print(f"字幕文件已创建: \nSRT: {srt_path}\nVTT: {vtt_path}\nASS: {ass_path}")
        
        # 清理GPU缓存
        if device == "cuda":
            torch.cuda.empty_cache()
        
        # 返回SRT文件路径作为默认字幕文件
        return srt_path
    
    except Exception as e:
        # 清理GPU缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print(f"创建字幕文件时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def embed_subtitles_to_video(video_path, subtitle_path, output_dir=VIDEOS_WITH_SUBTITLES_DIR):
    """
    将字幕嵌入到视频中
    
    Args:
        video_path: 视频文件路径
        subtitle_path: 字幕文件路径
        output_dir: 输出目录
        
    Returns:
        输出视频路径
    """
    try:
        # 确保输出目录存在
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 获取视频文件名（不含扩展名）
        video_name = Path(video_path).stem
        video_ext = Path(video_path).suffix
        
        # 生成输出文件路径
        output_path = os.path.join(output_dir, f"{video_name}_with_subtitles{video_ext}")
        
        # 获取字幕文件扩展名
        subtitle_ext = Path(subtitle_path).suffix
        
        # 如果是SRT字幕，优先使用ASS格式（如果存在）
        if subtitle_ext == '.srt' and os.path.exists(subtitle_path.replace('.srt', '.ass')):
            subtitle_path = subtitle_path.replace('.srt', '.ass')
            print(f"找到ASS格式字幕，使用: {subtitle_path}")
        
        print(f"正在将字幕嵌入视频: {video_path}")
        print(f"使用字幕文件: {subtitle_path}")
        
        # 检查文件是否存在
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")
        
        # 创建临时字幕文件，避免路径问题
        temp_dir = os.path.join(os.path.dirname(output_path), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # 使用简单的文件名，避免路径问题
        temp_subtitle = os.path.join(temp_dir, f"temp_subtitle{Path(subtitle_path).suffix}")
        
        # 复制字幕文件到临时位置
        import shutil
        shutil.copy2(subtitle_path, temp_subtitle)
        
        # 检查临时字幕文件是否存在
        if not os.path.exists(temp_subtitle):
            raise FileNotFoundError(f"临时字幕文件不存在: {temp_subtitle}")
        
        # 获取绝对路径
        video_path_abs = os.path.abspath(video_path)
        temp_subtitle_abs = os.path.abspath(temp_subtitle)
        output_path_abs = os.path.abspath(output_path)
        
        # 输出调试信息
        print(f"视频绝对路径: {video_path_abs}")
        print(f"临时字幕绝对路径: {temp_subtitle_abs}")
        print(f"输出视频绝对路径: {output_path_abs}")
        
        try:
            # 尝试使用简单的FFmpeg命令，使用escape=1参数
            # 首先尝试查找ffmpeg的路径
            ffmpeg_path = "ffmpeg"  # 默认命令名
            try:
                # 尝试使用which/where命令查找ffmpeg路径
                if os.name == 'nt':  # Windows
                    result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True, check=False)
                    if result.returncode == 0 and result.stdout.strip():
                        ffmpeg_path = result.stdout.strip().split('\n')[0]
                else:  # Unix/Linux/Mac
                    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        ffmpeg_path = result.stdout.strip()
                
                print(f"找到ffmpeg路径: {ffmpeg_path}")
            except Exception as e:
                print(f"查找ffmpeg路径失败，使用默认命令: {str(e)}")
            
            # 使用不同的方法处理不同类型的字幕文件
            subtitle_ext_lower = Path(subtitle_path).suffix.lower()
            
            if subtitle_ext_lower == '.ass':
                # 对于ASS字幕，直接使用ass文件过滤器
                filter_param = f'ass={temp_subtitle_abs.replace("\\", "/")}'
            else:
                # 对于其他字幕格式，使用subtitles过滤器
                if os.name == 'nt':  # Windows
                    # 将路径中的反斜杠替换为正斜杠
                    temp_subtitle_path = temp_subtitle_abs.replace('\\', '/')
                    # 简化字幕参数，避免引号嵌套问题
                    filter_param = f'subtitles={temp_subtitle_path}'
                else:  # Unix/Linux/Mac
                    filter_param = f"subtitles='{temp_subtitle_abs}'"
            
            cmd = [
                ffmpeg_path,
                "-i", video_path_abs,
                "-vf", filter_param,
                "-c:a", "copy",
                "-c:v", "libx264",
                "-crf", "20",
                "-vsync", "cfr",
                "-y",
                output_path_abs
            ]
            
            print(f"执行命令: {' '.join(cmd)}")
            
            # 在Windows下设置控制台编码为UTF-8
            if os.name == 'nt':
                os.system('chcp 65001 > nul')
                
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                print(f"FFmpeg错误输出: {stderr}")
                raise Exception(f"ffmpeg命令执行失败，返回代码: {process.returncode}")
            
            # 清理临时文件
            try:
                os.remove(temp_subtitle)
                os.rmdir(temp_dir)
            except Exception as e:
                print(f"清理临时文件失败: {str(e)}")
                
            print(f"字幕嵌入完成: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"嵌入字幕失败: {str(e)}")
            
            # 尝试使用替代方法
            print("尝试使用替代方法...")
            
            # 使用ffmpeg命令行方式，避免路径问题
            # 创建一个简单的批处理文件来执行命令
            batch_file = os.path.join(temp_dir, "embed_subtitles.bat")
            
            # 尝试直接使用ffmpeg-python库
            try:
                print("尝试使用ffmpeg-python库...")
                import ffmpeg
                
                # 构建ffmpeg命令
                subtitle_ext_lower = Path(subtitle_path).suffix.lower()
                if subtitle_ext_lower == '.ass':
                    filter_str = f"ass={temp_subtitle_abs.replace('\\', '/')}"
                else:
                    filter_str = f"subtitles={temp_subtitle_abs.replace('\\', '/')}"
                
                (
                    ffmpeg
                    .input(video_path_abs)
                    .output(
                        output_path_abs,
                        vf=filter_str,
                        acodec='copy',
                        vcodec='libx264',
                        crf=20,
                        vsync='cfr',
                        y=None
                    )
                    .run(capture_stdout=True, capture_stderr=True)
                )
                
                print(f"ffmpeg-python库执行成功")
                
                # 清理临时文件
                try:
                    os.remove(temp_subtitle)
                    os.rmdir(temp_dir)
                except Exception as e:
                    print(f"清理临时文件失败: {str(e)}")
                    
                print(f"字幕嵌入完成: {output_path}")
                return output_path
                
            except Exception as ffmpeg_error:
                print(f"ffmpeg-python库执行失败: {str(ffmpeg_error)}")
                print("尝试使用直接命令行方式...")
                
                # 查找系统中的ffmpeg可执行文件
                ffmpeg_executable = ffmpeg_path  # 使用之前找到的路径
                
                # 常见的ffmpeg安装路径
                possible_paths = [
                    r"C:\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe"),
                    r"D:\soft\bin\ffmpeg.exe"  # 添加用户环境中的路径
                ]
                
                # 检查可能的路径
                for path in possible_paths:
                    if os.path.exists(path):
                        ffmpeg_executable = path
                        print(f"找到ffmpeg可执行文件: {ffmpeg_executable}")
                        break
                
                # 构建批处理文件内容 - 使用简化的命令，避免引号和特殊字符问题
                subtitle_ext_lower = Path(subtitle_path).suffix.lower()
                if subtitle_ext_lower == '.ass':
                    filter_str = f"ass=temp_subtitle{Path(subtitle_path).suffix}"
                else:
                    filter_str = f"subtitles=temp_subtitle{Path(subtitle_path).suffix}"
                    
                batch_content = f"""@echo off
                cd /d "{os.path.dirname(temp_subtitle_abs)}"
                "{ffmpeg_executable}" -i "{video_path_abs}" -vf "{filter_str}" -c:a copy -c:v libx264 -crf 20 -vsync cfr -y "{output_path_abs}"
                """
                
                # 写入批处理文件
                with open(batch_file, 'w', encoding='utf-8') as f:
                    f.write(batch_content)
                
                print(f"执行批处理文件: {batch_file}")
                print(f"批处理文件内容:\n{batch_content}")
                
                # 执行批处理文件
                process = subprocess.Popen(
                    batch_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    shell=True
                )
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    print(f"批处理执行错误: {stderr}")
                    
                    # 最后尝试直接使用subprocess调用
                    print("尝试直接使用subprocess调用...")
                    
                    # 切换到临时目录
                    original_dir = os.getcwd()
                    os.chdir(os.path.dirname(temp_subtitle_abs))
                    
                    try:
                        # 使用相对路径引用字幕文件
                        subtitle_ext_lower = Path(subtitle_path).suffix.lower()
                        if subtitle_ext_lower == '.ass':
                            filter_str = f"ass=temp_subtitle{Path(subtitle_path).suffix}"
                        else:
                            filter_str = f"subtitles=temp_subtitle{Path(subtitle_path).suffix}"
                            
                        cmd = [
                            ffmpeg_executable,
                            "-i", video_path_abs,
                            "-vf", filter_str,
                            "-c:a", "copy",
                            "-c:v", "libx264",
                            "-crf", "20",
                            "-vsync", "cfr",
                            "-y",
                            output_path_abs
                        ]
                        
                        print(f"执行命令: {' '.join(cmd)}")
                        
                        result = subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=False
                        )
                        
                        if result.returncode != 0:
                            print(f"命令执行错误: {result.stderr}")
                            raise Exception(f"命令执行失败，返回代码: {result.returncode}")
                        
                    finally:
                        # 恢复原始目录
                        os.chdir(original_dir)
                    
                    # 清理临时文件
                    try:
                        os.remove(temp_subtitle)
                        os.remove(batch_file)
                        os.rmdir(temp_dir)
                    except Exception as e:
                        print(f"清理临时文件失败: {str(e)}")
                    
                    print(f"字幕嵌入完成: {output_path}")
                    return output_path
                
                # 清理临时文件
                try:
                    os.remove(temp_subtitle)
                    os.remove(batch_file)
                    os.rmdir(temp_dir)
                except Exception as e:
                    print(f"清理临时文件失败: {str(e)}")
                
                print(f"字幕嵌入完成: {output_path}")
                return output_path
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")
        raise Exception(f"嵌入字幕失败: {str(e)}")

def process_local_audio(audio_path, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir=DEFAULT_SUMMARY_DIR, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, enable_transcription=True, generate_article=True):
    """
    处理本地音频文件的主函数
    :param audio_path: 本地音频文件路径
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章，默认为True
    :return: 总结文件的路径或字幕文件路径（如果不生成摘要）
    """
    try:
        # 如果不需要转录，直接跳过
        if not enable_transcription:
            print("跳过转录步骤（用户未勾选执行转录）")
            return "SKIPPED"
            
        print("1. 开始转录音频...")
        # 使用统一转录函数，一次性完成转录和字幕生成
        text_path, subtitle_path = transcribe_audio_unified(
            audio_path,
            output_dir=TRANSCRIPTS_DIR,
            subtitle_dir=SUBTITLES_DIR,
            model_size=whisper_model_size,
            generate_subtitles=generate_subtitles,
            translate_to_chinese=translate_to_chinese,
            output_basename=audio_path,
        )
        print(f"转录文本已保存到: {text_path}")
        if subtitle_path:
            print(f"字幕文件已生成: {subtitle_path}")
        elif generate_subtitles:
            print("字幕生成失败")
        
        # 如果不需要生成摘要，直接返回字幕路径或文本路径
        if not generate_article:
            print("\n跳过生成文章步骤（用户未勾选生成文章）")
            return subtitle_path if subtitle_path else text_path
            
        print("\n3. 开始生成文章...")
        summary_path = summarize_text(
            text_path, 
            model=model, 
            api_key=api_key, 
            base_url=base_url, 
            stream=stream,
            output_dir=summary_dir,
            custom_prompt=custom_prompt,
            template_path=template_path
        )
        print(f"文章已保存到: {summary_path}")
        
        return summary_path
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")
        return None

def process_local_video(video_path, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir=DEFAULT_SUMMARY_DIR, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, embed_subtitles=False, enable_transcription=True, generate_article=True, source_language=None):
    """
    处理本地视频文件的主函数
    :param video_path: 本地视频文件路径
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param embed_subtitles: 是否将字幕嵌入到视频中，默认为False
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章，默认为True
    :param source_language: 指定源语言（可选），如果为None则自动检测
    :return: 总结文件的路径或字幕文件路径（如果不生成摘要）
    """
    try:
        # 如果不需要转录，直接跳过
        if not enable_transcription:
            print("跳过转录步骤（用户未勾选执行转录）")
            return "SKIPPED"
            
        print("1. 从视频中提取音频...")
        audio_path = extract_audio_from_video(video_path, output_dir=DOWNLOADS_DIR)
        print(f"音频已提取到: {audio_path}")
        
        print("2. 开始转录音频...")
        # 使用统一转录函数，一次性完成转录和字幕生成
        text_path, subtitle_path = transcribe_audio_unified(
            audio_path,
            output_dir=TRANSCRIPTS_DIR,
            subtitle_dir=SUBTITLES_DIR,
            model_size=whisper_model_size,
            generate_subtitles=generate_subtitles,
            translate_to_chinese=translate_to_chinese,
            source_language=source_language,
            output_basename=video_path,
        )
        print(f"转录文本已保存到: {text_path}")
        
        # 处理字幕和视频嵌入
        if subtitle_path:
            print(f"字幕文件已生成: {subtitle_path}")
            
            # 将字幕嵌入到视频中
            if embed_subtitles:
                print("\n3. 将字幕嵌入到视频中...")
                video_with_subtitles = embed_subtitles_to_video(
                    video_path,
                    subtitle_path,
                    output_dir=VIDEOS_WITH_SUBTITLES_DIR
                )
                if video_with_subtitles:
                    print(f"带字幕的视频已生成: {video_with_subtitles}")
                else:
                    print("字幕嵌入失败")
        elif generate_subtitles:
            print("字幕生成失败")
        
        # 如果不需要生成摘要，直接返回字幕路径或文本路径
        if not generate_article:
            print("\n跳过生成文章步骤（用户未勾选生成文章）")
            return subtitle_path if subtitle_path else text_path
            
        print("\n5. 开始生成文章...")
        summary_path = summarize_text(
            text_path, 
            model=model, 
            api_key=api_key, 
            base_url=base_url, 
            stream=stream,
            output_dir=summary_dir,
            custom_prompt=custom_prompt,
            template_path=template_path
        )
        print(f"文章已保存到: {summary_path}")
        
        return summary_path
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")
        return None

def process_local_videos_batch(input_path, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir=DEFAULT_SUMMARY_DIR, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, embed_subtitles=False, enable_transcription=True, generate_article=True, source_language=None):
    """
    批量处理本地视频文件（支持单个文件或目录）
    :param input_path: 输入路径（可以是单个视频文件或包含视频文件的目录）
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param embed_subtitles: 是否将字幕嵌入到视频中，默认为False
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章，默认为True
    :param source_language: 指定源语言（可选），如果为None则自动检测
    :return: 处理结果列表
    """
    import glob
    from pathlib import Path
    
    # 支持的视频文件扩展名
    video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg']
    
    # 收集需要处理的视频文件
    video_files = []
    
    if os.path.isfile(input_path):
        # 如果是单个文件
        if Path(input_path).suffix.lower() in video_extensions:
            video_files.append(input_path)
        else:
            print(f"错误：文件 {input_path} 不是支持的视频格式")
            return []
    elif os.path.isdir(input_path):
        # 如果是目录，查找所有视频文件
        print(f"扫描目录中的视频文件: {input_path}")
        for ext in video_extensions:
            pattern = os.path.join(input_path, f"*{ext}")
            video_files.extend(glob.glob(pattern))
            # 也搜索大写扩展名
            pattern = os.path.join(input_path, f"*{ext.upper()}")
            video_files.extend(glob.glob(pattern))
        
        video_files = sorted(list(set(video_files)))  # 去重并排序
        
        if not video_files:
            print(f"在目录 {input_path} 中未找到任何视频文件")
            return []
    else:
        print(f"错误：路径 {input_path} 不存在")
        return []
    
    print(f"\n找到 {len(video_files)} 个视频文件待处理:")
    for i, video_file in enumerate(video_files, 1):
        print(f"{i}. {os.path.basename(video_file)}")
    
    # 批量处理视频文件
    results = []
    successful_count = 0
    failed_count = 0
    
    for i, video_file in enumerate(video_files, 1):
        try:
            print(f"\n{'='*60}")
            print(f"处理第 {i}/{len(video_files)} 个视频: {os.path.basename(video_file)}")
            print(f"{'='*60}")
            
            # 处理单个视频
            result = process_local_video(
                video_file,
                model=model,
                api_key=api_key,
                base_url=base_url,
                whisper_model_size=whisper_model_size,
                stream=stream,
                summary_dir=summary_dir,
                custom_prompt=custom_prompt,
                template_path=template_path,
                generate_subtitles=generate_subtitles,
                translate_to_chinese=translate_to_chinese,
                embed_subtitles=embed_subtitles,
                enable_transcription=enable_transcription,
                generate_article=generate_article,
                source_language=source_language
            )
            
            if result and result != "SKIPPED":
                results.append({
                    'video_file': video_file,
                    'result_path': result,
                    'status': 'success'
                })
                successful_count += 1
                print(f"\n✓ 视频 {os.path.basename(video_file)} 处理成功")
            elif result == "SKIPPED":
                results.append({
                    'video_file': video_file,
                    'result_path': None,
                    'status': 'skipped'
                })
                print(f"\n- 视频 {os.path.basename(video_file)} 已跳过")
            else:
                results.append({
                    'video_file': video_file,
                    'result_path': None,
                    'status': 'failed'
                })
                failed_count += 1
                print(f"\n✗ 视频 {os.path.basename(video_file)} 处理失败")
            
        except Exception as e:
            print(f"\n✗ 处理视频 {os.path.basename(video_file)} 时出现错误: {str(e)}")
            results.append({
                'video_file': video_file,
                'result_path': None,
                'status': 'error',
                'error': str(e)
            })
            failed_count += 1
            continue
    
    # 输出处理结果摘要
    print(f"\n{'='*60}")
    print("批量处理完成!")
    print(f"总计: {len(video_files)} 个视频")
    print(f"成功: {successful_count} 个")
    print(f"失败: {failed_count} 个")
    print(f"跳过: {len([r for r in results if r.get('status') == 'skipped'])} 个")
    
    # 显示处理成功的文件
    if successful_count > 0:
        print(f"\n处理成功的文件:")
        for result in results:
            if result['status'] == 'success':
                print(f"✓ {os.path.basename(result['video_file'])} -> {result['result_path']}")
    
    # 显示处理失败的文件
    if failed_count > 0:
        print(f"\n处理失败的文件:")
        for result in results:
            if result['status'] in ['failed', 'error']:
                error_msg = result.get('error', '未知错误')
                print(f"✗ {os.path.basename(result['video_file'])} ({error_msg})")
    
    return results

def summarize_text(text_path, model=None, api_key=None, base_url=None, stream=False, output_dir=DEFAULT_SUMMARY_DIR, custom_prompt=None, template_path=None):
    """
    使用大语言模型总结文本内容
    :param text_path: 文本文件路径
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param stream: 是否使用流式输出，默认为False
    :param output_dir: 输出目录，默认为summaries
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :return: Markdown格式的总结文本
    """
    try:
        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 读取文本文件
        with open(text_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 使用组合模型生成摘要
        composite = TextSummaryComposite()
        
        # 生成输出文件名
        base_name = Path(text_path).stem.replace("_transcript", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{base_name}_{timestamp}_article.md"
        output_path = os.path.join(output_dir, output_filename)
        
        # 使用组合模型生成摘要
        print("开始使用组合模型生成文章...")

        # 创建新的 Composite 实例，强制重新加载环境变量（支持应用运行时的配置更新）
        composite = TextSummaryComposite(force_reload=True)

        # 从环境变量获取摘要生成配置（此时已经是最新值）
        generation_mode = os.getenv("SUMMARY_GENERATION_MODE", "single")
        thinking_model = os.getenv("THINKING_MODEL", "DeepSeek")
        output_model = os.getenv("OUTPUT_MODEL", "DeepSeek")

        print(f"📊 摘要生成配置: 模式={generation_mode}, 思考模型={thinking_model}, 生成模型={output_model}")

        article = composite.generate_summary(
            content,
            stream=stream,
            custom_prompt=custom_prompt,
            template_path=template_path,
            generation_mode=generation_mode,      # ✨ 添加
            thinking_model=thinking_model,        # ✨ 添加
            output_model=output_model             # ✨ 添加
        )
        
        # 保存摘要
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(article)
        
        print("文章生成完成!")
        return output_path
    except Exception as e:
        print(f"文章生成失败: {str(e)}")
        raise Exception(f"文章生成失败: {str(e)}")

class TextSummaryComposite:
    """处理 DeepSeek 和其他 OpenAI 兼容模型的组合，用于文本摘要生成"""

    def __init__(self, force_reload=False):
        """
        初始化组合模型
        :param force_reload: 是否强制重新加载环境变量（用于应用运行时配置更新）
        """
        # 如果需要，强制重新加载 .env 文件（用于支持应用运行时的配置更新）
        if force_reload:
            from dotenv import load_dotenv
            load_dotenv(override=True)
            print("✨ 已重新加载环境变量")

        # 从环境变量获取配置
        # 先读取 .env 文件中的最新值，然后再从环境变量获取
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_api_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.is_origin_reasoning = os.getenv("IS_ORIGIN_REASONING", "true").lower() == "true"

        self.target_api_key = os.getenv("OPENAI_COMPOSITE_API_KEY") or os.getenv("CLAUDE_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.target_api_url = os.getenv("OPENAI_COMPOSITE_API_URL") or os.getenv("CLAUDE_API_URL") or "https://api.openai.com/v1"
        self.target_model = os.getenv("OPENAI_COMPOSITE_MODEL") or os.getenv("CLAUDE_MODEL") or "gpt-3.5-turbo"

        # 检查必要的API密钥
        if not self.deepseek_api_key and not self.target_api_key:
            raise ValueError("缺少 API 密钥，请在设置中配置 DeepSeek 或 OpenAI API 密钥")

        print(f"✅ 已初始化摘要生成器: DeepSeek={bool(self.deepseek_api_key)}, 目标模型={bool(self.target_api_key)}")
    
    def get_short_model_name(self):
        """
        获取目标模型的简短名称，用于文件命名
        :return: 简化的模型名称
        """
        # 从完整模型名称中提取简短名称
        model_name = self.target_model
        
        # 移除路径前缀 (例如 "anthropic/" 或 "google/")
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
        
        # 提取主要模型名称 (例如 "claude-3-sonnet" 变为 "claude")
        if "claude" in model_name.lower():
            return "claude"
        elif "gpt" in model_name.lower():
            return "gpt"
        elif "gemini" in model_name.lower():
            return "gemini"
        elif "llama" in model_name.lower():
            return "llama"
        elif "qwen" in model_name.lower():
            return "qwen"
        else:
            # 如果无法识别，返回原始名称的前10个字符
            return model_name[:10].lower()
    
    def generate_summary(self, content, stream=False, custom_prompt=None, template_path=None, generation_mode="single", thinking_model=None, output_model=None):
        """
        生成文本摘要
        :param content: 需要摘要的文本内容
        :param stream: 是否使用流式输出
        :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
        :param template_path: 模板文件路径，如果提供则使用此模板
        :param generation_mode: 生成模式 ("single" 单模型或 "two_stage" 两阶段)
        :param thinking_model: 思考模型名称 ("DeepSeek" 或 "OpenAI")
        :param output_model: 生成模型名称 ("OpenAI" 或 "DeepSeek")
        :return: 生成的摘要文本
        """
        # 准备提示词
        system_prompt = "你是一个专业的内容编辑和文章撰写专家。"

        # 使用自定义提示词、模板或默认提示词
        if custom_prompt:
            user_prompt = custom_prompt.format(content=content)
        elif template_path:
            template = load_template(template_path)
            user_prompt = template.format(content=content)
        else:
            template = load_template()
            user_prompt = template.format(content=content)

        # 根据生成模式选择执行路径
        if generation_mode == "two_stage":
            print("📊 使用两阶段生成模式...")
            return self._generate_summary_two_stage(system_prompt, user_prompt, stream, thinking_model, output_model)
        else:
            print("⚡ 使用单模型生成模式...")
            return self._generate_summary_single_model(system_prompt, user_prompt, stream, output_model)
    
    def _generate_summary_single_model(self, system_prompt, user_prompt, stream=False, output_model=None):
        """
        单模型生成摘要（直接生成，不经过推理过程）
        :param system_prompt: 系统提示词
        :param user_prompt: 用户提示词
        :param stream: 是否流式输出
        :param output_model: 输出模型 ("OpenAI" 或 "DeepSeek")
        :return: 生成的摘要文本
        """
        try:
            # 确定使用的模型
            if output_model == "DeepSeek":
                print("✨ 使用 DeepSeek 直接生成摘要...")
                return self._get_deepseek_summary(system_prompt, user_prompt, stream)
            else:  # OpenAI
                print("✨ 使用 OpenAI 直接生成摘要...")
                return self._get_openai_summary(system_prompt, user_prompt, stream)
        except Exception as e:
            print(f"❌ 单模型生成失败: {str(e)}")
            return f"生成摘要失败: {str(e)}"

    def _generate_summary_two_stage(self, system_prompt, user_prompt, stream=False, thinking_model=None, output_model=None):
        """
        两阶段生成摘要（思考+生成）
        :param system_prompt: 系统提示词
        :param user_prompt: 用户提示词
        :param stream: 是否流式输出
        :param thinking_model: 思考模型 ("DeepSeek" 或 "OpenAI")
        :param output_model: 输出模型 ("OpenAI" 或 "DeepSeek")
        :return: 生成的摘要文本
        """
        # 第一步：使用思考模型生成推理过程
        if thinking_model == "OpenAI":
            print("💭 第一步：使用 OpenAI 进行深度思考...")
            reasoning = self._get_openai_reasoning(system_prompt, user_prompt)
        else:  # DeepSeek
            print("💭 第一步：使用 DeepSeek 进行深度思考...")
            reasoning = self._get_deepseek_reasoning(system_prompt, user_prompt)

        # 第二步：使用生成模型基于推理过程生成最终摘要
        if output_model == "DeepSeek":
            print("✨ 第二步：使用 DeepSeek 生成最终摘要...")
            return self._get_target_model_summary_custom(
                system_prompt, user_prompt, reasoning,
                use_openai=False, stream=stream
            )
        else:  # OpenAI
            print("✨ 第二步：使用 OpenAI 生成最终摘要...")
            return self._get_target_model_summary_custom(
                system_prompt, user_prompt, reasoning,
                use_openai=True, stream=stream
            )

    def _get_deepseek_summary(self, system_prompt, user_prompt, stream=False):
        """
        使用 DeepSeek 直接生成摘要
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "model": self.deepseek_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "stream": False
            }

            import requests
            response = requests.post(
                self.deepseek_api_url,
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code != 200:
                raise Exception(f"DeepSeek API 请求失败: {response.status_code}")

            response_data = response.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                content = response_data["choices"][0]["message"].get("content", "")
                cleaned = clean_markdown_formatting(content)
                return cleaned

            raise Exception("无法从 DeepSeek 响应中提取内容")

        except Exception as e:
            print(f"DeepSeek 摘要生成失败: {str(e)}")
            return f"DeepSeek 生成失败: {str(e)}"

    def _get_openai_summary(self, system_prompt, user_prompt, stream=False):
        """
        使用 OpenAI 直接生成摘要
        """
        try:
            client = OpenAI(
                api_key=self.target_api_key,
                base_url=self.target_api_url
            )

            response = client.chat.completions.create(
                model=self.target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                stream=stream
            )

            if stream:
                full_content = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        full_content += content
                print()
                return clean_markdown_formatting(full_content)
            else:
                if response.choices and len(response.choices) > 0:
                    article = response.choices[0].message.content
                    cleaned = clean_markdown_formatting(article)
                    return cleaned
                raise Exception("无法从 OpenAI 响应中提取内容")

        except Exception as e:
            print(f"OpenAI 摘要生成失败: {str(e)}")
            return f"OpenAI 生成失败: {str(e)}"

    def _get_openai_reasoning(self, system_prompt, user_prompt):
        """
        使用 OpenAI 进行推理（用于两阶段模式的第一步）
        """
        try:
            client = OpenAI(
                api_key=self.target_api_key,
                base_url=self.target_api_url
            )

            response = client.chat.completions.create(
                model=self.target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )

            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            return "无法获取 OpenAI 推理结果"

        except Exception as e:
            print(f"OpenAI 推理过程失败: {str(e)}")
            return f"OpenAI 推理失败: {str(e)}"

    def _get_target_model_summary_custom(self, system_prompt, user_prompt, reasoning, use_openai=True, stream=False):
        """
        使用目标模型基于推理生成最终摘要（支持两个模型选择）
        """
        try:
            combined_prompt = f"""这是我的原始请求：

{user_prompt}

以下是另一个模型的推理过程：

{reasoning}

请基于上述推理过程，提供你的最终文章。直接输出文章内容，不需要解释你的思考过程。
"""

            if use_openai:
                client = OpenAI(
                    api_key=self.target_api_key,
                    base_url=self.target_api_url
                )
                response = client.chat.completions.create(
                    model=self.target_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": combined_prompt}
                    ],
                    temperature=0.7,
                    stream=stream
                )
            else:  # DeepSeek
                headers = {
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": self.deepseek_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": combined_prompt}
                    ],
                    "temperature": 0.7,
                    "stream": stream
                }
                import requests
                response = requests.post(
                    self.deepseek_api_url,
                    headers=headers,
                    json=data,
                    timeout=60
                )
                if response.status_code != 200:
                    raise Exception(f"API 请求失败: {response.status_code}")
                response_data = response.json()
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    content = response_data["choices"][0]["message"].get("content", "")
                    cleaned = clean_markdown_formatting(content)
                    return cleaned
                raise Exception("无法从响应中提取内容")

            if stream:
                full_content = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        full_content += content
                print()
                return clean_markdown_formatting(full_content)
            else:
                if response.choices and len(response.choices) > 0:
                    article = response.choices[0].message.content
                    cleaned = clean_markdown_formatting(article)
                    return cleaned
                raise Exception("无法从响应中提取内容")

        except Exception as e:
            print(f"生成摘要失败: {str(e)}")
            return f"生成失败: {str(e)}"

    def _get_deepseek_reasoning(self, system_prompt, user_prompt):
        """
        获取 DeepSeek 的推理过程
        :param system_prompt: 系统提示词
        :param user_prompt: 用户提示词
        :return: 推理过程文本
        """
        try:
            # 准备请求头和数据
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.deepseek_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "stream": False
            }
            
            # 发送请求
            import requests
            response = requests.post(
                self.deepseek_api_url,
                headers=headers,
                json=data
            )
            
            # 检查响应
            if response.status_code != 200:
                raise Exception(f"DeepSeek API 请求失败: {response.status_code}, {response.text}")
            
            # 解析响应
            response_data = response.json()
            
            # 提取推理内容
            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0]["message"]
                
                # 检查是否有原生推理内容
                if "reasoning_content" in message:
                    return message["reasoning_content"]
                
                # 如果没有原生推理内容，尝试从普通内容中提取
                content = message.get("content", "")
                
                # 尝试从内容中提取 <div className="think-block">...</div> 标签
                import re
                think_match = re.search(r'<div className="think-block">(.*?)</div>', content, re.DOTALL)
                if think_match:
                    return think_match.group(1).strip()
                
                # 如果没有找到标签，则使用完整内容作为推理
                return content
            
            raise Exception("无法从 DeepSeek 响应中提取推理内容")
        
        except Exception as e:
            print(f"获取 DeepSeek 推理过程失败: {str(e)}")
            # 返回一个简单的提示，表示推理过程获取失败
            return "无法获取推理过程，但我会尽力生成一篇高质量的文章。"
    
    def _get_target_model_summary(self, system_prompt, user_prompt, reasoning):
        """
        使用目标模型生成最终摘要
        :param system_prompt: 系统提示词
        :param user_prompt: 用户提示词
        :param reasoning: DeepSeek 的推理过程
        :return: 生成的摘要文本
        """
        try:
            # 创建 OpenAI 客户端
            client = OpenAI(
                api_key=self.target_api_key,
                base_url=self.target_api_url
            )
            
            # 构造结合推理过程的提示词
            combined_prompt = f"""这是我的原始请求：
            
            {user_prompt}
            
            以下是另一个模型的推理过程：
            
            {reasoning}
            
            请基于上述推理过程，提供你的最终文章。直接输出文章内容，不需要解释你的思考过程。
            """
            
            # 发送请求
            response = client.chat.completions.create(
                model=self.target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": combined_prompt}
                ],
                temperature=0.7
            )
            
            # 提取回答
            if response.choices and len(response.choices) > 0:
                article = response.choices[0].message.content
                # 清理 Markdown 格式
                cleaned_markdown = clean_markdown_formatting(article)
                return cleaned_markdown
            
            raise Exception("无法从目标模型响应中提取内容")
        
        except Exception as e:
            print(f"获取目标模型摘要失败: {str(e)}")
            # 如果目标模型失败，则返回 DeepSeek 的推理作为备用
            return f"目标模型生成失败，以下是推理过程:\n\n{reasoning}"
    
    def _get_target_model_summary_stream(self, system_prompt, user_prompt, reasoning):
        """
        使用目标模型流式生成最终摘要
        :param system_prompt: 系统提示词
        :param user_prompt: 用户提示词
        :param reasoning: DeepSeek 的推理过程
        :return: 生成的摘要文本
        """
        try:
            # 创建 OpenAI 客户端
            client = OpenAI(
                api_key=self.target_api_key,
                base_url=self.target_api_url
            )
            
            # 构造结合推理过程的提示词
            combined_prompt = f"""这是我的原始请求：
            
            {user_prompt}
            
            以下是另一个模型的推理过程：
            
            {reasoning}
            
            请基于上述推理过程，提供你的最终文章。直接输出文章内容，不需要解释你的思考过程。
            """
            
            # 发送流式请求
            stream_response = client.chat.completions.create(
                model=self.target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": combined_prompt}
                ],
                temperature=0.7,
                stream=True
            )
            
            # 收集完整响应
            full_response = ""
            
            print("生成文章中...")
            for chunk in stream_response:
                if not chunk.choices:
                    continue
                content_chunk = chunk.choices[0].delta.content
                if content_chunk:
                    # 打印进度
                    print(".", end="", flush=True)
                    # 收集完整响应
                    full_response += content_chunk
            print("\n文章生成完成!")
            
            # 清理 Markdown 格式
            cleaned_markdown = clean_markdown_formatting(full_response)
            return cleaned_markdown
        
        except Exception as e:
            print(f"获取目标模型流式摘要失败: {str(e)}")
            # 如果目标模型失败，则返回 DeepSeek 的推理作为备用
            return f"目标模型生成失败，以下是推理过程:\n\n{reasoning}"

def extract_cookies_from_browser(browser_name="chrome", output_dir=".", youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    """
    从浏览器自动提取YouTube cookies
    :param browser_name: 浏览器名称 (chrome, firefox, edge, safari)
    :param output_dir: 输出目录
    :param youtube_url: 用于测试的YouTube URL
    :return: cookies文件路径和提取结果
    """
    import tempfile
    import time
    from pathlib import Path
    
    # 创建临时cookies文件
    timestamp = int(time.time())
    cookies_filename = f"youtube_cookies_{browser_name}_{timestamp}.txt"
    cookies_path = os.path.join(output_dir, cookies_filename)
    
    print(f"🍪 尝试从 {browser_name.title()} 浏览器提取YouTube cookies...")
    
    # yt-dlp选项，从浏览器提取cookies
    ydl_opts = {
        'cookiesfrombrowser': (browser_name, None, None, None),  # 浏览器名称
        'writeinfojson': False,
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        # 首先测试是否能从浏览器提取cookies
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
        if info:
            print(f"✅ 成功从 {browser_name.title()} 浏览器获取cookies")
            # 返回浏览器标记，表示直接使用浏览器cookies
            return f"browser:{browser_name}", True
        else:
            print(f"❌ 无法从 {browser_name.title()} 获取YouTube访问权限")
            return None, False
            
    except Exception as e:
        error_msg = str(e).lower()
        
        if 'no such browser' in error_msg or 'browser not found' in error_msg:
            print(f"❌ 未找到 {browser_name.title()} 浏览器或浏览器未安装")
        elif 'permission' in error_msg or 'access' in error_msg:
            print(f"❌ 无法访问 {browser_name.title()} 浏览器数据，可能需要关闭浏览器后重试")
        elif 'not logged' in error_msg or 'no cookies' in error_msg:
            print(f"⚠️  {browser_name.title()} 浏览器中未登录YouTube账户")
        else:
            print(f"❌ 从 {browser_name.title()} 提取cookies失败: {str(e)}")
            
        return None, False

def auto_extract_cookies_from_browsers(output_dir="."):
    """
    自动尝试从多个浏览器提取cookies
    :param output_dir: 输出目录
    :return: 成功的cookies路径和浏览器名称
    """
    browsers_to_try = [
        ("chrome", "Chrome"),
        ("edge", "Microsoft Edge"), 
        ("firefox", "Firefox"),
        ("safari", "Safari")
    ]
    
    print("🔍 自动检测可用的浏览器并提取YouTube cookies...")
    
    for browser_key, browser_name in browsers_to_try:
        print(f"\n🌐 尝试 {browser_name}...")
        
        cookies_path, success = extract_cookies_from_browser(
            browser_name=browser_key, 
            output_dir=output_dir
        )
        
        if success:
            print(f"🎉 成功从 {browser_name} 获取cookies!")
            return cookies_path, browser_name
        else:
            print(f"⏭️  跳过 {browser_name}")
    
    print("\n❌ 未能从任何浏览器成功提取cookies")
    print("\n💡 建议:")
    print("1. 确保至少一个浏览器已登录YouTube")
    print("2. 关闭所有浏览器窗口后重试")
    print("3. 或者手动使用浏览器插件导出cookies.txt文件")
    
    return None, None

def check_cookies_file(cookies_file):
    """
    检查cookies文件是否有效
    :param cookies_file: cookies文件路径或浏览器标记
    :return: 如果有效返回绝对路径或浏览器标记，否则返回None
    """
    if not cookies_file:
        return None
    
    # 检查是否是浏览器cookies标记
    if isinstance(cookies_file, str) and cookies_file.startswith("browser:"):
        browser_name = cookies_file.replace("browser:", "")
        print(f"将使用 {browser_name.title()} 浏览器cookies")
        return cookies_file
        
    # 如果是相对路径，转换为绝对路径
    if not os.path.isabs(cookies_file):
        cookies_file = os.path.abspath(cookies_file)
    
    if not os.path.exists(cookies_file):
        print(f"警告: cookies文件不存在: {cookies_file}")
        return None
    
    # 检查文件大小
    if os.path.getsize(cookies_file) == 0:
        print(f"警告: cookies文件为空: {cookies_file}")
        return None
    
    # 简单检查文件格式
    try:
        with open(cookies_file, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            # Netscape格式的cookies文件应该以注释开头
            if not first_line.startswith('#'):
                print(f"警告: cookies文件可能不是Netscape格式: {cookies_file}")
    except Exception as e:
        print(f"警告: 读取cookies文件时出错: {str(e)}")
        return None
    
    print(f"检测到有效的cookies文件: {cookies_file}")
    return cookies_file

def process_youtube_video(youtube_url, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir=DEFAULT_SUMMARY_DIR, download_video=False, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, embed_subtitles=False, cookies_file=None, enable_transcription=True, generate_article=True, prefer_native_subtitles=True):
    """
    处理YouTube视频的主函数
    :param youtube_url: YouTube视频链接
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param download_video: 是否下载视频（True）或仅音频（False），默认为False
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param embed_subtitles: 是否将字幕嵌入到视频中，默认为False
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章摘要，默认为True
    :param prefer_native_subtitles: 是否优先使用原生字幕，默认为True
    :return: 总结文件的路径或字幕文件路径（根据设置而定）
    """
    try:
        # 验证cookies文件
        valid_cookies_file = check_cookies_file(cookies_file)
        
        # 0. 优先检查原生字幕（如果启用了此选项，且需要生成文章或字幕/翻译）
        native_subtitle_text = None
        if prefer_native_subtitles and (generate_article or generate_subtitles or embed_subtitles or translate_to_chinese):
            print("0. 检查视频是否有原生字幕...")
            subtitle_info = check_youtube_subtitles(youtube_url, valid_cookies_file)
            
            if subtitle_info.get('error'):
                error_type = subtitle_info.get('error')
                if error_type == 'unable_to_access':
                    print("⚠️  无法检查原生字幕，可能需要Cookies文件或网络有问题")
                    print("将继续使用传统方式（下载音频 + Whisper转录）...")
                else:
                    print(f"检查字幕时出错: {subtitle_info['error']}")
                    print("将继续使用传统方式...")
            else:
                # 如果既没有手动字幕也没有自动字幕，直接给出提示
                if not subtitle_info.get('has_manual_subtitles') and not subtitle_info.get('has_auto_subtitles'):
                    print("该视频没有可用的原生字幕，将使用Whisper转录")
                else:
                    used_native_subtitles = False

                    # 先尝试手动字幕
                    if subtitle_info.get('has_manual_subtitles'):
                        print("发现人工制作的字幕，优先使用原生字幕")
                        print(f"可用的手动字幕语言: {subtitle_info['manual_languages']}")

                        # 优先使用 check_youtube_subtitles 计算出的最佳手动字幕语言
                        best_manual_lang = subtitle_info.get('best_manual_language')
                        if best_manual_lang:
                            manual_langs = [best_manual_lang]
                        else:
                            # 退回到旧逻辑：使用 preferred_languages 的前两个
                            manual_langs = subtitle_info.get('preferred_languages', ['zh', 'en'])[:2]

                        print(f"尝试下载手动字幕语言: {manual_langs}")

                        subtitle_files = download_youtube_subtitles(
                            youtube_url,
                            output_dir=NATIVE_SUBTITLES_DIR,
                            languages=manual_langs,
                            download_auto=False,
                            cookies_file=valid_cookies_file
                        )

                        if subtitle_files:
                            subtitle_file = subtitle_files[0]
                            print(f"使用手动字幕文件: {subtitle_file}")

                            # 统一生成与视频同名的双语字幕文件（放在全局 subtitles 目录下）
                            translated_subtitle_file = None
                            if translate_to_chinese:
                                try:
                                    # 从原始字幕文件名中去掉语言后缀和 .auto 等标记，得到原始视频标题
                                    subtitle_basename = os.path.splitext(os.path.basename(subtitle_file))[0]  # 去掉 .srt
                                    if subtitle_basename.endswith('.auto'):
                                        subtitle_basename = subtitle_basename[:-5]  # 去掉 .auto
                                    video_title_base = subtitle_basename
                                    if '.' in subtitle_basename:
                                        possible_lang = subtitle_basename.split('.')[-1]
                                        if len(possible_lang) <= 7 and all(c.isalpha() or c in ('-', '_') for c in possible_lang):
                                            video_title_base = subtitle_basename[:-(len(possible_lang) + 1)]

                                    translated_subtitle_file = translate_subtitle_file(
                                        subtitle_file,
                                        target_language="zh-CN",
                                        base_name=video_title_base,
                                        output_dir=SUBTITLES_DIR,
                                        keep_lang_suffix=False,  # 与视频完全同名，只保留扩展名不同
                                    )
                                    if translated_subtitle_file:
                                        print(f"已基于手动原生字幕生成中文字幕文件: {translated_subtitle_file}")
                                except Exception as e:
                                    print(f"⚠️ 基于手动原生字幕生成中文字幕失败: {str(e)}")

                            native_subtitle_text = convert_subtitle_to_text(subtitle_file)

                            if native_subtitle_text:
                                used_native_subtitles = True
                                print("成功从手动原生字幕获取文本，跳过音频下载和转录步骤")
                                # 如果用户勾选了下载视频，这里也顺便下载/复用本地视频文件
                                if download_video:
                                    try:
                                        print("\n检测到用户勾选了“下载视频”，将同时下载/复用视频文件...")
                                        video_file_for_native = download_youtube_video(
                                            youtube_url,
                                            output_dir=VIDEOS_DIR,
                                            audio_only=False,
                                            cookies_file=valid_cookies_file,
                                        )
                                        print(f"视频文件已就绪: {video_file_for_native}")
                                    except Exception as e:
                                        print(f"⚠️ 使用原生字幕时下载视频失败: {str(e)}")
                                if generate_article:
                                    print(f"\n直接使用原生字幕生成文章摘要...")
                                    summary_path = generate_summary(
                                        native_subtitle_text,
                                        model,
                                        api_key,
                                        base_url,
                                        stream,
                                        summary_dir,
                                        custom_prompt,
                                        template_path
                                    )
                                    if summary_path:
                                        print(f"摘要已生成: {summary_path}")
                                        return summary_path
                                    else:
                                        print("摘要生成失败，将退回到音频转写")
                                # 如果只需要字幕，优先返回已翻译的中文字幕，其次返回原始字幕
                                return translated_subtitle_file or subtitle_file
                            else:
                                print("从手动字幕转换文本失败，将尝试其他方式")
                        else:
                            print("未能成功下载任何手动字幕文件")

                    # 如果手动字幕不可用或处理失败，尝试自动字幕
                    if not used_native_subtitles and subtitle_info.get('has_auto_subtitles'):
                        print("尝试使用自动生成的字幕")
                        print(f"可用的自动字幕语言: {subtitle_info['auto_languages']}")

                        best_auto_lang = subtitle_info.get('best_auto_language')
                        auto_languages = subtitle_info.get('auto_languages', [])
                        auto_langs = []

                        if best_auto_lang:
                            auto_langs.append(best_auto_lang)

                        fallback_auto_priority = ['en', 'en-orig', 'en-US', 'en-GB', 'zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW']
                        for lang in fallback_auto_priority:
                            if lang in auto_languages and lang not in auto_langs:
                                auto_langs.append(lang)

                        max_auto_subtitle_attempts = 4
                        auto_langs = auto_langs[:max_auto_subtitle_attempts]

                        print(f"尝试下载自动字幕语言: {auto_langs}")

                        subtitle_files = download_youtube_subtitles(
                            youtube_url,
                            output_dir=NATIVE_SUBTITLES_DIR,
                            languages=auto_langs,
                            download_auto=True,
                            cookies_file=valid_cookies_file
                        )

                        if subtitle_files:
                            subtitle_file = subtitle_files[0]
                            print(f"使用自动字幕文件: {subtitle_file}")

                            # 如有需要，先基于原生自动字幕生成中文字幕文件
                            translated_subtitle_file = None
                            if translate_to_chinese:
                                try:
                                    subtitle_basename = os.path.splitext(os.path.basename(subtitle_file))[0]
                                    if subtitle_basename.endswith('.auto'):
                                        subtitle_basename = subtitle_basename[:-5]
                                    video_title_base = subtitle_basename
                                    if '.' in subtitle_basename:
                                        possible_lang = subtitle_basename.split('.')[-1]
                                        if len(possible_lang) <= 7 and all(c.isalpha() or c in ('-', '_') for c in possible_lang):
                                            video_title_base = subtitle_basename[:-(len(possible_lang) + 1)]

                                    translated_subtitle_file = translate_subtitle_file(
                                        subtitle_file,
                                        target_language="zh-CN",
                                        base_name=video_title_base,
                                        output_dir=SUBTITLES_DIR,
                                        keep_lang_suffix=False,
                                    )
                                    if translated_subtitle_file:
                                        print(f"已基于自动原生字幕生成中文字幕文件: {translated_subtitle_file}")
                                except Exception as e:
                                    print(f"⚠️ 基于自动原生字幕生成中文字幕失败: {str(e)}")

                            native_subtitle_text = convert_subtitle_to_text(subtitle_file)

                            if native_subtitle_text:
                                print("成功从自动字幕获取文本，跳过音频下载和转录步骤")
                                # 如果用户勾选了下载视频，这里也顺便下载/复用视频文件
                                if download_video:
                                    try:
                                        print("\n检测到用户勾选了“下载视频”，将同时下载/复用视频文件...")
                                        video_file_for_native = download_youtube_video(
                                            youtube_url,
                                            output_dir=VIDEOS_DIR,
                                            audio_only=False,
                                            cookies_file=valid_cookies_file,
                                        )
                                        print(f"视频文件已就绪: {video_file_for_native}")
                                    except Exception as e:
                                        print(f"⚠️ 使用原生字幕时下载视频失败: {str(e)}")
                                if generate_article:
                                    print(f"\n直接使用自动字幕生成文章摘要...")
                                    summary_path = generate_summary(
                                        native_subtitle_text,
                                        model,
                                        api_key,
                                        base_url,
                                        stream,
                                        summary_dir,
                                        custom_prompt,
                                        template_path
                                    )
                                    if summary_path:
                                        print(f"摘要已生成: {summary_path}")
                                        return summary_path
                                    else:
                                        print("摘要生成失败，继续使用Whisper转录")
                                else:
                                    # 如果只需要字幕，优先返回已翻译的中文字幕，其次返回原始字幕
                                    return translated_subtitle_file or subtitle_file
                            else:
                                print("从自动字幕转换文本失败，将退回到音频转写")
                        else:
                            print("未能成功下载任何自动字幕文件")

                    # 如果走到这里，说明即使存在原生字幕也没能成功使用
                    if subtitle_info.get('has_manual_subtitles') or subtitle_info.get('has_auto_subtitles'):
                        print("⚠️  检测到原生字幕，但下载或解析失败，将改用Whisper转录")
        
        print("1. 开始下载YouTube内容...")
        audio_path = None
        
        if download_video:
            print("下载视频（最佳画质）...")
            try:
                # 使用videos目录存储视频
                file_path = download_youtube_video(youtube_url, output_dir=VIDEOS_DIR, audio_only=False, cookies_file=valid_cookies_file)
                print(f"视频已下载到: {file_path}")
                
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    raise Exception(f"下载的视频文件不存在: {file_path}")
                
                # 如果下载的是视频，我们需要提取音频
                print("从视频中提取音频...")
                try:
                    audio_path = extract_audio_from_video(file_path, output_dir=DOWNLOADS_DIR)
                    print(f"音频已提取到: {audio_path}")
                except Exception as e:
                    print(f"从视频提取音频失败: {str(e)}")
                    print("尝试直接下载音频作为备选方案...")
                    audio_path = download_youtube_video(youtube_url, output_dir=DOWNLOADS_DIR, audio_only=True, cookies_file=valid_cookies_file)
            except Exception as e:
                print(f"视频下载失败: {str(e)}")
                print("尝试改为下载音频...")
                audio_path = download_youtube_video(youtube_url, output_dir=DOWNLOADS_DIR, audio_only=True, cookies_file=valid_cookies_file)
        else:
            print("仅下载音频...")
            # 使用downloads目录存储音频
            audio_path = download_youtube_video(youtube_url, output_dir=DOWNLOADS_DIR, audio_only=True, cookies_file=valid_cookies_file)
        
        # 如果只下载视频而不需要转录或生成文章，直接返回
        if not enable_transcription and not generate_article and download_video:
            print("\n仅下载视频完成")
            return file_path if 'file_path' in locals() else "视频下载完成"
        
        if not audio_path or not os.path.exists(audio_path):
            raise Exception(f"无法获取有效的音频文件")
            
        print(f"音频文件路径: {audio_path}")
        
        text_path = None
        if enable_transcription:
            print("\n2. 开始转录音频...")
            # 使用统一转录函数，一次性完成转录和字幕生成
            # 如果已经成功下载了视频，则以视频文件名作为输出基础名，保证字幕名与视频名一致
            output_basename = None
            if download_video and 'file_path' in locals() and os.path.exists(file_path):
                output_basename = file_path

            text_path, subtitle_path = transcribe_audio_unified(
                audio_path,
                output_dir=TRANSCRIPTS_DIR,
                subtitle_dir=SUBTITLES_DIR,
                model_size=whisper_model_size,
                generate_subtitles=(generate_subtitles or embed_subtitles),
                translate_to_chinese=translate_to_chinese,
                output_basename=output_basename,
            )
            print(f"转录文本已保存到: {text_path}")
            if subtitle_path:
                print(f"字幕文件已生成: {subtitle_path}")
        else:
            print("\n2. 跳过转录步骤（未勾选执行转录）")
            text_path = None
            subtitle_path = None
        
        # 处理字幕和视频
        video_path = None
        if (generate_subtitles or embed_subtitles) and not enable_transcription:
            print("\n3. 跳过字幕生成（需要先执行转录）")
        
        # 如果需要嵌入字幕到视频中，并且已下载了视频
        # 注意：这里使用ASS字幕文件，因为它支持更多格式化选项
        if embed_subtitles and download_video and subtitle_path and 'file_path' in locals() and os.path.exists(file_path):
            # 优先使用ASS格式字幕
            ass_subtitle_path = subtitle_path.replace('.srt', '.ass') if subtitle_path.endswith('.srt') else subtitle_path
            if os.path.exists(ass_subtitle_path):
                subtitle_path = ass_subtitle_path
                print(f"使用ASS格式字幕进行嵌入: {subtitle_path}")
            video_path = file_path
            print("\n4. 将字幕嵌入到视频中...")
            video_with_subtitles = embed_subtitles_to_video(
                video_path,
                subtitle_path,
                output_dir=VIDEOS_WITH_SUBTITLES_DIR
            )
            if video_with_subtitles:
                print(f"带字幕的视频已生成: {video_with_subtitles}")
            else:
                print("字幕嵌入失败")
        
        # 如果不需要生成摘要，直接返回字幕路径或文本路径
        if not generate_article:
            print("\n跳过生成文章步骤（用户未勾选生成文章）")
            return subtitle_path if subtitle_path else text_path
            
        print("\n5. 开始生成文章...")
        summary_path = summarize_text(
            text_path, 
            model=model, 
            api_key=api_key, 
            base_url=base_url, 
            stream=stream,
            output_dir=summary_dir,
            custom_prompt=custom_prompt,
            template_path=template_path
        )
        print(f"文章已保存到: {summary_path}")
        
        return summary_path
    except Exception as e:
        error_msg = str(e).lower()
        print(f"处理过程中出现错误: {str(e)}")
        
        # 提供具体的解决建议
        if 'nonetype' in error_msg and 'subscriptable' in error_msg:
            print("\n🔍 错误分析:")
            print("- 这通常是由于无法获取YouTube视频信息导致的")
            print("- 可能的原因：")
            print("  1. YouTube要求验证身份（机器人检测）")
            print("  2. 视频被地区限制或设为私有")
            print("  3. 网络连接问题")
            print("  4. 代理设置问题")
            
            print(f"\n💡 建议解决方案:")
            if not cookies_file:
                print("  ✅ 优先方案：设置Cookies文件")
                print("     - 使用浏览器插件导出cookies.txt")
                print("     - 在软件中设置Cookies文件路径")
            else:
                print(f"  ⚠️  检查Cookies文件：{cookies_file}")
                print("     - 确认文件存在且格式正确")
                print("     - 尝试重新导出最新的Cookies")
                
            print("  🌐 其他方案：")
            print("     - 检查网络连接和代理设置")
            print("     - 尝试其他视频链接测试")
            print("     - 确认视频链接有效且可公开访问")
            
        elif 'sign in' in error_msg or 'bot' in error_msg:
            print(f"\n🔐 YouTube机器人验证错误:")
            print("必须使用Cookies文件才能继续，请按照以下步骤设置：")
            print("1. 在浏览器中登录YouTube")
            print("2. 安装cookies导出插件")  
            print("3. 导出cookies.txt文件")
            print("4. 在软件中设置Cookies文件路径")
            
        elif 'network' in error_msg or 'connection' in error_msg:
            print(f"\n🌐 网络连接问题:")
            print("- 请检查网络连接")
            print("- 如果使用代理，请确认代理设置正确")
            print("- 尝试稍后重试")
            
        else:
            print(f"\n🔧 通用诊断建议:")
            print("1. 检查视频链接是否正确")
            print("2. 尝试设置Cookies文件")
            print("3. 检查网络连接")
            print("4. 查看详细错误信息")
        
        import traceback
        print(f"\n📋 详细错误信息:\n{traceback.format_exc()}")
        return None

def cleanup_files(directories_to_clean=None, dry_run=False):
    """
    清理指定目录中的文件
    
    :param directories_to_clean: 要清理的目录列表，如果为None则清理所有默认目录
    :param dry_run: 是否只是预览而不实际删除文件
    :return: 清理统计信息的字典
    """
    import os
    import glob
    
    # 默认的清理目录和文件类型（逻辑名称），实际路径通过 DIRECTORY_MAP 解析到 workspace 子目录
    all_directories = {
        "videos": ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"],
        "downloads": ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg"],
        "subtitles": ["*.srt", "*.vtt", "*.ass"],
        "transcripts": ["*.txt"],
        "summaries": ["*.md", "*.txt"],
        "videos_with_subtitles": ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"]
    }
    
    # 如果没有指定目录，则清理所有目录
    if directories_to_clean is None:
        directories_to_clean = list(all_directories.keys())
    
    print("🧹 开始清理文件...")
    if dry_run:
        print("📋 预览模式：只显示将要删除的文件，不实际删除")
    
    stats = {
        'total_files': 0,
        'total_size': 0,
        'directories': {}
    }
    
    for dir_name in directories_to_clean:
        if dir_name not in all_directories:
            print(f"⚠️ 未知目录: {dir_name}")
            continue

        # 将逻辑目录名映射到实际路径（workspace/xxx）
        dir_path = DIRECTORY_MAP.get(dir_name, dir_name)
        if not os.path.exists(dir_path):
            print(f"⚠️ 目录不存在: {dir_path}")
            continue
        
        extensions = all_directories[dir_name]
        print(f"\n🔄 {'预览' if dry_run else '清理'} {dir_path} 目录...")
        
        dir_files = 0
        dir_size = 0
        deleted_files = []
        
        for ext in extensions:
            pattern = os.path.join(dir_path, "**", ext)
            files = glob.glob(pattern, recursive=True)
            
            for file_path in files:
                try:
                    size = os.path.getsize(file_path)
                    
                    if not dry_run:
                        os.remove(file_path)
                        print(f"  ✅ 删除: {file_path}")
                    else:
                        print(f"  📋 将删除: {file_path}")
                    
                    dir_files += 1
                    dir_size += size
                    deleted_files.append(file_path)
                    
                except OSError as e:
                    print(f"  ❌ {'无法删除' if not dry_run else '无法访问'}: {file_path} - {str(e)}")
        
        if not dry_run and dir_files > 0:
            # 清理空目录
            try:
                for root, dirs, files in os.walk(dir_path, topdown=False):
                    for d in dirs:
                        dir_path = os.path.join(root, d)
                        try:
                            if not os.listdir(dir_path):  # 如果目录为空
                                os.rmdir(dir_path)
                                print(f"  🗂️ 删除空目录: {dir_path}")
                        except OSError:
                            pass
            except OSError:
                pass
        
        if dir_files > 0:
            size_mb = dir_size / (1024 * 1024)
            print(f"📁 {dir_name}: {'将删除' if dry_run else '删除了'} {dir_files} 个文件, {'将释放' if dry_run else '释放了'} {size_mb:.1f} MB")
            stats['directories'][dir_name] = {
                'files': dir_files,
                'size': dir_size,
                'deleted_files': deleted_files
            }
            stats['total_files'] += dir_files
            stats['total_size'] += dir_size
        else:
            print(f"📁 {dir_name}: 没有找到可删除的文件")
            stats['directories'][dir_name] = {
                'files': 0,
                'size': 0,
                'deleted_files': []
            }
    
    total_size_mb = stats['total_size'] / (1024 * 1024)
    action = "将删除" if dry_run else "删除了"
    print(f"\n🎉 {'预览' if dry_run else '清理'}完成！总共{action} {stats['total_files']} 个文件，{'将释放' if dry_run else '释放了'} {total_size_mb:.1f} MB 空间")
    
    return stats

def show_download_history():
    """
    显示下载历史记录
    """
    videos = list_downloaded_videos()
    if not videos:
        print("没有找到下载历史记录")
        return
    
    print(f"\n共找到 {len(videos)} 个下载记录:\n")
    for i, video in enumerate(videos, 1):
        title = video.get("title", "未知标题")
        url = video.get("url", "未知URL")
        last_time = video.get("last_download_time", "未知时间")
        file_path = video.get("file_path", "未知路径")
        
        print(f"{i}. 标题: {title}")
        print(f"   URL: {url}")
        print(f"   最后下载时间: {last_time}")
        print(f"   文件路径: {file_path}")
        print()

def process_youtube_videos_batch(youtube_urls, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir="summaries", download_video=False, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, embed_subtitles=False, cookies_file=None, enable_transcription=True, generate_article=True, prefer_native_subtitles=True):
    """
    批量处理多个YouTube视频
    :param youtube_urls: YouTube视频链接列表
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param download_video: 是否下载视频（True）或仅音频（False），默认为False
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param embed_subtitles: 是否将字幕嵌入到视频中，默认为False
    :param cookies_file: cookies文件路径，用于访问需要登录的YouTube内容
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章，默认为True
    :param prefer_native_subtitles: 是否优先使用原生字幕，默认为True
    :return: 处理结果的字典，键为URL，值为对应的总结文件路径或错误信息
    """
    results = {}
    total_urls = len(youtube_urls)
    
    print(f"开始批量处理 {total_urls} 个YouTube视频...")
    print(f"下载选项: {'完整视频' if download_video else '仅音频'}")
    
    for i, url in enumerate(youtube_urls):
        print(f"\n处理第 {i+1}/{total_urls} 个视频: {url}")
        try:
            summary_path = process_youtube_video(
                url,
                model=model,
                api_key=api_key,
                base_url=base_url,
                whisper_model_size=whisper_model_size,
                stream=stream,
                summary_dir=summary_dir,
                download_video=download_video,  # 确保正确传递download_video参数
                custom_prompt=custom_prompt,
                template_path=template_path,
                generate_subtitles=generate_subtitles,
                translate_to_chinese=translate_to_chinese,
                embed_subtitles=embed_subtitles,
                cookies_file=cookies_file,
                enable_transcription=enable_transcription,
                generate_article=generate_article,
                prefer_native_subtitles=True  # 批处理时默认使用原生字幕优化
            )
            
            if summary_path:
                print(f"视频处理成功: {url}")
                results[url] = {
                    "status": "success",
                    "summary_path": summary_path
                }
            else:
                print(f"视频处理失败: {url}")
                results[url] = {
                    "status": "failed",
                    "error": "处理过程中出现错误，请查看日志获取详细信息"
                }
        except Exception as e:
            print(f"处理视频时出错: {url}")
            print(f"错误详情: {str(e)}")
            results[url] = {
                "status": "failed",
                "error": str(e)
            }
    
    # 打印处理结果统计
    success_count = sum(1 for result in results.values() if result["status"] == "success")
    failed_count = sum(1 for result in results.values() if result["status"] == "failed")
    
    print("\n批量处理完成!")
    print(f"总计: {total_urls} 个视频")
    print(f"成功: {success_count} 个视频")
    print(f"失败: {failed_count} 个视频")
    
    if failed_count > 0:
        print("\n失败的视频:")
        for url, result in results.items():
            if result["status"] == "failed":
                print(f"- {url}: {result['error']}")
    
    return results

def extract_playlist_videos(playlist_url, cookies_file=None):
    """
    从YouTube播放列表提取所有视频URL
    :param playlist_url: YouTube播放列表链接
    :param cookies_file: cookies文件路径，用于访问需要登录的内容
    :return: 视频URL列表
    """
    try:
        import yt_dlp
        
        # 设置yt-dlp选项以获取播放列表信息
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,  # 只提取URL，不下载
            'force_json': True,
        }
        
        # 如果提供了cookies，添加到选项中
        if cookies_file:
            if cookies_file.startswith("browser:"):
                # 使用浏览器cookies
                browser_name = cookies_file.replace("browser:", "").strip()
                ydl_opts['cookiesfrombrowser'] = (browser_name, None, None, None)
                print(f"使用浏览器cookies: {browser_name}")
            elif os.path.isfile(cookies_file):
                # 使用cookies文件
                ydl_opts['cookiefile'] = cookies_file
                print(f"使用cookies文件: {cookies_file}")
            else:
                print(f"警告: cookies文件不存在: {cookies_file}")
        
        video_urls = []
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 获取播放列表信息
            info = ydl.extract_info(playlist_url, download=False)
            
            if 'entries' in info:
                print(f"发现播放列表: {info.get('title', '未知标题')}")
                print(f"包含 {len(info['entries'])} 个视频")
                
                for entry in info['entries']:
                    if entry and 'id' in entry:
                        video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        video_urls.append(video_url)
                        print(f"  - {entry.get('title', '未知标题')}: {video_url}")
            else:
                # 如果不是播放列表，可能是单个视频
                if 'id' in info:
                    video_url = f"https://www.youtube.com/watch?v={info['id']}"
                    video_urls.append(video_url)
                    print(f"单个视频: {info.get('title', '未知标题')}")
                    
        return video_urls
        
    except Exception as e:
        print(f"提取播放列表视频时出错: {str(e)}")
        return []

def is_youtube_playlist_url(url):
    """
    检查URL是否为YouTube播放列表
    :param url: 要检查的URL
    :return: 如果是播放列表URL返回True，否则返回False
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        path = parsed.path or ""

        # 1) 明确的播放列表页面，例如:
        #    https://www.youtube.com/playlist?list=PLxxxx
        if path.startswith("/playlist") and "list" in query:
            return True

        # 2) 特殊情况: /watch?list=... 但没有 v 参数，这种也视为播放列表入口
        if path.startswith("/watch") and "list" in query and "v" not in query:
            return True

        # 3) 其他情况（包括 watch?v=xxx&list=... ）都按“单个视频”处理
        return False
    except Exception:
        # 回退到简单字符串判断（极端异常情况下）
        return ("playlist?list=" in url) and ("v=" not in url)


def normalize_youtube_video_url(url: str) -> str:
    """
    规范化YouTube单个视频链接：
    - 对于包含播放列表参数的 watch 链接，只保留 v 参数，去掉 list/index 等
      例如: https://www.youtube.com/watch?v=pdqofxJeBN8&list=XXX&index=2
      规范化为: https://www.youtube.com/watch?v=pdqofxJeBN8
    - 对于短链 youtu.be/xxx，去掉多余的查询参数
    - 对于真正的播放列表链接（/playlist?list=...），保持不变
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        query = parse_qs(parsed.query)

        # 1) 非 YouTube 链接，直接返回
        if "youtube.com" not in host and "youtu.be" not in host:
            return url

        # 2) 播放列表链接保持不变
        if is_youtube_playlist_url(url):
            return url

        # 3) 短链形式: https://youtu.be/VIDEO_ID?xxx
        if "youtu.be" in host and path:
            # 去掉所有查询和片段，只保留基础短链
            return f"{parsed.scheme}://{parsed.netloc}{path}"

        # 4) 正常 watch 链接，只保留 v 参数
        if "youtube.com" in host and path.startswith("/watch") and "v" in query:
            video_id = query["v"][0]
            # 返回标准化的 watch 链接，去掉其他多余参数（list、index、si 等）
            return f"https://www.youtube.com/watch?v={video_id}"

        return url
    except Exception:
        return url

def process_youtube_playlist(playlist_url, model=None, api_key=None, base_url=None, whisper_model_size="medium", stream=True, summary_dir="summaries", download_video=False, custom_prompt=None, template_path=None, generate_subtitles=False, translate_to_chinese=True, embed_subtitles=False, cookies_file=None, enable_transcription=True, generate_article=True, prefer_native_subtitles=True):
    """
    处理YouTube播放列表，自动提取所有视频并批量处理
    :param playlist_url: YouTube播放列表链接
    :param model: 使用的模型名称，默认从环境变量获取
    :param api_key: API密钥，默认从环境变量获取
    :param base_url: 自定义API基础URL，默认从环境变量获取
    :param whisper_model_size: Whisper模型大小，默认为medium
    :param stream: 是否使用流式输出生成总结，默认为True
    :param summary_dir: 总结文件保存目录，默认为summaries
    :param download_video: 是否下载视频（True）或仅音频（False），默认为False
    :param custom_prompt: 自定义提示词，如果提供则使用此提示词代替默认提示词
    :param template_path: 模板文件路径，如果提供则使用此模板
    :param generate_subtitles: 是否生成字幕文件，默认为False
    :param translate_to_chinese: 是否将字幕翻译成中文，默认为True
    :param embed_subtitles: 是否将字幕嵌入到视频中，默认为False
    :param cookies_file: cookies文件路径，用于访问需要登录的YouTube内容
    :param enable_transcription: 是否执行转录，默认为True
    :param generate_article: 是否生成文章，默认为True
    :param prefer_native_subtitles: 是否优先使用原生字幕，默认为True
    :return: 处理结果的字典，键为URL，值为对应的总结文件路径或错误信息
    """
    print(f"开始处理YouTube播放列表: {playlist_url}")
    
    # 提取播放列表中的所有视频URL
    video_urls = extract_playlist_videos(playlist_url, cookies_file)
    
    if not video_urls:
        print("未能从播放列表中提取到任何视频URL")
        return {}
    
    print(f"\n播放列表包含 {len(video_urls)} 个视频，开始批量处理...")
    
    # 使用现有的批量处理函数处理视频列表
    return process_youtube_videos_batch(
        video_urls,
        model=model,
        api_key=api_key,
        base_url=base_url,
        whisper_model_size=whisper_model_size,
        stream=stream,
        summary_dir=summary_dir,
        download_video=download_video,
        custom_prompt=custom_prompt,
        template_path=template_path,
        generate_subtitles=generate_subtitles,
        translate_to_chinese=translate_to_chinese,
        embed_subtitles=embed_subtitles,
        cookies_file=cookies_file,
        enable_transcription=enable_transcription,
        generate_article=generate_article,
        prefer_native_subtitles=prefer_native_subtitles
    )

def process_local_text(text_path, model=None, api_key=None, base_url=None, stream=True, summary_dir="summaries", custom_prompt=None, template_path=None):
    """
    处理本地文本文件，直接生成摘要和文章
    
    参数:
        text_path (str): 本地文本文件路径
        model (str): 模型名称
        api_key (str): API密钥
        base_url (str): API基础URL
        stream (bool): 是否使用流式输出
        summary_dir (str): 摘要保存目录
        custom_prompt (str): 自定义提示词
        template_path (str): 模板路径
    
    返回:
        str: 生成的文章文件路径
    """
    print(f"正在处理本地文本文件: {text_path}")
    
    # 检查文件是否存在
    if not os.path.exists(text_path):
        print(f"错误: 文件 {text_path} 不存在")
        return None
    
    # 检查文件是否为文本文件
    if not text_path.lower().endswith(('.txt', '.md')):
        print(f"警告: 文件 {text_path} 可能不是文本文件，但仍将尝试处理")
    
    # 直接生成摘要
    summary_file = summarize_text(
        text_path, 
        model=model, 
        api_key=api_key, 
        base_url=base_url, 
        stream=stream, 
        output_dir=summary_dir,
        custom_prompt=custom_prompt,
        template_path=template_path
    )
    
    print(f"文本处理完成，文章已保存至: {summary_file}")
    return summary_file

def create_template(template_name, content=None):
    """
    创建新的模板文件
    :param template_name: 模板名称
    :param content: 模板内容，如果为None则使用默认模板内容
    :return: 模板文件路径
    """
    if not template_name.endswith('.txt'):
        template_name = f"{template_name}.txt"
    
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    
    if content is None:
        content = DEFAULT_TEMPLATE
    
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"模板已创建: {template_path}")
    return template_path

def list_templates():
    """
    列出所有可用的模板
    :return: 模板文件列表
    """
    templates = []
    for file in os.listdir(TEMPLATES_DIR):
        if file.endswith('.txt'):
            templates.append(file)
    
    return templates

def clean_markdown_formatting(markdown_text):
    """
    Clean up markdown formatting issues
    :param markdown_text: Original markdown text
    :return: Cleaned markdown text
    """
    import re

    # Split the text into lines for processing
    lines = markdown_text.split('\n')
    result_lines = []

    # Track if we're inside a code block
    in_code_block = False
    current_code_language = None
    skip_next_close = False  # Flag to skip the next closing ``` if we skipped an opening

    # First, check if the first line is ```markdown and remove it
    if lines and (lines[0].strip() == '```markdown' or lines[0].strip() == '```Markdown' or lines[0].strip() == '``` markdown'):
        lines = lines[1:]  # Remove the first line

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for code block start
        code_block_start = re.match(r'^(\s*)```\s*(\w+)?\s*$', line)
        if code_block_start and not in_code_block:
            # Starting a code block
            in_code_block = True
            indent = code_block_start.group(1)
            language = code_block_start.group(2) if code_block_start.group(2) else ''
            current_code_language = language

            # Skip unnecessary ```markdown markers at the start of a code block
            if language and language.lower() == 'markdown':
                # Skip this line, don't add it to result, but mark to skip next close
                skip_next_close = True
            else:
                # Add the properly formatted code block start
                if language:
                    result_lines.append(f"{indent}```{language}")
                else:
                    result_lines.append(f"{indent}```")

        # Check for code block end
        elif re.match(r'^(\s*)```\s*$', line) and in_code_block:
            # Ending a code block
            in_code_block = False
            current_code_language = None

            # Only add the closing ``` if we didn't skip the opening
            if not skip_next_close:
                result_lines.append(line)
            skip_next_close = False

        # Check for standalone triple backticks that aren't part of code blocks
        elif re.match(r'^(\s*)```\s*(markdown|Markdown)\s*$', line) and not in_code_block:
            # Skip unnecessary ```markdown markers
            pass
        elif line.strip() == '```' and not in_code_block:
            # Skip standalone closing backticks that aren't closing a code block
            pass

        # Regular line, add it to the result
        else:
            result_lines.append(line)

        i += 1

    # Ensure all code blocks are closed
    if in_code_block:
        result_lines.append("```")

    # Remove any trailing empty lines
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)

if __name__ == "__main__":
    import argparse
    import sys
    
    # 记录命令行参数
    log_command(sys.argv)
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='从YouTube视频或本地音频/视频文件中提取文本，并生成文章')
    
    # 创建互斥组，用户必须提供YouTube URL或本地音频/视频文件
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--youtube', type=str, help='YouTube视频URL')
    source_group.add_argument('--audio', type=str, help='本地音频文件路径')
    source_group.add_argument('--video', type=str, help='本地视频文件路径')
    source_group.add_argument('--text', type=str, help='本地文本文件路径，直接进行摘要生成')
    source_group.add_argument('--batch', type=str, help='包含多个YouTube URL的文本文件路径，每行一个URL')
    source_group.add_argument('--urls', nargs='+', type=str, help='多个YouTube URL，用空格分隔')
    source_group.add_argument('--create-batch-file', action='store_true', help='创建示例批处理文件')
    source_group.add_argument('--create-template', type=str, help='创建新模板，需要指定模板名称')
    source_group.add_argument('--list-templates', action='store_true', help='列出所有可用的模板')
    source_group.add_argument('--history', action='store_true', help='显示下载历史记录')
    
    # 其他参数
    parser.add_argument('--model', type=str, help='使用的模型名称，默认从环境变量获取')
    parser.add_argument('--cookies', type=str, help='cookies文件路径，用于访问需要登录的YouTube内容，可以使用浏览器扩展如"Get cookies.txt"导出')
    parser.add_argument('--api-key', type=str, help='API密钥，默认从环境变量获取')
    parser.add_argument('--base-url', type=str, help='自定义API基础URL，默认从环境变量获取')
    parser.add_argument('--whisper-model', type=str, default='small', 
                      choices=['tiny', 'base', 'small', 'medium', 'large'],
                      help='Whisper模型大小，默认为small')
    parser.add_argument('--no-stream', action='store_true', help='不使用流式输出')
    parser.add_argument('--summary-dir', type=str, default='summaries', help='文章保存目录，默认为summaries')
    parser.add_argument('--download-video', action='store_true', help='下载视频而不仅仅是音频（仅适用于YouTube）')
    parser.add_argument('--batch-file-name', type=str, default='youtube_urls.txt', help='创建示例批处理文件时的文件名')
    parser.add_argument('--prompt', type=str, help='自定义提示词，用于指导文章生成。使用{content}作为占位符表示转录内容')
    parser.add_argument('--template', type=str, help='使用指定的模板文件，可以是模板名称或完整路径')
    parser.add_argument('--template-content', type=str, help='创建模板时的模板内容，仅与--create-template一起使用')
    parser.add_argument('--transcribe-only', action='store_true', help='仅将音频转换为文本，不进行摘要生成')
    # 字幕相关参数
    parser.add_argument('--generate-subtitles', action='store_true', help='生成字幕文件（SRT、VTT和ASS格式）')
    parser.add_argument('--no-translate', action='store_true', help='不将字幕翻译成中文')
    parser.add_argument('--embed-subtitles', action='store_true', help='将字幕嵌入到视频中（仅当下载视频或处理本地视频时有效）')
    parser.add_argument('--no-summary', action='store_true', help='不生成摘要，仅进行转录和字幕生成')
    
    # 清理相关参数
    parser.add_argument('--cleanup', action='store_true', help='清理工作目录中的文件')
    parser.add_argument('--cleanup-preview', action='store_true', help='预览清理操作，不实际删除文件')
    parser.add_argument('--cleanup-dirs', nargs='+', 
                       choices=['videos', 'downloads', 'subtitles', 'transcripts', 'summaries', 'videos_with_subtitles'],
                       help='指定要清理的目录')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 处理模板路径
    template_path = None
    if args.template:
        # 检查是否是完整路径
        if os.path.exists(args.template):
            template_path = args.template
        else:
            # 检查是否是模板名称
            if not args.template.endswith('.txt'):
                template_name = f"{args.template}.txt"
            else:
                template_name = args.template
            
            potential_path = os.path.join(TEMPLATES_DIR, template_name)
            if os.path.exists(potential_path):
                template_path = potential_path
            else:
                print(f"警告: 找不到模板 '{args.template}'，将使用默认模板")
    
    # 如果用户请求创建示例批处理文件
    if args.create_batch_file:
        create_example_batch_file(args.batch_file_name)
        exit(0)
    
    # 如果用户请求创建新模板
    if args.create_template:
        create_template(args.create_template, args.template_content)
        exit(0)
    
    # 如果用户请求列出所有模板
    if args.list_templates:
        templates = list_templates()
        if templates:
            print("可用的模板:")
            for template in templates:
                print(f"- {template}")
        else:
            print("没有找到可用的模板")
        exit(0)
        
    # 如果用户请求显示下载历史记录
    if args.history:
        show_download_history()
        exit(0)
    
    # 如果用户请求清理文件
    if args.cleanup or args.cleanup_preview:
        dry_run = args.cleanup_preview
        directories = args.cleanup_dirs  # 可能为None，表示清理所有目录
        
        if dry_run:
            print("🔍 清理预览模式")
        else:
            print("🗑️ 开始清理文件")
            
        stats = cleanup_files(directories, dry_run)
        exit(0)
    
    # 如果没有提供参数，显示帮助信息
    if not (args.youtube or args.audio or args.video or args.text or args.batch or args.urls):
        parser.print_help()
        print("\n示例用法:")
        print("# 处理单个YouTube视频:")
        print("python youtube_transcriber.py --youtube https://www.youtube.com/watch?v=your_video_id")
        print("python youtube_transcriber.py --youtube https://www.youtube.com/watch?v=your_video_id --whisper-model large --no-stream")
        print("python youtube_transcriber.py --youtube https://www.youtube.com/watch?v=your_video_id --download-video")
        
        print("\n# 批量处理多个YouTube视频:")
        print("python youtube_transcriber.py --urls https://www.youtube.com/watch?v=id1 https://www.youtube.com/watch?v=id2")
        print("python youtube_transcriber.py --batch urls.txt  # 文件中每行一个URL")
        print("python youtube_transcriber.py --create-batch-file  # 创建示例批处理文件")
        
        print("\n# 处理本地音频文件:")
        print("python youtube_transcriber.py --audio path/to/your/audio.mp3")
        print("python youtube_transcriber.py --audio path/to/your/audio.mp3 --whisper-model large --summary-dir my_articles")
        
        print("\n# 处理本地视频文件:")
        print("python youtube_transcriber.py --video path/to/your/video.mp4")
        print("python youtube_transcriber.py --video path/to/your/video.mp4 --whisper-model large --summary-dir my_articles")
        print("python youtube_transcriber.py --video path/to/your/video.mp4 --generate-subtitles --embed-subtitles")
        
        print("\n# 处理本地文本文件:")
        print("python youtube_transcriber.py --text path/to/your/text.txt")
        print("python youtube_transcriber.py --text path/to/your/text.txt --summary-dir my_articles")
        
        print("\n# 清理工作目录:")
        print("python youtube_transcriber.py --cleanup-preview  # 预览将要删除的文件")
        print("python youtube_transcriber.py --cleanup  # 清理所有目录")
        print("python youtube_transcriber.py --cleanup --cleanup-dirs videos downloads  # 只清理指定目录")
        
        print("\n# 使用自定义提示词:")
        print('python youtube_transcriber.py --youtube https://www.youtube.com/watch?v=your_video_id --prompt "请将以下内容总结为一篇新闻报道：\\n\\n{content}"')
        
        print("\n# 使用模板功能:")
        print("python youtube_transcriber.py --youtube https://www.youtube.com/watch?v=your_video_id --template news")
        print("python youtube_transcriber.py --create-template news --template-content \"请将以下内容改写为新闻报道格式：\\n\\n{content}\"")
        print("python youtube_transcriber.py --list-templates")
    else:
        # 处理自定义提示词
        custom_prompt = args.prompt
        
        # 处理YouTube视频、批量处理或本地音频/视频
        if args.youtube:
            # 处理单个YouTube视频
            if args.transcribe_only:
                summary_path = transcribe_only(download_youtube_video(args.youtube, output_dir="downloads", audio_only=True), whisper_model_size=args.whisper_model, output_dir="transcripts")
            else:
                summary_path = process_youtube_video(
                    args.youtube,
                    model=args.model,
                    api_key=args.api_key,
                    base_url=args.base_url,
                    whisper_model_size=args.whisper_model,
                    stream=not args.no_stream,
                    summary_dir=args.summary_dir,
                    download_video=args.download_video,
                    custom_prompt=custom_prompt,
                    template_path=template_path,
                    generate_subtitles=args.generate_subtitles,
                    translate_to_chinese=not args.no_translate,
                    embed_subtitles=args.embed_subtitles,
                    cookies_file=args.cookies,
                    enable_transcription=not args.no_summary,
                    generate_article=not args.no_summary,
                    prefer_native_subtitles=True  # 命令行默认使用原生字幕优化
                )
            
            if summary_path:
                print(f"\n处理完成! 文章已保存到: {summary_path}")
            else:
                print("\n处理失败，请检查错误信息。")
                
        elif args.urls:
            # 直接从命令行处理多个URL
            results = process_youtube_videos_batch(
                args.urls,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                whisper_model_size=args.whisper_model,
                stream=not args.no_stream,
                summary_dir=args.summary_dir,
                download_video=args.download_video,
                custom_prompt=custom_prompt,
                template_path=template_path,
                generate_subtitles=args.generate_subtitles,
                translate_to_chinese=not args.no_translate,
                embed_subtitles=args.embed_subtitles
            )
            
        elif args.batch:
            # 从文件读取URL列表
            try:
                with open(args.batch, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                
                if not urls:
                    print(f"错误: 文件 {args.batch} 中没有找到有效的URL")
                else:
                    print(f"从文件 {args.batch} 中读取了 {len(urls)} 个URL")
                    results = process_youtube_videos_batch(
                        urls,
                        model=args.model,
                        api_key=args.api_key,
                        base_url=args.base_url,
                        whisper_model_size=args.whisper_model,
                        stream=not args.no_stream,
                        summary_dir=args.summary_dir,
                        download_video=args.download_video,
                        custom_prompt=custom_prompt,
                        template_path=template_path,
                        generate_subtitles=args.generate_subtitles,
                        translate_to_chinese=not args.no_translate,
                        embed_subtitles=args.embed_subtitles
                    )
            except Exception as e:
                print(f"读取批处理文件时出错: {str(e)}")
                
        elif args.video:
            # 处理本地视频文件
            if args.transcribe_only:
                summary_path = transcribe_only(extract_audio_from_video(args.video, output_dir="downloads"), whisper_model_size=args.whisper_model, output_dir="transcripts")
            else:
                summary_path = process_local_video(
                    args.video, 
                    model=args.model, 
                    api_key=args.api_key, 
                    base_url=args.base_url, 
                    whisper_model_size=args.whisper_model, 
                    stream=not args.no_stream, 
                    summary_dir=args.summary_dir,
                    custom_prompt=custom_prompt,
                    template_path=template_path,
                    generate_subtitles=args.generate_subtitles,
                    translate_to_chinese=not args.no_translate,
                    embed_subtitles=args.embed_subtitles
                )
            
            if summary_path:
                print(f"\n处理完成! 文章已保存到: {summary_path}")
            else:
                print("\n处理失败，请检查错误信息。")
                
        elif args.audio:
            # 处理本地音频文件
            if args.transcribe_only:
                summary_path = transcribe_only(args.audio, whisper_model_size=args.whisper_model, output_dir="transcripts")
            else:
                summary_path = process_local_audio(
                    args.audio, 
                    model=args.model, 
                    api_key=args.api_key, 
                    base_url=args.base_url, 
                    whisper_model_size=args.whisper_model, 
                    stream=not args.no_stream, 
                    summary_dir=args.summary_dir,
                    custom_prompt=custom_prompt,
                    template_path=template_path,
                    generate_subtitles=args.generate_subtitles,
                    translate_to_chinese=not args.no_translate
                )
            
            if summary_path:
                print(f"\n处理完成! 文章已保存到: {summary_path}")
            else:
                print("\n处理失败，请检查错误信息。")
                
        elif args.text:
            # 处理本地文本文件
            summary_path = process_local_text(
                args.text,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                stream=not args.no_stream,
                summary_dir=args.summary_dir,
                custom_prompt=custom_prompt,
                template_path=template_path
            )
            
            if summary_path:
                print(f"\n处理完成! 文章已保存到: {summary_path}")
            else:
                print("\n处理失败，请检查错误信息。")
                
        else:
            parser.print_help()
