#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
字幕视频合成工具
使用ffmpeg将ASS字幕烧录到视频中
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QGroupBox, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent


class MergeThread(QThread):
    """合成线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, video_path, subtitle_path, output_path, quality_mode, copy_audio):
        super().__init__()
        self.video_path = video_path
        self.subtitle_path = subtitle_path
        self.output_path = output_path
        self.quality_mode = quality_mode
        self.copy_audio = copy_audio
        self.process = None

    def run(self):
        try:
            # 构建ffmpeg命令
            cmd = self.build_ffmpeg_command()

            self.update_signal.emit(f"执行命令: {' '.join(cmd)}\n")

            # 执行ffmpeg
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore'
            )

            # 获取视频时长（用于进度计算）
            duration = self.get_video_duration(self.video_path)

            # 读取ffmpeg输出
            for line in self.process.stderr:
                self.update_signal.emit(line)

                # 解析进度
                if duration and "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split()[0]
                        current_seconds = self.time_to_seconds(time_str)
                        progress = int((current_seconds / duration) * 100)
                        self.progress_signal.emit(min(progress, 99))
                    except:
                        pass

            # 等待进程完成
            self.process.wait()

            if self.process.returncode == 0:
                self.progress_signal.emit(100)
                self.update_signal.emit("\n✅ 合成完成！\n")
                self.finished_signal.emit(True, self.output_path)
            else:
                self.update_signal.emit("\n❌ 合成失败！\n")
                self.finished_signal.emit(False, "")

        except Exception as e:
            self.update_signal.emit(f"\n❌ 错误: {str(e)}\n")
            self.finished_signal.emit(False, "")

    def build_ffmpeg_command(self):
        """构建ffmpeg命令"""
        # 转换路径为绝对路径并规范化
        subtitle_path = os.path.abspath(self.subtitle_path)

        # Windows 路径特殊处理：需要转义冒号和反斜杠
        if os.name == 'nt':  # Windows
            # 将反斜杠替换为正斜杠
            subtitle_path = subtitle_path.replace('\\', '/')
            # 转义冒号（C: -> C\\:）
            subtitle_path = subtitle_path.replace(':', '\\\\:')

        cmd = ['ffmpeg', '-i', self.video_path]

        # 视频滤镜 - 烧录字幕
        # 在 Windows 上路径已经转义，直接使用
        vf = f"ass={subtitle_path}"

        cmd.extend(['-vf', vf])

        # 根据质量模式选择编码参数
        if self.quality_mode == "无损（最高质量，文件大）":
            # 使用H.264无损编码
            cmd.extend(['-c:v', 'libx264', '-preset', 'veryslow', '-qp', '0'])
        elif self.quality_mode == "极高质量（接近无损）":
            # CRF 0 = 无损, CRF 18 = 视觉无损
            cmd.extend(['-c:v', 'libx264', '-preset', 'slow', '-crf', '0'])
        elif self.quality_mode == "高质量（推荐）":
            # CRF 18
            cmd.extend(['-c:v', 'libx264', '-preset', 'medium', '-crf', '18'])
        elif self.quality_mode == "平衡质量（较快）":
            # CRF 23
            cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23'])

        # 音频处理
        if self.copy_audio:
            cmd.extend(['-c:a', 'copy'])
        else:
            cmd.extend(['-c:a', 'aac', '-b:a', '320k'])

        # 输出文件
        cmd.extend(['-y', self.output_path])

        return cmd

    def get_video_duration(self, video_path):
        """获取视频时长（秒）"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return None

    def time_to_seconds(self, time_str):
        """将时间字符串转换为秒"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except:
            pass
        return 0

    def stop(self):
        """停止合成"""
        if self.process:
            self.process.terminate()


class DragDropLineEdit(QLineEdit):
    """支持拖放的输入框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            self.setText(file_path)


