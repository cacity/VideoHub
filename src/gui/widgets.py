"""
自定义 Qt 组件
从 main.py 提取的 GUI 组件
"""

import os
import re
from PyQt6.QtWidgets import QLineEdit, QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QAction, QClipboard, QEnterEvent


def safe_douyin_utils():
    """安全获取 DouyinUtils，失败返回 None"""
    try:
        from douyin import DouyinUtils
        return DouyinUtils()
    except ImportError:
        return None


class DouyinLineEdit(QLineEdit):
    """支持智能粘贴的抖音URL输入框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

    def keyPressEvent(self, event):
        """处理键盘事件，支持Ctrl+V智能粘贴"""
        try:
            if event.matches(QKeySequence.StandardKey.Paste):
                print("[键盘] 检测到Ctrl+V，执行智能粘贴")
                self.smart_paste()
                return
            super().keyPressEvent(event)
        except Exception as e:
            print(f"[键盘] 处理键盘事件错误: {e}")
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """直接执行智能粘贴，不显示菜单"""
        self.smart_paste()
        event.accept()

    def smart_paste(self):
        """智能粘贴功能"""
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()

            print(f"[智能粘贴] 剪贴板内容: {clipboard_text[:100] if clipboard_text else '空'}...")

            if clipboard_text:
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
                        is_user_profile = utils.is_user_profile_share_text(clipboard_text)
                        if self.main_window is not None:
                            self.main_window._pending_douyin_url_is_user = is_user_profile
                        if hasattr(self.main_window, 'douyin_status_label'):
                            if is_user_profile:
                                self.main_window.douyin_status_label.setText("✅ 已提取用户主页链接")
                                self.main_window.douyin_status_label.setStyleSheet("color: #2196F3;")
                            else:
                                self.main_window.douyin_status_label.setText("✅ 已从剪贴板提取有效链接")
                                self.main_window.douyin_status_label.setStyleSheet("color: #4CAF50;")
                        print("[智能粘贴] 设置URL成功")
                    else:
                        print("[智能粘贴] 未找到有效链接，使用普通粘贴")
                        if hasattr(self.main_window, 'douyin_status_label'):
                            self.main_window.douyin_status_label.setText("⚠️ 未检测到抖音链接，已使用普通粘贴")
                            self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
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
            if event.matches(QKeySequence.StandardKey.Paste):
                print("[键盘] 检测到Ctrl+V，执行批量智能粘贴")
                self.smart_paste()
                return
            super().keyPressEvent(event)
        except Exception as e:
            print(f"[键盘] 处理键盘事件错误: {e}")
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """直接执行智能粘贴，不显示菜单"""
        self.smart_paste()
        event.accept()

    def smart_paste(self):
        """智能粘贴功能"""
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()

            print(f"[批量智能粘贴] 剪贴板内容: {clipboard_text[:100] if clipboard_text else '空'}...")

            if clipboard_text:
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

                    all_urls = utils.extract_urls_from_text(clipboard_text)
                    valid_urls = []

                    print(f"[批量智能粘贴] 发现URL: {all_urls}")

                    for url in all_urls:
                        if utils.validate_url(url):
                            valid_urls.append(url)

                    if not valid_urls:
                        extracted = utils.parse_share_text(clipboard_text)
                        print(f"[批量智能粘贴] 分享文本提取结果: {extracted}")
                        if extracted:
                            valid_urls.append(extracted)

                    print(f"[批量智能粘贴] 有效链接: {valid_urls}")

                    if valid_urls:
                        current_text = self.toPlainText()

                        new_lines = []
                        for url in valid_urls:
                            if url not in current_text:
                                new_lines.append(url)

                        if new_lines:
                            if current_text and not current_text.endswith('\n'):
                                current_text += '\n'

                            new_content = current_text + '\n'.join(new_lines)
                            self.setPlainText(new_content)

                            if hasattr(self.main_window, 'douyin_status_label'):
                                self.main_window.douyin_status_label.setText(f"✅ 已添加 {len(new_lines)} 个有效链接")
                                self.main_window.douyin_status_label.setStyleSheet("color: #4CAF50;")
                            print(f"[批量智能粘贴] 成功添加 {len(new_lines)} 个链接")
                        else:
                            if hasattr(self.main_window, 'douyin_status_label'):
                                self.main_window.douyin_status_label.setText("ℹ️ 所有链接已存在")
                                self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
                            print("[批量智能粘贴] 所有链接已存在")
                    else:
                        print("[批量智能粘贴] 未找到有效链接，使用普通粘贴")
                        if hasattr(self.main_window, 'douyin_status_label'):
                            self.main_window.douyin_status_label.setText("⚠️ 未检测到抖音链接，已使用普通粘贴")
                            self.main_window.douyin_status_label.setStyleSheet("color: #FF9800;")
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

        if (current_url and
            ('youtube.com/watch' in current_url or 'youtu.be/' in current_url) and
            current_url != self.last_url):

            self.hover_timer.start(800)
            self.last_url = current_url

    def leaveEvent(self, event):
        """鼠标离开事件"""
        super().leaveEvent(event)
        self.hover_timer.stop()
        self.setToolTip("")

    def fetch_video_info(self):
        """获取视频信息并设置工具提示"""
        current_url = self.text().strip()
        if not current_url:
            return

        try:
            from youtube_transcriber import get_youtube_video_title, format_video_tooltip

            self.setToolTip("🔄 正在获取视频信息...")

            video_info = get_youtube_video_title(current_url, self.cookies_file)

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
        self.last_url = ""
        self.setToolTip("")

    def contextMenuEvent(self, event):
        """右键直接粘贴，不显示菜单"""
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()

        if clipboard_text:
            # 检查剪贴板是否包含抖音分享内容
            is_douyin_share = '抖音' in clipboard_text or 'douyin' in clipboard_text.lower()

            if is_douyin_share:
                # 抖音分享内容：使用智能粘贴提取链接
                utils = safe_douyin_utils()
                if utils:
                    try:
                        extracted_url = utils.parse_share_text(clipboard_text)
                        if extracted_url:
                            self.clear()
                            self.setText(extracted_url)
                            main_win = self.window()
                            if main_win is not None:
                                main_win._pending_douyin_url_is_user = utils.is_user_profile_share_text(clipboard_text)
                            print(f"[智能粘贴] 已提取抖音链接: {extracted_url}")
                            event.accept()
                            return
                    except Exception as e:
                        print(f"[智能粘贴] 提取失败: {e}")
                        # 回退到直接粘贴

            # 直接粘贴剪贴板内容
            self.paste_and_clear(clipboard_text)
        else:
            # 剪贴板为空，也调用默认粘贴操作
            self.paste()

        event.accept()

    def paste_and_clear(self, text):
        """粘贴文本并清空原内容"""
        self.clear()
        self.setText(text.strip() if text else '')


class URLTextEdit(QTextEdit):
    """支持右键直接粘贴的多行URL输入框"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def contextMenuEvent(self, event):
        """重写右键菜单事件"""
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()

        if clipboard_text:
            if any(keyword in clipboard_text.lower() for keyword in ['http', 'youtube', 'youtu.be', 'twitter.com', 'x.com', 'bilibili', 'instagram.com', 'instagr.am', 'tiktok.com', 'www.']):
                if not self.toPlainText().strip():
                    self.clear()
                    self.setPlainText(clipboard_text.strip())
                    event.accept()
                    return
                else:
                    current_text = self.toPlainText().strip()
                    new_text = current_text + '\n' + clipboard_text.strip()
                    self.setPlainText(new_text)
                    event.accept()
                    return

        menu = self.createStandardContextMenu()

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


