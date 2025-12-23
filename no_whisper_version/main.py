#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
YouTube 转录工具 PyQt6 版本
基于原始 youtube_transcriber.py 代码实现的图形界面版本
"""

import sys
import os
import threading
import time
import subprocess
import platform
from datetime import datetime
from pathlib import Path

# 导入 PyQt6 相关模块
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox, 
    QCheckBox, QTabWidget, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox, QRadioButton, QScrollArea, QSplitter, QListWidget,
    QListWidgetItem, QButtonGroup, QSpinBox, QStatusBar, QDialog,
    QDialogButtonBox, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl, QTimer, QObject
from PyQt6.QtGui import QIcon, QPixmap, QFont, QDesktopServices, QTextCursor, QAction, QClipboard, QEnterEvent

# 导入原始代码中的功能模块
import yt_dlp
import whisper
import torch
from dotenv import load_dotenv
from openai import OpenAI
import requests
import html
import subprocess
import json

# 导入抖音下载模块
try:
    from douyin import DouyinDownloader, DouyinConfig, DouyinUtils
    DOUYIN_AVAILABLE = True
    print("✅ 抖音模块导入成功")
except ImportError as e:
    print(f"⚠️ 抖音模块未找到: {e}")
    DouyinDownloader = None
    DouyinConfig = None
    DouyinUtils = None
    DOUYIN_AVAILABLE = False

# DouyinUtils 安全调用函数
def safe_douyin_utils():
    """安全获取 DouyinUtils，确保模块可用"""
    global DOUYIN_AVAILABLE, DouyinUtils
    
    try:
        print(f"[安全调用] 检查状态 - DOUYIN_AVAILABLE: {DOUYIN_AVAILABLE}, DouyinUtils: {DouyinUtils}")
        
        # 检查当前状态
        if DOUYIN_AVAILABLE and DouyinUtils is not None:
            print("[安全调用] 使用现有的 DouyinUtils")
            return DouyinUtils
        
        # 尝试重新导入
        print("[安全调用] 尝试重新导入 DouyinUtils...")
        from douyin.utils import DouyinUtils as _DouyinUtils
        DouyinUtils = _DouyinUtils
        DOUYIN_AVAILABLE = True
        print("[安全调用] DouyinUtils 重新导入成功")
        return DouyinUtils
        
    except ImportError as e:
        print(f"[安全调用] DouyinUtils 导入失败: {e}")
        DOUYIN_AVAILABLE = False
        DouyinUtils = None
        return None
    except Exception as e:
        print(f"[安全调用] DouyinUtils 获取异常: {e}")
        import traceback
        traceback.print_exc()
        DOUYIN_AVAILABLE = False
        DouyinUtils = None
        return None

# 自定义抖音输入框类
class DouyinLineEdit(QLineEdit):
    """支持智能粘贴的抖音URL输入框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
    
    def keyPressEvent(self, event):
        """处理键盘事件，支持Ctrl+V智能粘贴"""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QKeySequence
            
            # 检查是否是Ctrl+V
            if event.matches(QKeySequence.StandardKey.Paste):
                print("[键盘] 检测到Ctrl+V，执行智能粘贴")
                self.smart_paste()
                return
            
            # 其他键盘事件按正常处理
            super().keyPressEvent(event)
        except Exception as e:
            print(f"[键盘] 处理键盘事件错误: {e}")
            super().keyPressEvent(event)
    
    def contextMenuEvent(self, event):
        """自定义右键菜单"""
        menu = self.createStandardContextMenu()
        
        # 添加智能粘贴选项
        if menu.actions():
            paste_action = None
            for action in menu.actions():
                if "粘贴" in action.text() or "Paste" in action.text():
                    paste_action = action
                    break
            
            if paste_action:
                # 移除原来的粘贴操作
                menu.removeAction(paste_action)
                
                # 添加智能粘贴
                smart_paste_action = menu.addAction("🎯 智能粘贴")
                smart_paste_action.triggered.connect(self.smart_paste)
                
                # 添加普通粘贴
                normal_paste_action = menu.addAction("📋 普通粘贴")
                normal_paste_action.triggered.connect(self.paste)
        
        menu.exec(event.globalPos())
    
    def smart_paste(self):
        """智能粘贴功能"""
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            
            print(f"[智能粘贴] 剪贴板内容: {clipboard_text[:100] if clipboard_text else '空'}...")
            
            if clipboard_text:
                # 安全获取 DouyinUtils
                utils = safe_douyin_utils()
                if utils is None:
                    print("[智能粘贴] DouyinUtils 不可用")
                    if hasattr(self.main_window, 'douyin_status_label'):
                        self.main_window.douyin_status_label.setText("❌ 抖音模块不可用")
                        self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
                    self.paste()
                    return
                
                try:
                    print("[智能粘贴] 开始处理分享文本...")
                    extracted_url = utils.parse_share_text(clipboard_text)
                    print(f"[智能粘贴] 提取结果: {extracted_url}")
                    
                    if extracted_url:
                        self.setText(extracted_url)
                        if hasattr(self.main_window, 'douyin_status_label'):
                            self.main_window.douyin_status_label.setText("✅ 已从剪贴板提取有效链接")
                            self.main_window.douyin_status_label.setStyleSheet("color: #4CAF50;")
                        print("[智能粘贴] 设置URL成功")
                    else:
                        print("[智能粘贴] 未找到有效链接，使用普通粘贴")
                        if hasattr(self.main_window, 'douyin_status_label'):
                            self.main_window.douyin_status_label.setText("⚠️ 未检测到抖音链接，已使用普通粘贴")
                            self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
                        # 没有找到有效链接，使用普通粘贴
                        self.paste()
                        
                except Exception as e:
                    print(f"[智能粘贴] 处理出错: {e}")
                    import traceback
                    traceback.print_exc()
                    if hasattr(self.main_window, 'douyin_status_label'):
                        self.main_window.douyin_status_label.setText(f"❌ 处理出错: {str(e)}")
                        self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
                    self.paste()
            else:
                print("[智能粘贴] 剪贴板为空")
                if hasattr(self.main_window, 'douyin_status_label'):
                    self.main_window.douyin_status_label.setText("ℹ️ 剪贴板为空")
                    self.main_window.douyin_status_label.setStyleSheet("color: #666;")
                self.paste()
        except Exception as e:
            print(f"[智能粘贴] 总体错误: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self.main_window, 'douyin_status_label'):
                self.main_window.douyin_status_label.setText(f"❌ 智能粘贴失败: {str(e)}")
                self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
            self.paste()

class DouyinTextEdit(QTextEdit):
    """支持智能粘贴的抖音批量输入框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
    
    def keyPressEvent(self, event):
        """处理键盘事件，支持Ctrl+V智能粘贴"""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QKeySequence
            
            # 检查是否是Ctrl+V
            if event.matches(QKeySequence.StandardKey.Paste):
                print("[键盘] 检测到Ctrl+V，执行批量智能粘贴")
                self.smart_paste()
                return
            
            # 其他键盘事件按正常处理
            super().keyPressEvent(event)
        except Exception as e:
            print(f"[键盘] 处理键盘事件错误: {e}")
            super().keyPressEvent(event)
    
    def contextMenuEvent(self, event):
        """自定义右键菜单"""
        menu = self.createStandardContextMenu()
        
        # 添加智能粘贴选项
        if menu.actions():
            paste_action = None
            for action in menu.actions():
                if "粘贴" in action.text() or "Paste" in action.text():
                    paste_action = action
                    break
            
            if paste_action:
                # 移除原来的粘贴操作
                menu.removeAction(paste_action)
                
                # 添加智能粘贴
                smart_paste_action = menu.addAction("🎯 智能粘贴")
                smart_paste_action.triggered.connect(self.smart_paste)
                
                # 添加普通粘贴
                normal_paste_action = menu.addAction("📋 普通粘贴")
                normal_paste_action.triggered.connect(self.paste)
        
        menu.exec(event.globalPos())
    
    def smart_paste(self):
        """智能粘贴功能"""
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            
            print(f"[批量智能粘贴] 剪贴板内容: {clipboard_text[:100] if clipboard_text else '空'}...")
            
            if clipboard_text:
                # 安全获取 DouyinUtils
                utils = safe_douyin_utils()
                if utils is None:
                    print("[批量智能粘贴] DouyinUtils 不可用")
                    if hasattr(self.main_window, 'douyin_status_label'):
                        self.main_window.douyin_status_label.setText("❌ 抖音模块不可用")
                        self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
                    self.paste()
                    return
                
                try:
                    print("[批量智能粘贴] 开始处理分享文本...")
                    
                    # 提取所有有效URL
                    all_urls = utils.extract_urls_from_text(clipboard_text)
                    valid_urls = []
                    
                    print(f"[批量智能粘贴] 发现URL: {all_urls}")
                    
                    # 验证每个URL
                    for url in all_urls:
                        if utils.validate_url(url):
                            valid_urls.append(url)
                    
                    # 如果没有直接链接，尝试从分享文本提取
                    if not valid_urls:
                        extracted = utils.parse_share_text(clipboard_text)
                        print(f"[批量智能粘贴] 分享文本提取结果: {extracted}")
                        if extracted:
                            valid_urls.append(extracted)
                    
                    print(f"[批量智能粘贴] 有效链接: {valid_urls}")
                    
                    if valid_urls:
                        # 获取当前文本内容
                        current_text = self.toPlainText()
                        
                        # 准备要添加的内容
                        new_lines = []
                        for url in valid_urls:
                            if url not in current_text:  # 避免重复
                                new_lines.append(url)
                        
                        if new_lines:
                            # 如果当前有内容且不是空行结尾，添加换行
                            if current_text and not current_text.endswith('\n'):
                                current_text += '\n'
                            
                            # 添加新链接
                            new_content = current_text + '\n'.join(new_lines)
                            self.setPlainText(new_content)
                            
                            # 更新状态提示
                            if hasattr(self.main_window, 'douyin_status_label'):
                                self.main_window.douyin_status_label.setText(f"✅ 已添加 {len(new_lines)} 个有效链接")
                                self.main_window.douyin_status_label.setStyleSheet("color: #4CAF50;")
                            print(f"[批量智能粘贴] 成功添加 {len(new_lines)} 个链接")
                        else:
                            # 所有链接已存在
                            if hasattr(self.main_window, 'douyin_status_label'):
                                self.main_window.douyin_status_label.setText("ℹ️ 所有链接已存在")
                                self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
                            print("[批量智能粘贴] 所有链接已存在")
                    else:
                        print("[批量智能粘贴] 未找到有效链接，使用普通粘贴")
                        if hasattr(self.main_window, 'douyin_status_label'):
                            self.main_window.douyin_status_label.setText("⚠️ 未检测到抖音链接，已使用普通粘贴")
                            self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
                        # 没有找到有效链接，使用普通粘贴
                        self.paste()
                        
                except Exception as e:
                    print(f"[批量智能粘贴] 处理出错: {e}")
                    import traceback
                    traceback.print_exc()
                    if hasattr(self.main_window, 'douyin_status_label'):
                        self.main_window.douyin_status_label.setText(f"❌ 处理出错: {str(e)}")
                        self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
                    self.paste()
            else:
                print("[批量智能粘贴] 剪贴板为空")
                if hasattr(self.main_window, 'douyin_status_label'):
                    self.main_window.douyin_status_label.setText("ℹ️ 剪贴板为空")
                    self.main_window.douyin_status_label.setStyleSheet("color: #666;")
                self.paste()
        except Exception as e:
            print(f"[批量智能粘贴] 总体错误: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self.main_window, 'douyin_status_label'):
                self.main_window.douyin_status_label.setText(f"❌ 智能粘贴失败: {str(e)}")
                self.main_window.douyin_status_label.setStyleSheet("color: #f44336;")
            self.paste()

# 加载环境变量（指定 main.py 所在目录的 .env 文件）
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=True)  # override=True 确保总是从.env文件中加载最新的值
print(f"✅ 已加载环境变量: {_env_path}")


# 创建模板目录
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# 创建日志目录
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# 日志文件路径
COMMAND_LOG_FILE = os.path.join(LOGS_DIR, "command_history.log")
VIDEO_LIST_FILE = os.path.join(LOGS_DIR, "downloaded_videos.json")

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

# 从原始代码导入工具函数
from youtube_transcriber import (
    sanitize_filename, translate_text, format_timestamp, log_command,
    log_downloaded_video, list_downloaded_videos, download_youtube_video,
    download_youtube_audio, extract_audio_from_video, transcribe_audio_to_text,
    transcribe_only, create_bilingual_subtitles, embed_subtitles_to_video,
    process_local_audio, process_local_video, process_local_videos_batch, summarize_text, TextSummaryComposite,
    check_cookies_file, process_youtube_video, show_download_history,
    process_youtube_videos_batch, process_local_text, create_template,
    list_templates, clean_markdown_formatting, load_template,
    is_youtube_playlist_url, process_youtube_playlist, normalize_youtube_video_url
)

# 统一的工作目录与子目录
from paths_config import (
    WORKSPACE_DIR,
    VIDEOS_DIR,
    DOWNLOADS_DIR,
    SUBTITLES_DIR,
    TRANSCRIPTS_DIR,
    SUMMARIES_DIR,
    VIDEOS_WITH_SUBTITLES_DIR,
    NATIVE_SUBTITLES_DIR,
    TWITTER_DOWNLOADS_DIR,
    BILIBILI_DOWNLOADS_DIR,
    DOUYIN_DOWNLOADS_DIR,
    LIVE_DOWNLOADS_DIR,
    DIRECTORY_MAP,
    DEFAULT_SUMMARY_DIR,
)

# 自定义URL输入框类，支持右键直接粘贴
class URLLineEdit(QLineEdit):
    """支持右键直接粘贴和鼠标悬停显示视频信息的URL输入框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cookies_file = None
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.fetch_video_info)
        self.last_url = ""
        
    def set_cookies_file(self, cookies_file):
        """设置cookies文件路径"""
        self.cookies_file = cookies_file
        
    def enterEvent(self, event: QEnterEvent):
        """鼠标进入事件"""
        super().enterEvent(event)
        current_url = self.text().strip()
        
        # 只有当URL是YouTube链接且与上次不同时才获取信息
        if (current_url and 
            ('youtube.com/watch' in current_url or 'youtu.be/' in current_url) and 
            current_url != self.last_url):
            
            # 延迟800ms再获取信息，避免频繁请求
            self.hover_timer.start(800)
            self.last_url = current_url
    
    def leaveEvent(self, event):
        """鼠标离开事件"""
        super().leaveEvent(event)
        # 停止计时器
        self.hover_timer.stop()
        # 清除工具提示
        self.setToolTip("")
    
    def fetch_video_info(self):
        """获取视频信息并设置工具提示"""
        current_url = self.text().strip()
        if not current_url:
            return
            
        try:
            # 导入必要的函数
            from youtube_transcriber import get_youtube_video_title, format_video_tooltip
            
            # 显示加载提示
            self.setToolTip("🔄 正在获取视频信息...")
            
            # 获取视频信息
            video_info = get_youtube_video_title(current_url, self.cookies_file)
            
            # 格式化并设置工具提示
            if video_info:
                tooltip_text = format_video_tooltip(video_info)
                self.setToolTip(tooltip_text)
            else:
                self.setToolTip("❌ 无法获取视频信息")
                
        except Exception as e:
            self.setToolTip(f"❌ 获取视频信息时出错: {str(e)}")
    
    def textChanged(self, text):
        """文本改变时重置状态"""
        super().textChanged(text)
        self.last_url = ""  # 重置URL缓存
        self.setToolTip("")  # 清除工具提示
    
    def contextMenuEvent(self, event):
        """重写右键菜单事件"""
        # 获取剪贴板内容
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        
        # 如果剪贴板中有内容，智能处理
        if clipboard_text:
            # 优先检查抖音分享内容，使用智能提取
            if '抖音' in clipboard_text or 'douyin' in clipboard_text.lower():
                # 尝试使用DouyinUtils智能提取
                utils = safe_douyin_utils()
                if utils:
                    try:
                        # 使用智能解析从分享文本提取链接
                        extracted_url = utils.parse_share_text(clipboard_text)
                        if extracted_url:
                            self.clear()
                            self.setText(extracted_url)
                            event.accept()
                            return
                    except Exception as e:
                        print(f"[URL输入框] DouyinUtils提取失败: {e}")
                
                # 备用方案：简单正则提取
                import re
                douyin_pattern = r'https?://[^\s]*douyin\.com[^\s]*'
                matches = re.findall(douyin_pattern, clipboard_text)
                if matches:
                    self.clear()
                    self.setText(matches[0])
                    event.accept()
                    return
            
            # 检查是否是简单的直接URL（排除复杂分享文本）
            clipboard_lines = clipboard_text.strip().split('\n')
            if len(clipboard_lines) == 1 and any(keyword in clipboard_text.lower() for keyword in ['youtube', 'youtu.be', 'twitter.com', 'x.com', 'bilibili']):
                self.clear()
                self.setText(clipboard_text.strip())
                event.accept()
                return
        
        # 如果剪贴板中没有内容或不像URL，显示标准右键菜单
        menu = self.createStandardContextMenu()
        
        # 添加自定义"直接粘贴"动作
        if clipboard_text:
            menu.addSeparator()
            paste_action = QAction("直接粘贴并清空", self)
            paste_action.triggered.connect(lambda: self.paste_and_clear(clipboard_text))
            menu.addAction(paste_action)
        
        menu.exec(event.globalPos())
        event.accept()
    
    def paste_and_clear(self, text):
        """粘贴文本并清空原内容"""
        self.clear()
        self.setText(text.strip())

