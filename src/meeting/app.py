"""Optional PySide6 UI, launched in its own process from VideoHub's PyQt GUI."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QTimer, QLockFile
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QLineEdit, QFileDialog, QMessageBox, QSystemTrayIcon,
    QMenu, QDialog, QDialogButtonBox,
)

from .project import new_project, save_live
from .recording import Recorder, finalize
from .live import LiveCaptions, complete_project
from .translation import TranslationStore, TranslationError, MODELS
from .windows import audio_capture, exclude_window, monitors, region_for

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'VideoHubMeeting'


def configure_fonts(app):
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Microsoft YaHei', 10))


class Task(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.done.emit(self.operation(self))
        except Exception as error:
            self.failed.emit(str(error) if isinstance(error, (ValueError, InterruptedError, TranslationError)) else '操作失败，请检查设备、模型或磁盘；原始媒体保留')


class Signals(QObject):
    caption = Signal(object)
    status = Signal(str)


class Settings(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle('翻译设置')
        self.store = store
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('本地翻译完全离线。DeepSeek仅发送识别出的英文片段，按API用量计费。\n保存设置不会开始录音或调用模型。'))
        form = QFormLayout()
        self.provider, self.model = QComboBox(), QComboBox()
        self.provider.addItem('本地离线 OPUS-MT', 'local')
        self.provider.addItem('DeepSeek 官方API', 'deepseek')
        self.model.addItems(MODELS)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('留空沿用已保存密钥；使用Windows用户加密保存')
        form.addRow('翻译方式', self.provider)
        form.addRow('模型', self.model)
        form.addRow('API Key', self.key)
        layout.addLayout(form)
        config = store.load()
        self.provider.setCurrentIndex(self.provider.findData(config['provider']))
        self.model.setCurrentText(config['model'])
        self.error = QLabel()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            self.store.save(self.provider.currentData(), self.model.currentText(), self.key.text())
        except Exception:
            self.error.setText('保存失败，请检查密钥格式及目录权限')
            return
        self.key.clear()
        self.accept()


class CaptionOverlay(QLabel):
    def __init__(self):
        super().__init__('正在等待英文发言…')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resize(900, 150)
        self.setStyleSheet('background:#15232a;color:#f2e6c8;padding:18px;font-size:27px;border-radius:12px;')
        self.drag_start = None

    def mousePressEvent(self, event):
        self.drag_start = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start)

    def mouseReleaseEvent(self, event):
        self.drag_start = None


class MeetingWindow(QWidget):
    def __init__(self, output: Path, ffmpeg: str, models: Path):
        super().__init__()
        self.output, self.ffmpeg, self.models = output, ffmpeg, models
        self.recorder = self.live = self.task = self.root = None
        self.cancel_countdown = False
        self.store = TranslationStore(DATA)
        self.overlay = CaptionOverlay()
        self.signals = Signals()
        self.signals.caption.connect(self.caption)
        self.signals.status.connect(self.status_message)
        self.setWindowTitle('VideoHub · 会议翻译与录屏')
        self.resize(760, 640)
        layout = QVBoxLayout(self)
        description = QLabel('录屏、系统声音与中英字幕保存为一个学习工程。只有点击开始后才采集。\n首版不采集麦克风；自己的发言需由会议播放声音包含或另行录音。')
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.title = QLineEdit('会议学习')
        self.screens = QComboBox()
        self.screen_items = monitors()
        for screen in self.screen_items:
            self.screens.addItem(f"{screen['name']} · {screen['width']}×{screen['height']}")
        self.mode = QComboBox()
        self.mode.addItems(['整个所选屏幕', '固定区域（相对所选屏幕的像素）'])
        self.region = QWidget()
        region_layout = QHBoxLayout(self.region)
        region_layout.setContentsMargins(0, 0, 0, 0)
        self.coordinates = []
        for name, value in [('X', 0), ('Y', 0), ('宽', 1280), ('高', 720)]:
            spin = QSpinBox()
            spin.setRange(0 if name in ('X', 'Y') else 128, 20000)
            spin.setValue(value)
            spin.setPrefix(name + ' ')
            self.coordinates.append(spin)
            region_layout.addWidget(spin)
        self.region.hide()
        self.mode.currentIndexChanged.connect(self.region_mode)
        self.devices = QComboBox()
        self.device_refresh = QPushButton('刷新设备')
        self.device_refresh.clicked.connect(self.refresh_devices)
        device_row = QWidget()
        row = QHBoxLayout(device_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.devices, 1)
        row.addWidget(self.device_refresh)
        self.destination = QLineEdit(str(output))
        self.choose = QPushButton('选择保存目录')
        self.choose.clicked.connect(self.choose_folder)
        destination_row = QWidget()
        row = QHBoxLayout(destination_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.destination, 1)
        row.addWidget(self.choose)
        form.addRow('工程名称', self.title)
        form.addRow('录制屏幕', self.screens)
        form.addRow('录制范围', self.mode)
        form.addRow('区域', self.region)
        self.region_label = form.labelForField(self.region)
        self.region_label.hide()
        form.addRow('系统声音', device_row)
        form.addRow('保存目录', destination_row)
        layout.addLayout(form)
        self.translate = QCheckBox('同时显示实时英文→中文字幕（可能有延迟或缺段，原始录音仍完整保存）')
        layout.addWidget(self.translate)
        self.english = QCheckBox('悬浮字幕同时显示英文')
        self.english.setChecked(True)
        layout.addWidget(self.english)
        self.configure = QPushButton('翻译设置 · 本地 / DeepSeek')
        self.configure.clicked.connect(self.settings)
        layout.addWidget(self.configure)
        self.models_label = QLabel('本地模型目录：' + str(models))
        self.models_label.setWordWrap(True)
        layout.addWidget(self.models_label)
        controls = QHBoxLayout()
        self.start_button = QPushButton('开始录制（3秒倒计时）')
        self.stop_button = QPushButton('停止录制 / 取消倒计时')
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.countdown)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        self.clock = QLabel('未开始录制')
        self.status = QLabel('就绪。所选播放设备的所有声音都会被录入，请先核对屏幕范围和声音设备。')
        self.status.setWordWrap(True)
        layout.addWidget(self.clock)
        layout.addWidget(self.status)
        self.project_label = QLabel()
        self.project_label.setWordWrap(True)
        layout.addWidget(self.project_label)
        after = QHBoxLayout()
        self.learning = QPushButton('在视频学习中打开')
        self.complete = QPushButton('会后完整转写并翻译')
        self.recover = QPushButton('恢复未完成录制')
        self.learning.setEnabled(False)
        self.complete.setEnabled(False)
        self.learning.clicked.connect(self.open_learning)
        self.complete.clicked.connect(self.complete_recording)
        self.recover.clicked.connect(self.recover_recording)
        after.addWidget(self.learning)
        after.addWidget(self.complete)
        after.addWidget(self.recover)
        layout.addLayout(after)
        self.tray = QSystemTrayIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon), self)
        self.tray.setToolTip('VideoHub 会议录屏')
        menu = QMenu(self)
        menu.addAction('显示录制面板', self.showNormal)
        menu.addAction('停止录制', self.stop)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.refresh_devices()

    @Slot(str)
    def status_message(self, message):
        if isinstance(self.sender(), Task) and self.sender() is not self.task:
            return
        self.status.setText(message)

    def region_mode(self, mode):
        self.region.setVisible(mode == 1)
        self.region_label.setVisible(mode == 1)

    def settings(self):
        Settings(self.store, self).exec()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '选择会议工程保存目录', self.destination.text())
        if path:
            self.destination.setText(path)

    def refresh_devices(self):
        from .engine import devices
        try:
            items, default = devices()
            self.devices.clear()
            for item in items:
                self.devices.addItem(item['name'], item['index'])
            self.devices.setCurrentIndex(max(0, self.devices.findData(default)))
        except Exception:
            self.status.setText('未找到系统声音设备，请连接扬声器/耳机并刷新')

    def locked(self, busy):
        for widget in (self.title, self.screens, self.mode, self.region, self.devices, self.device_refresh,
                       self.destination, self.choose, self.translate, self.configure, self.recover):
            widget.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.learning.setEnabled(not busy and bool(self.root and (self.root / 'meeting.mp4').is_file()))
        self.complete.setEnabled(self.learning.isEnabled())

    def countdown(self):
        if self.task and self.task.isRunning():
            return
        try:
            if self.devices.currentData() is None or not self.screen_items:
                raise ValueError('请先选择屏幕和系统声音设备')
            screen = self.screen_items[self.screens.currentIndex()]
            self.selected_region = region_for(screen, *(s.value() for s in self.coordinates)) if self.mode.currentIndex() else region_for(screen)
            self.selected_output = Path(self.destination.text()).expanduser().resolve()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.cancel_countdown = False
        self.locked(True)
        self.stop_button.setEnabled(True)
        self.remaining = 3
        self.count_step()

    def count_step(self):
        if self.cancel_countdown:
            return
        if self.remaining:
            self.clock.setText(f'{self.remaining} 秒后开始录制，可点击停止取消')
            self.remaining -= 1
            QTimer.singleShot(1000, self.count_step)
            return
        self.begin()

    def operation(self, operation, done):
        if self.task and self.task.isRunning():
            return
        self.task = Task(operation, self)
        self.task.completion = done
        self.task.progress.connect(self.status_message)
        self.task.done.connect(self.task_done)
        self.task.failed.connect(self.failed)
        self.task.start()

    @Slot(object)
    def task_done(self, result):
        task = self.sender()
        if task is self.task:
            task.completion(result)

    def begin(self):
        try:
            self.root = new_project(self.selected_output, self.title.text())
        except OSError:
            self.failed('无法创建会议工程，请检查保存目录权限和剩余空间；尚未开始采集')
            return
        self.project_label.setText(str(self.root))
        if self.translate.isChecked():
            self.live = LiveCaptions(self.signals.caption.emit, self.signals.status.emit, self.store)
        else:
            self.live = None
        self.recorder = Recorder(self.root, self.title.text(), self.ffmpeg, self.selected_region,
                                 audio_capture, self.live.feed if self.live else None)
        if not exclude_window(self):
            if self.live:
                self.overlay.hide()
            self.status.setText('系统不支持排除字幕窗，将隐藏悬浮字幕；录制面板可最小化，托盘菜单仍可停止')
            self.showMinimized()
        self.operation(lambda task: self.recorder.start(self.devices.currentData()), self.started)

    def started(self, result):
        self.started_at = time.monotonic()
        self.clock.setText('录制中 00:00:00')
        self.status.setText('正在保存屏幕和系统声音；停止按钮或托盘菜单可结束录制')
        if self.live:
            self.overlay.show()
            if not exclude_window(self.overlay):
                self.overlay.hide()
                self.status.setText('屏幕仍在录制；系统无法排除字幕浮窗，已隐藏以保留干净原片')

    @Slot(object)
    def caption(self, row):
        if not self.live or not self.recorder or self.recorder.stop_event.is_set():
            return
        self.overlay.setText((row['text'] + '\n' if self.english.isChecked() else '') + row.get('translation', ''))
        self.persist_live()

    def persist_live(self):
        if self.live and self.recorder and self.root:
            state = self.recorder.state
            offset = state.get('audio_epoch', 0) - state.get('video_epoch', state.get('audio_epoch', 0))
            save_live(self.root, self.live.snapshot(), offset)

    def tick(self):
        if self.recorder and self.recorder.state['status'] == 'recording':
            elapsed = int(time.monotonic() - getattr(self, 'started_at', time.monotonic()))
            self.clock.setText(f'录制中 {elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}')
            self.recorder.save()
            if self.recorder.video.poll() is not None:
                self.recorder.fail('屏幕编码意外停止，已录媒体保留，请恢复封装')
        if self.recorder and self.recorder.failure and not (self.task and self.task.isRunning()):
            self.stop()

    def stop(self):
        if self.task and self.task.isRunning():
            if self.recorder:
                self.recorder.stop_event.set()
            self.task.cancelled.set()
            return
        if not self.recorder:
            self.cancel_countdown = True
            self.locked(False)
            self.stop_button.setEnabled(False)
            self.clock.setText('已取消倒计时')
            return
        self.stop_button.setEnabled(False)
        self.overlay.hide()
        if self.live:
            self.live.close()
            self.persist_live()
        self.clock.setText('录制已停止，正在封装学习工程…')
        recorder = self.recorder
        self.operation(lambda task: recorder.finish(), self.finished)

    def finished(self, path):
        self.recorder = None
        self.live = None
        self.overlay.hide()
        self.clock.setText('已保存录制工程')
        self.status.setText('实时字幕可能缺段。可选择会后完整转写，或直接打开学习页；原始媒体已保留。')
        self.locked(False)
        self.stop_button.setEnabled(False)
        self.showNormal()

    @Slot(str)
    def failed(self, error):
        if isinstance(self.sender(), Task) and self.sender() is not self.task:
            return
        self.overlay.hide()
        if self.live:
            self.live.close()
        self.live = None
        self.recorder = None
        self.status.setText(error)
        self.clock.setText('操作未完成；原始媒体保留')
        self.locked(False)
        self.stop_button.setEnabled(False)
        self.showNormal()

    def open_learning(self):
        root = self.root
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..meeting_desktop import open_project
        self.operation(lambda task: open_project(root), lambda url: QDesktopServices.openUrl(QUrl(url)))

    def complete_recording(self):
        if not self.root:
            return
        config = self.store.load()
        label = 'DeepSeek，将发送完整录音识别出的英文并按API用量计费' if config['provider'] == 'deepseek' else '本机离线模型'
        if QMessageBox.question(self, '会后完整转写', '从完整原始录音重转写，并使用' + label + '翻译。是否开始？') != QMessageBox.StandardButton.Yes:
            return
        self.locked(True)
        self.stop_button.setEnabled(True)
        self.operation(lambda task: complete_project(self.root, self.models, self.store, task.cancelled, task.progress.emit),
                       lambda result: self.completed())

    def completed(self):
        self.locked(False)
        self.stop_button.setEnabled(False)
        self.status.setText('完整字幕已保存；学习页“字幕版本”可选择meeting.full原文和译文')

    def recover_recording(self):
        directory = QFileDialog.getExistingDirectory(self, '选择未完成的会议工程', self.destination.text())
        if not directory:
            return
        self.root = Path(directory)
        try:
            state = json.loads((self.root / 'meeting.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.status.setText('此目录没有有效会议录制清单')
            return
        if (self.root / 'meeting.mp4').is_file():
            self.completed()
            return
        self.project_label.setText(str(self.root))
        self.locked(True)
        self.operation(lambda task: finalize(self.root, self.ffmpeg, state), self.finished)

    def closeEvent(self, event):
        if self.recorder or (self.task and self.task.isRunning()):
            self.status.setText('请先停止并等待保存完成，再关闭窗口；也可通过托盘菜单停止')
            self.showNormal()
            event.ignore()
            return
        self.cancel_countdown = True
        self.overlay.close()
        self.tray.hide()
        event.accept()


def main(output, ffmpeg, models):
    DATA.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_fonts(app)
    lock = QLockFile(str(DATA / 'meeting.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None, '会议录屏', '会议录屏已经打开，请从任务栏找到窗口')
        return 0
    window = MeetingWindow(output, ffmpeg, models)
    window.show()
    return app.exec()