class CollapsibleGroupBox(QWidget):
    """可折叠的分组框组件，用于节省界面空间"""

    def __init__(self, title="", parent=None, collapsed=True):
        super().__init__(parent)
        self.is_collapsed = collapsed

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 2)
        self.main_layout.setSpacing(2)

        self.title_frame = QFrame()
        self.title_frame.setFrameShape(QFrame.Shape.NoFrame)
        self.title_frame.setFixedHeight(24)
        self.title_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 0px;
                padding: 0px;
            }
            QFrame:hover {
                background-color: #eeeeee;
            }
        """)

        title_layout = QHBoxLayout(self.title_frame)
        title_layout.setContentsMargins(4, 0, 4, 0)
        title_layout.setSpacing(4)

        blue_line = QFrame()
        blue_line.setFixedWidth(3)
        blue_line.setFixedHeight(12)
        blue_line.setStyleSheet("background-color: #2196F3; border: none;")
        title_layout.addWidget(blue_line)

        self.toggle_button = QPushButton()
        self.toggle_button.setFixedSize(12, 12)
        self.toggle_button.setFlat(True)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 10px;
                color: #2196F3;
            }
        """)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        self.update_toggle_icon()

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333;")

        title_layout.addWidget(self.toggle_button)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        self.title_frame.mousePressEvent = lambda event: self.toggle_collapsed()

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 10, 15, 10)
        self.content_layout.setSpacing(8)

        self.main_layout.addWidget(self.title_frame)
        self.main_layout.addWidget(self.content_widget)

        self.content_widget.setVisible(not collapsed)

    def update_toggle_icon(self):
        """更新折叠/展开图标"""
        if self.is_collapsed:
            self.toggle_button.setText("▶")
        else:
            self.toggle_button.setText("▼")

    def toggle_collapsed(self):
        """切换折叠/展开状态"""
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.update_toggle_icon()

    def set_collapsed(self, collapsed):
        """设置折叠状态"""
        self.is_collapsed = collapsed
        self.content_widget.setVisible(not collapsed)
        self.update_toggle_icon()

    def add_layout(self, layout):
        """添加布局到内容区域"""
        self.content_layout.addLayout(layout)

    def add_widget(self, widget):
        """添加组件到内容区域"""
        self.content_layout.addWidget(widget)