# 自定义文本编辑框类，支持右键直接粘贴多个URL
class URLTextEdit(QTextEdit):
    """支持右键直接粘贴的多行URL输入框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def contextMenuEvent(self, event):
        """重写右键菜单事件"""
        # 获取剪贴板内容
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        
        # 如果剪贴板中有内容，检查是否包含URL
        if clipboard_text:
            # 检查是否看起来像包含URL
            if any(keyword in clipboard_text.lower() for keyword in ['http', 'youtube', 'youtu.be', 'twitter.com', 'x.com', 'bilibili', 'www.']):
                # 如果当前文本框为空，直接粘贴
                if not self.toPlainText().strip():
                    self.clear()
                    self.setPlainText(clipboard_text.strip())
                    event.accept()
                    return
                else:
                    # 如果已有内容，添加到新行
                    current_text = self.toPlainText().strip()
                    new_text = current_text + '\n' + clipboard_text.strip()
                    self.setPlainText(new_text)
                    event.accept()
                    return
        
        # 如果剪贴板中没有内容或不像URL，显示标准右键菜单
        menu = self.createStandardContextMenu()
        
        # 添加自定义动作
        if clipboard_text:
            menu.addSeparator()
            if not self.toPlainText().strip():
                paste_action = QAction("直接粘贴", self)
                paste_action.triggered.connect(lambda: self.paste_direct(clipboard_text))
            else:
                paste_action = QAction("添加到新行", self)
                paste_action.triggered.connect(lambda: self.paste_append(clipboard_text))
            menu.addAction(paste_action)
            
            clear_paste_action = QAction("清空并粘贴", self)
            clear_paste_action.triggered.connect(lambda: self.paste_and_clear_text(clipboard_text))
            menu.addAction(clear_paste_action)
        
        menu.exec(event.globalPos())
        event.accept()
    
    def paste_direct(self, text):
        """直接粘贴文本"""
        self.setPlainText(text.strip())
    
    def paste_append(self, text):
        """添加文本到新行"""
        current_text = self.toPlainText().strip()
        new_text = current_text + '\n' + text.strip()
        self.setPlainText(new_text)
    
    def paste_and_clear_text(self, text):
        """清空并粘贴文本"""
        self.clear()
        self.setPlainText(text.strip())

# 工作线程类，用于执行耗时操作
class WorkerThread(QThread):
    """工作线程，用于执行耗时操作，避免界面卡顿"""
    update_signal = pyqtSignal(str)  # 更新信息信号
    progress_signal = pyqtSignal(int)  # 进度信号
    finished_signal = pyqtSignal(str, bool)  # 完成信号，参数：结果路径，是否成功
    
    def __init__(self, task_type, params):
        """
        初始化工作线程
        :param task_type: 任务类型
        :param params: 任务参数
        """
        super().__init__()
        self.task_type = task_type
        self.params = params
        self.is_running = True
        self.stopped = False
    
    def run(self):
        """执行任务"""
        try:
            # 根据任务类型执行不同的操作
            if not self.stopped and self.task_type == "youtube":
                self.process_youtube()
            elif not self.stopped and self.task_type == "twitter":
                self.process_twitter()
            elif not self.stopped and self.task_type == "bilibili":
                self.process_bilibili()
            elif not self.stopped and self.task_type == "local_audio":
                self.process_local_audio()
            elif not self.stopped and self.task_type == "local_video":
                self.process_local_video()
            elif not self.stopped and self.task_type == "local_video_batch":
                self.process_local_video_batch()
            elif not self.stopped and self.task_type == "local_text":
                self.process_local_text()
            elif not self.stopped and self.task_type == "batch":
                self.process_batch()
        except Exception as e:
            if not self.stopped:  # 只有在非停止状态下才报告错误
                import traceback
                error_msg = f"执行任务时出错: {str(e)}\n{traceback.format_exc()}"
                self.update_signal.emit(error_msg)
                self.finished_signal.emit("", False)
    
    def process_youtube(self):
        """处理YouTube视频"""
        self.update_signal.emit("开始处理YouTube视频...")
        
        # 从参数中获取值
        youtube_url = self.params.get("youtube_url", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        download_video = self.params.get("download_video", False)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        cookies_file = self.params.get("cookies_file", None)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        prefer_native_subtitles = self.params.get("prefer_native_subtitles", True)
        show_translation_logs = self.params.get("show_translation_logs", True)
        
        # 重定向print输出到信号
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        # 替换全局print函数
        import builtins
        builtins.print = custom_print

        # 控制翻译日志详细程度
        try:
            from youtube_transcriber import set_translation_verbose
            set_translation_verbose(show_translation_logs)
        except Exception:
            pass
        
        try:
            # 检查是否为抖音URL
            if DOUYIN_AVAILABLE and DouyinUtils.validate_url(youtube_url):
                self.update_signal.emit(f"检测到抖音视频，开始下载...")
                
                # 使用抖音下载器处理
                try:
                    # 创建下载器
                    downloader = DouyinDownloader()
                    
                    # 获取视频信息
                    self.update_signal.emit("正在获取视频信息...")
                    video_info = downloader.get_video_info(youtube_url)
                    
                    if not video_info:
                        self.update_signal.emit("❌ 无法获取抖音视频信息")
                        self.update_signal.emit("可能原因：")
                        self.update_signal.emit("1. 视频链接已失效或被删除")
                        self.update_signal.emit("2. douyinVd 服务器暂时不可用")
                        self.update_signal.emit("3. 网络连接问题")
                        self.update_signal.emit("建议：尝试使用其他抖音链接或稍后重试")
                        self.finished_signal.emit("抖音视频信息获取失败", False)
                        return
                    
                    # 显示视频信息
                    summary = DouyinUtils.get_video_info_summary(video_info)
                    self.update_signal.emit(f"视频信息:\n{summary}")
                    
                    # 下载视频
                    self.update_signal.emit("开始下载抖音视频...")
                    def progress_callback(message, progress):
                        self.update_signal.emit(f"[{progress}%] {message}")
                    
                    result = downloader.download_video(youtube_url, progress_callback=progress_callback)
                    
                    if result.get("success"):
                        downloaded_files = result.get("downloaded_files", [])
                        if downloaded_files:
                            video_file = None
                            for file_info in downloaded_files:
                                if file_info.get("type") == "video":
                                    video_file = file_info.get("path")
                                    break
                            
                            if video_file:
                                self.update_signal.emit(f"✅ 抖音视频下载完成: {video_file}")
                                
                                # 检查是否需要执行转录和摘要
                                if enable_transcription or generate_article:
                                    self.process_douyin_transcription_and_summary(
                                        video_file, model, api_key, base_url, whisper_model_size,
                                        stream, summary_dir, custom_prompt, template_path,
                                        generate_subtitles, translate_to_chinese, embed_subtitles,
                                        enable_transcription, generate_article
                                    )
                                else:
                                    self.finished_signal.emit(video_file, True)
                            else:
                                self.update_signal.emit("✅ 抖音视频处理完成")
                                self.finished_signal.emit("", True)
                        else:
                            self.update_signal.emit("✅ 抖音视频处理完成")
                            self.finished_signal.emit("", True)
                    else:
                        error_msg = result.get("error", "未知错误")
                        self.update_signal.emit(f"❌ 抖音视频下载失败: {error_msg}")
                        self.finished_signal.emit("", False)
                    
                    return
                    
                except Exception as e:
                    self.update_signal.emit(f"❌ 抖音视频处理异常: {str(e)}")
                    self.finished_signal.emit("", False)
                    return
            
            # 检查是否为播放列表URL
            elif is_youtube_playlist_url(youtube_url):
                self.update_signal.emit(f"检测到YouTube播放列表，开始批量处理...")
                # 调用播放列表处理函数
                results = process_youtube_playlist(
                    youtube_url, model, api_key, base_url, whisper_model_size,
                    stream, summary_dir, download_video, custom_prompt,
                    template_path, generate_subtitles, translate_to_chinese,
                    embed_subtitles, cookies_file, enable_transcription, generate_article,
                    prefer_native_subtitles
                )
                
                if results:
                    success_count = sum(1 for result in results.values() if result.get("status") == "success")
                    total_count = len(results)
                    self.update_signal.emit(f"播放列表处理完成! 成功处理 {success_count}/{total_count} 个视频")
                    
                    # 返回第一个成功的结果作为主要结果
                    first_success = None
                    for result in results.values():
                        if result.get("status") == "success":
                            first_success = result.get("summary_path")
                            break
                    
                    self.finished_signal.emit(first_success or "", success_count > 0)
                else:
                    self.update_signal.emit("播放列表处理失败，请检查错误信息。")
                    self.finished_signal.emit("", False)
            else:
                # 调用原始代码中的处理函数
                result = process_youtube_video(
                    youtube_url, model, api_key, base_url, whisper_model_size,
                    stream, summary_dir, download_video, custom_prompt,
                    template_path, generate_subtitles, translate_to_chinese,
                    embed_subtitles, cookies_file, enable_transcription, generate_article,
                    prefer_native_subtitles
                )
                
                if result:
                    self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                    self.finished_signal.emit(result, True)
                else:
                    self.update_signal.emit("处理失败，请检查错误信息。")
                    self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            # 恢复原始print函数
            builtins.print = original_print
    
    def process_douyin_transcription_and_summary(self, video_file, model, api_key, base_url, 
                                                 whisper_model_size, stream, summary_dir, custom_prompt, 
                                                 template_path, generate_subtitles, translate_to_chinese, 
                                                 embed_subtitles, enable_transcription, generate_article):
        """处理抖音视频的转录和摘要"""
        try:
            self.update_signal.emit("开始处理抖音视频转录和摘要...")
            
            # 导入处理函数
            from youtube_transcriber import process_local_video
            
            # 执行转录和摘要处理
            result = process_local_video(
                video_file, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, None  # source_language
            )
            
            if result:
                self.update_signal.emit(f"✅ 抖音视频转录和摘要完成！结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("⚠️ 转录和摘要处理失败，但视频下载成功")
                self.finished_signal.emit(video_file, True)
                
        except Exception as e:
            self.update_signal.emit(f"❌ 转录处理失败: {str(e)}")
            # 即使转录失败，视频下载成功也算成功
            self.finished_signal.emit(video_file, True)

    def process_twitter(self):
        """处理Twitter视频 - 使用yt-dlp下载"""
        self.update_signal.emit("开始处理Twitter视频...")

        # 从参数中获取Twitter URL
        twitter_url = self.params.get("url", "")
        if not twitter_url:
            self.update_signal.emit("错误: 未提供Twitter URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"Twitter URL: {twitter_url}")

        try:
            import yt_dlp
            import os

            # 创建下载目录
            download_dir = TWITTER_DOWNLOADS_DIR
            os.makedirs(download_dir, exist_ok=True)

            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': False,
            }

            self.update_signal.emit("正在下载Twitter视频...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(twitter_url, download=True)
                video_title = info.get('title', 'twitter_video')
                video_ext = info.get('ext', 'mp4')
                video_file = os.path.join(download_dir, f"{video_title}.{video_ext}")

                self.update_signal.emit(f"✓ Twitter视频下载完成!")
                self.update_signal.emit(f"保存位置: {video_file}")
                self.finished_signal.emit(video_file, True)

        except Exception as e:
            import traceback
            error_msg = f"Twitter视频下载失败: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(error_msg)
            self.finished_signal.emit("", False)

    def process_bilibili(self):
        """处理Bilibili视频 - 使用yt-dlp下载"""
        self.update_signal.emit("开始处理Bilibili视频...")

        # 从参数中获取Bilibili URL
        bilibili_url = self.params.get("url", "")
        if not bilibili_url:
            self.update_signal.emit("错误: 未提供Bilibili URL")
            self.finished_signal.emit("", False)
            return

        self.update_signal.emit(f"Bilibili URL: {bilibili_url}")

        try:
            import yt_dlp
            import os

            # 创建下载目录
            download_dir = BILIBILI_DOWNLOADS_DIR
            os.makedirs(download_dir, exist_ok=True)

            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': False,
            }

            self.update_signal.emit("正在下载Bilibili视频...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(bilibili_url, download=True)
                video_title = info.get('title', 'bilibili_video')
                video_ext = info.get('ext', 'mp4')
                video_file = os.path.join(download_dir, f"{video_title}.{video_ext}")

                self.update_signal.emit(f"✓ Bilibili视频下载完成!")
                self.update_signal.emit(f"保存位置: {video_file}")
                self.finished_signal.emit(video_file, True)

        except Exception as e:
            import traceback
            error_msg = f"Bilibili视频下载失败: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(error_msg)
            self.finished_signal.emit("", False)

    def process_local_audio(self):
        """处理本地音频文件"""
        self.update_signal.emit("开始处理本地音频文件...")
        
        # 从参数中获取值
        audio_path = self.params.get("audio_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        
        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        import builtins
        builtins.print = custom_print
        
        try:
            # 调用原始代码中的处理函数
            result = process_local_audio(
                audio_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, enable_transcription, generate_article
            )
            
            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print
    
    def process_local_video(self):
        """处理本地视频文件"""
        self.update_signal.emit("开始处理本地视频文件...")
        
        # 从参数中获取值
        video_path = self.params.get("video_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        source_language = self.params.get("source_language", None)  # 获取选择的源语言代码
        
        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        import builtins
        builtins.print = custom_print
        
        try:
            # 调用原始代码中的处理函数
            result = process_local_video(
                video_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language
            )
            
            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print
    
    def process_local_video_batch(self):
        """批量处理本地视频文件"""
        self.update_signal.emit("开始批量处理本地视频文件...")
        
        # 从参数中获取值
        input_path = self.params.get("video_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        source_language = self.params.get("source_language", None)
        
        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        import builtins
        builtins.print = custom_print
        
        try:
            # 调用批量处理函数
            results = process_local_videos_batch(
                input_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language
            )
            
            if results:
                # 统计成功和失败的数量
                success_count = sum(1 for result in results if result.get("status") == "success")
                failed_count = sum(1 for result in results if result.get("status") in ["failed", "error"])
                skipped_count = sum(1 for result in results if result.get("status") == "skipped")
                
                self.update_signal.emit(f"\n批量处理完成!")
                self.update_signal.emit(f"成功: {success_count} 个，失败: {failed_count} 个，跳过: {skipped_count} 个")
                
                # 如果有成功的文件，返回第一个成功的结果路径
                success_results = [r for r in results if r.get("status") == "success"]
                if success_results:
                    self.finished_signal.emit(success_results[0].get("result_path", ""), True)
                else:
                    self.finished_signal.emit("", len(results) > 0)
            else:
                self.update_signal.emit("批量处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"批量处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print
    
    def process_local_text(self):
        """处理本地文本文件"""
        self.update_signal.emit("开始处理本地文本文件...")
        
        # 从参数中获取值
        text_path = self.params.get("text_path", "")
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        
        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        import builtins
        builtins.print = custom_print
        
        try:
            # 调用原始代码中的处理函数
            result = process_local_text(
                text_path, model, api_key, base_url, stream,
                summary_dir, custom_prompt, template_path
            )
            
            if result:
                self.update_signal.emit(f"处理完成! 结果保存在: {result}")
                self.finished_signal.emit(result, True)
            else:
                self.update_signal.emit("处理失败，请检查错误信息。")
                self.finished_signal.emit("", False)
        except Exception as e:
            self.update_signal.emit(f"处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print
    
    def process_batch(self):
        """批量处理YouTube视频"""
        self.update_signal.emit("开始批量处理YouTube视频...")
        
        # 从参数中获取值
        youtube_urls = self.params.get("youtube_urls", [])
        model = self.params.get("model", None)
        api_key = self.params.get("api_key", None)
        base_url = self.params.get("base_url", None)
        whisper_model_size = self.params.get("whisper_model_size", "medium")
        stream = self.params.get("stream", True)
        summary_dir = self.params.get("summary_dir", DEFAULT_SUMMARY_DIR)
        download_video = self.params.get("download_video", False)
        custom_prompt = self.params.get("custom_prompt", None)
        template_path = self.params.get("template_path", None)
        generate_subtitles = self.params.get("generate_subtitles", False)
        translate_to_chinese = self.params.get("translate_to_chinese", True)
        embed_subtitles = self.params.get("embed_subtitles", False)
        cookies_file = self.params.get("cookies_file", None)
        enable_transcription = self.params.get("enable_transcription", True)
        generate_article = self.params.get("generate_article", True)
        
        # 重定向print输出
        original_print = print
        def custom_print(*args, **kwargs):
            text = " ".join(map(str, args))
            self.update_signal.emit(text)
            original_print(*args, **kwargs)
        
        import builtins
        builtins.print = custom_print
        
        try:
            # 调用原始代码中的处理函数
            results = process_youtube_videos_batch(
                youtube_urls, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, download_video, custom_prompt,
                template_path, generate_subtitles, translate_to_chinese,
                embed_subtitles, cookies_file, enable_transcription, generate_article
            )
            
            # 统计成功和失败的数量
            success_count = sum(1 for result in results.values() if result.get("status") == "success")
            failed_count = sum(1 for result in results.values() if result.get("status") == "failed")
            
            self.update_signal.emit(f"\n批量处理完成!")
            self.update_signal.emit(f"总计: {len(youtube_urls)} 个视频")
            self.update_signal.emit(f"成功: {success_count} 个视频")
            self.update_signal.emit(f"失败: {failed_count} 个视频")
            
            if failed_count > 0:
                self.update_signal.emit("\n失败的视频:")
                for url, result in results.items():
                    if result.get("status") == "failed":
                        self.update_signal.emit(f"- {url}: {result.get('error', '未知错误')}")
            
            # 返回结果
            self.finished_signal.emit(str(results), success_count > 0)
        except Exception as e:
            self.update_signal.emit(f"批量处理过程中出现错误: {str(e)}")
            self.finished_signal.emit("", False)
        finally:
            builtins.print = original_print
    
    def stop(self):
        """停止线程"""
        self.stopped = True
        self.is_running = False
        self.update_signal.emit("正在停止任务...")
        # 等待一小段时间，给线程一个优雅停止的机会
        QTimer.singleShot(500, self.terminate)

class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        self.worker_thread = None
        
        # 初始化闲时任务相关变量
        self.idle_queue_file = "idle_queue.json"  # 闲时队列持久化文件
        self.idle_tasks = []  # 闲时任务队列
        self.idle_start_time = "23:00"  # 默认闲时开始时间
        self.idle_end_time = "07:00"    # 默认闲时结束时间
        self.idle_timer = QTimer()      # 用于检查闲时的定时器
        self.idle_timer.timeout.connect(self.check_idle_time)
        self.idle_timer.start(60000)    # 每分钟检查一次
        self.is_idle_running = False    # 是否正在执行闲时任务
        self.idle_paused = False        # 是否暂停闲时执行
        self.extension_event_history = []  # Chrome扩展事件记录
        self.extension_event_limit = 200   # 日志显示上限

        # 初始化API服务器
        self.api_server = None
        self.init_api_server()
        
        # 加载保存的闲时队列
        self.load_idle_queue()
        
        # 设置应用程序图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "icons8-youtube-96.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口标题和大小
        self.setWindowTitle("视频转录工具 (抖音/B站/YouTube/Twitter/X)")
        self.resize(900, 700)
        
        # 创建中央部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建选项卡部件
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        
        # 创建各个选项卡
        youtube_tab = self.create_youtube_tab()
        local_audio_tab = self.create_local_audio_tab()
        local_video_tab = self.create_local_video_tab()
        local_text_tab = self.create_local_text_tab()
        batch_tab = self.create_batch_tab()
        idle_queue_tab = self.create_idle_queue_tab()
        history_tab = self.create_history_tab()
        settings_tab = self.create_settings_tab()
        
        # 添加选项卡
        tab_widget.addTab(youtube_tab, "在线视频")
        tab_widget.addTab(local_audio_tab, "本地音频")
        tab_widget.addTab(local_video_tab, "本地视频")
        tab_widget.addTab(local_text_tab, "本地文本")
        tab_widget.addTab(batch_tab, "批量处理")
        tab_widget.addTab(idle_queue_tab, "闲时队列")
        tab_widget.addTab(history_tab, "下载历史")
        subtitle_translate_tab = self.create_subtitle_translate_tab()
        tab_widget.addTab(subtitle_translate_tab, "字幕翻译")
        
        # 创建直播录制标签页（替换原来的抖音下载标签页）
        try:
            print("📺 正在创建直播录制标签页...")
            live_recorder_tab = self.create_live_recorder_tab()
            if live_recorder_tab:
                tab_widget.addTab(live_recorder_tab, "直播录制")
                print("✅ 直播录制标签页创建成功")
            else:
                print("❌ 直播录制标签页创建失败：返回None")
        except Exception as e:
            print(f"❌ 直播录制标签页创建异常: {e}")
            import traceback
            traceback.print_exc()
        
        # 注释掉抖音下载标签页（不再使用）
        # douyin_tab = self.create_douyin_tab()
        # tab_widget.addTab(douyin_tab, "抖音下载")
        
        cleanup_tab = self.create_cleanup_tab()
        tab_widget.addTab(cleanup_tab, "清理工具")
        tab_widget.addTab(settings_tab, "设置")
        
        # 调试：打印所有标签页
        print(f"📋 总标签页数: {tab_widget.count()}")
        for i in range(tab_widget.count()):
            tab_name = tab_widget.tabText(i)
            print(f"  {i+1}. {tab_name}")
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")
    
    def create_youtube_tab(self):
        """创建YouTube视频选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建输入区域
        input_group = QGroupBox("视频链接（支持YouTube、Twitter等平台）")
        input_layout = QVBoxLayout(input_group)
        
        # 添加URL输入框
        url_layout = QHBoxLayout()
        url_label = QLabel("视频URL:")
        self.youtube_url_input = URLLineEdit()
        self.youtube_url_input.setPlaceholderText("输入YouTube、Twitter、X、抖音等视频链接或播放列表（右键可直接粘贴）...")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.youtube_url_input)
        input_layout.addLayout(url_layout)
        
        # 添加处理选项
        options_layout = QHBoxLayout()
        
        # 左侧选项
        left_options = QVBoxLayout()
        self.download_video_checkbox = QCheckBox("下载完整视频（而不仅是音频）")
        self.generate_subtitles_checkbox = QCheckBox("生成字幕文件")
        self.translate_checkbox = QCheckBox("将字幕翻译成中文")
        self.translate_checkbox.setChecked(True)
        self.embed_subtitles_checkbox = QCheckBox("将字幕嵌入到视频中")
        
        # 处理步骤选择
        self.prefer_native_subtitles_checkbox = QCheckBox("优先使用原生字幕（快速生成摘要）")
        self.prefer_native_subtitles_checkbox.setChecked(True)  # 默认开启
        self.prefer_native_subtitles_checkbox.setToolTip("如果视频有原生字幕，直接使用字幕生成摘要，跳过音频下载和转录步骤")
        self.enable_transcription_checkbox = QCheckBox("执行转录（音频转文字）")
        self.enable_transcription_checkbox.setChecked(True)  # 默认开启
        self.generate_article_checkbox = QCheckBox("生成文章摘要")
        self.generate_article_checkbox.setChecked(True)  # 默认开启
        
        # 按照正确的处理流程排序：下载视频 -> 优先原生字幕 -> 执行转录/生成字幕 -> 嵌入视频 -> 生成摘要
        left_options.addWidget(self.download_video_checkbox)
        left_options.addWidget(self.prefer_native_subtitles_checkbox)
        left_options.addWidget(self.enable_transcription_checkbox)
        left_options.addWidget(self.generate_subtitles_checkbox)
        left_options.addWidget(self.translate_checkbox)
        left_options.addWidget(self.embed_subtitles_checkbox)
        left_options.addWidget(self.generate_article_checkbox)
        
        # 右侧选项
        right_options = QVBoxLayout()
        model_layout = QHBoxLayout()
        model_label = QLabel("Whisper模型:")
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.whisper_model_combo.setCurrentText("small")
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.whisper_model_combo)
        
        cookies_layout = QHBoxLayout()
        cookies_label = QLabel("Cookies文件:")
        self.cookies_path_input = QLineEdit()
        self.cookies_path_input.setPlaceholderText("可选，用于绕过YouTube机器人验证")
        self.cookies_path_input.setToolTip("""🍪 Cookies文件用途:
• 绕过YouTube的机器人验证
• 访问需要登录的内容
• 提高访问成功率

📥 获取方法:
1. Chrome: 安装"Get cookies.txt"插件
2. Firefox: 安装"cookies.txt"插件  
3. 在YouTube登录后导出cookies.txt文件
4. 将文件路径填入此处

💡 提示: 遇到"Sign in to confirm you're not a bot"错误时必须使用Cookies文件""")
        self.cookies_browse_button = QPushButton("浏览...")
        self.cookies_auto_button = QPushButton("🔄 自动获取")
        self.cookies_auto_button.setToolTip("自动从浏览器获取Cookies（Chrome、Edge、Firefox）")
        self.cookies_help_button = QPushButton("❓")
        self.cookies_help_button.setMaximumWidth(30)
        self.cookies_help_button.setToolTip("点击查看Cookies获取教程")
        cookies_layout.addWidget(cookies_label)
        cookies_layout.addWidget(self.cookies_path_input)
        cookies_layout.addWidget(self.cookies_browse_button)
        cookies_layout.addWidget(self.cookies_auto_button)
        cookies_layout.addWidget(self.cookies_help_button)
        
        # 连接cookies文件变化事件到URL输入框
        self.cookies_path_input.textChanged.connect(
            lambda text: self.youtube_url_input.set_cookies_file(text.strip() if text.strip() else None)
        )
        
        right_options.addLayout(model_layout)

        # 翻译日志开关（仅影响字幕翻译等详细日志输出）
        self.show_translation_logs_checkbox = QCheckBox("显示翻译日志")
        self.show_translation_logs_checkbox.setChecked(True)  # 默认保持原有行为：显示详细日志
        right_options.addWidget(self.show_translation_logs_checkbox)
        right_options.addLayout(cookies_layout)
        right_options.addStretch()
        
        options_layout.addLayout(left_options)
        options_layout.addLayout(right_options)
        input_layout.addLayout(options_layout)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.youtube_process_button = QPushButton("开始处理")
        self.youtube_process_button.setMinimumHeight(40)
        self.youtube_stop_button = QPushButton("中断操作")
        self.youtube_stop_button.setMinimumHeight(40)
        self.youtube_stop_button.setEnabled(False)
        self.youtube_idle_button = QPushButton("闲时操作")
        self.youtube_idle_button.setMinimumHeight(40)
        button_layout.addWidget(self.youtube_process_button)
        button_layout.addWidget(self.youtube_stop_button)
        button_layout.addWidget(self.youtube_idle_button)
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_group)
        
        # 创建输出区域
        output_group = QGroupBox("处理日志")
        output_layout = QVBoxLayout(output_group)
        self.youtube_output_text = QTextEdit()
        self.youtube_output_text.setReadOnly(True)
        output_layout.addWidget(self.youtube_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.youtube_process_button.clicked.connect(self.process_youtube)
        self.youtube_stop_button.clicked.connect(self.stop_current_task)
        self.youtube_idle_button.clicked.connect(self.add_youtube_to_idle_queue)
        self.cookies_browse_button.clicked.connect(self.browse_cookies_file)
        self.cookies_auto_button.clicked.connect(self.auto_get_cookies)
        self.cookies_help_button.clicked.connect(self.show_cookies_help)
        
        return tab
    
    def create_local_audio_tab(self):
        """创建本地音频选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建输入区域
        input_group = QGroupBox("本地音频文件")
        input_layout = QVBoxLayout(input_group)
        
        # 添加文件选择
        file_layout = QHBoxLayout()
        file_label = QLabel("音频文件:")
        self.audio_path_input = QLineEdit()
        self.audio_path_input.setPlaceholderText("选择本地音频文件...")
        self.audio_browse_button = QPushButton("浏览...")
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.audio_path_input)
        file_layout.addWidget(self.audio_browse_button)
        input_layout.addLayout(file_layout)
        
        # 添加处理选项
        options_layout = QHBoxLayout()
        
        # 左侧选项
        left_options = QVBoxLayout()
        self.audio_generate_subtitles_checkbox = QCheckBox("生成字幕文件")
        self.audio_translate_checkbox = QCheckBox("将字幕翻译成中文")
        self.audio_translate_checkbox.setChecked(True)
        
        # 处理步骤选择
        self.audio_enable_transcription_checkbox = QCheckBox("执行转录（音频转文字）")
        self.audio_enable_transcription_checkbox.setChecked(True)  # 默认开启
        self.audio_generate_article_checkbox = QCheckBox("生成文章摘要")
        self.audio_generate_article_checkbox.setChecked(True)  # 默认开启
        
        # 按照正确的处理流程排序：执行转录 -> 生成字幕 -> 生成摘要
        left_options.addWidget(self.audio_enable_transcription_checkbox)
        left_options.addWidget(self.audio_generate_subtitles_checkbox)
        left_options.addWidget(self.audio_translate_checkbox)
        left_options.addWidget(self.audio_generate_article_checkbox)
        left_options.addStretch()
        
        # 右侧选项
        right_options = QVBoxLayout()
        audio_model_layout = QHBoxLayout()
        audio_model_label = QLabel("Whisper模型:")
        self.audio_whisper_model_combo = QComboBox()
        self.audio_whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.audio_whisper_model_combo.setCurrentText("small")
        audio_model_layout.addWidget(audio_model_label)
        audio_model_layout.addWidget(self.audio_whisper_model_combo)
        
        right_options.addLayout(audio_model_layout)
        right_options.addStretch()
        
        options_layout.addLayout(left_options)
        options_layout.addLayout(right_options)
        input_layout.addLayout(options_layout)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.audio_process_button = QPushButton("开始处理")
        self.audio_process_button.setMinimumHeight(40)
        self.audio_stop_button = QPushButton("中断操作")
        self.audio_stop_button.setMinimumHeight(40)
        self.audio_stop_button.setEnabled(False)
        self.audio_idle_button = QPushButton("闲时操作")
        self.audio_idle_button.setMinimumHeight(40)
        button_layout.addWidget(self.audio_process_button)
        button_layout.addWidget(self.audio_stop_button)
        button_layout.addWidget(self.audio_idle_button)
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_group)
        
        # 创建输出区域
        output_group = QGroupBox("处理日志")
        output_layout = QVBoxLayout(output_group)
        self.audio_output_text = QTextEdit()
        self.audio_output_text.setReadOnly(True)
        output_layout.addWidget(self.audio_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.audio_process_button.clicked.connect(self.process_local_audio)
        self.audio_stop_button.clicked.connect(self.stop_current_task)
        self.audio_idle_button.clicked.connect(self.add_audio_to_idle_queue)
        self.audio_browse_button.clicked.connect(self.browse_audio_file)
        
        return tab
    
    def create_local_video_tab(self):
        """创建本地视频选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建输入区域
        input_group = QGroupBox("本地视频文件")
        input_layout = QVBoxLayout(input_group)
        
        # 添加处理模式选择
        mode_layout = QHBoxLayout()
        mode_label = QLabel("处理模式:")
        self.video_mode_group = QButtonGroup()
        self.video_single_mode_radio = QRadioButton("单个视频文件")
        self.video_batch_mode_radio = QRadioButton("批量处理（目录）")
        self.video_single_mode_radio.setChecked(True)  # 默认选择单个文件模式
        
        self.video_mode_group.addButton(self.video_single_mode_radio, 0)
        self.video_mode_group.addButton(self.video_batch_mode_radio, 1)
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.video_single_mode_radio)
        mode_layout.addWidget(self.video_batch_mode_radio)
        mode_layout.addStretch()
        input_layout.addLayout(mode_layout)
        
        # 添加文件选择
        file_layout = QHBoxLayout()
        self.video_path_label = QLabel("视频文件:")
        self.video_path_input = QLineEdit()
        self.video_path_input.setPlaceholderText("选择本地视频文件...")
        self.video_browse_button = QPushButton("浏览...")
        file_layout.addWidget(self.video_path_label)
        file_layout.addWidget(self.video_path_input)
        file_layout.addWidget(self.video_browse_button)
        input_layout.addLayout(file_layout)
        
        # 添加处理选项
        options_layout = QHBoxLayout()
        
        # 左侧选项
        left_options = QVBoxLayout()
        self.video_generate_subtitles_checkbox = QCheckBox("生成字幕文件")
        self.video_translate_checkbox = QCheckBox("将字幕翻译成中文")
        self.video_translate_checkbox.setChecked(True)
        self.video_embed_subtitles_checkbox = QCheckBox("将字幕嵌入到视频中")
        
        # 处理步骤选择
        self.video_enable_transcription_checkbox = QCheckBox("执行转录（音频转文字）")
        self.video_enable_transcription_checkbox.setChecked(True)  # 默认开启
        self.video_generate_article_checkbox = QCheckBox("生成文章摘要")
        self.video_generate_article_checkbox.setChecked(True)  # 默认开启
        
        # 按照正确的处理流程排序：执行转录 -> 生成字幕 -> 嵌入视频 -> 生成摘要
        left_options.addWidget(self.video_enable_transcription_checkbox)
        left_options.addWidget(self.video_generate_subtitles_checkbox)
        left_options.addWidget(self.video_translate_checkbox)
        left_options.addWidget(self.video_embed_subtitles_checkbox)
        left_options.addWidget(self.video_generate_article_checkbox)
        
        # 右侧选项
        right_options = QVBoxLayout()
        video_model_layout = QHBoxLayout()
        video_model_label = QLabel("Whisper模型:")
        self.video_whisper_model_combo = QComboBox()
        self.video_whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.video_whisper_model_combo.setCurrentText("small")
        video_model_layout.addWidget(video_model_label)
        video_model_layout.addWidget(self.video_whisper_model_combo)
        
        # 添加源语言选择
        source_lang_layout = QHBoxLayout()
        source_lang_label = QLabel("源语言:")
        self.video_source_language_combo = QComboBox()
        # 添加常见语言选项
        language_options = [
            ("自动检测", "auto"),
            ("英语", "en"),
            ("中文", "zh"),
            ("日语", "ja"),
            ("韩语", "ko"),
            ("法语", "fr"),
            ("德语", "de"),
            ("西班牙语", "es"),
            ("意大利语", "it"),
            ("俄语", "ru"),
            ("阿拉伯语", "ar"),
            ("葡萄牙语", "pt"),
            ("荷兰语", "nl"),
            ("瑞典语", "sv"),
            ("丹麦语", "da"),
            ("挪威语", "no"),
            ("芬兰语", "fi"),
            ("波兰语", "pl"),
            ("捷克语", "cs"),
            ("匈牙利语", "hu"),
            ("泰语", "th"),
            ("越南语", "vi"),
            ("印尼语", "id"),
            ("马来语", "ms"),
            ("希腊语", "el"),
            ("土耳其语", "tr")
        ]
        for display_name, code in language_options:
            self.video_source_language_combo.addItem(display_name, code)
        self.video_source_language_combo.setCurrentText("自动检测")
        source_lang_layout.addWidget(source_lang_label)
        source_lang_layout.addWidget(self.video_source_language_combo)
        
        right_options.addLayout(video_model_layout)
        right_options.addLayout(source_lang_layout)
        right_options.addStretch()
        
        options_layout.addLayout(left_options)
        options_layout.addLayout(right_options)
        input_layout.addLayout(options_layout)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.video_process_button = QPushButton("开始处理")
        self.video_process_button.setMinimumHeight(40)
        self.video_stop_button = QPushButton("中断操作")
        self.video_stop_button.setMinimumHeight(40)
        self.video_stop_button.setEnabled(False)
        self.video_idle_button = QPushButton("闲时操作")
        self.video_idle_button.setMinimumHeight(40)
        button_layout.addWidget(self.video_process_button)
        button_layout.addWidget(self.video_stop_button)
        button_layout.addWidget(self.video_idle_button)
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_group)
        
        # 创建输出区域
        output_group = QGroupBox("处理日志")
        output_layout = QVBoxLayout(output_group)
        self.video_output_text = QTextEdit()
        self.video_output_text.setReadOnly(True)
        output_layout.addWidget(self.video_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.video_process_button.clicked.connect(self.process_local_video)
        self.video_stop_button.clicked.connect(self.stop_current_task)
        self.video_idle_button.clicked.connect(self.add_video_to_idle_queue)
        self.video_browse_button.clicked.connect(self.browse_video_path)
        self.video_mode_group.buttonClicked.connect(self.on_video_mode_changed)
        
        return tab
    
    def create_local_text_tab(self):
        """创建本地文本选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建输入区域
        input_group = QGroupBox("本地文本文件")
        input_layout = QVBoxLayout(input_group)
        
        # 添加文件选择
        file_layout = QHBoxLayout()
        file_label = QLabel("文本文件:")
        self.text_path_input = QLineEdit()
        self.text_path_input.setPlaceholderText("选择本地文本文件...")
        self.text_browse_button = QPushButton("浏览...")
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.text_path_input)
        file_layout.addWidget(self.text_browse_button)
        input_layout.addLayout(file_layout)
        
        # 添加处理选项
        options_layout = QHBoxLayout()
        
        # 模型选择
        model_layout = QHBoxLayout()
        model_label = QLabel("使用模型:")
        self.text_model_input = QLineEdit()
        self.text_model_input.setPlaceholderText("留空使用默认模型")
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.text_model_input)
        
        options_layout.addLayout(model_layout)
        input_layout.addLayout(options_layout)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.text_process_button = QPushButton("开始处理")
        self.text_process_button.setMinimumHeight(40)
        self.text_stop_button = QPushButton("中断操作")
        self.text_stop_button.setMinimumHeight(40)
        self.text_stop_button.setEnabled(False)
        self.text_idle_button = QPushButton("闲时操作")
        self.text_idle_button.setMinimumHeight(40)
        button_layout.addWidget(self.text_process_button)
        button_layout.addWidget(self.text_stop_button)
        button_layout.addWidget(self.text_idle_button)
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_group)
        
        # 创建输出区域
        output_group = QGroupBox("处理日志")
        output_layout = QVBoxLayout(output_group)
        self.text_output_text = QTextEdit()
        self.text_output_text.setReadOnly(True)
        output_layout.addWidget(self.text_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.text_process_button.clicked.connect(self.process_local_text)
        self.text_stop_button.clicked.connect(self.stop_current_task)
        self.text_idle_button.clicked.connect(self.add_text_to_idle_queue)
        self.text_browse_button.clicked.connect(self.browse_text_file)
        
        return tab
    
    def create_batch_tab(self):
        """创建批量处理选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建输入区域
        input_group = QGroupBox("批量处理视频（支持YouTube、Twitter等平台）")
        input_layout = QVBoxLayout(input_group)
        
        # 添加URL输入框
        self.batch_urls_text = URLTextEdit()
        self.batch_urls_text.setPlaceholderText("输入多个视频链接，每行一个，支持YouTube、Twitter、X等（右键可直接粘贴）...")
        input_layout.addWidget(self.batch_urls_text)
        
        # 添加文件选择
        file_layout = QHBoxLayout()
        file_label = QLabel("或从文件导入:")
        self.batch_file_input = QLineEdit()
        self.batch_file_input.setPlaceholderText("选择包含URL的文本文件...")
        self.batch_browse_button = QPushButton("浏览...")
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.batch_file_input)
        file_layout.addWidget(self.batch_browse_button)
        input_layout.addLayout(file_layout)
        
        # 添加处理选项
        options_layout = QHBoxLayout()
        
        # 左侧选项
        left_options = QVBoxLayout()
        self.batch_download_video_checkbox = QCheckBox("下载完整视频（而不仅是音频）")
        self.batch_generate_subtitles_checkbox = QCheckBox("生成字幕文件")
        self.batch_translate_checkbox = QCheckBox("将字幕翻译成中文")
        self.batch_translate_checkbox.setChecked(True)
        self.batch_embed_subtitles_checkbox = QCheckBox("将字幕嵌入到视频中")
        
        # 处理步骤选择
        self.batch_prefer_native_subtitles_checkbox = QCheckBox("优先使用原生字幕（快速生成摘要）")
        self.batch_prefer_native_subtitles_checkbox.setChecked(True)  # 默认开启
        self.batch_prefer_native_subtitles_checkbox.setToolTip("如果视频有原生字幕，直接使用字幕生成摘要，跳过音频下载和转录步骤")
        self.batch_enable_transcription_checkbox = QCheckBox("执行转录（音频转文字）")
        self.batch_enable_transcription_checkbox.setChecked(True)  # 默认开启
        self.batch_generate_article_checkbox = QCheckBox("生成文章摘要")
        self.batch_generate_article_checkbox.setChecked(True)  # 默认开启
        
        # 按照正确的处理流程排序：下载视频 -> 优先原生字幕 -> 执行转录/生成字幕 -> 嵌入视频 -> 生成摘要
        left_options.addWidget(self.batch_download_video_checkbox)
        left_options.addWidget(self.batch_prefer_native_subtitles_checkbox)
        left_options.addWidget(self.batch_enable_transcription_checkbox)
        left_options.addWidget(self.batch_generate_subtitles_checkbox)
        left_options.addWidget(self.batch_translate_checkbox)
        left_options.addWidget(self.batch_embed_subtitles_checkbox)
        left_options.addWidget(self.batch_generate_article_checkbox)
        
        # 右侧选项
        right_options = QVBoxLayout()
        batch_model_layout = QHBoxLayout()
        batch_model_label = QLabel("Whisper模型:")
        self.batch_whisper_model_combo = QComboBox()
        self.batch_whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.batch_whisper_model_combo.setCurrentText("small")
        batch_model_layout.addWidget(batch_model_label)
        batch_model_layout.addWidget(self.batch_whisper_model_combo)
        
        batch_cookies_layout = QHBoxLayout()
        batch_cookies_label = QLabel("Cookies文件:")
        self.batch_cookies_path_input = QLineEdit()
        self.batch_cookies_path_input.setPlaceholderText("可选，用于访问需要登录的内容")
        self.batch_cookies_browse_button = QPushButton("浏览...")
        batch_cookies_layout.addWidget(batch_cookies_label)
        batch_cookies_layout.addWidget(self.batch_cookies_path_input)
        batch_cookies_layout.addWidget(self.batch_cookies_browse_button)
        
        right_options.addLayout(batch_model_layout)
        right_options.addLayout(batch_cookies_layout)
        right_options.addStretch()
        
        options_layout.addLayout(left_options)
        options_layout.addLayout(right_options)
        input_layout.addLayout(options_layout)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.batch_process_button = QPushButton("开始批量处理")
        self.batch_process_button.setMinimumHeight(40)
        self.batch_stop_button = QPushButton("中断操作")
        self.batch_stop_button.setMinimumHeight(40)
        self.batch_stop_button.setEnabled(False)
        self.batch_idle_button = QPushButton("闲时操作")
        self.batch_idle_button.setMinimumHeight(40)
        button_layout.addWidget(self.batch_process_button)
        button_layout.addWidget(self.batch_stop_button)
        button_layout.addWidget(self.batch_idle_button)
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_group)
        
        # 创建输出区域
        output_group = QGroupBox("处理日志")
        output_layout = QVBoxLayout(output_group)
        self.batch_output_text = QTextEdit()
        self.batch_output_text.setReadOnly(True)
        output_layout.addWidget(self.batch_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.batch_process_button.clicked.connect(self.process_batch)
        self.batch_stop_button.clicked.connect(self.stop_current_task)
        self.batch_idle_button.clicked.connect(self.add_batch_to_idle_queue)
        self.batch_browse_button.clicked.connect(self.browse_batch_file)
        self.batch_cookies_browse_button.clicked.connect(self.browse_batch_cookies_file)
        
        return tab
    
    def create_idle_queue_tab(self):
        """创建闲时队列管理选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 闲时设置区域
        settings_group = QGroupBox("闲时执行设置")
        settings_layout = QVBoxLayout(settings_group)
        
        # 时间设置
        time_layout = QHBoxLayout()
        start_label = QLabel("开始时间:")
        self.idle_queue_start_input = QLineEdit()
        self.idle_queue_start_input.setText(self.idle_start_time)
        self.idle_queue_start_input.setPlaceholderText("例如: 23:00")
        
        end_label = QLabel("结束时间:")
        self.idle_queue_end_input = QLineEdit()
        self.idle_queue_end_input.setText(self.idle_end_time)
        self.idle_queue_end_input.setPlaceholderText("例如: 07:00")
        
        update_time_button = QPushButton("更新时间")
        update_time_button.clicked.connect(self.update_idle_time)
        
        time_layout.addWidget(start_label)
        time_layout.addWidget(self.idle_queue_start_input)
        time_layout.addWidget(end_label)
        time_layout.addWidget(self.idle_queue_end_input)
        time_layout.addWidget(update_time_button)
        settings_layout.addLayout(time_layout)
        
        # 队列状态
        status_layout = QHBoxLayout()
        self.queue_status_label = QLabel("队列状态: 0 个任务等待执行")
        self.idle_status_label = QLabel("当前状态: 非闲时")
        status_layout.addWidget(self.queue_status_label)
        status_layout.addWidget(self.idle_status_label)
        settings_layout.addLayout(status_layout)
        
        layout.addWidget(settings_group)
        
        # 任务队列显示区域
        queue_group = QGroupBox("任务队列")
        queue_layout = QVBoxLayout(queue_group)
        
        # 队列列表
        self.idle_queue_list = QListWidget()
        self.idle_queue_list.setAlternatingRowColors(True)
        queue_layout.addWidget(self.idle_queue_list)
        
        # 队列操作按钮
        queue_buttons_layout = QHBoxLayout()
        self.refresh_queue_button = QPushButton("刷新队列")
        self.remove_task_button = QPushButton("删除选中")
        self.clear_all_button = QPushButton("清空队列")
        self.move_up_button = QPushButton("上移")
        self.move_down_button = QPushButton("下移")
        
        queue_buttons_layout.addWidget(self.refresh_queue_button)
        queue_buttons_layout.addWidget(self.remove_task_button)
        queue_buttons_layout.addWidget(self.move_up_button)
        queue_buttons_layout.addWidget(self.move_down_button)
        queue_buttons_layout.addWidget(self.clear_all_button)
        queue_layout.addLayout(queue_buttons_layout)
        
        layout.addWidget(queue_group)
        
        # 手动控制区域
        control_group = QGroupBox("手动控制")
        control_layout = QHBoxLayout(control_group)
        
        self.force_start_button = QPushButton("立即开始下一个任务")
        self.pause_idle_button = QPushButton("暂停闲时执行")
        self.resume_idle_button = QPushButton("恢复闲时执行")
        
        control_layout.addWidget(self.force_start_button)
        control_layout.addWidget(self.pause_idle_button)
        control_layout.addWidget(self.resume_idle_button)
        layout.addWidget(control_group)

        # Chrome扩展通信日志
        log_group = QGroupBox("Chrome扩展通信日志")
        log_layout = QVBoxLayout(log_group)
        self.chrome_extension_log = QTextEdit()
        self.chrome_extension_log.setReadOnly(True)
        self.chrome_extension_log.setPlaceholderText("这里会显示来自Chrome扩展的请求和处理状态...")
        self.chrome_extension_log.setMinimumHeight(140)
        log_layout.addWidget(self.chrome_extension_log)

        log_buttons = QHBoxLayout()
        log_buttons.addStretch()
        clear_log_button = QPushButton("清空日志")
        clear_log_button.clicked.connect(self.clear_extension_log)
        log_buttons.addWidget(clear_log_button)
        log_layout.addLayout(log_buttons)

        layout.addWidget(log_group)

        # 连接信号和槽
        self.refresh_queue_button.clicked.connect(self.refresh_idle_queue_display)
        self.remove_task_button.clicked.connect(self.remove_selected_task)
        self.clear_all_button.clicked.connect(self.clear_idle_queue)
        self.move_up_button.clicked.connect(self.move_task_up)
        self.move_down_button.clicked.connect(self.move_task_down)
        self.force_start_button.clicked.connect(self.force_start_next_task)
        self.pause_idle_button.clicked.connect(self.pause_idle_execution)
        self.resume_idle_button.clicked.connect(self.resume_idle_execution)
        
        # 初始化显示
        self.refresh_idle_queue_display()
        self.update_idle_status_display()
        
        # 创建定时器来更新状态显示
        self.status_update_timer = QTimer()
        self.status_update_timer.timeout.connect(self.update_idle_status_display)
        self.status_update_timer.start(5000)  # 每5秒更新一次
        
        return tab
    
    def create_history_tab(self):
        """创建下载历史选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 创建历史列表
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        
        # 添加刷新按钮
        refresh_button = QPushButton("刷新历史记录")
        layout.addWidget(refresh_button)
        
        # 连接信号和槽
        refresh_button.clicked.connect(self.refresh_history)
        
        # 初始加载历史记录
        self.refresh_history()
        
        return tab
    
    def create_subtitle_translate_tab(self):
        """创建字幕翻译选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 标题和说明
        title_label = QLabel("🌐 字幕翻译工具")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("独立翻译字幕文件，支持处理中断后的单独翻译需求。")
        desc_label.setStyleSheet("color: #666; margin-bottom: 20px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 输入方式选择
        input_method_group = QGroupBox("选择输入方式")
        input_method_layout = QVBoxLayout(input_method_group)
        
        # 输入方式单选按钮
        input_method_radio_layout = QHBoxLayout()
        self.file_input_radio = QRadioButton("本地字幕文件")
        self.youtube_input_radio = QRadioButton("YouTube 视频链接")
        self.file_input_radio.setChecked(True)  # 默认选择文件输入
        
        input_method_radio_layout.addWidget(self.file_input_radio)
        input_method_radio_layout.addWidget(self.youtube_input_radio)
        input_method_radio_layout.addStretch()
        input_method_layout.addLayout(input_method_radio_layout)
        
        layout.addWidget(input_method_group)
        
        # YouTube输入区域
        youtube_group = QGroupBox("YouTube 视频")
        youtube_layout = QVBoxLayout(youtube_group)
        
        # YouTube URL输入
        youtube_url_layout = QHBoxLayout()
        youtube_url_label = QLabel("视频链接:")
        self.subtitle_youtube_url_input = QLineEdit()
        self.subtitle_youtube_url_input.setPlaceholderText("输入YouTube视频链接，例如：https://www.youtube.com/watch?v=...")
        self.get_subtitle_languages_button = QPushButton("获取可用语言")
        self.get_subtitle_languages_button.setEnabled(False)
        
        youtube_url_layout.addWidget(youtube_url_label)
        youtube_url_layout.addWidget(self.subtitle_youtube_url_input)
        youtube_url_layout.addWidget(self.get_subtitle_languages_button)
        youtube_layout.addLayout(youtube_url_layout)
        
        # 可用语言显示和选择
        language_selection_layout = QHBoxLayout()
        language_selection_label = QLabel("字幕语言:")
        self.available_languages_combo = QComboBox()
        self.available_languages_combo.setEnabled(False)
        self.download_subtitle_button = QPushButton("下载字幕")
        self.download_subtitle_button.setEnabled(False)
        
        language_selection_layout.addWidget(language_selection_label)
        language_selection_layout.addWidget(self.available_languages_combo)
        language_selection_layout.addWidget(self.download_subtitle_button)
        language_selection_layout.addStretch()
        youtube_layout.addLayout(language_selection_layout)
        
        layout.addWidget(youtube_group)
        
        # 文件选择区域
        file_group = QGroupBox("选择字幕文件")
        file_layout = QVBoxLayout(file_group)
        
        # 文件选择
        file_select_layout = QHBoxLayout()
        file_label = QLabel("字幕文件:")
        self.subtitle_file_input = QLineEdit()
        self.subtitle_file_input.setPlaceholderText("选择要翻译的字幕文件（支持 .srt, .vtt, .ass 格式）...")
        self.subtitle_browse_button = QPushButton("浏览...")
        file_select_layout.addWidget(file_label)
        file_select_layout.addWidget(self.subtitle_file_input)
        file_select_layout.addWidget(self.subtitle_browse_button)
        file_layout.addLayout(file_select_layout)
        
        # 批量选择
        batch_file_layout = QHBoxLayout()
        batch_label = QLabel("批量翻译:")
        self.batch_subtitle_button = QPushButton("选择多个文件...")
        self.batch_subtitle_button.setToolTip("选择多个字幕文件进行批量翻译")
        batch_file_layout.addWidget(batch_label)
        batch_file_layout.addWidget(self.batch_subtitle_button)
        batch_file_layout.addStretch()
        file_layout.addLayout(batch_file_layout)
        
        layout.addWidget(file_group)
        
        # 翻译选项
        options_group = QGroupBox("翻译选项")
        options_layout = QVBoxLayout(options_group)
        
        # 目标语言选择
        lang_layout = QHBoxLayout()
        lang_label = QLabel("目标语言:")
        self.target_language_combo = QComboBox()
        self.target_language_combo.addItems([
            "中文（简体）",
            "中文（繁体）", 
            "英语",
            "日语",
            "韩语",
            "法语",
            "德语",
            "西班牙语",
            "意大利语",
            "俄语"
        ])
        self.target_language_combo.setCurrentText("中文（简体）")
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.target_language_combo)
        lang_layout.addStretch()
        options_layout.addLayout(lang_layout)
        
        # 翻译模式选择
        mode_layout = QHBoxLayout()
        mode_label = QLabel("翻译模式:")
        self.translation_mode_combo = QComboBox()
        self.translation_mode_combo.addItems([
            "智能翻译（推荐）",
            "逐句翻译",
            "段落翻译"
        ])
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.translation_mode_combo)
        mode_layout.addStretch()
        options_layout.addLayout(mode_layout)
        
        # 高级选项
        advanced_options = QHBoxLayout()
        self.preserve_timestamps_cb = QCheckBox("保留时间轴")
        self.preserve_timestamps_cb.setChecked(True)
        self.preserve_timestamps_cb.setToolTip("保持原始字幕的时间轴不变")
        
        self.backup_original_cb = QCheckBox("备份原文件")
        self.backup_original_cb.setChecked(True)
        self.backup_original_cb.setToolTip("翻译前备份原始字幕文件")
        
        advanced_options.addWidget(self.preserve_timestamps_cb)
        advanced_options.addWidget(self.backup_original_cb)
        advanced_options.addStretch()
        options_layout.addLayout(advanced_options)
        
        layout.addWidget(options_group)
        
        # 操作按钮
        buttons_layout = QHBoxLayout()
        
        self.subtitle_translate_button = QPushButton("🌐 开始翻译")
        self.subtitle_translate_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 16px; font-weight: bold;")
        self.subtitle_translate_button.setMinimumHeight(40)
        
        self.subtitle_stop_button = QPushButton("⏹ 停止翻译")
        self.subtitle_stop_button.setStyleSheet("background-color: #f44336; color: white; padding: 8px 16px; font-weight: bold;")
        self.subtitle_stop_button.setEnabled(False)
        self.subtitle_stop_button.setMinimumHeight(40)
        
        buttons_layout.addWidget(self.subtitle_translate_button)
        buttons_layout.addWidget(self.subtitle_stop_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        # 进度显示
        progress_group = QGroupBox("翻译进度")
        progress_layout = QVBoxLayout(progress_group)
        
        self.subtitle_progress_bar = QProgressBar()
        self.subtitle_progress_bar.setVisible(False)
        progress_layout.addWidget(self.subtitle_progress_bar)
        
        self.subtitle_status_label = QLabel("准备就绪")
        self.subtitle_status_label.setStyleSheet("color: #666; margin: 5px 0;")
        progress_layout.addWidget(self.subtitle_status_label)
        
        layout.addWidget(progress_group)
        
        # 输出日志
        output_group = QGroupBox("翻译日志")
        output_layout = QVBoxLayout(output_group)
        
        self.subtitle_output_text = QTextEdit()
        self.subtitle_output_text.setMaximumHeight(200)
        self.subtitle_output_text.setPlaceholderText("翻译过程和结果将在这里显示...")
        output_layout.addWidget(self.subtitle_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.subtitle_browse_button.clicked.connect(self.browse_subtitle_file)
        self.batch_subtitle_button.clicked.connect(self.browse_batch_subtitle_files)
        self.subtitle_translate_button.clicked.connect(self.translate_subtitle)
        self.subtitle_stop_button.clicked.connect(self.stop_subtitle_translation)
        
        # YouTube相关信号连接
        self.file_input_radio.toggled.connect(self.toggle_input_method)
        self.youtube_input_radio.toggled.connect(self.toggle_input_method)
        self.subtitle_youtube_url_input.textChanged.connect(self.on_youtube_url_changed)
        self.get_subtitle_languages_button.clicked.connect(self.get_available_languages)
        self.download_subtitle_button.clicked.connect(self.download_youtube_subtitle)
        
        # 设置初始状态
        self.toggle_input_method()
        
        layout.addStretch()
        return tab
    
    def create_douyin_tab(self):
        """创建抖音下载选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 标题和说明
        title_label = QLabel("📱 抖音视频下载")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("下载抖音视频、音频、封面等内容，支持无水印下载和批量处理。")
        desc_label.setStyleSheet("color: #666; margin-bottom: 20px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 输入区域
        input_group = QGroupBox("视频链接")
        input_layout = QVBoxLayout(input_group)
        
        # URL输入
        url_layout = QHBoxLayout()
        url_label = QLabel("抖音链接/分享文本:")
        self.douyin_url_input = DouyinLineEdit(self)
        self.douyin_url_input.setPlaceholderText("可留空直接点击'智能解析'，或输入抖音分享文本/视频链接")
        
        # 安装事件过滤器支持Ctrl+V
        self.douyin_url_input.installEventFilter(self)
        
        self.douyin_parse_button = QPushButton("🎯 智能解析")
        self.douyin_parse_button.setStyleSheet("background-color: #007acc; color: white; padding: 5px 15px;")
        self.douyin_parse_button.setToolTip("自动从剪贴板或输入框智能提取抖音链接并解析视频信息")
        
        # 测试按钮：提取剪贴板中的抖音链接
        self.douyin_test_extract_button = QPushButton("🔍 测试提取")
        self.douyin_test_extract_button.setStyleSheet("background-color: #28a745; color: white; padding: 5px 10px;")
        self.douyin_test_extract_button.setToolTip("从剪贴板提取抖音链接并在控制台打印（调试用）")
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.douyin_url_input)
        url_layout.addWidget(self.douyin_parse_button)
        url_layout.addWidget(self.douyin_test_extract_button)
        input_layout.addLayout(url_layout)
        
        # 批量输入
        batch_layout = QHBoxLayout()
        batch_label = QLabel("批量链接:")
        self.douyin_batch_input = DouyinTextEdit(self)
        self.douyin_batch_input.setMaximumHeight(100)
        self.douyin_batch_input.setPlaceholderText("每行一个链接或分享文本，支持右键智能粘贴和自动去重")
        
        # 安装事件过滤器支持Ctrl+V
        self.douyin_batch_input.installEventFilter(self)
        
        batch_layout.addWidget(batch_label)
        batch_layout.addWidget(self.douyin_batch_input)
        input_layout.addLayout(batch_layout)
        
        layout.addWidget(input_group)
        
        # 视频信息显示
        info_group = QGroupBox("视频信息")
        info_layout = QVBoxLayout(info_group)
        
        self.douyin_info_display = QTextEdit()
        self.douyin_info_display.setMaximumHeight(150)
        self.douyin_info_display.setReadOnly(True)
        self.douyin_info_display.setPlaceholderText("解析视频后将在这里显示视频信息...")
        info_layout.addWidget(self.douyin_info_display)
        
        layout.addWidget(info_group)
        
        # 下载选项
        options_group = QGroupBox("下载选项")
        options_layout = QVBoxLayout(options_group)
        
        # 基础选项
        basic_options_layout = QHBoxLayout()
        
        self.douyin_download_video_cb = QCheckBox("下载视频")
        self.douyin_download_video_cb.setChecked(True)
        self.douyin_download_cover_cb = QCheckBox("下载封面")
        self.douyin_download_cover_cb.setChecked(True)
        self.douyin_download_music_cb = QCheckBox("下载音频")
        self.douyin_download_music_cb.setChecked(False)
        self.douyin_remove_watermark_cb = QCheckBox("去除水印")
        self.douyin_remove_watermark_cb.setChecked(True)
        
        basic_options_layout.addWidget(self.douyin_download_video_cb)
        basic_options_layout.addWidget(self.douyin_download_cover_cb)
        basic_options_layout.addWidget(self.douyin_download_music_cb)
        basic_options_layout.addWidget(self.douyin_remove_watermark_cb)
        basic_options_layout.addStretch()
        options_layout.addLayout(basic_options_layout)
        
        # 高级选项
        advanced_options_layout = QHBoxLayout()
        
        quality_label = QLabel("视频质量:")
        self.douyin_quality_combo = QComboBox()
        self.douyin_quality_combo.addItems(["高清", "标清", "流畅"])
        self.douyin_quality_combo.setCurrentText("高清")
        
        self.douyin_save_metadata_cb = QCheckBox("保存元数据")
        self.douyin_save_metadata_cb.setChecked(True)
        
        # 转录和摘要选项
        transcription_options_layout = QHBoxLayout()
        self.douyin_enable_transcription_cb = QCheckBox("执行转录（音频转文字）")
        self.douyin_enable_transcription_cb.setChecked(True)
        self.douyin_generate_article_cb = QCheckBox("生成文章摘要")
        self.douyin_generate_article_cb.setChecked(True)
        
        transcription_options_layout.addWidget(self.douyin_enable_transcription_cb)
        transcription_options_layout.addWidget(self.douyin_generate_article_cb)
        transcription_options_layout.addStretch()
        options_layout.addLayout(transcription_options_layout)
        
        # 下载目录选择
        dir_label = QLabel("下载目录:")
        self.douyin_download_dir_input = QLineEdit(DOUYIN_DOWNLOADS_DIR)
        self.douyin_browse_dir_button = QPushButton("浏览...")
        
        advanced_options_layout.addWidget(quality_label)
        advanced_options_layout.addWidget(self.douyin_quality_combo)
        advanced_options_layout.addWidget(self.douyin_save_metadata_cb)
        advanced_options_layout.addWidget(dir_label)
        advanced_options_layout.addWidget(self.douyin_download_dir_input)
        advanced_options_layout.addWidget(self.douyin_browse_dir_button)
        options_layout.addLayout(advanced_options_layout)
        
        layout.addWidget(options_group)
        
        # 操作按钮
        buttons_layout = QHBoxLayout()
        
        self.douyin_download_button = QPushButton("🎬 开始下载")
        self.douyin_download_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 16px; font-weight: bold;")
        self.douyin_download_button.setMinimumHeight(40)
        self.douyin_download_button.setEnabled(False)
        
        self.douyin_batch_download_button = QPushButton("📦 批量下载")
        self.douyin_batch_download_button.setStyleSheet("background-color: #FF9800; color: white; padding: 8px 16px; font-weight: bold;")
        self.douyin_batch_download_button.setMinimumHeight(40)
        
        self.douyin_stop_button = QPushButton("⏹ 停止下载")
        self.douyin_stop_button.setStyleSheet("background-color: #f44336; color: white; padding: 8px 16px; font-weight: bold;")
        self.douyin_stop_button.setEnabled(False)
        self.douyin_stop_button.setMinimumHeight(40)
        
        buttons_layout.addWidget(self.douyin_download_button)
        buttons_layout.addWidget(self.douyin_batch_download_button)
        buttons_layout.addWidget(self.douyin_stop_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        # 进度显示
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)
        
        self.douyin_progress_bar = QProgressBar()
        self.douyin_progress_bar.setVisible(False)
        progress_layout.addWidget(self.douyin_progress_bar)
        
        self.douyin_status_label = QLabel("准备就绪")
        self.douyin_status_label.setStyleSheet("color: #666; margin: 5px 0;")
        progress_layout.addWidget(self.douyin_status_label)
        
        layout.addWidget(progress_group)
        
        # 输出日志
        output_group = QGroupBox("下载日志")
        output_layout = QVBoxLayout(output_group)
        
        self.douyin_output_text = QTextEdit()
        self.douyin_output_text.setMaximumHeight(200)
        self.douyin_output_text.setPlaceholderText("下载过程和结果将在这里显示...")
        output_layout.addWidget(self.douyin_output_text)
        
        layout.addWidget(output_group)
        
        # 连接信号和槽
        self.douyin_url_input.textChanged.connect(self.on_douyin_url_changed)
        self.douyin_parse_button.clicked.connect(self.parse_douyin_video)
        self.douyin_test_extract_button.clicked.connect(self.test_extract_douyin_url)
        self.douyin_download_button.clicked.connect(self.download_douyin_video)
        self.douyin_batch_download_button.clicked.connect(self.batch_download_douyin_videos)
        self.douyin_stop_button.clicked.connect(self.stop_douyin_download)
        self.douyin_browse_dir_button.clicked.connect(self.browse_douyin_download_dir)
        
        layout.addStretch()
        return tab
    
    def eventFilter(self, obj, event):
        """事件过滤器，处理Ctrl+V快捷键智能粘贴"""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QApplication
        
        # 检查是否是键盘按下事件
        if event.type() == QEvent.Type.KeyPress:
            # 检测Ctrl+V粘贴
            if (event.key() == 86 and  # V键
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                
                # 处理抖音输入框的Ctrl+V
                if isinstance(obj, DouyinLineEdit):
                    obj.smart_paste()
                    return True
                elif isinstance(obj, DouyinTextEdit):
                    obj.smart_paste()
                    return True
        
        # 调用父类的事件过滤器
        return super().eventFilter(obj, event)
    
    def create_live_recorder_tab(self):
        """创建直播录制选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 标题和说明
        title_label = QLabel("📺 直播录制")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e91e63; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("支持65+平台直播录制：抖音、快手、虎牙、斗鱼、B站、小红书、TikTok等")
        desc_label.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(desc_label)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # 直播间URL输入区域
        url_group = QGroupBox("直播间URL管理")
        url_layout = QVBoxLayout(url_group)
        
        # URL输入框
        input_layout = QHBoxLayout()
        self.live_url_input = QLineEdit()
        self.live_url_input.setPlaceholderText("输入直播间URL (支持抖音、快手、虎牙、斗鱼、B站等65+平台)")
        add_url_btn = QPushButton("添加URL")
        add_url_btn.clicked.connect(self.add_live_url)
        input_layout.addWidget(self.live_url_input)
        input_layout.addWidget(add_url_btn)
        url_layout.addLayout(input_layout)
        
        # URL列表
        self.live_url_list = QListWidget()
        self.live_url_list.setMaximumHeight(120)
        url_layout.addWidget(self.live_url_list)
        
        # URL操作按钮
        url_btn_layout = QHBoxLayout()
        remove_url_btn = QPushButton("删除选中")
        clear_urls_btn = QPushButton("清空全部")
        load_urls_btn = QPushButton("从配置文件加载")
        save_urls_btn = QPushButton("保存到配置文件")
        remove_url_btn.clicked.connect(self.remove_live_url)
        clear_urls_btn.clicked.connect(self.clear_live_urls)
        load_urls_btn.clicked.connect(self.load_live_urls)
        save_urls_btn.clicked.connect(self.save_live_urls)
        url_btn_layout.addWidget(remove_url_btn)
        url_btn_layout.addWidget(clear_urls_btn)
        url_btn_layout.addWidget(load_urls_btn)
        url_btn_layout.addWidget(save_urls_btn)
        url_layout.addLayout(url_btn_layout)
        
        scroll_layout.addWidget(url_group)
        
        # 录制设置区域
        settings_group = QGroupBox("录制设置")
        settings_layout = QVBoxLayout(settings_group)
        
        # 第一行设置
        settings_row1 = QHBoxLayout()
        
        # 视频格式
        format_label = QLabel("视频格式:")
        self.live_format_combo = QComboBox()
        self.live_format_combo.addItems(["ts", "mp4", "flv"])
        self.live_format_combo.setCurrentText("ts")
        
        # 视频画质
        quality_label = QLabel("视频画质:")
        self.live_quality_combo = QComboBox()
        self.live_quality_combo.addItems(["原画", "超清", "高清", "标清"])
        
        # 监测间隔
        interval_label = QLabel("监测间隔(秒):")
        self.live_interval_spin = QSpinBox()
        self.live_interval_spin.setRange(30, 600)
        self.live_interval_spin.setValue(60)
        
        settings_row1.addWidget(format_label)
        settings_row1.addWidget(self.live_format_combo)
        settings_row1.addWidget(quality_label)
        settings_row1.addWidget(self.live_quality_combo)
        settings_row1.addWidget(interval_label)
        settings_row1.addWidget(self.live_interval_spin)
        settings_row1.addStretch()
        
        settings_layout.addLayout(settings_row1)
        
        # 第二行设置
        settings_row2 = QHBoxLayout()
        
        # 保存路径
        path_label = QLabel("保存路径:")
        self.live_path_input = QLineEdit()
        self.live_path_input.setText(LIVE_DOWNLOADS_DIR)
        browse_path_btn = QPushButton("浏览")
        browse_path_btn.clicked.connect(self.browse_live_path)
        
        settings_row2.addWidget(path_label)
        settings_row2.addWidget(self.live_path_input)
        settings_row2.addWidget(browse_path_btn)
        
        settings_layout.addLayout(settings_row2)
        
        # 高级设置
        advanced_layout = QHBoxLayout()
        self.show_ffmpeg_log = QCheckBox("显示FFmpeg日志")
        self.save_log = QCheckBox("保存日志到文件")
        self.save_log.setChecked(True)
        advanced_layout.addWidget(self.show_ffmpeg_log)
        advanced_layout.addWidget(self.save_log)
        advanced_layout.addStretch()
        
        settings_layout.addLayout(advanced_layout)
        
        scroll_layout.addWidget(settings_group)
        
        # 录制控制区域
        control_group = QGroupBox("录制控制")
        control_layout = QVBoxLayout(control_group)
        
        # 控制按钮
        control_btn_layout = QHBoxLayout()
        self.start_record_btn = QPushButton("开始录制")
        self.stop_record_btn = QPushButton("停止录制")
        self.pause_record_btn = QPushButton("暂停监测")
        
        self.start_record_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        self.stop_record_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        self.pause_record_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-weight: bold; }")
        
        self.start_record_btn.clicked.connect(self.start_live_recording)
        self.stop_record_btn.clicked.connect(self.stop_live_recording)
        self.pause_record_btn.clicked.connect(self.pause_live_recording)
        
        # 初始状态
        self.stop_record_btn.setEnabled(False)
        self.pause_record_btn.setEnabled(False)
        
        control_btn_layout.addWidget(self.start_record_btn)
        control_btn_layout.addWidget(self.stop_record_btn)
        control_btn_layout.addWidget(self.pause_record_btn)
        control_btn_layout.addStretch()
        
        control_layout.addLayout(control_btn_layout)
        
        # 状态显示
        self.live_status_label = QLabel("状态: 未开始")
        self.live_status_label.setStyleSheet("color: #666; font-weight: bold;")
        control_layout.addWidget(self.live_status_label)
        
        scroll_layout.addWidget(control_group)
        
        # 日志显示区域
        log_group = QGroupBox("录制日志")
        log_layout = QVBoxLayout(log_group)
        
        self.live_log_display = QTextEdit()
        self.live_log_display.setMaximumHeight(200)
        self.live_log_display.setReadOnly(True)
        self.live_log_display.append("📺 直播录制工具已就绪")
        self.live_log_display.append("💡 支持平台：抖音、快手、虎牙、斗鱼、B站、小红书、TikTok等65+平台")
        
        log_layout.addWidget(self.live_log_display)
        
        # 日志控制按钮
        log_btn_layout = QHBoxLayout()
        clear_log_btn = QPushButton("清空日志")
        save_log_btn = QPushButton("保存日志")
        clear_log_btn.clicked.connect(self.clear_live_log)
        save_log_btn.clicked.connect(self.save_live_log)
        log_btn_layout.addWidget(clear_log_btn)
        log_btn_layout.addWidget(save_log_btn)
        log_btn_layout.addStretch()
        
        log_layout.addLayout(log_btn_layout)
        
        scroll_layout.addWidget(log_group)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # 初始化直播录制相关变量
        self.live_recorder = None
        self.live_recording_thread = None
        self.is_live_recording = False
        
        return tab
    
    def add_live_url(self):
        """添加直播URL到列表"""
        url = self.live_url_input.text().strip()
        if url:
            # 检查URL是否已存在
            for i in range(self.live_url_list.count()):
                if self.live_url_list.item(i).text() == url:
                    QMessageBox.information(self, "提示", "该URL已存在于列表中")
                    return
            
            self.live_url_list.addItem(url)
            self.live_url_input.clear()
            self.live_log_display.append(f"✅ 已添加URL: {url}")
    
    def remove_live_url(self):
        """删除选中的URL"""
        current_row = self.live_url_list.currentRow()
        if current_row >= 0:
            item = self.live_url_list.takeItem(current_row)
            self.live_log_display.append(f"🗑️ 已删除URL: {item.text()}")
    
    def clear_live_urls(self):
        """清空所有URL"""
        self.live_url_list.clear()
        self.live_log_display.append("🗑️ 已清空所有URL")
    
    def load_live_urls(self):
        """从配置文件加载URL"""
        try:
            config_file = "live_config/URL_config.ini"
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                self.live_url_list.clear()
                count = 0
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and line.startswith('http'):
                        self.live_url_list.addItem(line)
                        count += 1
                
                self.live_log_display.append(f"📂 已从配置文件加载 {count} 个URL")
            else:
                QMessageBox.information(self, "提示", "配置文件不存在")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载配置文件失败: {str(e)}")
    
    def save_live_urls(self):
        """保存URL到配置文件"""
        try:
            config_file = "live_config/URL_config.ini"
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write("# 直播间URL配置文件\n")
                f.write("# 一行一个直播间地址\n")
                f.write("# 要停止某个直播间录制，在URL前添加 # 号\n\n")
                
                for i in range(self.live_url_list.count()):
                    url = self.live_url_list.item(i).text()
                    f.write(f"{url}\n")
            
            self.live_log_display.append(f"💾 已保存 {self.live_url_list.count()} 个URL到配置文件")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置文件失败: {str(e)}")
    
    def browse_live_path(self):
        """浏览保存路径"""
        path = QFileDialog.getExistingDirectory(self, "选择保存路径")
        if path:
            self.live_path_input.setText(path)
    
    def start_live_recording(self):
        """开始直播录制"""
        if self.live_url_list.count() == 0:
            QMessageBox.warning(self, "错误", "请先添加直播间URL")
            return
        
        try:
            # 更新按钮状态
            self.start_record_btn.setEnabled(False)
            self.stop_record_btn.setEnabled(True)
            self.pause_record_btn.setEnabled(True)
            self.is_live_recording = True
            
            # 更新状态
            self.live_status_label.setText("状态: 正在录制...")
            self.live_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            
            # 启动录制线程
            self.live_recording_thread = LiveRecordingThread(self)
            self.live_recording_thread.log_signal.connect(self.append_live_log)
            self.live_recording_thread.start()
            
            self.live_log_display.append("🎬 开始直播录制监控...")
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动录制失败: {str(e)}")
            self.stop_live_recording()
    
    def stop_live_recording(self):
        """停止直播录制"""
        try:
            self.is_live_recording = False
            
            if self.live_recording_thread and self.live_recording_thread.isRunning():
                self.live_recording_thread.stop()
                self.live_recording_thread.wait()
            
            # 更新按钮状态
            self.start_record_btn.setEnabled(True)
            self.stop_record_btn.setEnabled(False)
            self.pause_record_btn.setEnabled(False)
            
            # 更新状态
            self.live_status_label.setText("状态: 已停止")
            self.live_status_label.setStyleSheet("color: #f44336; font-weight: bold;")
            
            self.live_log_display.append("⏹️ 已停止直播录制")
            
        except Exception as e:
            self.live_log_display.append(f"❌ 停止录制时出错: {str(e)}")
    
    def pause_live_recording(self):
        """暂停/恢复直播录制监测"""
        if hasattr(self.live_recording_thread, 'paused'):
            self.live_recording_thread.paused = not self.live_recording_thread.paused
            if self.live_recording_thread.paused:
                self.pause_record_btn.setText("恢复监测")
                self.live_status_label.setText("状态: 已暂停")
                self.live_status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                self.live_log_display.append("⏸️ 已暂停监测")
            else:
                self.pause_record_btn.setText("暂停监测")
                self.live_status_label.setText("状态: 正在录制...")
                self.live_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.live_log_display.append("▶️ 已恢复监测")
    
    def append_live_log(self, message):
        """添加日志消息"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.live_log_display.append(f"[{timestamp}] {message}")
        
        # 自动滚动到底部
        cursor = self.live_log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.live_log_display.setTextCursor(cursor)
    
    def clear_live_log(self):
        """清空日志"""
        self.live_log_display.clear()
        self.live_log_display.append("📺 直播录制日志已清空")
    
    def save_live_log(self):
        """保存日志到文件"""
        try:
            from datetime import datetime
            filename, _ = QFileDialog.getSaveFileName(
                self, "保存日志", 
                f"live_record_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "文本文件 (*.txt)"
            )
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.live_log_display.toPlainText())
                self.live_log_display.append(f"💾 日志已保存到: {filename}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存日志失败: {str(e)}")

    def create_cleanup_tab(self):
        """创建清理工具选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 标题和说明
        title_label = QLabel("🧹 清理工具")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("清理工作目录中的各种文件类型，释放磁盘空间。请谨慎操作，删除的文件无法恢复。")
        desc_label.setStyleSheet("color: #666; margin-bottom: 20px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 文件类型选择组
        file_types_group = QGroupBox("选择要清理的文件类型")
        file_types_layout = QVBoxLayout(file_types_group)
        
        # 创建复选框和打开目录按钮
        # 视频文件
        videos_layout = QHBoxLayout()
        self.cleanup_videos_cb = QCheckBox("视频文件 (videos/ 目录)")
        self.cleanup_videos_cb.setChecked(True)
        videos_layout.addWidget(self.cleanup_videos_cb)
        videos_open_btn = QPushButton("📁")
        videos_open_btn.setFixedSize(30, 25)
        videos_open_btn.setToolTip("打开 videos/ 目录")
        videos_open_btn.clicked.connect(lambda: self.open_directory("videos"))
        videos_layout.addWidget(videos_open_btn)
        videos_layout.addStretch()
        file_types_layout.addLayout(videos_layout)
        
        # 音频文件
        audios_layout = QHBoxLayout()
        self.cleanup_audios_cb = QCheckBox("音频文件 (downloads/ 目录)")
        self.cleanup_audios_cb.setChecked(True)
        audios_layout.addWidget(self.cleanup_audios_cb)
        audios_open_btn = QPushButton("📁")
        audios_open_btn.setFixedSize(30, 25)
        audios_open_btn.setToolTip("打开 downloads/ 目录")
        audios_open_btn.clicked.connect(lambda: self.open_directory("downloads"))
        audios_layout.addWidget(audios_open_btn)
        audios_layout.addStretch()
        file_types_layout.addLayout(audios_layout)
        
        # 字幕文件
        subtitles_layout = QHBoxLayout()
        self.cleanup_subtitles_cb = QCheckBox("字幕文件 (subtitles/ 目录)")
        self.cleanup_subtitles_cb.setChecked(True)
        subtitles_layout.addWidget(self.cleanup_subtitles_cb)
        subtitles_open_btn = QPushButton("📁")
        subtitles_open_btn.setFixedSize(30, 25)
        subtitles_open_btn.setToolTip("打开 subtitles/ 目录")
        subtitles_open_btn.clicked.connect(lambda: self.open_directory("subtitles"))
        subtitles_layout.addWidget(subtitles_open_btn)
        subtitles_layout.addStretch()
        file_types_layout.addLayout(subtitles_layout)
        
        # 转录文本
        transcripts_layout = QHBoxLayout()
        self.cleanup_transcripts_cb = QCheckBox("转录文本 (transcripts/ 目录)")
        self.cleanup_transcripts_cb.setChecked(True)
        transcripts_layout.addWidget(self.cleanup_transcripts_cb)
        transcripts_open_btn = QPushButton("📁")
        transcripts_open_btn.setFixedSize(30, 25)
        transcripts_open_btn.setToolTip("打开 transcripts/ 目录")
        transcripts_open_btn.clicked.connect(lambda: self.open_directory("transcripts"))
        transcripts_layout.addWidget(transcripts_open_btn)
        transcripts_layout.addStretch()
        file_types_layout.addLayout(transcripts_layout)
        
        # 文章摘要
        summaries_layout = QHBoxLayout()
        self.cleanup_summaries_cb = QCheckBox("文章摘要 (summaries/ 目录)")
        self.cleanup_summaries_cb.setChecked(True)
        summaries_layout.addWidget(self.cleanup_summaries_cb)
        summaries_open_btn = QPushButton("📁")
        summaries_open_btn.setFixedSize(30, 25)
        summaries_open_btn.setToolTip("打开 summaries/ 目录")
        summaries_open_btn.clicked.connect(lambda: self.open_directory("summaries"))
        summaries_layout.addWidget(summaries_open_btn)
        summaries_layout.addStretch()
        file_types_layout.addLayout(summaries_layout)
        
        # 带字幕视频
        videos_with_subtitles_layout = QHBoxLayout()
        self.cleanup_videos_with_subtitles_cb = QCheckBox("带字幕视频 (videos_with_subtitles/ 目录)")
        self.cleanup_videos_with_subtitles_cb.setChecked(False)  # 默认不删除，因为这些可能比较宝贵
        videos_with_subtitles_layout.addWidget(self.cleanup_videos_with_subtitles_cb)
        videos_with_subtitles_open_btn = QPushButton("📁")
        videos_with_subtitles_open_btn.setFixedSize(30, 25)
        videos_with_subtitles_open_btn.setToolTip("打开 videos_with_subtitles/ 目录")
        videos_with_subtitles_open_btn.clicked.connect(lambda: self.open_directory("videos_with_subtitles"))
        videos_with_subtitles_layout.addWidget(videos_with_subtitles_open_btn)
        videos_with_subtitles_layout.addStretch()
        file_types_layout.addLayout(videos_with_subtitles_layout)
        
        layout.addWidget(file_types_group)
        
        # 快速选择按钮
        quick_select_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all_cleanup_types)
        quick_select_layout.addWidget(select_all_btn)
        
        select_none_btn = QPushButton("全不选")
        select_none_btn.clicked.connect(self.select_none_cleanup_types)
        quick_select_layout.addWidget(select_none_btn)
        
        select_common_btn = QPushButton("常用选择")
        select_common_btn.clicked.connect(self.select_common_cleanup_types)
        quick_select_layout.addWidget(select_common_btn)
        
        quick_select_layout.addStretch()
        layout.addLayout(quick_select_layout)
        
        # 文件统计信息
        self.cleanup_stats_label = QLabel("点击'扫描文件'查看各目录文件统计")
        self.cleanup_stats_label.setStyleSheet("background-color: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0;")
        self.cleanup_stats_label.setWordWrap(True)
        layout.addWidget(self.cleanup_stats_label)
        
        # 操作按钮
        buttons_layout = QHBoxLayout()
        
        scan_btn = QPushButton("🔍 扫描文件")
        scan_btn.clicked.connect(self.scan_cleanup_files)
        scan_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 16px; font-weight: bold;")
        buttons_layout.addWidget(scan_btn)
        
        cleanup_btn = QPushButton("🗑️ 执行清理")
        cleanup_btn.clicked.connect(self.execute_cleanup)
        cleanup_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px 16px; font-weight: bold;")
        buttons_layout.addWidget(cleanup_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        # 操作日志
        self.cleanup_log = QTextEdit()
        self.cleanup_log.setMaximumHeight(200)
        self.cleanup_log.setPlaceholderText("清理操作日志将在这里显示...")
        layout.addWidget(self.cleanup_log)
        
        layout.addStretch()
        return tab
    
    def open_directory(self, directory_path):
        """打开指定目录
        
        directory_path 可以是逻辑名称（如 'videos'、'downloads'），
        也可以是实际路径。逻辑名称会通过 DIRECTORY_MAP 映射到
        workspace/ 下的真实目录。
        """
        # 将逻辑目录名映射到实际路径
        real_path = DIRECTORY_MAP.get(directory_path, directory_path)
        
        if not os.path.exists(real_path):
            QMessageBox.warning(self, "目录不存在", f"目录 '{real_path}' 不存在")
            return
        
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(real_path)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", real_path])
            else:  # Linux
                subprocess.run(["xdg-open", real_path])
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开目录: {str(e)}")
    
    def select_all_cleanup_types(self):
        """全选清理类型"""
        self.cleanup_videos_cb.setChecked(True)
        self.cleanup_audios_cb.setChecked(True)
        self.cleanup_subtitles_cb.setChecked(True)
        self.cleanup_transcripts_cb.setChecked(True)
        self.cleanup_summaries_cb.setChecked(True)
        self.cleanup_videos_with_subtitles_cb.setChecked(True)
    
    def select_none_cleanup_types(self):
        """全不选清理类型"""
        self.cleanup_videos_cb.setChecked(False)
        self.cleanup_audios_cb.setChecked(False)
        self.cleanup_subtitles_cb.setChecked(False)
        self.cleanup_transcripts_cb.setChecked(False)
        self.cleanup_summaries_cb.setChecked(False)
        self.cleanup_videos_with_subtitles_cb.setChecked(False)
    
    def select_common_cleanup_types(self):
        """常用清理选择（保留带字幕视频）"""
        self.cleanup_videos_cb.setChecked(True)
        self.cleanup_audios_cb.setChecked(True)
        self.cleanup_subtitles_cb.setChecked(True)
        self.cleanup_transcripts_cb.setChecked(True)
        self.cleanup_summaries_cb.setChecked(True)
        self.cleanup_videos_with_subtitles_cb.setChecked(False)  # 保留带字幕的视频
    
    def scan_cleanup_files(self):
        """扫描要清理的文件"""
        import os
        import glob
        
        self.cleanup_log.append("🔍 开始扫描文件...")
        
        # 定义目录和对应的文件扩展名（逻辑名称，实际路径通过 DIRECTORY_MAP 解析到 workspace/ 下）
        directories = {
            "videos": ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"],
            "downloads": ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg"],
            "subtitles": ["*.srt", "*.vtt", "*.ass"],
            "transcripts": ["*.txt"],
            "summaries": ["*.md", "*.txt"],
            "videos_with_subtitles": ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"]
        }
        
        stats = []
        total_files = 0
        total_size = 0
        
        for dir_name, extensions in directories.items():
            dir_path = DIRECTORY_MAP.get(dir_name, dir_name)
            if not os.path.exists(dir_path):
                continue
                
            dir_files = 0
            dir_size = 0
            
            for ext in extensions:
                pattern = os.path.join(dir_path, "**", ext)
                files = glob.glob(pattern, recursive=True)
                for file_path in files:
                    try:
                        size = os.path.getsize(file_path)
                        dir_files += 1
                        dir_size += size
                    except OSError:
                        continue
            
            if dir_files > 0:
                size_mb = dir_size / (1024 * 1024)
                stats.append(f"📁 {dir_name}: {dir_files} 个文件, {size_mb:.1f} MB")
                total_files += dir_files
                total_size += dir_size
        
        total_size_mb = total_size / (1024 * 1024)
        stats_text = "\n".join(stats)
        if stats_text:
            stats_text += f"\n\n📊 总计: {total_files} 个文件, {total_size_mb:.1f} MB"
        else:
            stats_text = "✨ 没有找到可清理的文件"
        
        self.cleanup_stats_label.setText(stats_text)
        self.cleanup_log.append("✅ 文件扫描完成")
    
    def execute_cleanup(self):
        """执行清理操作"""
        from PyQt6.QtWidgets import QMessageBox
        import os
        import glob
        import shutil
        
        # 获取选中的清理类型（使用逻辑目录名，实际路径通过 DIRECTORY_MAP 映射）
        cleanup_types = []
        if self.cleanup_videos_cb.isChecked():
            cleanup_types.append(("videos", ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"]))
        if self.cleanup_audios_cb.isChecked():
            cleanup_types.append(("downloads", ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg"]))
        if self.cleanup_subtitles_cb.isChecked():
            cleanup_types.append(("subtitles", ["*.srt", "*.vtt", "*.ass"]))
        if self.cleanup_transcripts_cb.isChecked():
            cleanup_types.append(("transcripts", ["*.txt"]))
        if self.cleanup_summaries_cb.isChecked():
            cleanup_types.append(("summaries", ["*.md", "*.txt"]))
        if self.cleanup_videos_with_subtitles_cb.isChecked():
            cleanup_types.append(("videos_with_subtitles", ["*.mp4", "*.avi", "*.mov", "*.webm", "*.mkv", "*.flv"]))
        
        if not cleanup_types:
            QMessageBox.warning(self, "清理错误", "请至少选择一种文件类型进行清理")
            return
        
        # 确认对话框
        selected_dirs = [dir_name for dir_name, _ in cleanup_types]
        reply = QMessageBox.question(
            self, "确认清理", 
            f"确定要清理以下目录吗？\n\n{', '.join(selected_dirs)}\n\n⚠️ 此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.cleanup_log.append("🗑️ 开始执行清理操作...")
        
        total_deleted = 0
        total_size = 0
        
        for dir_name, extensions in cleanup_types:
            dir_path = DIRECTORY_MAP.get(dir_name, dir_name)
            if not os.path.exists(dir_path):
                self.cleanup_log.append(f"⚠️ 目录不存在: {dir_path}")
                continue
            
            self.cleanup_log.append(f"🔄 正在清理 {dir_path} 目录...")
            dir_deleted = 0
            dir_size = 0
            
            for ext in extensions:
                pattern = os.path.join(dir_path, "**", ext)
                files = glob.glob(pattern, recursive=True)
                
                for file_path in files:
                    try:
                        size = os.path.getsize(file_path)
                        os.remove(file_path)
                        dir_deleted += 1
                        dir_size += size
                        self.cleanup_log.append(f"  ✅ 删除: {file_path}")
                    except OSError as e:
                        self.cleanup_log.append(f"  ❌ 删除失败: {file_path} - {str(e)}")
            
            if dir_deleted > 0:
                size_mb = dir_size / (1024 * 1024)
                self.cleanup_log.append(f"📁 {dir_path}: 删除了 {dir_deleted} 个文件, 释放 {size_mb:.1f} MB")
                total_deleted += dir_deleted
                total_size += dir_size
            else:
                self.cleanup_log.append(f"📁 {dir_name}: 没有找到可删除的文件")
        
        # 清理空目录
        for dir_name, _ in cleanup_types:
            dir_path = DIRECTORY_MAP.get(dir_name, dir_name)
            if os.path.exists(dir_path):
                try:
                    # 删除空的子目录
                    for root, dirs, files in os.walk(dir_path, topdown=False):
                        for d in dirs:
                            dir_path = os.path.join(root, d)
                            try:
                                if not os.listdir(dir_path):  # 如果目录为空
                                    os.rmdir(dir_path)
                                    self.cleanup_log.append(f"  🗂️ 删除空目录: {dir_path}")
                            except OSError:
                                pass
                except OSError:
                    pass
        
        total_size_mb = total_size / (1024 * 1024)
        self.cleanup_log.append(f"\n🎉 清理完成！总共删除了 {total_deleted} 个文件，释放了 {total_size_mb:.1f} MB 空间")
        
        # 清理完成后重新扫描
        self.scan_cleanup_files()
        
        QMessageBox.information(self, "清理完成", f"清理完成！\n\n删除文件: {total_deleted} 个\n释放空间: {total_size_mb:.1f} MB")
    
    def create_settings_tab(self):
        """创建设置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # API设置组
        api_group = QGroupBox("API设置")
        api_layout = QVBoxLayout(api_group)
        
        # OpenAI API设置
        openai_layout = QHBoxLayout()
        openai_label = QLabel("OpenAI API密钥:")
        self.openai_api_key_input = QLineEdit()
        self.openai_api_key_input.setPlaceholderText("输入OpenAI API密钥...")
        self.openai_api_key_input.setText(os.getenv("OPENAI_API_KEY", ""))
        openai_layout.addWidget(openai_label)
        openai_layout.addWidget(self.openai_api_key_input)
        api_layout.addLayout(openai_layout)
        
        # DeepSeek API设置
        deepseek_layout = QHBoxLayout()
        deepseek_label = QLabel("DeepSeek API密钥:")
        self.deepseek_api_key_input = QLineEdit()
        self.deepseek_api_key_input.setPlaceholderText("输入DeepSeek API密钥...")
        self.deepseek_api_key_input.setText(os.getenv("DEEPSEEK_API_KEY", ""))
        deepseek_layout.addWidget(deepseek_label)
        deepseek_layout.addWidget(self.deepseek_api_key_input)
        api_layout.addLayout(deepseek_layout)
        
        # 代理设置
        proxy_layout = QHBoxLayout()
        proxy_label = QLabel("代理服务器:")
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("例如: http://127.0.0.1:7890")
        self.proxy_input.setText(os.getenv("PROXY", ""))
        proxy_layout.addWidget(proxy_label)
        proxy_layout.addWidget(self.proxy_input)
        api_layout.addLayout(proxy_layout)

        # OpenAI 模型设置
        openai_model_layout = QHBoxLayout()
        openai_model_label = QLabel("OpenAI 模型名称:")
        self.openai_model_input = QLineEdit()
        self.openai_model_input.setPlaceholderText("例如: gpt-4, gpt-3.5-turbo")
        self.openai_model_input.setText(os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"))
        openai_model_layout.addWidget(openai_model_label)
        openai_model_layout.addWidget(self.openai_model_input)
        api_layout.addLayout(openai_model_layout)

        # OpenAI Base URL设置
        openai_base_url_layout = QHBoxLayout()
        openai_base_url_label = QLabel("OpenAI Base URL:")
        self.openai_base_url_input = QLineEdit()
        self.openai_base_url_input.setPlaceholderText("默认: https://api.openai.com/v1")
        self.openai_base_url_input.setText(os.getenv("OPENAI_BASE_URL", ""))
        openai_base_url_layout.addWidget(openai_base_url_label)
        openai_base_url_layout.addWidget(self.openai_base_url_input)
        api_layout.addLayout(openai_base_url_layout)

        # DeepSeek 模型设置
        deepseek_model_layout = QHBoxLayout()
        deepseek_model_label = QLabel("DeepSeek 模型名称:")
        self.deepseek_model_input = QLineEdit()
        self.deepseek_model_input.setPlaceholderText("默认: deepseek-chat")
        self.deepseek_model_input.setText(os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
        deepseek_model_layout.addWidget(deepseek_model_label)
        deepseek_model_layout.addWidget(self.deepseek_model_input)
        api_layout.addLayout(deepseek_model_layout)

        # DeepSeek Base URL设置
        deepseek_base_url_layout = QHBoxLayout()
        deepseek_base_url_label = QLabel("DeepSeek Base URL:")
        self.deepseek_base_url_input = QLineEdit()
        self.deepseek_base_url_input.setPlaceholderText("默认: https://api.deepseek.com")
        self.deepseek_base_url_input.setText(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
        deepseek_base_url_layout.addWidget(deepseek_base_url_label)
        deepseek_base_url_layout.addWidget(self.deepseek_base_url_input)
        api_layout.addLayout(deepseek_base_url_layout)

        # 翻译方式设置
        translate_method_layout = QHBoxLayout()
        translate_method_label = QLabel("字幕翻译方式:")
        self.translate_method_combo = QComboBox()
        self.translate_method_combo.addItems(["谷歌翻译", "大模型翻译"])
        # 从环境变量读取设置，默认为谷歌翻译
        current_method = os.getenv("TRANSLATION_METHOD", "google")
        if current_method == "llm":
            self.translate_method_combo.setCurrentText("大模型翻译")
        else:
            self.translate_method_combo.setCurrentText("谷歌翻译")
        translate_method_layout.addWidget(translate_method_label)
        translate_method_layout.addWidget(self.translate_method_combo)
        api_layout.addLayout(translate_method_layout)

        # 摘要生成设置组
        summary_group = QGroupBox("摘要生成设置")
        summary_layout = QVBoxLayout(summary_group)

        # 摘要生成模式选择
        summary_mode_layout = QHBoxLayout()
        summary_mode_label = QLabel("摘要生成模式:")
        self.summary_mode_combo = QComboBox()
        self.summary_mode_combo.addItems(["单模型生成", "两阶段生成（思考+生成）"])
        # 从环境变量读取设置，默认为单模型
        current_summary_mode = os.getenv("SUMMARY_GENERATION_MODE", "single")
        if current_summary_mode == "two_stage":
            self.summary_mode_combo.setCurrentText("两阶段生成（思考+生成）")
        else:
            self.summary_mode_combo.setCurrentText("单模型生成")
        summary_mode_layout.addWidget(summary_mode_label)
        summary_mode_layout.addWidget(self.summary_mode_combo)
        summary_layout.addLayout(summary_mode_layout)

        # 思考模型选择（第一步）
        thinking_model_layout = QHBoxLayout()
        thinking_model_label = QLabel("思考模型（第一步）:")
        self.thinking_model_combo = QComboBox()
        self.thinking_model_combo.addItems(["DeepSeek", "OpenAI"])
        thinking_model_layout.addWidget(thinking_model_label)
        thinking_model_layout.addWidget(self.thinking_model_combo)
        thinking_model_layout.addStretch()
        summary_layout.addLayout(thinking_model_layout)

        # 生成模型选择（第二步）
        output_model_layout = QHBoxLayout()
        output_model_label = QLabel("生成模型（第二步）:")
        self.output_model_combo = QComboBox()
        self.output_model_combo.addItems(["OpenAI", "DeepSeek"])
        output_model_layout.addWidget(output_model_label)
        output_model_layout.addWidget(self.output_model_combo)
        output_model_layout.addStretch()
        summary_layout.addLayout(output_model_layout)

        # 说明文字
        summary_info_label = QLabel(
            "💡 单模型模式：直接使用一个模型生成摘要\n"
            "💡 两阶段模式：第一步用思考模型分析内容，第二步用生成模型输出最终结果"
        )
        summary_info_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 5px;")
        summary_info_label.setWordWrap(True)
        summary_layout.addWidget(summary_info_label)

        # 模板设置
        template_group = QGroupBox("模板设置")
        template_layout = QVBoxLayout(template_group)
        
        # 模板选择
        template_select_layout = QHBoxLayout()
        template_label = QLabel("选择模板:")
        self.template_combo = QComboBox()
        self.refresh_templates()
        template_select_layout.addWidget(template_label)
        template_select_layout.addWidget(self.template_combo)
        template_layout.addLayout(template_select_layout)
        
        # 模板内容
        self.template_content = QTextEdit()
        template_layout.addWidget(self.template_content)
        
        # 模板按钮
        template_buttons_layout = QHBoxLayout()
        self.load_template_button = QPushButton("加载模板")
        self.save_template_button = QPushButton("保存模板")
        self.new_template_button = QPushButton("新建模板")
        template_buttons_layout.addWidget(self.load_template_button)
        template_buttons_layout.addWidget(self.save_template_button)
        template_buttons_layout.addWidget(self.new_template_button)
        template_layout.addLayout(template_buttons_layout)
        
        # 闲时设置组
        idle_group = QGroupBox("闲时执行设置")
        idle_layout = QVBoxLayout(idle_group)
        
        # 闲时时间设置
        idle_time_layout = QHBoxLayout()
        idle_start_label = QLabel("闲时开始时间:")
        self.idle_start_input = QLineEdit()
        self.idle_start_input.setText(self.idle_start_time)
        self.idle_start_input.setPlaceholderText("例如: 23:00")
        
        idle_end_label = QLabel("闲时结束时间:")
        self.idle_end_input = QLineEdit()
        self.idle_end_input.setText(self.idle_end_time)
        self.idle_end_input.setPlaceholderText("例如: 07:00")
        
        idle_time_layout.addWidget(idle_start_label)
        idle_time_layout.addWidget(self.idle_start_input)
        idle_time_layout.addWidget(idle_end_label)
        idle_time_layout.addWidget(self.idle_end_input)
        idle_layout.addLayout(idle_time_layout)
        
        # 任务队列管理
        queue_layout = QHBoxLayout()
        self.view_queue_button = QPushButton("查看任务队列")
        self.clear_queue_button = QPushButton("清空队列")
        queue_layout.addWidget(self.view_queue_button)
        queue_layout.addWidget(self.clear_queue_button)
        idle_layout.addLayout(queue_layout)
        
        # 添加到主布局
        layout.addWidget(api_group)
        layout.addWidget(summary_group)
        layout.addWidget(template_group)
        layout.addWidget(idle_group)
        
        # 保存设置按钮
        self.save_settings_button = QPushButton("保存设置")
        self.save_settings_button.setMinimumHeight(40)
        layout.addWidget(self.save_settings_button)
        
        # 连接信号和槽
        self.save_settings_button.clicked.connect(self.save_settings)
        self.load_template_button.clicked.connect(self.load_template)
        self.save_template_button.clicked.connect(self.save_template)
        self.new_template_button.clicked.connect(self.create_new_template)
        self.template_combo.currentIndexChanged.connect(self.template_selected)
        self.view_queue_button.clicked.connect(self.view_idle_queue)
        self.clear_queue_button.clicked.connect(self.clear_idle_queue)
        
        return tab

    def get_model_and_base_url(self):
        """获取配置的模型和Base URL"""
        # 确定使用哪个API的模型和base_url
        if self.translate_method_combo.currentText() == "大模型翻译":
            # 优先使用DeepSeek（如果配置了密钥），否则使用OpenAI
            deepseek_key = self.deepseek_api_key_input.text().strip()
            openai_key = self.openai_api_key_input.text().strip()

            if deepseek_key:
                model = self.deepseek_model_input.text() or "deepseek-chat"
                base_url = self.deepseek_base_url_input.text() or "https://api.deepseek.com"
            elif openai_key:
                model = self.openai_model_input.text() or "gpt-3.5-turbo"
                base_url = self.openai_base_url_input.text() if self.openai_base_url_input.text() else None
            else:
                model = None
                base_url = None
        else:
            model = None
            base_url = None

        return model, base_url

    def get_summary_generation_config(self):
        """获取摘要生成配置"""
        summary_mode = self.summary_mode_combo.currentText()
        thinking_model = self.thinking_model_combo.currentText()
        output_model = self.output_model_combo.currentText()

        return {
            "mode": "two_stage" if summary_mode == "两阶段生成（思考+生成）" else "single",
            "thinking_model": thinking_model,  # DeepSeek 或 OpenAI
            "output_model": output_model,       # OpenAI 或 DeepSeek
            "deepseek_key": self.deepseek_api_key_input.text().strip(),
            "openai_key": self.openai_api_key_input.text().strip(),
            "deepseek_model": self.deepseek_model_input.text() or "deepseek-chat",
            "openai_model": self.openai_model_input.text() or "gpt-3.5-turbo",
            "deepseek_base_url": self.deepseek_base_url_input.text() or "https://api.deepseek.com",
            "openai_base_url": self.openai_base_url_input.text() if self.openai_base_url_input.text() else None
        }

    def process_youtube(self):
        """处理YouTube视频"""
        # 获取输入框内容
        raw_url = self.youtube_url_input.text()
        
        # 如果输入框为空，尝试强制刷新UI并重新获取
        if not raw_url.strip():
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()  # 强制处理UI事件
            raw_url = self.youtube_url_input.text()
        
        youtube_url = raw_url.strip()
        
        if not youtube_url:
            QMessageBox.warning(
                self, 
                "输入错误", 
                "请输入视频链接（支持YouTube、Twitter、X、抖音等平台）\n\n提示：如果您已经输入了链接但仍看到此错误，请尝试：\n1. 重新粘贴链接\n2. 手动输入链接\n3. 检查链接是否完整"
            )
            # 将焦点设置回输入框
            self.youtube_url_input.setFocus()
            return
        
        # 清理URL中的空格和其他空白字符（常见于复制粘贴的抖音/YouTube链接）
        youtube_url = youtube_url.replace(' ', '').replace('\t', '').replace('\n', '').replace('\r', '')

        # 对YouTube视频链接进行规范化处理：
        # 如果是 watch?v=xxx&list=...&index=... 这类“列表中的单个视频”，
        # 自动提取真实的视频地址 https://www.youtube.com/watch?v=xxx
        normalized_url = normalize_youtube_video_url(youtube_url)
        if normalized_url != youtube_url:
            youtube_url = normalized_url
            # 在主线程中更新输入框，方便用户看到已经被清理过的真实视频地址
            self.youtube_url_input.setText(youtube_url)
        
        # 设置代理环境变量
        os.environ["PROXY"] = self.proxy_input.text()
        
        # 获取参数
        model, base_url = self.get_model_and_base_url()

        params = {
            "youtube_url": youtube_url,
            "model": model,  # 使用配置的模型
            "api_key": None,  # 使用环境变量中的API密钥
            "base_url": base_url,  # 使用配置的API基础URL
            "whisper_model_size": self.whisper_model_combo.currentText(),
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "download_video": self.download_video_checkbox.isChecked(),
            "custom_prompt": None,  # 使用默认提示词
            "template_path": None,  # 使用默认模板
            "generate_subtitles": self.generate_subtitles_checkbox.isChecked(),
            "translate_to_chinese": self.translate_checkbox.isChecked(),
            "embed_subtitles": self.embed_subtitles_checkbox.isChecked(),
            "cookies_file": self.cookies_path_input.text() if self.cookies_path_input.text() else None,
            "prefer_native_subtitles": self.prefer_native_subtitles_checkbox.isChecked(),
            "enable_transcription": self.enable_transcription_checkbox.isChecked(),
            "generate_article": self.generate_article_checkbox.isChecked(),
            "show_translation_logs": self.show_translation_logs_checkbox.isChecked(),
        }
        
        # 验证至少选择一个处理选项
        if not params["enable_transcription"] and not params["generate_article"] and not params["download_video"]:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：下载视频、执行转录或生成文章")
            return
        
        # 清空输出
        self.youtube_output_text.clear()
        
        # 禁用开始按钮，启用停止按钮
        self.youtube_process_button.setEnabled(False)
        self.youtube_process_button.setText("处理中...")
        self.youtube_stop_button.setEnabled(True)
        
        # 创建并启动工作线程
        self.worker_thread = WorkerThread("youtube", params)
        self.worker_thread.update_signal.connect(self.update_youtube_output)
        self.worker_thread.finished_signal.connect(self.on_youtube_finished)
        self.worker_thread.start()
    
    def update_youtube_output(self, text):
        """更新YouTube输出文本"""
        self.youtube_output_text.append(text)
        # 滚动到底部
        cursor = self.youtube_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.youtube_output_text.setTextCursor(cursor)
    
    def on_youtube_finished(self, result_path, success):
        """YouTube处理完成回调"""
        # 恢复按钮状态
        self.youtube_process_button.setEnabled(True)
        self.youtube_process_button.setText("开始处理")
        self.youtube_stop_button.setEnabled(False)
        
        if success:
            self.statusBar.showMessage(f"处理完成! 结果保存在: {result_path}")
            # 如果是文件路径，提供打开选项
            if os.path.exists(result_path):
                reply = QMessageBox.question(
                    self, "处理完成",
                    f"处理已完成，结果保存在:\n{result_path}\n\n是否打开该文件?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # 使用系统默认程序打开文件
                    QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
        else:
            # 显示具体的错误信息
            if result_path:  # result_path 现在可能包含错误消息
                self.statusBar.showMessage(f"处理失败: {result_path}")
                # 如果是抖音相关错误，显示详细提示
                if "抖音" in result_path:
                    QMessageBox.warning(self, "抖音视频处理失败", f"{result_path}\n\n详细错误信息请查看输出区域。")
            else:
                self.statusBar.showMessage("处理失败，请检查错误信息")
    
    def update_audio_output(self, text):
        """更新音频输出文本"""
        self.audio_output_text.append(text)
        # 滚动到底部
        cursor = self.audio_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.audio_output_text.setTextCursor(cursor)
    
    def on_audio_finished(self, result_path, success):
        """音频处理完成回调"""
        # 恢复按钮状态
        self.audio_process_button.setEnabled(True)
        self.audio_process_button.setText("开始处理")
        self.audio_stop_button.setEnabled(False)
        
        if success:
            self.statusBar.showMessage(f"处理完成! 结果保存在: {result_path}")
            # 如果是文件路径，提供打开选项
            if os.path.exists(result_path):
                reply = QMessageBox.question(
                    self, "处理完成",
                    f"处理已完成，结果保存在:\n{result_path}\n\n是否打开该文件?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # 使用系统默认程序打开文件
                    QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
        else:
            self.statusBar.showMessage("处理失败，请检查错误信息")
    
    def process_local_video(self):
        """处理本地视频文件"""
        video_path = self.video_path_input.text().strip()
        if not video_path or not os.path.exists(video_path):
            if self.video_single_mode_radio.isChecked():
                QMessageBox.warning(self, "输入错误", "请选择有效的本地视频文件")
            else:
                QMessageBox.warning(self, "输入错误", "请选择有效的包含视频文件的目录")
            return
        
        # 设置代理环境变量
        os.environ["PROXY"] = self.proxy_input.text()

        # 获取参数
        model, base_url = self.get_model_and_base_url()

        params = {
            "video_path": video_path,
            "model": model,  # 使用配置的模型
            "api_key": None,  # 使用环境变量中的API密钥
            "base_url": base_url,  # 使用配置的API基础URL
            "whisper_model_size": self.video_whisper_model_combo.currentText(),
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "custom_prompt": None,  # 使用默认提示词
            "template_path": None,  # 使用默认模板
            "generate_subtitles": self.video_generate_subtitles_checkbox.isChecked(),
            "translate_to_chinese": self.video_translate_checkbox.isChecked(),
            "embed_subtitles": self.video_embed_subtitles_checkbox.isChecked(),
            "enable_transcription": self.video_enable_transcription_checkbox.isChecked(),
            "generate_article": self.video_generate_article_checkbox.isChecked(),
            "source_language": self.video_source_language_combo.currentData()  # 获取选择的源语言代码
        }
        
        # 验证至少选择一个处理选项
        if not params["enable_transcription"] and not params["generate_article"]:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：执行转录或生成文章")
            return
        
        # 清空输出
        self.video_output_text.clear()
        
        # 禁用开始按钮，启用停止按钮
        self.video_process_button.setEnabled(False)
        self.video_process_button.setText("处理中...")
        self.video_stop_button.setEnabled(True)
        
        # 创建并启动工作线程
        task_type = "local_video_batch" if self.video_batch_mode_radio.isChecked() else "local_video"
        self.worker_thread = WorkerThread(task_type, params)
        self.worker_thread.update_signal.connect(self.update_video_output)
        self.worker_thread.finished_signal.connect(self.on_video_finished)
        self.worker_thread.start()
    
    def update_video_output(self, text):
        """更新视频输出文本"""
        self.video_output_text.append(text)
        # 滚动到底部
        cursor = self.video_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.video_output_text.setTextCursor(cursor)
    
    def on_video_finished(self, result_path, success):
        """视频处理完成回调"""
        # 恢复按钮状态
        self.video_process_button.setEnabled(True)
        self.video_process_button.setText("开始处理")
        self.video_stop_button.setEnabled(False)
        
        if success:
            # 检查是否为批量处理模式
            is_batch_mode = hasattr(self, 'video_batch_mode_radio') and self.video_batch_mode_radio.isChecked()
            
            if is_batch_mode:
                # 批量处理完成
                if result_path and os.path.exists(result_path):
                    # 有具体的结果文件
                    self.statusBar.showMessage(f"批量处理完成! 示例结果: {os.path.basename(result_path)}")
                    reply = QMessageBox.information(
                        self, "批量处理完成",
                        f"批量处理已完成!\n\n查看处理日志了解详细结果。\n\n是否打开其中一个结果文件?\n{result_path}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
                else:
                    # 批量处理完成但没有具体文件路径
                    self.statusBar.showMessage("批量处理完成! 请查看处理日志了解详细结果")
                    QMessageBox.information(
                        self, "批量处理完成", 
                        "批量处理已完成!\n\n请查看上方的处理日志了解每个文件的处理结果。"
                    )
            else:
                # 单文件处理完成
                if result_path and os.path.exists(result_path):
                    self.statusBar.showMessage(f"处理完成! 结果保存在: {result_path}")
                    reply = QMessageBox.question(
                        self, "处理完成",
                        f"处理已完成，结果保存在:\n{result_path}\n\n是否打开该文件?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
                else:
                    # 处理成功但没有结果文件（可能只是转录跳过）
                    self.statusBar.showMessage("处理完成!")
                    QMessageBox.information(self, "处理完成", "处理已完成! 请查看处理日志了解详细信息。")
        else:
            self.statusBar.showMessage("处理失败，请检查错误信息")
            QMessageBox.warning(self, "处理失败", "处理过程中出现错误，请查看处理日志了解详细错误信息。")
    
    def process_local_audio(self):
        """处理本地音频文件"""
        audio_path = self.audio_path_input.text().strip()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "输入错误", "请选择有效的本地音频文件")
            return

        # 设置代理环境变量
        os.environ["PROXY"] = self.proxy_input.text()

        # 获取参数
        model, base_url = self.get_model_and_base_url()

        params = {
            "audio_path": audio_path,
            "model": model,  # 使用配置的模型
            "api_key": None,  # 使用环境变量中的API密钥
            "base_url": base_url,  # 使用配置的API基础URL
            "whisper_model_size": self.audio_whisper_model_combo.currentText(),
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "custom_prompt": None,  # 使用默认提示词
            "template_path": None,  # 使用默认模板
            "generate_subtitles": self.audio_generate_subtitles_checkbox.isChecked(),
            "translate_to_chinese": self.audio_translate_checkbox.isChecked(),
            "enable_transcription": self.audio_enable_transcription_checkbox.isChecked(),
            "generate_article": self.audio_generate_article_checkbox.isChecked()
        }
        
        # 验证至少选择一个处理选项
        if not params["enable_transcription"] and not params["generate_article"]:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：执行转录或生成文章")
            return
        
        # 清空输出
        self.audio_output_text.clear()
        
        # 禁用开始按钮，启用停止按钮
        self.audio_process_button.setEnabled(False)
        self.audio_process_button.setText("处理中...")
        self.audio_stop_button.setEnabled(True)
        
        # 创建并启动工作线程
        self.worker_thread = WorkerThread("local_audio", params)
        self.worker_thread.update_signal.connect(self.update_audio_output)
        self.worker_thread.finished_signal.connect(self.on_audio_finished)
        self.worker_thread.start()
    
    def update_audio_output(self, text):
        """更新音频输出文本"""
        self.audio_output_text.append(text)
        # 滚动到底部
        cursor = self.audio_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.audio_output_text.setTextCursor(cursor)
    
    def on_audio_finished(self, result_path, success):
        """音频处理完成回调"""
        # 恢复按钮状态
        self.audio_process_button.setEnabled(True)
        self.audio_process_button.setText("开始处理")
        self.audio_stop_button.setEnabled(False)
        
        if success:
            self.statusBar.showMessage(f"处理完成! 结果保存在: {result_path}")
            # 如果是文件路径，提供打开选项
            if os.path.exists(result_path):
                reply = QMessageBox.question(
                    self, "处理完成",
                    f"处理已完成，结果保存在:\n{result_path}\n\n是否打开该文件?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # 使用系统默认程序打开文件
                    QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
        else:
            self.statusBar.showMessage("处理失败，请检查错误信息")
    
    def process_local_text(self):
        """处理本地文本文件"""
        text_path = self.text_path_input.text().strip()
        if not text_path or not os.path.exists(text_path):
            QMessageBox.warning(self, "输入错误", "请选择有效的本地文本文件")
            return

        # 获取参数
        model, base_url = self.get_model_and_base_url()

        params = {
            "text_path": text_path,
            "model": model,  # 使用配置的模型
            "api_key": None,  # 使用环境变量中的API密钥
            "base_url": base_url,  # 使用配置的API基础URL
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "custom_prompt": None,  # 使用默认提示词
            "template_path": None,  # 使用默认模板
        }
        
        # 清空输出
        self.text_output_text.clear()
        
        # 禁用开始按钮，启用停止按钮
        self.text_process_button.setEnabled(False)
        self.text_process_button.setText("处理中...")
        self.text_stop_button.setEnabled(True)
        
        # 创建并启动工作线程
        self.worker_thread = WorkerThread("local_text", params)
        self.worker_thread.update_signal.connect(self.update_text_output)
        self.worker_thread.finished_signal.connect(self.on_text_finished)
        self.worker_thread.start()
    
    def update_text_output(self, text):
        """更新文本输出"""
        self.text_output_text.append(text)
        # 滚动到底部
        cursor = self.text_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_output_text.setTextCursor(cursor)
    
    def on_text_finished(self, result_path, success):
        """文本处理完成回调"""
        # 恢复按钮状态
        self.text_process_button.setEnabled(True)
        self.text_process_button.setText("开始处理")
        self.text_stop_button.setEnabled(False)
        
        if success:
            self.statusBar.showMessage(f"处理完成! 结果保存在: {result_path}")
            # 如果是文件路径，提供打开选项
            if os.path.exists(result_path):
                reply = QMessageBox.question(
                    self, "处理完成",
                    f"处理已完成，结果保存在:\n{result_path}\n\n是否打开该文件?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # 使用系统默认程序打开文件
                    QDesktopServices.openUrl(QUrl.fromLocalFile(result_path))
        else:
            self.statusBar.showMessage("处理失败，请检查错误信息")
    
    def process_batch(self):
        """批量处理YouTube视频"""
        # 获取URL列表
        urls = []
        
        # 从文本框获取URL
        if self.batch_urls_text.toPlainText().strip():
            urls = [url.strip() for url in self.batch_urls_text.toPlainText().strip().split('\n') if url.strip()]
        
        # 从文件获取URL
        if self.batch_file_input.text().strip() and os.path.exists(self.batch_file_input.text().strip()):
            try:
                with open(self.batch_file_input.text().strip(), 'r', encoding='utf-8') as f:
                    file_urls = [url.strip() for url in f if url.strip() and not url.strip().startswith('#')]
                    urls.extend(file_urls)
            except Exception as e:
                QMessageBox.warning(self, "文件读取错误", f"读取URL文件时出错: {str(e)}")
                return
        
        # 检查是否有URL
        if not urls:
            QMessageBox.warning(self, "输入错误", "请输入至少一个YouTube视频链接")
            return
        
        # 设置代理环境变量
        os.environ["PROXY"] = self.proxy_input.text()

        # 获取参数
        model, base_url = self.get_model_and_base_url()

        params = {
            "youtube_urls": urls,
            "model": model,  # 使用配置的模型
            "api_key": None,  # 使用环境变量中的API密钥
            "base_url": base_url,  # 使用配置的API基础URL
            "whisper_model_size": self.batch_whisper_model_combo.currentText(),
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "download_video": self.batch_download_video_checkbox.isChecked(),
            "custom_prompt": None,  # 使用默认提示词
            "template_path": None,  # 使用默认模板
            "generate_subtitles": self.batch_generate_subtitles_checkbox.isChecked(),
            "translate_to_chinese": self.batch_translate_checkbox.isChecked(),
            "embed_subtitles": self.batch_embed_subtitles_checkbox.isChecked(),
            "cookies_file": self.batch_cookies_path_input.text() if self.batch_cookies_path_input.text() else None,
            "prefer_native_subtitles": self.batch_prefer_native_subtitles_checkbox.isChecked(),
            "enable_transcription": self.batch_enable_transcription_checkbox.isChecked(),
            "generate_article": self.batch_generate_article_checkbox.isChecked()
        }
        
        # 验证至少选择一个处理选项
        if not params["enable_transcription"] and not params["generate_article"] and not params["download_video"]:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：下载视频、执行转录或生成文章")
            return
        
        # 清空输出
        self.batch_output_text.clear()
        
        # 禁用开始按钮，启用停止按钮
        self.batch_process_button.setEnabled(False)
        self.batch_process_button.setText("处理中...")
        self.batch_stop_button.setEnabled(True)
        
        # 创建并启动工作线程
        self.worker_thread = WorkerThread("batch", params)
        self.worker_thread.update_signal.connect(self.update_batch_output)
        self.worker_thread.finished_signal.connect(self.on_batch_finished)
        self.worker_thread.start()
    
    def update_batch_output(self, text):
        """更新批量处理输出文本"""
        self.batch_output_text.append(text)
        # 滚动到底部
        cursor = self.batch_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.batch_output_text.setTextCursor(cursor)
    
    def on_batch_finished(self, result, success):
        """批量处理完成回调"""
        # 恢复按钮状态
        self.batch_process_button.setEnabled(True)
        self.batch_process_button.setText("开始批量处理")
        self.batch_stop_button.setEnabled(False)
        
        if success:
            self.statusBar.showMessage("批量处理完成!")
        else:
            self.statusBar.showMessage("批量处理失败，请检查错误信息")
    
    def refresh_history(self):
        """刷新下载历史"""
        self.history_list.clear()
        
        videos = list_downloaded_videos()
        if not videos:
            self.history_list.addItem("没有找到下载历史记录")
            return
        
        for i, video in enumerate(videos, 1):
            title = video.get("title", "未知标题")
            url = video.get("url", "未知URL")
            last_time = video.get("last_download_time", "未知时间")
            file_path = video.get("file_path", "未知路径")
            
            item_text = f"{i}. {title}\n   URL: {url}\n   最后下载时间: {last_time}\n   文件路径: {file_path}"
            item = QListWidgetItem(item_text)
            self.history_list.addItem(item)
    
    def refresh_templates(self):
        """刷新模板列表"""
        self.template_combo.clear()
        
        templates = list_templates()
        if templates:
            self.template_combo.addItems(templates)
    
    def template_selected(self, index):
        """模板选择改变时的回调"""
        if index >= 0:
            template_name = self.template_combo.currentText()
            template_path = os.path.join(TEMPLATES_DIR, template_name)
            
            if os.path.exists(template_path):
                try:
                    with open(template_path, "r", encoding="utf-8") as f:
                        self.template_content.setText(f.read())
                except Exception as e:
                    QMessageBox.warning(self, "模板读取错误", f"读取模板时出错: {str(e)}")
    
    def load_template(self):
        """加载模板"""
        template_name = self.template_combo.currentText()
        if not template_name:
            QMessageBox.warning(self, "模板错误", "请选择一个模板")
            return
        
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        
        if os.path.exists(template_path):
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    self.template_content.setText(f.read())
                QMessageBox.information(self, "模板加载", f"模板 '{template_name}' 已加载")
            except Exception as e:
                QMessageBox.warning(self, "模板读取错误", f"读取模板时出错: {str(e)}")
    
    def save_template(self):
        """保存模板"""
        template_name = self.template_combo.currentText()
        if not template_name:
            QMessageBox.warning(self, "模板错误", "请选择一个模板")
            return
        
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        template_content = self.template_content.toPlainText()
        
        try:
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(template_content)
            QMessageBox.information(self, "模板保存", f"模板 '{template_name}' 已保存")
        except Exception as e:
            QMessageBox.warning(self, "模板保存错误", f"保存模板时出错: {str(e)}")
    
    def create_new_template(self):
        """创建新模板"""
        template_name, ok = QInputDialog.getText(self, "新建模板", "请输入模板名称:")
        
        if ok and template_name:
            if not template_name.endswith('.txt'):
                template_name = f"{template_name}.txt"
            
            template_path = os.path.join(TEMPLATES_DIR, template_name)
            
            if os.path.exists(template_path):
                reply = QMessageBox.question(
                    self, "模板已存在",
                    f"模板 '{template_name}' 已存在，是否覆盖?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            try:
                with open(template_path, "w", encoding="utf-8") as f:
                    f.write(DEFAULT_TEMPLATE)
                
                self.refresh_templates()
                index = self.template_combo.findText(template_name)
                if index >= 0:
                    self.template_combo.setCurrentIndex(index)
                
                self.template_content.setText(DEFAULT_TEMPLATE)
                
                QMessageBox.information(self, "新建模板", f"模板 '{template_name}' 已创建")
            except Exception as e:
                QMessageBox.warning(self, "模板创建错误", f"创建模板时出错: {str(e)}")
    
    def _removed_check_deno(self):
        """检查 Deno 是否已安装"""
        try:
            self.deno_status_text.setText("检查中...")
            self.check_deno_button.setEnabled(False)
            
            # 检查 Deno 版本
            result = subprocess.run(['deno', '--version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            if result.returncode == 0:
                # 提取版本号
                version_output = result.stdout.strip()
                version_line = version_output.split('\n')[0] if version_output else "Deno"
                
                self.deno_status_text.setText(f"✅ 已安装 ({version_line})")
                self.deno_status_text.setStyleSheet("color: #4CAF50;")
                self.install_deno_button.setEnabled(False)
                self.install_deno_button.setText("Deno 已安装")
                
                # 启用服务管理按钮
                self.start_deno_service_button.setEnabled(True)
                self.stop_deno_service_button.setEnabled(True)
                
                # 检查服务状态
                self._check_deno_service_status()
            else:
                self._deno_not_found()
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            self._deno_not_found()
        except FileNotFoundError:
            self._deno_not_found()
        except Exception as e:
            self.deno_status_text.setText(f"❌ 检查失败: {str(e)}")
            self.deno_status_text.setStyleSheet("color: #F44336;")
            self.install_deno_button.setEnabled(True)
        finally:
            self.check_deno_button.setEnabled(True)
    
    def _removed_deno_not_found(self):
        """Deno 未找到时的处理"""
        self.deno_status_text.setText("❌ 未安装")
        self.deno_status_text.setStyleSheet("color: #F44336;")
        self.install_deno_button.setEnabled(True)
        self.install_deno_button.setText("安装 Deno")
        
        # 禁用服务管理按钮
        self.start_deno_service_button.setEnabled(False)
        self.stop_deno_service_button.setEnabled(False)
        self.deno_service_status.setText("Deno 未安装")
        self.deno_service_status.setStyleSheet("color: #666;")
    
    def _removed_install_deno(self):
        """安装 Deno"""
        try:
            self.install_deno_button.setEnabled(False)
            self.install_deno_button.setText("安装中...")
            self.deno_status_text.setText("正在下载并安装 Deno...")
            self.deno_status_text.setStyleSheet("color: #FF9800;")
            
            # 检查操作系统
            if os.name == 'nt':  # Windows
                # 使用 PowerShell 安装 Deno
                install_cmd = [
                    'powershell', '-Command',
                    'irm https://deno.land/install.ps1 | iex'
                ]
            else:  # macOS/Linux
                install_cmd = [
                    'sh', '-c',
                    'curl -fsSL https://deno.land/install.sh | sh'
                ]
            
            # 在新线程中执行安装以避免阻塞UI
            import threading
            threading.Thread(target=self._install_deno_worker, args=(install_cmd,), daemon=True).start()
            
        except Exception as e:
            self.deno_status_text.setText(f"❌ 安装失败: {str(e)}")
            self.deno_status_text.setStyleSheet("color: #F44336;")
            self.install_deno_button.setEnabled(True)
            self.install_deno_button.setText("重试安装")
    
    def _removed_install_deno_worker(self, install_cmd):
        """在后台线程中执行 Deno 安装"""
        try:
            # 执行安装命令
            result = subprocess.run(install_cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=300,  # 5分钟超时
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            # 在主线程中更新UI
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._handle_install_result(result))
            
        except subprocess.TimeoutExpired:
            QTimer.singleShot(0, lambda: self._handle_install_timeout())
        except Exception as e:
            QTimer.singleShot(0, lambda: self._handle_install_error(str(e)))
    
    def _removed_handle_install_result(self, result):
        """处理安装结果"""
        if result.returncode == 0:
            self.deno_status_text.setText("✅ 安装成功！请重启应用程序以使用 Deno")
            self.deno_status_text.setStyleSheet("color: #4CAF50;")
            self.install_deno_button.setText("安装完成")
            
            # 显示成功对话框
            QMessageBox.information(
                self, 
                "安装成功", 
                "Deno 已成功安装！\n\n请重启应用程序以确保 PATH 环境变量更新。\n如需立即验证，可点击'检查 Deno'按钮。"
            )
            
        else:
            error_msg = result.stderr if result.stderr else "未知错误"
            self.deno_status_text.setText(f"❌ 安装失败")
            self.deno_status_text.setStyleSheet("color: #F44336;")
            self.install_deno_button.setText("重试安装")
            self.install_deno_button.setEnabled(True)
            
            # 显示详细错误
            QMessageBox.warning(
                self, 
                "安装失败", 
                f"Deno 安装失败，请检查网络连接或手动安装。\n\n错误信息：\n{error_msg}\n\n手动安装方法：\n访问 https://deno.land/manual/getting_started/installation"
            )
    
    def _removed_handle_install_timeout(self):
        """处理安装超时"""
        self.deno_status_text.setText("❌ 安装超时")
        self.deno_status_text.setStyleSheet("color: #F44336;")
        self.install_deno_button.setText("重试安装")
        self.install_deno_button.setEnabled(True)
        
        QMessageBox.warning(
            self, 
            "安装超时", 
            "Deno 安装超时，请检查网络连接后重试，或手动安装。\n\n手动安装方法：\n访问 https://deno.land/manual/getting_started/installation"
        )
    
    def _removed_handle_install_error(self, error_msg):
        """处理安装错误"""
        self.deno_status_text.setText(f"❌ 安装失败")
        self.deno_status_text.setStyleSheet("color: #F44336;")
        self.install_deno_button.setText("重试安装")
        self.install_deno_button.setEnabled(True)
        
        QMessageBox.warning(
            self, 
            "安装错误", 
            f"Deno 安装过程中发生错误：\n{error_msg}\n\n请尝试手动安装：\n访问 https://deno.land/manual/getting_started/installation"
        )
    
    def _removed_check_deno_service_status(self):
        """检查 Deno 服务状态"""
        if self.deno_service_process and self.deno_service_process.poll() is None:
            # 服务正在运行
            self.deno_service_status.setText("✅ 运行中")
            self.deno_service_status.setStyleSheet("color: #4CAF50;")
            self.start_deno_service_button.setEnabled(False)
            self.stop_deno_service_button.setEnabled(True)
        else:
            # 服务未运行
            self.deno_service_status.setText("❌ 未启动")
            self.deno_service_status.setStyleSheet("color: #666;")
            self.start_deno_service_button.setEnabled(True)
            self.stop_deno_service_button.setEnabled(False)
    
    def _removed_start_deno_service(self):
        """启动 douyinVd Deno 后台服务"""
        try:
            if self.deno_service_process and self.deno_service_process.poll() is None:
                QMessageBox.information(self, "服务状态", "douyinVd 服务已在运行中")
                return
            
            port = self.deno_port_input.text().strip() or "8080"
            
            # 检查 douyinVd 目录和 main.ts 文件
            douyinvd_dir = os.path.join(os.path.dirname(__file__), "douyinVd")
            main_ts_path = os.path.join(douyinvd_dir, "main.ts")
            
            if not os.path.exists(douyinvd_dir):
                QMessageBox.warning(self, "目录不存在", f"douyinVd 目录不存在：\n{douyinvd_dir}")
                return
                
            if not os.path.exists(main_ts_path):
                QMessageBox.warning(self, "文件不存在", f"main.ts 文件不存在：\n{main_ts_path}")
                return
            
            # 设置环境变量来配置端口
            env = os.environ.copy()
            env['PORT'] = port
            
            # 启动 douyinVd 服务，使用 --port= 参数指定端口
            self.deno_service_process = subprocess.Popen(
                ['deno', 'run', '--allow-net', '--allow-read', f'--port={port}', 'main.ts'],
                cwd=douyinvd_dir,  # 在 douyinVd 目录中运行
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,  # 传递环境变量
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 保存端口信息供后续使用
            self.deno_service_port = port
            
            # 更新状态
            self.deno_service_status.setText("🟡 启动中...")
            self.deno_service_status.setStyleSheet("color: #FF9800;")
            self.start_deno_service_button.setEnabled(False)
            
            # 延迟检查服务状态
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, self._check_deno_service_status)
            
            QMessageBox.information(
                self, 
                "douyinVd 服务启动", 
                f"douyinVd 服务正在启动...\n端口: {port}\n\n"
                f"服务地址: http://localhost:{port}\n"
                f"获取视频URL: http://localhost:{port}?url=<douyin_url>\n"
                f"获取视频信息: http://localhost:{port}?url=<douyin_url>&data=1"
            )
            
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法启动 douyinVd 服务：\n{str(e)}")
            self._check_deno_service_status()
    
    def _removed_stop_deno_service(self):
        """停止 Deno 后台服务"""
        try:
            if self.deno_service_process:
                self.deno_service_process.terminate()
                
                # 等待进程终止
                try:
                    self.deno_service_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.deno_service_process.kill()
                
                self.deno_service_process = None
            
            # 更新状态
            self._check_deno_service_status()
            QMessageBox.information(self, "服务停止", "Deno 后台服务已停止")
            
        except Exception as e:
            QMessageBox.warning(self, "停止失败", f"停止 Deno 服务时出错：\n{str(e)}")
    
    def closeEvent(self, event):
        """应用程序关闭时清理"""
        super().closeEvent(event)
    
    def save_settings(self):
        """保存设置"""
        # 保存API密钥到环境变量
        os.environ["OPENAI_API_KEY"] = self.openai_api_key_input.text()
        os.environ["DEEPSEEK_API_KEY"] = self.deepseek_api_key_input.text()
        os.environ["OPENAI_MODEL"] = self.openai_model_input.text()
        os.environ["OPENAI_BASE_URL"] = self.openai_base_url_input.text()
        os.environ["DEEPSEEK_MODEL"] = self.deepseek_model_input.text()
        os.environ["DEEPSEEK_BASE_URL"] = self.deepseek_base_url_input.text()

        # 保存翻译方式设置
        translation_method = "llm" if self.translate_method_combo.currentText() == "大模型翻译" else "google"
        os.environ["TRANSLATION_METHOD"] = translation_method

        # 保存摘要生成设置
        summary_mode = "two_stage" if self.summary_mode_combo.currentText() == "两阶段生成（思考+生成）" else "single"
        os.environ["SUMMARY_GENERATION_MODE"] = summary_mode
        os.environ["THINKING_MODEL"] = self.thinking_model_combo.currentText()
        os.environ["OUTPUT_MODEL"] = self.output_model_combo.currentText()

        # 保存闲时设置
        self.idle_start_time = self.idle_start_input.text()
        self.idle_end_time = self.idle_end_input.text()

        # 更新.env文件
        try:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

            # 读取现有.env文件，同时记录键值对和结构
            env_vars = {}
            env_lines = []  # 保持原文件的行结构

            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if line.startswith("#") or line.strip() == "":
                            # 保留注释和空行
                            env_lines.append(("comment", line))
                        elif "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key] = value
                            env_lines.append(("key", key))

            # 更新API密钥、模型名称、Base URL、翻译方式和摘要生成设置
            new_keys = {
                "OPENAI_API_KEY": self.openai_api_key_input.text(),
                "DEEPSEEK_API_KEY": self.deepseek_api_key_input.text(),
                "OPENAI_MODEL": self.openai_model_input.text(),
                "OPENAI_BASE_URL": self.openai_base_url_input.text(),
                "DEEPSEEK_MODEL": self.deepseek_model_input.text(),
                "DEEPSEEK_BASE_URL": self.deepseek_base_url_input.text(),
                "PROXY": self.proxy_input.text(),
                "TRANSLATION_METHOD": translation_method,
                "SUMMARY_GENERATION_MODE": summary_mode,
                "THINKING_MODEL": self.thinking_model_combo.currentText(),
                "OUTPUT_MODEL": self.output_model_combo.currentText()
            }

            # 更新env_vars字典
            env_vars.update(new_keys)

            # 写入.env文件，同时保留注释和原有结构
            with open(env_path, "w", encoding="utf-8") as f:
                # 先写入原文件中存在的键值对（保留顺序和注释）
                for item_type, item_value in env_lines:
                    if item_type == "comment":
                        f.write(f"{item_value}\n")
                    elif item_type == "key":
                        f.write(f"{item_value}={env_vars[item_value]}\n")

                # 再写入新添加的键（不在原文件中的键）
                existing_keys = {item_value for item_type, item_value in env_lines if item_type == "key"}
                for key, value in new_keys.items():
                    if key not in existing_keys:
                        f.write(f"{key}={value}\n")

            # 验证文件写入成功（读取一次确保文件存在且可读）
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    saved_content = f.read()
                    saved_lines = len(saved_content.strip().split("\n"))

                print(f"✅ 配置文件已保存: {env_path}")
                print(f"   - 文件大小: {len(saved_content)} 字节")
                print(f"   - 配置项数: {saved_lines}")
                print(f"   - OpenAI API Key: {'已配置' if env_vars.get('OPENAI_API_KEY') else '未配置'}")
                print(f"   - DeepSeek API Key: {'已配置' if env_vars.get('DEEPSEEK_API_KEY') else '未配置'}")
                print(f"   - OpenAI Base URL: {env_vars.get('OPENAI_BASE_URL', '(默认)')}")
                print(f"   - DeepSeek Base URL: {env_vars.get('DEEPSEEK_BASE_URL', '(默认)')}")

                # 重新加载环境变量，确保应用内存中的值也更新了
                from dotenv import load_dotenv
                load_dotenv(env_path, override=True)
                print(f"✅ 环境变量已重新加载")

                QMessageBox.information(self, "设置保存", f"✅ 设置已保存\n\n配置文件: {env_path}\n配置项数: {saved_lines}")
            else:
                QMessageBox.warning(self, "保存失败", "配置文件保存失败，请检查文件权限")

        except Exception as e:
            print(f"❌ 保存配置文件时出错: {str(e)}")
            print(f"   路径: {env_path}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "设置保存错误", f"保存设置时出错: {str(e)}\n\n请检查文件权限和磁盘空间")
    
    def browse_cookies_file(self):
        """浏览cookies文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Cookies文件", "", "Cookies文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            self.cookies_path_input.setText(file_path)
    
    def show_cookies_help(self):
        """显示Cookies获取帮助"""
        help_text = """🍪 YouTube Cookies获取详细教程

📌 为什么需要Cookies?
YouTube现在经常要求验证"您不是机器人"，使用Cookies文件可以绕过这个限制。

📥 方法一: 使用浏览器插件 (推荐)

🔵 Chrome用户:
1. 打开Chrome应用商店
2. 搜索"Get cookies.txt LOCALLY"插件
3. 安装后，访问youtube.com并登录
4. 点击插件图标，选择"Export cookies"
5. 保存为cookies.txt文件

🦊 Firefox用户:
1. 打开Firefox附加组件
2. 搜索"cookies.txt"插件
3. 安装后，访问youtube.com并登录
4. 点击插件，导出cookies.txt文件

📥 方法二: 使用yt-dlp命令行
在命令行中运行:
yt-dlp --cookies-from-browser chrome --write-info-json --skip-download [视频URL]

📂 Cookies文件格式:
文件应该是 .txt 格式，包含YouTube的认证信息。

⚠️ 安全提醒:
• 不要分享您的cookies文件
• 定期更新cookies文件
• cookies文件包含您的登录信息，请妥善保管

💡 使用提示:
• 有了cookies文件，可以访问需要登录的内容
• 提高视频信息获取的成功率
• 避免"机器人验证"错误

🔗 更多信息:
https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"""
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Cookies获取教程")
        dialog.setMinimumSize(600, 500)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(help_text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec()
    
    def auto_get_cookies(self):
        """自动从浏览器获取Cookies"""
        # 显示进度对话框
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("自动获取Cookies")
        progress_dialog.setMinimumSize(400, 200)
        progress_dialog.setModal(True)
        
        layout = QVBoxLayout(progress_dialog)
        
        progress_label = QLabel("正在尝试从浏览器获取Cookies...")
        layout.addWidget(progress_label)
        
        progress_text = QTextEdit()
        progress_text.setReadOnly(True)
        progress_text.setMaximumHeight(120)
        layout.addWidget(progress_text)
        
        button_box = QDialogButtonBox()
        close_button = button_box.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(progress_dialog.reject)
        layout.addWidget(button_box)
        
        # 非阻塞显示对话框
        progress_dialog.show()
        QApplication.processEvents()
        
        try:
            # 导入必要的函数
            from youtube_transcriber import auto_extract_cookies_from_browsers
            
            # 重定向print输出到对话框
            original_print = print
            def custom_print(*args, **kwargs):
                text = " ".join(map(str, args))
                progress_text.append(text)
                QApplication.processEvents()
                original_print(*args, **kwargs)
            
            import builtins
            builtins.print = custom_print
            
            try:
                # 尝试自动获取cookies
                progress_label.setText("🔍 正在检测浏览器...")
                QApplication.processEvents()
                
                cookies_path, browser_name = auto_extract_cookies_from_browsers()
                
                if cookies_path:
                    # 成功获取cookies
                    progress_label.setText(f"✅ 成功从 {browser_name} 获取Cookies!")
                    self.cookies_path_input.setText(cookies_path)
                    
                    # 显示成功消息
                    success_msg = f"🎉 成功设置Cookies!\n\n"
                    if cookies_path.startswith("browser:"):
                        success_msg += f"将直接使用 {browser_name} 浏览器的登录状态\n"
                        success_msg += "无需手动导出cookies文件"
                    else:
                        success_msg += f"Cookies已保存到: {cookies_path}"
                    
                    progress_text.append(f"\n{success_msg}")
                    
                else:
                    # 获取失败
                    progress_label.setText("❌ 自动获取失败")
                    error_msg = "\n💡 自动获取失败的可能原因:\n"
                    error_msg += "• 没有浏览器登录YouTube账户\n"
                    error_msg += "• 浏览器正在运行（请关闭浏览器后重试）\n" 
                    error_msg += "• 浏览器权限问题\n\n"
                    error_msg += "🔧 建议解决方案:\n"
                    error_msg += "1. 关闭所有浏览器窗口后重试\n"
                    error_msg += "2. 确保至少一个浏览器已登录YouTube\n"
                    error_msg += "3. 或点击帮助按钮查看手动获取教程"
                    
                    progress_text.append(error_msg)
                    
            finally:
                # 恢复原始print函数
                builtins.print = original_print
                
        except Exception as e:
            progress_label.setText("❌ 获取过程中出错")
            progress_text.append(f"\n错误信息: {str(e)}")
            progress_text.append(f"\n请尝试手动获取Cookies文件")
    
    def browse_batch_cookies_file(self):
        """浏览批量处理cookies文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Cookies文件", "", "Cookies文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            self.batch_cookies_path_input.setText(file_path)
    
    def browse_audio_file(self):
        """浏览音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", "音频文件 (*.mp3 *.wav *.m4a *.aac);;所有文件 (*.*)"
        )
        if file_path:
            self.audio_path_input.setText(file_path)
    
    def browse_video_file(self):
        """浏览视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mkv *.mov);;所有文件 (*.*)"
        )
        if file_path:
            self.video_path_input.setText(file_path)
    
    def browse_video_path(self):
        """浏览视频文件或目录（根据选择的模式）"""
        if self.video_single_mode_radio.isChecked():
            # 单个文件模式
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择视频文件", "", 
                "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.3gp *.mpg *.mpeg);;所有文件 (*.*)"
            )
            if file_path:
                self.video_path_input.setText(file_path)
        else:
            # 目录模式
            dir_path = QFileDialog.getExistingDirectory(
                self, "选择包含视频文件的目录"
            )
            if dir_path:
                self.video_path_input.setText(dir_path)
    
    def on_video_mode_changed(self):
        """当视频处理模式改变时更新UI"""
        if self.video_single_mode_radio.isChecked():
            self.video_path_label.setText("视频文件:")
            self.video_path_input.setPlaceholderText("选择本地视频文件...")
        else:
            self.video_path_label.setText("视频目录:")
            self.video_path_input.setPlaceholderText("选择包含视频文件的目录...")
        
        # 清空当前路径
        self.video_path_input.clear()
    
    def browse_text_file(self):
        """浏览文本文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文本文件", "", "文本文件 (*.txt *.md);;所有文件 (*.*)"
        )
        if file_path:
            self.text_path_input.setText(file_path)
    
    def browse_batch_file(self):
        """浏览批量处理文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择URL文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            self.batch_file_input.setText(file_path)
    
    def stop_current_task(self):
        """停止当前正在执行的任务"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认中断",
                "确定要中断当前操作吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.worker_thread.stop()
                self.statusBar.showMessage("用户中断了当前操作")
        else:
            QMessageBox.information(self, "提示", "当前没有正在运行的任务")
    
    def add_youtube_to_idle_queue(self):
        """将YouTube处理任务添加到闲时队列"""
        print("DEBUG: add_youtube_to_idle_queue 函数被调用")
        
        def restore_button_state():
            """恢复按钮状态的辅助函数"""
            try:
                self.youtube_idle_button.setEnabled(True)
                self.youtube_idle_button.setText("闲时操作")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                print("DEBUG: 按钮状态已恢复")
            except Exception as e:
                print(f"DEBUG: 恢复按钮状态时出错: {e}")
        
        # 设置按钮状态为处理中
        try:
            self.youtube_idle_button.setEnabled(False)
            self.youtube_idle_button.setText("添加中...")
            print("DEBUG: 按钮状态已设置为 '添加中...'")
            
            # 强制刷新UI
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            print("DEBUG: UI已刷新")
        except Exception as e:
            print(f"DEBUG: 设置按钮状态时出错: {e}")
            restore_button_state()
            return
            
        try:
            youtube_url = self.youtube_url_input.text().strip()
            
            if not youtube_url:
                QMessageBox.warning(self, "输入错误", "请输入视频链接（支持YouTube、Twitter、X、抖音等平台）")
                restore_button_state()
                return
            
            # 清理URL中的空格（常见于复制粘贴的抖音链接）
            youtube_url = youtube_url.replace(' ', '').replace('\t', '').replace('\n', '').replace('\r', '')
            
            # 验证至少选择一个处理选项
            enable_transcription = self.enable_transcription_checkbox.isChecked()
            generate_article = self.generate_article_checkbox.isChecked()
            download_video = self.download_video_checkbox.isChecked()
            if not enable_transcription and not generate_article and not download_video:
                QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：下载视频、执行转录或生成文章")
                restore_button_state()
                return
            
            # 创建任务参数
            model, base_url = self.get_model_and_base_url()

            task = {
                "type": "youtube",
                "params": {
                    "youtube_url": youtube_url,
                    "model": model,
                    "api_key": None,
                    "base_url": base_url,
                    "whisper_model_size": self.whisper_model_combo.currentText(),
                    "stream": True,
                    "summary_dir": DEFAULT_SUMMARY_DIR,
                    "download_video": self.download_video_checkbox.isChecked(),
                    "custom_prompt": None,
                    "template_path": None,
                    "generate_subtitles": self.generate_subtitles_checkbox.isChecked(),
                    "translate_to_chinese": self.translate_checkbox.isChecked(),
                    "embed_subtitles": self.embed_subtitles_checkbox.isChecked(),
                    "cookies_file": self.cookies_path_input.text() if self.cookies_path_input.text() else None,
                    "prefer_native_subtitles": self.prefer_native_subtitles_checkbox.isChecked(),
                    "enable_transcription": self.enable_transcription_checkbox.isChecked(),
                    "generate_article": self.generate_article_checkbox.isChecked()
                },
                "title": f"视频: {youtube_url[:50]}..."
            }
            
            print("DEBUG: 任务创建完成，添加到队列")
            self.idle_tasks.append(task)
            print(f"DEBUG: 任务已添加，队列长度: {len(self.idle_tasks)}")
            self.statusBar.showMessage(f"已添加到闲时队列，当前队列中有 {len(self.idle_tasks)} 个任务")
            
            # 保存队列并刷新显示
            print("DEBUG: 开始保存队列")
            self.save_idle_queue()
            print("DEBUG: 开始刷新队列显示")
            self.refresh_idle_queue_display()
            
            # 先恢复按钮状态，再显示对话框
            restore_button_state()
            
            print("DEBUG: 显示成功对话框")
            QMessageBox.information(
                self, "添加成功", 
                f"任务已添加到闲时队列\n当前队列中有 {len(self.idle_tasks)} 个任务\n"
                f"闲时执行时间：{self.idle_start_time} - {self.idle_end_time}"
            )
            print("DEBUG: 对话框已关闭")
            
        except Exception as e:
            print(f"DEBUG: 发生异常: {e}")
            import traceback
            traceback.print_exc()
            restore_button_state()
            QMessageBox.critical(self, "错误", f"添加任务时发生错误: {str(e)}")
    
    def check_idle_time(self):
        """检查是否处于闲时，如果是则执行队列中的任务"""
        if self.is_idle_running or not self.idle_tasks or self.idle_paused:
            return
        
        from datetime import datetime, time
        
        current_time = datetime.now().time()
        start_time = datetime.strptime(self.idle_start_time, "%H:%M").time()
        end_time = datetime.strptime(self.idle_end_time, "%H:%M").time()
        
        # 判断是否在闲时时间段内
        is_idle_time = False
        if start_time <= end_time:
            # 同一天内的时间段，例如 09:00-17:00
            is_idle_time = start_time <= current_time <= end_time
        else:
            # 跨天的时间段，例如 23:00-07:00
            is_idle_time = current_time >= start_time or current_time <= end_time
        
        if is_idle_time and not (self.worker_thread and self.worker_thread.isRunning()):
            self.execute_next_idle_task()
    
    def execute_next_idle_task(self):
        """执行队列中的下一个闲时任务"""
        if not self.idle_tasks or self.is_idle_running:
            return
        
        task = self.idle_tasks.pop(0)  # 取出第一个任务
        self.save_idle_queue()  # 保存队列变化
        self.is_idle_running = True
        
        print(f"开始执行闲时任务: {task['title']}")
        self.statusBar.showMessage(f"正在执行闲时任务: {task['title']} (剩余 {len(self.idle_tasks)} 个)")
        
        # 根据任务类型执行相应的处理
        task_type = task.get("type", "youtube")

        if task_type == "youtube":
            # 设置按钮状态
            self.youtube_process_button.setEnabled(False)
            self.youtube_process_button.setText("闲时处理中...")
            self.youtube_stop_button.setEnabled(True)

            # 清空输出
            self.youtube_output_text.clear()
            self.youtube_output_text.append(f"[闲时任务] 开始处理: {task['title']}")

            # 创建并启动工作线程
            self.worker_thread = WorkerThread("youtube", task["params"])
            self.worker_thread.update_signal.connect(self.update_youtube_output)
            self.worker_thread.finished_signal.connect(self.on_idle_task_finished)
            self.worker_thread.start()

        elif task_type == "twitter":
            # Twitter视频下载
            print(f"[闲时任务] 开始处理 Twitter 视频: {task['title']}")
            self.youtube_output_text.clear()
            self.youtube_output_text.append(f"[闲时任务] 开始处理 Twitter 视频: {task['title']}")

            # 设置按钮状态
            self.youtube_process_button.setEnabled(False)
            self.youtube_process_button.setText("闲时处理中...")
            self.youtube_stop_button.setEnabled(True)

            # 使用 yt-dlp 下载 Twitter 视频
            self.worker_thread = WorkerThread("twitter", task["params"])
            self.worker_thread.update_signal.connect(self.update_youtube_output)
            self.worker_thread.finished_signal.connect(self.on_idle_task_finished)
            self.worker_thread.start()

        elif task_type == "bilibili":
            # Bilibili视频下载
            print(f"[闲时任务] 开始处理 Bilibili 视频: {task['title']}")
            self.youtube_output_text.clear()
            self.youtube_output_text.append(f"[闲时任务] 开始处理 Bilibili 视频: {task['title']}")

            # 设置按钮状态
            self.youtube_process_button.setEnabled(False)
            self.youtube_process_button.setText("闲时处理中...")
            self.youtube_stop_button.setEnabled(True)

            # 使用 yt-dlp 下载 Bilibili 视频
            self.worker_thread = WorkerThread("bilibili", task["params"])
            self.worker_thread.update_signal.connect(self.update_youtube_output)
            self.worker_thread.finished_signal.connect(self.on_idle_task_finished)
            self.worker_thread.start()

        else:
            # 未知类型，标记为失败并继续下一个
            print(f"[闲时任务] 警告: 未知任务类型 '{task_type}'，跳过此任务")
            self.youtube_output_text.append(f"[闲时任务] 错误: 不支持的任务类型 '{task_type}'")
            self.is_idle_running = False
            self.refresh_idle_queue_display()

            # 继续下一个任务
            if self.idle_tasks:
                QTimer.singleShot(1000, self.execute_next_idle_task)
    
    def on_idle_task_finished(self, result_path, success):
        """闲时任务完成回调"""
        # 恢复按钮状态
        self.youtube_process_button.setEnabled(True)
        self.youtube_process_button.setText("开始处理")
        self.youtube_stop_button.setEnabled(False)
        
        self.is_idle_running = False
        
        if success:
            self.statusBar.showMessage(f"闲时任务完成! 结果保存在: {result_path} (剩余 {len(self.idle_tasks)} 个)")
            print(f"闲时任务完成: {result_path}")
        else:
            self.statusBar.showMessage(f"闲时任务失败 (剩余 {len(self.idle_tasks)} 个)")
            print("闲时任务执行失败")
        
        # 刷新队列显示
        self.refresh_idle_queue_display()
        
        # 如果还有任务且仍在闲时时间内，继续执行下一个任务
        if self.idle_tasks:
            QTimer.singleShot(5000, self.check_idle_time)  # 5秒后检查下一个任务
    
    def view_idle_queue(self):
        """查看闲时任务队列"""
        if not self.idle_tasks:
            QMessageBox.information(self, "任务队列", "当前队列为空")
            return
        
        queue_text = f"当前队列中有 {len(self.idle_tasks)} 个任务：\n\n"
        for i, task in enumerate(self.idle_tasks, 1):
            queue_text += f"{i}. {task['title']}\n"
        
        queue_text += f"\n闲时执行时间：{self.idle_start_time} - {self.idle_end_time}"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("闲时任务队列")
        msg_box.setText(queue_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    def clear_idle_queue(self):
        """清空闲时任务队列"""
        if not self.idle_tasks:
            QMessageBox.information(self, "任务队列", "当前队列为空")
            return
        
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空队列中的 {len(self.idle_tasks)} 个任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.idle_tasks.clear()
            self.save_idle_queue()  # 保存队列变化
            self.refresh_idle_queue_display()  # 刷新显示
            self.statusBar.showMessage("闲时任务队列已清空")
            QMessageBox.information(self, "队列清空", "闲时任务队列已清空")
    
    def refresh_idle_queue_display(self):
        """刷新闲时队列显示"""
        print(f"DEBUG: refresh_idle_queue_display 被调用，当前任务数: {len(self.idle_tasks)}")
        
        # 只有当控件存在时才更新UI显示
        if hasattr(self, 'idle_queue_list'):
            print("DEBUG: idle_queue_list 控件存在，开始更新UI")
            self.idle_queue_list.clear()
            
            for i, task in enumerate(self.idle_tasks):
                item_text = f"{i+1}. {task['title']}"
                if task['type'] == 'youtube':
                    url = task['params']['youtube_url']
                    platform = "YouTube"
                    if 'twitter.com' in url.lower() or 'x.com' in url.lower():
                        platform = "Twitter/X"
                    elif 'bilibili.com' in url.lower():
                        platform = "Bilibili"
                    item_text += f" [{platform}: {url[:30]}...]"
                
                item = QListWidgetItem(item_text)
                self.idle_queue_list.addItem(item)
            
            print(f"DEBUG: UI列表已更新，显示 {len(self.idle_tasks)} 个任务")
        else:
            print("DEBUG: idle_queue_list 控件不存在，跳过UI更新")
        
        # 更新状态标签（如果存在）
        if hasattr(self, 'queue_status_label'):
            self.queue_status_label.setText(f"队列状态: {len(self.idle_tasks)} 个任务等待执行")
            print("DEBUG: 状态标签已更新")
    
    def update_idle_status_display(self):
        """更新闲时状态显示"""
        if not hasattr(self, 'idle_status_label'):
            return
        
        from datetime import datetime, time
        
        current_time = datetime.now().time()
        start_time = datetime.strptime(self.idle_start_time, "%H:%M").time()
        end_time = datetime.strptime(self.idle_end_time, "%H:%M").time()
        
        # 判断是否在闲时时间段内
        is_idle_time = False
        if start_time <= end_time:
            is_idle_time = start_time <= current_time <= end_time
        else:
            is_idle_time = current_time >= start_time or current_time <= end_time
        
        if self.idle_paused:
            status_text = "当前状态: 已暂停"
        elif self.is_idle_running:
            status_text = "当前状态: 正在执行闲时任务"
        elif is_idle_time:
            status_text = "当前状态: 闲时（等待任务）"
        else:
            status_text = "当前状态: 非闲时"
        
        self.idle_status_label.setText(status_text)
    
    def update_idle_time(self):
        """更新闲时时间设置"""
        new_start = self.idle_queue_start_input.text()
        new_end = self.idle_queue_end_input.text()
        
        # 验证时间格式
        try:
            datetime.strptime(new_start, "%H:%M")
            datetime.strptime(new_end, "%H:%M")
        except ValueError:
            QMessageBox.warning(self, "时间格式错误", "请使用正确的时间格式，例如: 23:00")
            return
        
        self.idle_start_time = new_start
        self.idle_end_time = new_end
        
        # 同步到设置页面
        if hasattr(self, 'idle_start_input'):
            self.idle_start_input.setText(new_start)
        if hasattr(self, 'idle_end_input'):
            self.idle_end_input.setText(new_end)
        
        self.statusBar.showMessage(f"闲时时间已更新为 {new_start} - {new_end}")
        QMessageBox.information(self, "设置已更新", f"闲时时间已更新为 {new_start} - {new_end}")
        self.log_extension_event(f"闲时设置已更新: {new_start}-{new_end}")

    def log_extension_event(self, message):
        """记录来自Chrome扩展或API的事件"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.extension_event_history.append(entry)
        if len(self.extension_event_history) > self.extension_event_limit:
            self.extension_event_history = self.extension_event_history[-self.extension_event_limit:]

        def update_log_view():
            if hasattr(self, 'chrome_extension_log'):
                self.chrome_extension_log.setPlainText("\n".join(self.extension_event_history))
                self.chrome_extension_log.moveCursor(QTextCursor.MoveOperation.End)

        QTimer.singleShot(0, update_log_view)

    def clear_extension_log(self):
        """清空Chrome扩展通信日志"""
        self.extension_event_history.clear()
        if hasattr(self, 'chrome_extension_log'):
            self.chrome_extension_log.clear()
        self.statusBar.showMessage("扩展通信日志已清空", 3000)

    def remove_selected_task(self):
        """删除选中的任务"""
        if not hasattr(self, 'idle_queue_list'):
            return
            
        current_row = self.idle_queue_list.currentRow()
        if current_row < 0 or current_row >= len(self.idle_tasks):
            QMessageBox.information(self, "提示", "请选择要删除的任务")
            return
        
        task = self.idle_tasks[current_row]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除任务：{task['title']} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.idle_tasks[current_row]
            self.save_idle_queue()  # 保存队列变化
            self.refresh_idle_queue_display()
            self.statusBar.showMessage("任务已删除")
    
    def move_task_up(self):
        """将选中任务上移"""
        if not hasattr(self, 'idle_queue_list'):
            return
            
        current_row = self.idle_queue_list.currentRow()
        if current_row <= 0 or current_row >= len(self.idle_tasks):
            return
        
        # 交换位置
        self.idle_tasks[current_row], self.idle_tasks[current_row-1] = \
            self.idle_tasks[current_row-1], self.idle_tasks[current_row]
        
        self.save_idle_queue()  # 保存队列变化
        self.refresh_idle_queue_display()
        self.idle_queue_list.setCurrentRow(current_row-1)
        self.statusBar.showMessage("任务已上移")
    
    def move_task_down(self):
        """将选中任务下移"""
        if not hasattr(self, 'idle_queue_list'):
            return
            
        current_row = self.idle_queue_list.currentRow()
        if current_row < 0 or current_row >= len(self.idle_tasks) - 1:
            return
        
        # 交换位置
        self.idle_tasks[current_row], self.idle_tasks[current_row+1] = \
            self.idle_tasks[current_row+1], self.idle_tasks[current_row]
        
        self.save_idle_queue()  # 保存队列变化
        self.refresh_idle_queue_display()
        self.idle_queue_list.setCurrentRow(current_row+1)
        self.statusBar.showMessage("任务已下移")
    
    def force_start_next_task(self):
        """立即开始下一个任务"""
        if not self.idle_tasks:
            QMessageBox.information(self, "提示", "队列中没有任务")
            return
        
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "提示", "当前有任务正在运行，请等待完成或中断后再试")
            return
        
        reply = QMessageBox.question(
            self, "确认执行",
            "确定要立即开始执行下一个任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.execute_next_idle_task()
    
    def pause_idle_execution(self):
        """暂停闲时执行"""
        self.idle_paused = True
        self.statusBar.showMessage("闲时执行已暂停")
        QMessageBox.information(self, "暂停执行", "闲时执行已暂停")
        self.update_idle_status_display()
    
    def resume_idle_execution(self):
        """恢复闲时执行"""
        self.idle_paused = False
        self.statusBar.showMessage("闲时执行已恢复")
        QMessageBox.information(self, "恢复执行", "闲时执行已恢复")
        self.update_idle_status_display()
    
    def save_idle_queue(self):
        """保存闲时队列到文件"""
        try:
            import json
            print(f"DEBUG: 准备保存队列，任务数: {len(self.idle_tasks)}")
            print(f"DEBUG: 保存位置: {self.idle_queue_file}")
            
            queue_data = {
                'tasks': self.idle_tasks,
                'idle_start_time': self.idle_start_time,
                'idle_end_time': self.idle_end_time
            }
            
            with open(self.idle_queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
            print(f"DEBUG: 闲时队列已成功保存到 {self.idle_queue_file}")
            
            # 验证保存结果
            with open(self.idle_queue_file, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                print(f"DEBUG: 验证保存结果，文件中任务数: {len(saved_data.get('tasks', []))}")
                
        except Exception as e:
            print(f"DEBUG: 保存闲时队列失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def load_idle_queue(self):
        """从文件加载闲时队列"""
        try:
            import json
            if not os.path.exists(self.idle_queue_file):
                print("闲时队列文件不存在，使用空队列")
                return
            
            with open(self.idle_queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.idle_tasks = data.get('tasks', [])
            self.idle_start_time = data.get('idle_start_time', "23:00")
            self.idle_end_time = data.get('idle_end_time', "07:00")
            
            print(f"从 {self.idle_queue_file} 加载了 {len(self.idle_tasks)} 个闲时任务")
            if self.idle_tasks:
                print("队列中的任务:")
                for i, task in enumerate(self.idle_tasks, 1):
                    print(f"  {i}. {task.get('title', '未知任务')}")
        
        except Exception as e:
            print(f"加载闲时队列失败: {str(e)}")
            self.idle_tasks = []  # 如果加载失败，使用空队列
    
    def init_api_server(self):
        """初始化API服务器"""
        try:
            from api_server import APIServer
            self.api_server = APIServer(self, port=8765)
            self.api_server.start_server()
            print("API服务器已启动，Chrome插件可以通过 http://127.0.0.1:8765 访问")
        except ImportError as e:
            print(f"无法导入API服务器模块: {e}")
            print("Chrome插件功能将不可用，请安装 flask 和 flask-cors")
        except Exception as e:
            print(f"启动API服务器失败: {e}")

    def closeEvent(self, event):
        """关闭窗口时的事件处理"""
        # 保存闲时队列
        self.save_idle_queue()
        
        # 停止API服务器
        if self.api_server:
            try:
                self.api_server.stop_server()
            except Exception as e:
                print(f"停止API服务器时出错: {e}")
        
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "有任务正在进行中，确定要退出吗?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # 停止线程
                self.worker_thread.stop()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
    
    # 字幕翻译相关方法
    
    def toggle_input_method(self):
        """切换输入方式"""
        if self.file_input_radio.isChecked():
            # 启用文件选择，禁用YouTube输入
            self.subtitle_file_input.setEnabled(True)
            self.subtitle_browse_button.setEnabled(True)
            self.batch_subtitle_button.setEnabled(True)
            self.subtitle_youtube_url_input.setEnabled(False)
            self.get_subtitle_languages_button.setEnabled(False)
            self.available_languages_combo.setEnabled(False)
            self.download_subtitle_button.setEnabled(False)
        else:
            # 启用YouTube输入，禁用文件选择
            self.subtitle_file_input.setEnabled(False)
            self.subtitle_browse_button.setEnabled(False)
            self.batch_subtitle_button.setEnabled(False)
            self.subtitle_youtube_url_input.setEnabled(True)
            # 根据URL是否有效来决定是否启用按钮
            self.on_youtube_url_changed()
    
    def on_youtube_url_changed(self):
        """YouTube URL输入变化时的处理"""
        url = self.subtitle_youtube_url_input.text().strip()
        if url and ("youtube.com" in url or "youtu.be" in url):
            self.get_subtitle_languages_button.setEnabled(True)
        else:
            self.get_subtitle_languages_button.setEnabled(False)
            self.available_languages_combo.setEnabled(False)
            self.available_languages_combo.clear()
            self.download_subtitle_button.setEnabled(False)
    
    def get_available_languages(self):
        """获取YouTube视频的可用字幕语言"""
        url = self.subtitle_youtube_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "输入错误", "请输入YouTube视频链接")
            return
        
        self.get_subtitle_languages_button.setEnabled(False)
        self.get_subtitle_languages_button.setText("获取中...")
        self.subtitle_output_text.append(f"正在获取视频字幕信息: {url}")
        
        # 创建获取语言线程
        self.language_worker_thread = GetLanguagesThread(url)
        self.language_worker_thread.languages_signal.connect(self.on_languages_received)
        self.language_worker_thread.error_signal.connect(self.on_languages_error)
        self.language_worker_thread.start()
    
    def on_languages_received(self, languages_info):
        """接收到可用语言信息"""
        self.get_subtitle_languages_button.setEnabled(True)
        self.get_subtitle_languages_button.setText("获取可用语言")
        
        if not languages_info:
            self.subtitle_output_text.append("该视频没有可用的字幕")
            return
            
        self.available_languages_combo.clear()
        self.available_languages_combo.setEnabled(True)
        
        # 添加语言选项
        for lang_code, lang_info in languages_info.items():
            display_text = f"{lang_info['name']} ({lang_code})"
            if lang_info.get('auto'):
                display_text += " [自动生成]"
            self.available_languages_combo.addItem(display_text, lang_code)
        
        self.download_subtitle_button.setEnabled(True)
        self.subtitle_output_text.append(f"找到 {len(languages_info)} 种可用字幕语言")
    
    def on_languages_error(self, error_msg):
        """获取语言信息出错"""
        self.get_subtitle_languages_button.setEnabled(True)
        self.get_subtitle_languages_button.setText("获取可用语言")
        self.subtitle_output_text.append(f"获取字幕语言失败: {error_msg}")
        QMessageBox.warning(self, "获取失败", f"无法获取字幕语言信息:\n{error_msg}")
    
    def download_youtube_subtitle(self):
        """下载YouTube字幕"""
        url = self.subtitle_youtube_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "输入错误", "请输入YouTube视频链接")
            return
            
        if self.available_languages_combo.count() == 0:
            QMessageBox.warning(self, "语言错误", "请先获取可用语言")
            return
        
        selected_lang = self.available_languages_combo.currentData()
        if not selected_lang:
            QMessageBox.warning(self, "选择错误", "请选择要下载的字幕语言")
            return
            
        self.download_subtitle_button.setEnabled(False)
        self.download_subtitle_button.setText("下载中...")
        self.subtitle_output_text.append(f"开始下载字幕: {selected_lang}")
        
        # 创建下载线程
        self.download_worker_thread = DownloadSubtitleThread(url, selected_lang)
        self.download_worker_thread.download_signal.connect(self.on_subtitle_downloaded)
        self.download_worker_thread.error_signal.connect(self.on_download_error)
        self.download_worker_thread.start()
    
    def on_subtitle_downloaded(self, subtitle_path):
        """字幕下载完成"""
        self.download_subtitle_button.setEnabled(True)
        self.download_subtitle_button.setText("下载字幕")
        
        if subtitle_path and os.path.exists(subtitle_path):
            self.subtitle_file_input.setText(subtitle_path)
            self.subtitle_output_text.append(f"字幕下载成功: {subtitle_path}")
            
            # 自动切换到文件输入模式以便进行翻译
            self.file_input_radio.setChecked(True)
        else:
            self.subtitle_output_text.append("字幕下载失败")
    
    def on_download_error(self, error_msg):
        """字幕下载出错"""
        self.download_subtitle_button.setEnabled(True)
        self.download_subtitle_button.setText("下载字幕")
        self.subtitle_output_text.append(f"下载失败: {error_msg}")
        QMessageBox.warning(self, "下载失败", f"字幕下载失败:\n{error_msg}")

    # 抖音下载相关方法
    
    def on_douyin_url_changed(self):
        """抖音URL输入变化时的处理"""
        text = self.douyin_url_input.text().strip()
        # 导入抖音工具类
        try:
            from douyin.utils import DouyinUtils
            
            if not text:
                self.douyin_parse_button.setEnabled(False)
                self.douyin_status_label.setText("请输入抖音视频链接或分享文本")
                self.douyin_status_label.setStyleSheet("color: #666;")
                self.douyin_download_button.setEnabled(False)
                return
            
            # 首先直接验证是否为有效URL
            utils = safe_douyin_utils()
            is_direct_url = utils.validate_url(text) if utils else False
            
            if is_direct_url:
                # 直接是有效的抖音链接
                self.douyin_parse_button.setEnabled(True)
                self.douyin_status_label.setText("检测到有效的抖音链接")
                self.douyin_status_label.setStyleSheet("color: #4CAF50;")
            else:
                # 尝试从分享文本中提取链接
                extracted_url = utils.parse_share_text(text) if utils else None
                if extracted_url:
                    # 找到有效链接，自动替换输入框内容
                    self.douyin_url_input.blockSignals(True)  # 阻止信号避免递归
                    self.douyin_url_input.setText(extracted_url)
                    self.douyin_url_input.blockSignals(False)
                    
                    self.douyin_parse_button.setEnabled(True)
                    self.douyin_status_label.setText("已从分享文本中提取有效链接")
                    self.douyin_status_label.setStyleSheet("color: #4CAF50;")
                else:
                    # 无法提取有效链接
                    self.douyin_parse_button.setEnabled(False)
                    
                    # 检查是否包含抖音关键词，给出更友好的提示
                    if any(keyword in text.lower() for keyword in ['douyin', '抖音', 'dou音']):
                        self.douyin_status_label.setText("检测到抖音分享文本，但未找到有效链接")
                        self.douyin_status_label.setStyleSheet("color: #FF9800;")
                    else:
                        self.douyin_status_label.setText("请输入有效的抖音视频链接或分享文本")
                        self.douyin_status_label.setStyleSheet("color: #666;")
                    
                    self.douyin_download_button.setEnabled(False)
                
        except ImportError:
            self.douyin_status_label.setText("抖音下载模块未安装")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
    
    def parse_douyin_video(self):
        """解析抖音视频信息（集成智能粘贴功能）"""
        url = self.douyin_url_input.text().strip()
        
        # 第一步：如果输入框为空，尝试智能粘贴
        if not url:
            print("[解析视频] 输入框为空，尝试智能粘贴...")
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            
            if clipboard_text:
                print(f"[解析视频] 检测到剪贴板内容: {clipboard_text[:50]}...")
                
                # 尝试智能粘贴
                utils = safe_douyin_utils()
                if utils:
                    extracted_url = utils.parse_share_text(clipboard_text)
                    if extracted_url:
                        print(f"[解析视频] 智能提取链接: {extracted_url}")
                        self.douyin_url_input.setText(extracted_url)
                        self.douyin_status_label.setText("✅ 已从剪贴板智能提取链接")
                        self.douyin_status_label.setStyleSheet("color: #4CAF50;")
                        url = extracted_url
                    else:
                        self.douyin_status_label.setText("⚠️ 剪贴板中未检测到抖音链接")
                        self.douyin_status_label.setStyleSheet("color: #FF9800;")
                else:
                    self.douyin_status_label.setText("❌ 智能粘贴不可用")
                    self.douyin_status_label.setStyleSheet("color: #f44336;")
            
            # 如果仍然没有URL，提示用户
            if not url:
                QMessageBox.warning(self, "输入错误", "请输入抖音视频链接，或复制分享文本到剪贴板后再点击解析")
                return
        
        # 第二步：如果输入框有内容但可能是分享文本，尝试智能处理
        elif not url.startswith('http'):
            print(f"[解析视频] 检测到非URL格式，尝试智能处理: {url[:50]}...")
            utils = safe_douyin_utils()
            if utils:
                extracted_url = utils.parse_share_text(url)
                if extracted_url:
                    print(f"[解析视频] 从输入内容提取链接: {extracted_url}")
                    self.douyin_url_input.setText(extracted_url)
                    self.douyin_status_label.setText("✅ 已从输入内容提取有效链接")
                    self.douyin_status_label.setStyleSheet("color: #4CAF50;")
                    url = extracted_url
                else:
                    self.douyin_status_label.setText("⚠️ 输入内容中未找到有效链接")
                    self.douyin_status_label.setStyleSheet("color: #FF9800;")
                    QMessageBox.warning(self, "输入错误", "未能从输入内容中提取有效的抖音链接")
                    return
        
        # 第三步：验证最终的URL
        utils = safe_douyin_utils()
        if utils and not utils.validate_url(url):
            QMessageBox.warning(self, "输入错误", "输入的不是有效的抖音视频链接")
            return
        
        print(f"[解析视频] 开始解析链接: {url}")
        
        self.douyin_parse_button.setEnabled(False)
        self.douyin_parse_button.setText("解析中...")
        self.douyin_status_label.setText("正在解析视频信息...")
        self.douyin_info_display.clear()
        
        # 创建解析线程
        self.douyin_parse_thread = DouyinParseThread(url)
        self.douyin_parse_thread.result_signal.connect(self.on_douyin_info_parsed)
        self.douyin_parse_thread.finished_signal.connect(self.on_douyin_parse_finished)
        self.douyin_parse_thread.update_signal.connect(self.update_douyin_output)
        self.douyin_parse_thread.start()
    
    def test_extract_douyin_url(self):
        """测试从剪贴板提取抖音链接（调试功能）"""
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            
            print("=" * 60)
            print("🔍 测试提取抖音链接")
            print("=" * 60)
            print(f"剪贴板内容: {clipboard_text}")
            print()
            
            if not clipboard_text:
                print("❌ 剪贴板为空")
                self.douyin_status_label.setText("⚠️ 剪贴板为空")
                self.douyin_status_label.setStyleSheet("color: #FF9800;")
                return
            
            # 安全获取 DouyinUtils
            utils = safe_douyin_utils()
            if not utils:
                print("❌ DouyinUtils 不可用")
                self.douyin_status_label.setText("❌ 抖音模块不可用")
                self.douyin_status_label.setStyleSheet("color: #f44336;")
                return
            
            print("✅ DouyinUtils 可用")
            
            # 1. 提取所有URL
            print("\n1. 提取所有URL...")
            all_urls = utils.extract_urls_from_text(clipboard_text)
            print(f"   发现的所有URL: {all_urls}")
            
            # 2. 筛选出包含 douyin.com 的链接
            print("\n2. 筛选包含 douyin.com 的链接...")
            douyin_urls = []
            for url in all_urls:
                if 'douyin.com' in url.lower():
                    douyin_urls.append(url)
                    print(f"   ✅ 找到抖音链接: {url}")
            
            if not douyin_urls:
                print("   ❌ 未找到包含 douyin.com 的链接")
            
            # 3. 验证链接有效性
            print("\n3. 验证链接有效性...")
            valid_douyin_urls = []
            for url in douyin_urls:
                is_valid = utils.validate_url(url)
                print(f"   {url} -> {'✅ 有效' if is_valid else '❌ 无效'}")
                if is_valid:
                    valid_douyin_urls.append(url)
            
            # 4. 使用智能解析
            print("\n4. 使用智能解析...")
            extracted_url = utils.parse_share_text(clipboard_text)
            print(f"   智能解析结果: {extracted_url}")
            
            # 5. 总结结果
            print("\n" + "=" * 60)
            print("📊 提取结果总结:")
            print(f"   - 原始文本长度: {len(clipboard_text)} 字符")
            print(f"   - 发现的所有URL: {len(all_urls)} 个")
            print(f"   - 包含 douyin.com 的URL: {len(douyin_urls)} 个")
            print(f"   - 有效的抖音URL: {len(valid_douyin_urls)} 个")
            print(f"   - 智能解析结果: {'有效链接' if extracted_url else '无'}")
            
            if extracted_url:
                print(f"\n🎯 推荐使用的链接: {extracted_url}")
                
                # 更新状态标签
                self.douyin_status_label.setText(f"✅ 测试完成，找到有效链接")
                self.douyin_status_label.setStyleSheet("color: #4CAF50;")
                
                # 可选：将提取的链接填入输入框
                self.douyin_url_input.setText(extracted_url)
                
            else:
                print("\n⚠️ 未能提取有效的抖音视频链接")
                self.douyin_status_label.setText("⚠️ 未找到有效的抖音链接")
                self.douyin_status_label.setStyleSheet("color: #FF9800;")
            
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 测试提取失败: {e}")
            import traceback
            traceback.print_exc()
            self.douyin_status_label.setText(f"❌ 测试失败: {str(e)}")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
    
    def on_douyin_info_parsed(self, video_info):
        """视频信息解析完成"""
        print(f"[主线程] 收到 result_signal，视频信息: {type(video_info)}")
        self.douyin_parse_button.setEnabled(True)
        self.douyin_parse_button.setText("🎯 智能解析")
        
        if video_info:
            # 显示视频信息
            from douyin.utils import DouyinUtils
            info_summary = DouyinUtils.get_video_info_summary(video_info)
            self.douyin_info_display.setText(info_summary)
            
            # 保存视频信息供下载使用
            self.current_douyin_info = video_info
            
            # 启用下载按钮
            self.douyin_download_button.setEnabled(True)
            self.douyin_status_label.setText("视频信息解析成功，可以开始下载")
            self.douyin_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self.douyin_info_display.setText("解析失败，无法获取视频信息")
            self.douyin_download_button.setEnabled(False)
            self.douyin_status_label.setText("视频信息解析失败")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
    
    def on_douyin_parse_finished(self, success, message):
        """视频信息解析完成（成功或失败）"""
        print(f"[主线程] 收到 finished_signal: success={success}, message={message}")
        self.douyin_parse_button.setEnabled(True)
        self.douyin_parse_button.setText("🎯 智能解析")
        
        if success:
            self.douyin_status_label.setText("解析完成")
            self.douyin_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self.douyin_info_display.setText(f"解析失败: {message}")
            self.douyin_download_button.setEnabled(False)
            self.douyin_status_label.setText("解析失败")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
            QMessageBox.warning(self, "解析失败", f"无法解析视频信息:\n{message}")
    
    def on_douyin_parse_error(self, error_msg):
        """视频信息解析出错"""
        self.douyin_parse_button.setEnabled(True)
        self.douyin_parse_button.setText("🎯 智能解析")
        self.douyin_info_display.setText(f"解析失败: {error_msg}")
        self.douyin_download_button.setEnabled(False)
        self.douyin_status_label.setText("解析出错")
        self.douyin_status_label.setStyleSheet("color: #f44336;")
        QMessageBox.warning(self, "解析失败", f"无法解析视频信息:\n{error_msg}")
    
    def download_douyin_video(self):
        """下载抖音视频"""
        if not hasattr(self, 'current_douyin_info') or not self.current_douyin_info:
            QMessageBox.warning(self, "下载错误", "请先解析视频信息")
            return
        
        # 验证至少选择一个处理选项
        download_video = self.douyin_download_video_cb.isChecked()
        enable_transcription = self.douyin_enable_transcription_cb.isChecked()
        generate_article = self.douyin_generate_article_cb.isChecked()
        
        if not download_video and not enable_transcription and not generate_article:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：下载视频、执行转录或生成文章摘要")
            return
        
        # 获取下载配置
        config = self.get_douyin_download_config()
        
        # 如果只需要转录摘要而不需要保存视频，临时启用视频下载用于转录
        if not download_video and (enable_transcription or generate_article):
            config.set("download_video", True)
            config.set("temp_download_for_transcription", True)
        else:
            config.set("download_video", download_video)
            config.set("temp_download_for_transcription", False)
        
        # 更新UI状态
        self.douyin_download_button.setEnabled(False)
        self.douyin_download_button.setText("下载中...")
        self.douyin_stop_button.setEnabled(True)
        self.douyin_progress_bar.setVisible(True)
        self.douyin_progress_bar.setValue(0)
        self.douyin_status_label.setText("准备开始下载...")
        self.douyin_output_text.clear()
        
        # 创建下载线程
        url = self.douyin_url_input.text().strip()
        self.douyin_download_thread = DouyinDownloadThread(url, config)
        self.douyin_download_thread.progress_signal.connect(self.update_douyin_progress)
        self.douyin_download_thread.update_signal.connect(self.update_douyin_output)
        self.douyin_download_thread.result_signal.connect(self.on_douyin_download_finished)
        self.douyin_download_thread.finished_signal.connect(self.on_douyin_download_status)
        self.douyin_download_thread.start()
    
    def batch_download_douyin_videos(self):
        """批量下载抖音视频"""
        batch_text = self.douyin_batch_input.toPlainText().strip()
        if not batch_text:
            QMessageBox.warning(self, "输入错误", "请输入要批量下载的视频链接或分享文本")
            return
        
        # 解析批量文本，支持分享文本和直接链接混合
        from douyin.utils import DouyinUtils
        
        # 按行分割输入文本
        lines = [line.strip() for line in batch_text.split('\n') if line.strip()]
        if not lines:
            QMessageBox.warning(self, "输入错误", "没有找到有效的输入内容")
            return
        
        valid_urls = []
        processed_lines = 0
        extracted_from_text = 0
        
        # 安全获取 DouyinUtils
        utils = safe_douyin_utils()
        if not utils:
            self.douyin_status_label.setText("❌ 抖音模块不可用")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
            return
        
        # 处理每一行
        for line in lines:
            processed_lines += 1
            
            # 直接验证是否为有效URL
            if utils.validate_url(line):
                if line not in valid_urls:
                    valid_urls.append(line)
            else:
                # 尝试从分享文本中提取链接
                extracted_url = utils.parse_share_text(line)
                if extracted_url and extracted_url not in valid_urls:
                    valid_urls.append(extracted_url)
                    extracted_from_text += 1
        
        if not valid_urls:
            QMessageBox.warning(self, "输入错误", "没有找到有效的抖音视频链接\n请确保输入包含抖音链接或分享文本")
            return
        
        # 显示处理结果
        if extracted_from_text > 0:
            QMessageBox.information(
                self, 
                "链接提取结果", 
                f"处理完成！\n"
                f"共处理 {processed_lines} 行内容\n"
                f"提取到 {len(valid_urls)} 个有效链接\n"
                f"其中 {extracted_from_text} 个从分享文本中提取"
            )
        elif len(valid_urls) != processed_lines:
            QMessageBox.information(
                self, 
                "链接检查", 
                f"共处理 {processed_lines} 行，其中 {len(valid_urls)} 个有效链接"
            )
        
        # 获取下载配置
        config = self.get_douyin_download_config()
        
        # 更新UI状态
        self.douyin_batch_download_button.setEnabled(False)
        self.douyin_batch_download_button.setText("批量下载中...")
        self.douyin_stop_button.setEnabled(True)
        self.douyin_progress_bar.setVisible(True)
        self.douyin_progress_bar.setValue(0)
        self.douyin_status_label.setText(f"准备批量下载 {len(valid_urls)} 个视频...")
        self.douyin_output_text.clear()
        
        # 创建批量下载线程
        self.douyin_batch_thread = DouyinBatchDownloadThread(valid_urls, config)
        self.douyin_batch_thread.progress_signal.connect(self.update_douyin_progress)
        self.douyin_batch_thread.update_signal.connect(self.update_douyin_output)
        self.douyin_batch_thread.finished_signal.connect(self.on_douyin_batch_finished)
        self.douyin_batch_thread.start()
    
    def stop_douyin_download(self):
        """停止抖音下载"""
        if hasattr(self, 'douyin_download_thread') and self.douyin_download_thread.isRunning():
            self.douyin_download_thread.stop()
        
        if hasattr(self, 'douyin_batch_thread') and self.douyin_batch_thread.isRunning():
            self.douyin_batch_thread.stop()
        
        if hasattr(self, 'douyin_parse_thread') and self.douyin_parse_thread.isRunning():
            self.douyin_parse_thread.terminate()
        
        self.reset_douyin_ui()
        self.douyin_status_label.setText("下载已停止")
        self.douyin_output_text.append("用户取消了下载")
    
    def browse_douyin_download_dir(self):
        """浏览下载目录"""
        current_dir = self.douyin_download_dir_input.text()
        download_dir = QFileDialog.getExistingDirectory(
            self,
            "选择下载目录",
            current_dir if current_dir and os.path.exists(current_dir) else os.getcwd()
        )
        
        if download_dir:
            self.douyin_download_dir_input.setText(download_dir)
    
    def get_douyin_download_config(self):
        """获取下载配置"""
        from douyin.config import DouyinConfig
        
        # 质量映射
        quality_map = {
            "高清": "high",
            "标清": "medium", 
            "流畅": "low"
        }
        
        config = DouyinConfig({
            "download_dir": self.douyin_download_dir_input.text().strip() or DOUYIN_DOWNLOADS_DIR,
            "video_quality": quality_map.get(self.douyin_quality_combo.currentText(), "high"),
            "download_cover": self.douyin_download_cover_cb.isChecked(),
            "download_music": self.douyin_download_music_cb.isChecked(),
            "remove_watermark": self.douyin_remove_watermark_cb.isChecked(),
            "save_metadata": self.douyin_save_metadata_cb.isChecked(),
            "enable_transcription": self.douyin_enable_transcription_cb.isChecked(),
            "generate_article": self.douyin_generate_article_cb.isChecked(),
        })
        
        return config
    
    def update_douyin_progress(self, progress, message):
        """更新抖音下载进度"""
        self.douyin_status_label.setText(str(message))
        self.douyin_progress_bar.setValue(progress)
    
    def update_douyin_output(self, message):
        """更新抖音下载输出"""
        timestamp = time.strftime("%H:%M:%S")
        self.douyin_output_text.append(f"[{timestamp}] {message}")
        
        # 自动滚动到底部
        cursor = self.douyin_output_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.douyin_output_text.setTextCursor(cursor)
    
    def on_douyin_download_finished(self, result):
        """单个视频下载完成"""
        self.reset_douyin_ui()
        
        if result.get("success"):
            downloaded_files = result.get("downloaded_files", [])
            self.douyin_status_label.setText(f"下载完成！共下载 {len(downloaded_files)} 个文件")
            self.douyin_status_label.setStyleSheet("color: #4CAF50;")
            
            # 显示下载结果
            self.douyin_output_text.append("="*50)
            self.douyin_output_text.append("📥 下载完成！")
            for file_info in downloaded_files:
                file_type = file_info.get("type", "文件")
                file_path = file_info.get("path", "未知路径")
                file_size = file_info.get("size", 0)
                from douyin.utils import DouyinUtils
                size_str = DouyinUtils.format_file_size(file_size)
                self.douyin_output_text.append(f"✅ {file_type}: {os.path.basename(file_path)} ({size_str})")
                
        else:
            error_msg = result.get("error", "未知错误")
            self.douyin_status_label.setText("下载失败")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
            self.douyin_output_text.append(f"❌ 下载失败: {error_msg}")
    
    def on_douyin_download_status(self, success, message):
        """处理下载状态更新"""
        if not success:
            self.reset_douyin_ui()
            self.douyin_status_label.setText(f"下载失败: {message}")
            self.douyin_status_label.setStyleSheet("color: #F44336;")
            self.update_douyin_output(f"❌ 下载失败: {message}")
    
    def on_douyin_batch_finished(self, result):
        """批量下载完成"""
        self.reset_douyin_ui()
        
        if result.get("success"):
            total_count = result.get("total_count", 0)
            successful_count = result.get("successful_count", 0)
            failed_count = result.get("failed_count", 0)
            
            self.douyin_status_label.setText(f"批量下载完成！成功 {successful_count}/{total_count}")
            
            if failed_count == 0:
                self.douyin_status_label.setStyleSheet("color: #4CAF50;")
            else:
                self.douyin_status_label.setStyleSheet("color: #FF9800;")
                
            # 显示批量下载结果
            self.douyin_output_text.append("="*50)
            self.douyin_output_text.append("📦 批量下载完成！")
            self.douyin_output_text.append(f"📊 总计: {total_count} 个，成功: {successful_count} 个，失败: {failed_count} 个")
        else:
            error_msg = result.get("error", "未知错误")
            self.douyin_status_label.setText("批量下载失败")
            self.douyin_status_label.setStyleSheet("color: #f44336;")
            self.douyin_output_text.append(f"❌ 批量下载失败: {error_msg}")
    
    def reset_douyin_ui(self):
        """重置抖音下载UI状态"""
        self.douyin_download_button.setEnabled(hasattr(self, 'current_douyin_info'))
        self.douyin_download_button.setText("🎬 开始下载")
        self.douyin_batch_download_button.setEnabled(True)
        self.douyin_batch_download_button.setText("📦 批量下载")
        self.douyin_stop_button.setEnabled(False)
        self.douyin_progress_bar.setVisible(False)

    def browse_subtitle_file(self):
        """浏览单个字幕文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字幕文件",
            "",
            "字幕文件 (*.srt *.vtt *.ass);;所有文件 (*)"
        )
        if file_path:
            self.subtitle_file_input.setText(file_path)
            self.subtitle_output_text.append(f"已选择文件: {file_path}")
    
    def browse_batch_subtitle_files(self):
        """批量选择字幕文件"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择多个字幕文件",
            "",
            "字幕文件 (*.srt *.vtt *.ass);;所有文件 (*)"
        )
        if file_paths:
            # 将多个文件路径显示在输入框中（用分号分隔）
            self.subtitle_file_input.setText("; ".join(file_paths))
            self.subtitle_output_text.append(f"已选择 {len(file_paths)} 个文件进行批量翻译:")
            for file_path in file_paths:
                self.subtitle_output_text.append(f"  - {file_path}")
    
    def translate_subtitle(self):
        """执行字幕翻译"""
        file_paths_text = self.subtitle_file_input.text().strip()
        if not file_paths_text:
            QMessageBox.warning(self, "文件错误", "请先选择要翻译的字幕文件")
            return
        
        # 解析文件路径（支持单个文件和批量文件）
        if ";" in file_paths_text:
            file_paths = [path.strip() for path in file_paths_text.split(";") if path.strip()]
        else:
            file_paths = [file_paths_text]
        
        # 验证文件存在性
        invalid_files = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                invalid_files.append(file_path)
        
        if invalid_files:
            QMessageBox.warning(
                self, "文件错误", 
                f"以下文件不存在：\n" + "\n".join(invalid_files)
            )
            return
        
        # 获取翻译参数
        target_language = self.target_language_combo.currentText()
        translation_mode = self.translation_mode_combo.currentText()
        preserve_timestamps = self.preserve_timestamps_cb.isChecked()
        backup_original = self.backup_original_cb.isChecked()
        
        # 创建翻译参数
        params = {
            "file_paths": file_paths,
            "target_language": target_language,
            "translation_mode": translation_mode,
            "preserve_timestamps": preserve_timestamps,
            "backup_original": backup_original
        }
        
        # 更新UI状态
        self.subtitle_translate_button.setEnabled(False)
        self.subtitle_translate_button.setText("翻译中...")
        self.subtitle_stop_button.setEnabled(True)
        self.subtitle_progress_bar.setVisible(True)
        self.subtitle_progress_bar.setValue(0)
        self.subtitle_status_label.setText("准备开始翻译...")
        self.subtitle_output_text.clear()
        
        # 创建并启动翻译线程
        self.subtitle_worker_thread = SubtitleTranslateThread(params)
        self.subtitle_worker_thread.update_signal.connect(self.update_subtitle_output)
        self.subtitle_worker_thread.progress_signal.connect(self.update_subtitle_progress)
        self.subtitle_worker_thread.finished_signal.connect(self.on_subtitle_translate_finished)
        self.subtitle_worker_thread.start()
    
    def stop_subtitle_translation(self):
        """停止字幕翻译"""
        if hasattr(self, 'subtitle_worker_thread'):
            self.subtitle_worker_thread.stop()
            self.subtitle_output_text.append("正在停止翻译...")
    
    def update_subtitle_output(self, text):
        """更新字幕翻译输出"""
        self.subtitle_output_text.append(text)
        # 滚动到底部
        cursor = self.subtitle_output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.subtitle_output_text.setTextCursor(cursor)
    
    def update_subtitle_progress(self, value, status_text):
        """更新字幕翻译进度"""
        self.subtitle_progress_bar.setValue(value)
        self.subtitle_status_label.setText(status_text)
    
    def on_subtitle_translate_finished(self, success, result_info):
        """字幕翻译完成回调"""
        # 恢复UI状态
        self.subtitle_translate_button.setEnabled(True)
        self.subtitle_translate_button.setText("🌐 开始翻译")
        self.subtitle_stop_button.setEnabled(False)
        self.subtitle_progress_bar.setVisible(False)
        
        if success:
            self.subtitle_status_label.setText("翻译完成")
            QMessageBox.information(self, "翻译完成", result_info)
        else:
            self.subtitle_status_label.setText("翻译失败")
            QMessageBox.critical(self, "翻译失败", result_info)
    
    # 各页面的闲时操作方法
    def add_audio_to_idle_queue(self):
        """将本地音频处理任务添加到闲时队列"""
        audio_path = self.audio_path_input.text().strip()
        if not audio_path:
            QMessageBox.warning(self, "输入错误", "请先选择音频文件")
            return
        
        # 验证至少选择一个处理选项
        enable_transcription = self.audio_enable_transcription_checkbox.isChecked()
        generate_article = self.audio_generate_article_checkbox.isChecked()
        if not enable_transcription and not generate_article:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：执行转录或生成文章")
            return
        
        # 创建任务参数
        model, base_url = self.get_model_and_base_url()

        task = {
            "type": "local_audio",
            "params": {
                "audio_path": audio_path,
                "model": model,
                "api_key": None,
                "base_url": base_url,
                "whisper_model_size": self.audio_whisper_model_combo.currentText(),
                "stream": True,
                "summary_dir": DEFAULT_SUMMARY_DIR,
                "custom_prompt": None,
                "template_path": None,
                "generate_subtitles": self.audio_generate_subtitles_checkbox.isChecked(),
                "translate_to_chinese": self.audio_translate_checkbox.isChecked(),
                "enable_transcription": enable_transcription,
                "generate_article": generate_article
            },
            "title": f"音频: {os.path.basename(audio_path)}"
        }
        
        self.idle_tasks.append(task)
        self.save_idle_queue()
        self.refresh_idle_queue_display()
        self.statusBar.showMessage(f"已添加到闲时队列，当前队列中有 {len(self.idle_tasks)} 个任务")
        QMessageBox.information(self, "添加成功", f"任务已添加到闲时队列\n当前队列中有 {len(self.idle_tasks)} 个任务")
    
    def add_video_to_idle_queue(self):
        """将本地视频处理任务添加到闲时队列"""
        video_path = self.video_path_input.text().strip()
        if not video_path:
            QMessageBox.warning(self, "输入错误", "请先选择视频文件或目录")
            return
        
        # 验证至少选择一个处理选项
        enable_transcription = self.video_enable_transcription_checkbox.isChecked()
        generate_article = self.video_generate_article_checkbox.isChecked()
        if not enable_transcription and not generate_article:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：执行转录或生成文章")
            return
        
        # 创建任务参数
        task_type = "local_video_batch" if self.video_batch_mode_radio.isChecked() else "local_video"
        model, base_url = self.get_model_and_base_url()

        task = {
            "type": task_type,
            "params": {
                "video_path": video_path,
                "model": model,
                "api_key": None,
                "base_url": base_url,
                "whisper_model_size": self.video_whisper_model_combo.currentText(),
                "stream": True,
                "summary_dir": DEFAULT_SUMMARY_DIR,
                "custom_prompt": None,
                "template_path": None,
                "generate_subtitles": self.video_generate_subtitles_checkbox.isChecked(),
                "translate_to_chinese": self.video_translate_checkbox.isChecked(),
                "embed_subtitles": self.video_embed_subtitles_checkbox.isChecked(),
                "enable_transcription": enable_transcription,
                "generate_article": generate_article,
                "source_language": self.video_source_language_combo.currentData()
            },
            "title": f"视频: {os.path.basename(video_path)}"
        }
        
        self.idle_tasks.append(task)
        self.save_idle_queue()
        self.refresh_idle_queue_display()
        self.statusBar.showMessage(f"已添加到闲时队列，当前队列中有 {len(self.idle_tasks)} 个任务")
        QMessageBox.information(self, "添加成功", f"任务已添加到闲时队列\n当前队列中有 {len(self.idle_tasks)} 个任务")
    
    def add_text_to_idle_queue(self):
        """将本地文本处理任务添加到闲时队列"""
        text_path = self.text_path_input.text().strip()
        if not text_path:
            QMessageBox.warning(self, "输入错误", "请先选择文本文件")
            return

        # 创建任务参数
        model, base_url = self.get_model_and_base_url()

        task = {
            "type": "local_text",
            "params": {
                "text_path": text_path,
                "model": model,
                "api_key": None,
                "base_url": base_url,
                "stream": True,
                "summary_dir": DEFAULT_SUMMARY_DIR,
                "custom_prompt": None,
                "template_path": None
            },
            "title": f"文本: {os.path.basename(text_path)}"
        }
        
        self.idle_tasks.append(task)
        self.save_idle_queue()
        self.refresh_idle_queue_display()
        self.statusBar.showMessage(f"已添加到闲时队列，当前队列中有 {len(self.idle_tasks)} 个任务")
        QMessageBox.information(self, "添加成功", f"任务已添加到闲时队列\n当前队列中有 {len(self.idle_tasks)} 个任务")
    
    def add_batch_to_idle_queue(self):
        """将批量处理任务添加到闲时队列"""
        # 获取URL列表
        urls = []
        urls_text = self.batch_urls_text.toPlainText().strip()
        if urls_text:
            for line in urls_text.split('\n'):
                url = line.strip()
                if url and not url.startswith('#'):
                    urls.append(url)
        
        # 检查是否有URL
        if not urls:
            QMessageBox.warning(self, "输入错误", "请输入至少一个视频链接")
            return
        
        # 验证至少选择一个处理选项
        enable_transcription = self.batch_enable_transcription_checkbox.isChecked()
        generate_article = self.batch_generate_article_checkbox.isChecked()
        download_video = self.batch_download_video_checkbox.isChecked()
        if not enable_transcription and not generate_article and not download_video:
            QMessageBox.warning(self, "选择错误", "请至少选择一个处理选项：下载视频、执行转录或生成文章")
            return
        
        # 创建任务参数
        model, base_url = self.get_model_and_base_url()

        task = {
            "type": "batch",
            "params": {
                "youtube_urls": urls,
                "model": model,
                "api_key": None,
                "base_url": base_url,
                "whisper_model_size": self.batch_whisper_model_combo.currentText(),
                "stream": True,
                "summary_dir": DEFAULT_SUMMARY_DIR,
                "download_video": download_video,
                "custom_prompt": None,
                "template_path": None,
                "generate_subtitles": self.batch_generate_subtitles_checkbox.isChecked(),
                "translate_to_chinese": self.batch_translate_checkbox.isChecked(),
                "embed_subtitles": self.batch_embed_subtitles_checkbox.isChecked(),
                "cookies_file": self.batch_cookies_path_input.text() if self.batch_cookies_path_input.text() else None,
                "prefer_native_subtitles": self.batch_prefer_native_subtitles_checkbox.isChecked(),
                "enable_transcription": enable_transcription,
                "generate_article": generate_article
            },
            "title": f"批量处理: {len(urls)} 个视频"
        }
        
        self.idle_tasks.append(task)
        self.save_idle_queue()
        self.refresh_idle_queue_display()
        self.statusBar.showMessage(f"已添加到闲时队列，当前队列中有 {len(self.idle_tasks)} 个任务")
        QMessageBox.information(self, "添加成功", f"任务已添加到闲时队列\n当前队列中有 {len(self.idle_tasks)} 个任务")

# YouTube字幕相关工作线程
class GetLanguagesThread(QThread):
    languages_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
    
    def run(self):
        """获取YouTube视频的可用字幕语言"""
        try:
            import yt_dlp
            
            # 尝试多种配置
            proxy_configs = []
            
            # 配置1：使用系统代理
            proxy = os.getenv("PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if proxy:
                proxy_configs.append({
                    'quiet': True,
                    'no_warnings': True,
                    'proxy': proxy
                })
            
            # 配置2：不使用代理
            proxy_configs.append({
                'quiet': True,
                'no_warnings': True,
            })
            
            info = None
            for ydl_opts in proxy_configs:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.url, download=False)
                        break  # 成功则退出循环
                except Exception as e:
                    if "proxy" in ydl_opts:
                        print(f"使用代理失败，尝试直连: {str(e)}")
                    else:
                        raise e  # 如果直连也失败，抛出异常
                
            if not info:
                self.error_signal.emit("无法获取视频信息")
                return
            
            # 获取可用字幕
            subtitles = info.get('subtitles', {})
            auto_subtitles = info.get('automatic_captions', {})
            
            # 合并手动字幕和自动字幕
            all_languages = {}
            
            # 处理手动字幕
            for lang_code, sub_list in subtitles.items():
                lang_name = self.get_language_name(lang_code)
                all_languages[lang_code] = {
                    'name': lang_name,
                    'auto': False,
                    'formats': sub_list
                }
            
            # 处理自动字幕
            for lang_code, sub_list in auto_subtitles.items():
                if lang_code not in all_languages:  # 优先使用手动字幕
                    lang_name = self.get_language_name(lang_code)
                    all_languages[lang_code] = {
                        'name': lang_name,
                        'auto': True,
                        'formats': sub_list
                    }
            
            self.languages_signal.emit(all_languages)
                
        except Exception as e:
            self.error_signal.emit(str(e))
    
    def get_language_name(self, lang_code):
        """获取语言名称"""
        language_names = {
            'zh': '中文',
            'zh-CN': '中文（简体）',
            'zh-TW': '中文（繁体）',
            'zh-HK': '中文（香港）',
            'en': '英语',
            'ja': '日语',
            'ko': '韩语',
            'fr': '法语',
            'de': '德语',
            'es': '西班牙语',
            'it': '意大利语',
            'ru': '俄语',
            'pt': '葡萄牙语',
            'ar': '阿拉伯语',
            'hi': '印地语',
            'th': '泰语',
            'vi': '越南语',
            'id': '印尼语',
            'ms': '马来语',
            'tr': '土耳其语',
            'pl': '波兰语',
            'nl': '荷兰语',
            'sv': '瑞典语',
            'da': '丹麦语',
            'no': '挪威语',
            'fi': '芬兰语',
            'cs': '捷克语',
            'hu': '匈牙利语',
            'ro': '罗马尼亚语',
            'bg': '保加利亚语',
            'hr': '克罗地亚语',
            'sk': '斯洛伐克语',
            'sl': '斯洛文尼亚语',
            'et': '爱沙尼亚语',
            'lv': '拉脱维亚语',
            'lt': '立陶宛语',
            'uk': '乌克兰语',
            'be': '白俄罗斯语',
            'mk': '马其顿语',
            'sq': '阿尔巴尼亚语',
            'sr': '塞尔维亚语',
            'bs': '波斯尼亚语',
            'mt': '马耳他语',
            'is': '冰岛语',
            'ga': '爱尔兰语',
            'cy': '威尔士语',
            'eu': '巴斯克语',
            'ca': '加泰罗尼亚语',
            'gl': '加利西亚语',
            'af': '南非荷兰语',
            'sw': '斯瓦希里语',
            'am': '阿姆哈拉语',
            'he': '希伯来语',
            'fa': '波斯语',
            'ur': '乌尔都语',
            'bn': '孟加拉语',
            'gu': '古吉拉特语',
            'kn': '卡纳达语',
            'ml': '马拉雅拉姆语',
            'mr': '马拉地语',
            'ne': '尼泊尔语',
            'pa': '旁遮普语',
            'si': '僧伽罗语',
            'ta': '泰米尔语',
            'te': '泰卢固语',
            'my': '缅甸语',
            'km': '柬埔寨语',
            'lo': '老挝语',
            'ka': '格鲁吉亚语',
            'hy': '亚美尼亚语',
            'az': '阿塞拜疆语',
            'kk': '哈萨克语',
            'ky': '吉尔吉斯语',
            'tg': '塔吉克语',
            'tk': '土库曼语',
            'uz': '乌兹别克语',
            'mn': '蒙古语',
        }
        return language_names.get(lang_code, lang_code.upper())


class DownloadSubtitleThread(QThread):
    download_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self, url, language):
        super().__init__()
        self.url = url
        self.language = language
    
    def run(self):
        """下载YouTube字幕"""
        try:
            # 确保导入路径正确
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)
            
            from youtube_transcriber import download_youtube_subtitles
            
            # 创建输出目录（统一使用 workspace/native_subtitles）
            output_dir = NATIVE_SUBTITLES_DIR
            os.makedirs(output_dir, exist_ok=True)
            
            print(f"开始下载字幕: URL={self.url}, 语言={self.language}")
            
            # 下载字幕
            downloaded_files = download_youtube_subtitles(
                self.url,
                output_dir=output_dir,
                languages=[self.language],
                download_auto=True
            )
            
            print(f"下载结果: {downloaded_files}")
            
            if downloaded_files:
                # 验证文件是否真实存在并标准化路径
                valid_files = []
                for f in downloaded_files:
                    # 标准化路径分隔符
                    normalized_path = os.path.normpath(f)
                    if os.path.exists(normalized_path):
                        # 转换为绝对路径
                        abs_path = os.path.abspath(normalized_path)
                        valid_files.append(abs_path)
                
                if valid_files:
                    self.download_signal.emit(valid_files[0])
                else:
                    self.error_signal.emit(f"字幕文件下载后未找到: {downloaded_files}")
            else:
                self.error_signal.emit("没有找到可下载的字幕文件，可能的原因：\n1. 该视频没有此语言的字幕\n2. 字幕不可下载\n3. 网络连接问题")
                
        except ImportError as e:
            self.error_signal.emit(f"导入模块失败: {str(e)}")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.error_signal.emit(f"下载失败: {str(e)}\n\n详细错误信息:\n{error_details}")


# 字幕翻译工作线程
class SubtitleTranslateThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, params):
        super().__init__()
        self.params = params
        self.stopped = False
    
    def stop(self):
        """停止翻译"""
        self.stopped = True
    
    def run(self):
        """执行字幕翻译"""
        try:
            file_paths = self.params["file_paths"]
            target_language = self.params["target_language"]
            backup_original = self.params["backup_original"]
            
            total_files = len(file_paths)
            completed_files = 0
            failed_files = []
            
            self.update_signal.emit(f"开始翻译 {total_files} 个字幕文件...")
            
            for i, file_path in enumerate(file_paths):
                if self.stopped:
                    self.update_signal.emit("翻译已被用户停止")
                    break
                    
                self.update_signal.emit(f"\n正在处理文件 {i+1}/{total_files}: {os.path.basename(file_path)}")
                self.progress_signal.emit(int((i / total_files) * 100), f"正在翻译: {os.path.basename(file_path)}")
                
                try:
                    # 备份原文件
                    if backup_original:
                        backup_path = file_path + ".backup"
                        import shutil
                        shutil.copy2(file_path, backup_path)
                        self.update_signal.emit(f"已备份原文件: {backup_path}")
                    
                    # 执行翻译
                    success = self.translate_single_file(file_path, target_language)
                    
                    if success:
                        completed_files += 1
                        self.update_signal.emit(f"✅ 翻译完成: {os.path.basename(file_path)}")
                    else:
                        failed_files.append(file_path)
                        self.update_signal.emit(f"❌ 翻译失败: {os.path.basename(file_path)}")
                        
                except Exception as e:
                    failed_files.append(file_path)
                    self.update_signal.emit(f"❌ 翻译出错: {os.path.basename(file_path)} - {str(e)}")
            
            if not self.stopped:
                self.progress_signal.emit(100, "翻译完成")
                
                # 生成结果信息
                result_info = f"翻译完成！\n\n"
                result_info += f"总文件数: {total_files}\n"
                result_info += f"成功翻译: {completed_files}\n"
                result_info += f"失败文件: {len(failed_files)}\n"
                
                if failed_files:
                    result_info += f"\n失败的文件:\n"
                    for file_path in failed_files:
                        result_info += f"- {os.path.basename(file_path)}\n"
                
                self.finished_signal.emit(len(failed_files) == 0, result_info)
            else:
                self.finished_signal.emit(False, "翻译被用户停止")
                
        except Exception as e:
            self.update_signal.emit(f"翻译过程出错: {str(e)}")
            self.finished_signal.emit(False, f"翻译过程出错: {str(e)}")
    
    def translate_single_file(self, file_path, target_language):
        """翻译单个字幕文件"""
        try:
            # 标准化文件路径
            normalized_path = os.path.normpath(file_path)
            self.update_signal.emit(f"处理文件: {normalized_path}")
            
            # 验证文件存在
            if not os.path.exists(normalized_path):
                self.update_signal.emit(f"❌ 文件不存在: {normalized_path}")
                return False
            
            # 尝试调用原有的字幕翻译功能
            try:
                from youtube_transcriber import translate_subtitle_file
                
                # 映射语言
                language_map = {
                    "中文（简体）": "zh",
                    "中文（繁体）": "zh-TW",
                    "英语": "en",
                    "日语": "ja",
                    "韩语": "ko",
                    "法语": "fr",
                    "德语": "de",
                    "西班牙语": "es",
                    "意大利语": "it",
                    "俄语": "ru"
                }
                
                target_lang_code = language_map.get(target_language, "zh")
                
                # 调用翻译函数
                result = translate_subtitle_file(normalized_path, target_lang_code)
                return result is not None
                
            except ImportError:
                # 如果没有翻译函数，使用简单的示例实现
                self.update_signal.emit("⚠️ 翻译功能模块未找到，使用示例实现")
                return self.simple_translate_implementation(normalized_path, target_language)
            
        except Exception as e:
            self.update_signal.emit(f"❌ 翻译文件时出错: {str(e)}")
            return False
    
    def simple_translate_implementation(self, file_path, target_language):
        """简单的翻译实现"""
        try:
            self.update_signal.emit(f"使用简单翻译实现处理: {os.path.basename(file_path)}")
            
            # 读取原文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 生成翻译后的文件名
            file_dir = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)
            name, ext = os.path.splitext(file_name)
            translated_file = os.path.join(file_dir, f"{name}_translated{ext}")
            
            # 写入翻译文件（这里只是复制，实际需要调用翻译API）
            with open(translated_file, 'w', encoding='utf-8') as f:
                f.write(f"# 翻译文件 - {target_language}\n")
                f.write(content)
            
            self.update_signal.emit(f"已生成翻译文件: {translated_file}")
            return True
            
        except Exception as e:
            self.update_signal.emit(f"翻译文件时出错: {str(e)}")
            return False


# ====================== 抖音下载线程类 ======================

class DouyinParseThread(QThread):
    """抖音视频信息解析线程"""
    update_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.stopped = False
    
    def stop(self):
        """停止解析"""
        self.stopped = True
    
    def run(self):
        """执行视频信息解析"""
        try:
            self.update_signal.emit("正在解析视频信息...")
            
            # 安全获取 DouyinUtils 并验证URL
            try:
                from douyin.utils import DouyinUtils
                if not DouyinUtils.validate_url(self.url):
                    self.finished_signal.emit(False, "无效的抖音URL")
                    return
            except ImportError:
                self.finished_signal.emit(False, "抖音模块不可用")
                return
            
            # 创建下载器，使用默认端口8080
            downloader = DouyinDownloader(port="8080")
            
            # 解析视频信息
            print(f"[线程] 调用 downloader.get_video_info({self.url})")
            video_info = downloader.get_video_info(self.url)
            print(f"[线程] get_video_info 返回: {type(video_info)}")
            
            if self.stopped:
                return
                
            if video_info:
                print(f"[线程] 成功获取视频信息，发出 result_signal")
                self.result_signal.emit(video_info)
                print(f"[线程] 发出 finished_signal(True)")
                self.finished_signal.emit(True, "解析完成")
                print(f"[线程] 信号发送完成，等待处理...")
                # 强制刷新事件循环
                QApplication.processEvents()
                print(f"[线程] 事件循环处理完成")
            else:
                print(f"[线程] 视频信息为空，发出失败信号")
                self.finished_signal.emit(False, "无法解析视频信息")
                
        except Exception as e:
            if not self.stopped:
                self.update_signal.emit(f"解析失败: {str(e)}")
                self.finished_signal.emit(False, f"解析失败: {str(e)}")
        finally:
            print(f"[线程] DouyinParseThread.run() 结束")


class DouyinDownloadThread(QThread):
    """抖音视频下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, url, config):
        super().__init__()
        self.url = url
        self.config = config
        self.stopped = False
    
    def stop(self):
        """停止下载"""
        self.stopped = True
    
    def process_transcription_and_summary(self, download_result):
        """处理转录和摘要生成"""
        try:
            # 获取下载的视频文件路径
            video_files = download_result.get("files", {}).get("video", [])
            if not video_files:
                self.result_signal.emit(download_result)
                self.finished_signal.emit(True, "下载完成（未找到视频文件进行转录）")
                return
            
            # 使用第一个视频文件
            video_path = video_files[0]
            if not os.path.exists(video_path):
                self.result_signal.emit(download_result)
                self.finished_signal.emit(True, "下载完成（视频文件不存在）")
                return
            
            self.update_signal.emit("开始处理转录和摘要...")
            self.progress_signal.emit(80, "开始转录处理...")
            
            # 导入必要的模块
            from youtube_transcriber import process_local_video
            import os
            
            # 设置处理参数（使用默认值）
            model = "gpt-4o-mini"  # 默认模型
            api_key = os.getenv('OPENAI_API_KEY')
            base_url = os.getenv('OPENAI_BASE_URL')
            whisper_model_size = "medium"
            stream = True
            summary_dir = "summaries"
            custom_prompt = None
            template_path = None
            generate_subtitles = True
            translate_to_chinese = True
            embed_subtitles = False
            enable_transcription = self.config.get("enable_transcription", True)
            generate_article = self.config.get("generate_article", True)
            source_language = None
            
            # 执行转录和摘要处理
            result = process_local_video(
                video_path, model, api_key, base_url, whisper_model_size,
                stream, summary_dir, custom_prompt, template_path,
                generate_subtitles, translate_to_chinese, embed_subtitles,
                enable_transcription, generate_article, source_language
            )
            
            self.progress_signal.emit(100, "转录和摘要完成")
            
            # 合并结果
            if result:
                download_result["transcription_result"] = result
                self.update_signal.emit(f"转录和摘要完成！结果保存在: {result}")
                self.finished_signal.emit(True, "下载、转录和摘要全部完成")
            else:
                self.update_signal.emit("转录和摘要处理失败，但视频下载成功")
                self.finished_signal.emit(True, "下载完成，转录处理失败")
            
            self.result_signal.emit(download_result)
            
            # 如果是临时下载用于转录，删除视频文件
            if self.config.get("temp_download_for_transcription"):
                try:
                    if os.path.exists(video_path):
                        os.remove(video_path)
                        self.update_signal.emit("已删除临时视频文件")
                except Exception as cleanup_e:
                    self.update_signal.emit(f"清理临时文件失败: {str(cleanup_e)}")
            
        except Exception as e:
            self.update_signal.emit(f"转录处理失败: {str(e)}")
            # 即使转录失败，下载成功也要返回成功
            self.result_signal.emit(download_result)
            self.finished_signal.emit(True, f"下载完成，转录失败: {str(e)}")
    
    def run(self):
        """执行视频下载"""
        try:
            self.update_signal.emit("开始下载视频...")
            self.progress_signal.emit(0, "初始化下载...")
            
            # 创建下载器
            if not DOUYIN_AVAILABLE:
                raise ImportError("抖音模块不可用")
            downloader = DouyinDownloader(self.config, port="8080")
            
            # 进度回调函数
            def progress_callback(message, progress):
                if not self.stopped:
                    self.update_signal.emit(message)
                    self.progress_signal.emit(progress, message)
            
            # 下载视频
            result = downloader.download_video(self.url, progress_callback)
            
            if self.stopped:
                return
                
            if result and result.get("success"):
                # 检查是否需要执行转录和摘要
                if self.config.get("enable_transcription") or self.config.get("generate_article"):
                    self.process_transcription_and_summary(result)
                else:
                    self.result_signal.emit(result)
                    self.finished_signal.emit(True, "下载完成")
            else:
                error_msg = result.get("error", "下载失败") if result else "下载失败"
                self.finished_signal.emit(False, error_msg)
                
        except Exception as e:
            if not self.stopped:
                self.update_signal.emit(f"下载失败: {str(e)}")
                self.finished_signal.emit(False, f"下载失败: {str(e)}")


class DouyinBatchDownloadThread(QThread):
    """抖音批量下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, urls, config):
        super().__init__()
        self.urls = urls
        self.config = config
        self.stopped = False
    
    def stop(self):
        """停止下载"""
        self.stopped = True
    
    def run(self):
        """执行批量下载"""
        try:
            total_count = len(self.urls)
            self.update_signal.emit(f"开始批量下载 {total_count} 个视频...")
            self.progress_signal.emit(0, "初始化批量下载...")
            
            # 创建下载器
            if not DOUYIN_AVAILABLE:
                raise ImportError("抖音模块不可用")
            downloader = DouyinDownloader(self.config, port="8080")
            
            # 进度回调函数
            def progress_callback(message, progress):
                if not self.stopped:
                    self.update_signal.emit(message)
                    self.progress_signal.emit(progress, message)
            
            # 批量下载
            result = downloader.download_videos_batch(self.urls, progress_callback)
            
            if self.stopped:
                return
                
            if result and result.get("success"):
                successful_count = result.get("successful_count", 0)
                failed_count = result.get("failed_count", 0)
                
                result_message = f"批量下载完成\n成功: {successful_count} 个\n失败: {failed_count} 个"
                
                self.result_signal.emit(result)
                self.finished_signal.emit(True, result_message)
            else:
                error_msg = result.get("error", "批量下载失败") if result else "批量下载失败"
                self.finished_signal.emit(False, error_msg)
                
        except Exception as e:
            if not self.stopped:
                self.update_signal.emit(f"批量下载失败: {str(e)}")
                self.finished_signal.emit(False, f"批量下载失败: {str(e)}")


class LiveRecordingThread(QThread):
    """直播录制线程"""
    log_signal = pyqtSignal(str)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.running = False
        self.paused = False
        
    def run(self):
        """运行直播录制"""
        self.running = True
        self.log_signal.emit("🔄 初始化直播录制系统...")
        
        try:
            # 导入直播录制适配器
            from live_recorder_adapter import get_live_recorder_manager
            
            # 获取直播录制管理器
            self.manager = get_live_recorder_manager()
            if not self.manager:
                self.log_signal.emit("❌ 直播录制管理器初始化失败")
                return
            
            # 设置日志回调
            self.manager.set_log_callback(self.log_signal.emit)
            
            # 获取URL列表
            urls = []
            for i in range(self.main_window.live_url_list.count()):
                url = self.main_window.live_url_list.item(i).text()
                if url and url.startswith('http'):
                    urls.append(url)
            
            if not urls:
                self.log_signal.emit("❌ 没有有效的直播间URL")
                return
            
            # 获取设置
            settings = {
                'interval': self.main_window.live_interval_spin.value(),
                'format': self.main_window.live_format_combo.currentText(),
                'quality': self.main_window.live_quality_combo.currentText(),
                'save_path': self.main_window.live_path_input.text(),
                'show_ffmpeg_log': self.main_window.show_ffmpeg_log.isChecked(),
                'save_log': self.main_window.save_log.isChecked()
            }
            
            # 开始监控
            success = self.manager.start_monitoring(urls, settings)
            if not success:
                self.log_signal.emit("❌ 启动监控失败")
                return
            
            # 保持线程运行，等待停止信号
            while self.running:
                self.msleep(1000)
            
        except Exception as e:
            self.log_signal.emit(f"❌ 直播录制系统错误: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # 停止监控
            if hasattr(self, 'manager') and self.manager:
                self.manager.stop_monitoring()
            self.log_signal.emit("🛑 直播录制监控已停止")
    
    def stop(self):
        """停止录制"""
        self.running = False
        self.log_signal.emit("🛑 正在停止直播录制...")


def youtuber():
    try:
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 设置应用程序样式
        app.setStyle("Fusion")
        
        # 设置应用程序图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "icons8-youtube-96.png")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            app.setWindowIcon(app_icon)
        
        # 创建主窗口
        window = MainWindow()
        
        # 显示主窗口
        window.show()
        
        # 进入应用程序主循环
        sys.exit(app.exec())
    except Exception as e:
        print(f"启动应用程序时出错: {str(e)}")
        import traceback
        traceback.print_exc()

# 主函数入口点
if __name__ == "__main__":
    youtuber()