class SubtitleMergerWindow(QMainWindow):
    """字幕视频合成主窗口"""

    def __init__(self):
        super().__init__()
        self.merge_thread = None
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("字幕视频合成工具")
        self.setGeometry(100, 100, 800, 600)

        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel("字幕视频合成工具")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 文件选择组
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)

        # 视频文件
        video_layout = QHBoxLayout()
        video_label = QLabel("视频文件:")
        video_label.setFixedWidth(80)
        self.video_input = DragDropLineEdit()
        self.video_input.setPlaceholderText("选择或拖放视频文件（支持mp4、avi、mkv等格式）")
        video_btn = QPushButton("浏览...")
        video_btn.setFixedWidth(80)
        video_btn.clicked.connect(self.select_video)
        video_layout.addWidget(video_label)
        video_layout.addWidget(self.video_input)
        video_layout.addWidget(video_btn)
        file_layout.addLayout(video_layout)

        # 字幕文件
        subtitle_layout = QHBoxLayout()
        subtitle_label = QLabel("字幕文件:")
        subtitle_label.setFixedWidth(80)
        self.subtitle_input = DragDropLineEdit()
        self.subtitle_input.setPlaceholderText("选择或拖放ASS字幕文件")
        subtitle_btn = QPushButton("浏览...")
        subtitle_btn.setFixedWidth(80)
        subtitle_btn.clicked.connect(self.select_subtitle)
        subtitle_layout.addWidget(subtitle_label)
        subtitle_layout.addWidget(self.subtitle_input)
        subtitle_layout.addWidget(subtitle_btn)
        file_layout.addLayout(subtitle_layout)

        # 输出文件
        output_layout = QHBoxLayout()
        output_label = QLabel("输出文件:")
        output_label.setFixedWidth(80)
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("选择输出文件路径")
        output_btn = QPushButton("浏览...")
        output_btn.setFixedWidth(80)
        output_btn.clicked.connect(self.select_output)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_input)
        output_layout.addWidget(output_btn)
        file_layout.addLayout(output_layout)

        layout.addWidget(file_group)

        # 设置组
        settings_group = QGroupBox("合成设置")
        settings_layout = QVBoxLayout(settings_group)

        # 质量模式
        quality_layout = QHBoxLayout()
        quality_label = QLabel("质量模式:")
        quality_label.setFixedWidth(80)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "无损（最高质量，文件大）",
            "极高质量（接近无损）",
            "高质量（推荐）",
            "平衡质量（较快）"
        ])
        self.quality_combo.setCurrentIndex(2)  # 默认"高质量"
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        settings_layout.addLayout(quality_layout)

        # 音频处理
        audio_layout = QHBoxLayout()
        self.copy_audio_check = QCheckBox("直接复制音频流（不重新编码）")
        self.copy_audio_check.setChecked(True)
        audio_layout.addWidget(self.copy_audio_check)
        audio_layout.addStretch()
        settings_layout.addLayout(audio_layout)

        layout.addWidget(settings_group)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.merge_btn = QPushButton("开始合成")
        self.merge_btn.setFixedHeight(40)
        self.merge_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.merge_btn.clicked.connect(self.start_merge)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_merge)

        button_layout.addWidget(self.merge_btn)
        button_layout.addWidget(self.stop_btn)
        layout.addLayout(button_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(25)
        layout.addWidget(self.progress_bar)

        # 日志输出
        log_label = QLabel("合成日志:")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', monospace;")
        layout.addWidget(self.log_text)

        # 提示信息
        hint_label = QLabel("💡 提示：支持拖放文件到输入框 | 使用FFmpeg进行合成")
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(hint_label)

    def select_video(self):
        """选择视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.video_input.setText(file_path)
            # 自动生成输出文件名
            if not self.output_input.text():
                self.auto_generate_output_path(file_path)

    def select_subtitle(self):
        """选择字幕文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字幕文件",
            "",
            "ASS字幕文件 (*.ass);;所有文件 (*.*)"
        )
        if file_path:
            self.subtitle_input.setText(file_path)

    def select_output(self):
        """选择输出文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            "",
            "MP4文件 (*.mp4);;MKV文件 (*.mkv);;所有文件 (*.*)"
        )
        if file_path:
            self.output_input.setText(file_path)

    def auto_generate_output_path(self, video_path):
        """自动生成输出路径"""
        path = Path(video_path)
        output_path = path.parent / f"{path.stem}_with_subtitle{path.suffix}"
        self.output_input.setText(str(output_path))

    def start_merge(self):
        """开始合成"""
        # 验证输入
        video_path = self.video_input.text().strip()
        subtitle_path = self.subtitle_input.text().strip()
        output_path = self.output_input.text().strip()

        if not video_path or not os.path.exists(video_path):
            QMessageBox.warning(self, "错误", "请选择有效的视频文件！")
            return

        if not subtitle_path or not os.path.exists(subtitle_path):
            QMessageBox.warning(self, "错误", "请选择有效的字幕文件！")
            return

        if not output_path:
            QMessageBox.warning(self, "错误", "请指定输出文件路径！")
            return

        # 检查ffmpeg
        if not self.check_ffmpeg():
            QMessageBox.critical(self, "错误", "未找到FFmpeg！请确保FFmpeg已安装并添加到系统PATH。")
            return

        # 清空日志
        self.log_text.clear()
        self.progress_bar.setValue(0)

        # 禁用按钮
        self.merge_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 创建并启动合成线程
        quality_mode = self.quality_combo.currentText()
        copy_audio = self.copy_audio_check.isChecked()

        self.merge_thread = MergeThread(
            video_path,
            subtitle_path,
            output_path,
            quality_mode,
            copy_audio
        )
        self.merge_thread.update_signal.connect(self.update_log)
        self.merge_thread.progress_signal.connect(self.update_progress)
        self.merge_thread.finished_signal.connect(self.merge_finished)
        self.merge_thread.start()

    def stop_merge(self):
        """停止合成"""
        if self.merge_thread:
            self.merge_thread.stop()
            self.update_log("\n⏹ 用户停止合成\n")
            self.merge_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def update_log(self, message):
        """更新日志"""
        self.log_text.append(message.rstrip())
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)

    def merge_finished(self, success, output_path):
        """合成完成"""
        self.merge_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if success:
            QMessageBox.information(
                self,
                "成功",
                f"字幕已成功合成到视频！\n\n输出文件：\n{output_path}"
            )
        else:
            QMessageBox.warning(
                self,
                "失败",
                "合成失败，请查看日志了解详情。"
            )

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True
            )
            return True
        except:
            return False


def main():
    app = QApplication(sys.argv)
    window = SubtitleMergerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
