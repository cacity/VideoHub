"""Isolated Qt checks: actual form and desktop handlers, no AI or media jobs."""

import ast
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QLineEdit, QMainWindow, QMessageBox, QStatusBar


class Worker(QObject):
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, bool)
    finished = pyqtSignal()

    def __init__(self, task_type, params):
        super().__init__()
        self.task_type, self.params = task_type, params
        self.running = False

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def stop(self):
        self.running = False
        self.finished.emit()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    # Load only the desktop methods under test to avoid starting its API,
    # timers, models, live-recorder integrations, or accessing user settings.
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
    names = {"create_local_files_tab", "run_local_file_action", "create_translation_target_combo", "get_combo_data",
             "process_local_video", "process_local_audio", "process_local_text", "extract_local_video_audio",
             "add_audio_to_idle_queue", "add_video_to_idle_queue", "add_text_to_idle_queue",
             "update_video_output", "update_audio_output", "update_text_output",
             "on_video_finished", "on_audio_finished", "on_text_finished"}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    messages = []
    dialogs = SimpleNamespace(warning=lambda *args: messages.append(args[2]), information=lambda *args: None,
                              question=lambda *args: QMessageBox.StandardButton.No, StandardButton=QMessageBox.StandardButton)
    namespace = {"QMainWindow": QMainWindow, "os": os, "WorkerThread": Worker, "QMessageBox": dialogs,
                 "DEFAULT_SUMMARY_DIR": str(tmp_path / "summaries"), "SONGS_DIR": str(tmp_path / "songs"),
                 "QTextCursor": QTextCursor}
    from PyQt6.QtWidgets import QComboBox
    namespace["QComboBox"] = QComboBox
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    instance = namespace["MainWindow"]()
    instance.worker_thread = None
    instance.proxy_input = QLineEdit()
    instance.get_model_and_base_url = lambda: ("test-model", "https://model.example")
    instance.is_translation_polish_enabled = lambda: True
    instance.stop_current_task = lambda: instance.worker_thread.stop()
    instance.open_directory = lambda name: None
    instance.idle_tasks = []
    instance.save_idle_queue = lambda: None
    instance.refresh_idle_queue_display = lambda: None
    instance.statusBar = QStatusBar()
    panel = instance.create_local_files_tab()
    instance.setCentralWidget(panel)
    instance.resize(900, 700)
    instance.show()
    app.processEvents()
    instance.messages = messages
    yield instance
    instance.close()
    app.processEvents()


@pytest.mark.parametrize("suffix,kind", [(".MP4", "video"), (".mp3", "audio"), (".flac", "audio"), (".txt", "text"), (".md", "text"), ("", "video_directory")])
def test_auto_detection_and_relevant_controls(window, tmp_path, suffix, kind):
    path = tmp_path / ("lesson" + suffix)
    path.write_bytes(b"fixture") if suffix else path.mkdir()
    panel = window.local_files_panel
    panel.path_input.setText(str(path))
    assert panel.validate_input() == kind
    assert panel.media_options.isVisible() == (kind != "text")
    assert panel.text_hint.isVisible() == (kind == "text")
    assert panel.video_options.isVisible() == kind.startswith("video")
    assert panel.extract_group.isVisible() == kind.startswith("video")
    assert panel.series_checkbox.isVisible() == (kind == "video_directory")
    assert window.audio_path_input is window.video_path_input is window.text_path_input
    assert window.audio_output_text is window.video_output_text is window.text_output_text


@pytest.mark.parametrize("suffix,task_type", [(".mp4", "local_video"), (".wav", "local_audio"), (".md", "local_text"), ("", "local_video_batch")])
def test_start_routes_actual_handlers_with_shared_settings_and_recovers_after_stop(window, tmp_path, suffix, task_type):
    path = tmp_path / ("lesson" + suffix)
    path.write_bytes(b"fixture") if suffix else path.mkdir()
    panel = window.local_files_panel
    panel.path_input.setText(str(path))
    panel.subtitles_checkbox.setChecked(True)
    panel.whisper_combo.setCurrentText("medium")
    panel.target_combo.setCurrentIndex(panel.target_combo.findData("ja"))
    panel.process_button.click()
    worker = window.worker_thread
    assert worker.task_type == task_type
    assert worker.params["model"] == "test-model"
    assert str(path) in worker.params.values()
    if task_type != "local_text":
        assert worker.params["target_language"] == "ja"
        assert worker.params["whisper_model_size"] == "medium"
        assert worker.params["generate_subtitles"]
        assert worker.params["enable_translation_polish"]
    if task_type.startswith("local_video"):
        assert worker.params["series_project"] == (task_type == "local_video_batch")
        assert worker.params["source_language"] == "auto"
    assert panel.busy and not panel.input_group.isEnabled()
    assert not panel.idle_button.isEnabled() and panel.stop_button.isEnabled()
    window.run_local_file_action("process")
    assert window.worker_thread is worker and window.messages
    worker.update_signal.emit("progress")
    assert "progress" in panel.output_text.toPlainText()
    panel.stop_button.click()
    assert not panel.busy and panel.process_button.isEnabled() and panel.input_group.isEnabled()
    assert not panel.stop_button.isEnabled()


@pytest.mark.parametrize("suffix,task_type", [(".mp4", "local_video"), (".mp3", "local_audio"), (".txt", "local_text"), ("", "local_video_batch")])
def test_idle_actions_preserve_task_types_and_parameters(window, tmp_path, suffix, task_type):
    path = tmp_path / ("lesson" + suffix)
    path.write_bytes(b"fixture") if suffix else path.mkdir()
    panel = window.local_files_panel
    panel.path_input.setText(str(path))
    panel.idle_button.click()
    assert len(window.idle_tasks) == 1
    task = window.idle_tasks[0]
    assert task["type"] == task_type
    assert str(path) in task["params"].values()
    assert not panel.busy and window.worker_thread is None


@pytest.mark.parametrize("directory", [False, True])
def test_audio_extraction_keeps_directory_recursion(window, tmp_path, directory):
    path = tmp_path / ("videos" if directory else "lesson.mp4")
    path.mkdir() if directory else path.write_bytes(b"fixture")
    panel = window.local_files_panel
    panel.path_input.setText(str(path))
    panel.extract_button.click()
    worker = window.worker_thread
    assert worker.task_type == "extract_audio"
    assert worker.params["recursive"] == directory
    assert worker.params["input_path"] == str(path)
    worker.running = False
    worker.finished_signal.emit("", False)
    worker.finished.emit()
    assert not panel.busy and panel.extract_button.isEnabled()


@pytest.mark.parametrize("suffix", [".mp4", ".mp3", ".txt", ""])
def test_completion_restores_shared_controls_with_original_callbacks(window, tmp_path, suffix):
    path = tmp_path / ("lesson" + suffix)
    path.write_bytes(b"fixture") if suffix else path.mkdir()
    panel = window.local_files_panel
    panel.path_input.setText(str(path))
    panel.process_button.click()
    worker = window.worker_thread
    worker.running = False
    worker.finished_signal.emit(str(path), True)
    worker.finished.emit()
    assert not panel.busy and panel.process_button.isEnabled() and panel.idle_button.isEnabled()
    assert not panel.stop_button.isEnabled() and panel.process_button.text() == "开始处理"


def test_invalid_inputs_never_start_or_enqueue_and_settings_survive_type_switch(window, tmp_path):
    panel = window.local_files_panel
    for path in ["", str(tmp_path / "missing.mp4"), str(tmp_path / "document.pdf")]:
        panel.path_input.setText(path)
        panel.process_button.click()
        panel.idle_button.click()
    audio = tmp_path / "lesson.mp3"
    audio.write_bytes(b"fixture")
    panel.path_input.setText(str(audio))
    panel.kind_combo.setCurrentIndex(panel.kind_combo.findData("video"))
    panel.process_button.click()
    assert window.worker_thread is None and not window.idle_tasks
    assert len(window.messages) == 7
    panel.kind_combo.setCurrentIndex(0)
    panel.summary_checkbox.setChecked(False)
    text = tmp_path / "notes.md"
    text.write_text("hello", encoding="utf-8")
    panel.path_input.setText(str(text))
    panel.path_input.setText(str(audio))
    assert not panel.summary_checkbox.isChecked()


def test_picker_cancel_preserves_input_and_directory_then_file_redetects(window, tmp_path, monkeypatch):
    from src.gui import local_files
    panel = window.local_files_panel
    text = tmp_path / "notes.md"
    text.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(local_files.QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    monkeypatch.setattr(local_files.QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    panel.directory_button.click()
    assert panel.is_video_directory()
    panel.browse_button.click()
    assert panel.path_input.text() == str(tmp_path)
    monkeypatch.setattr(local_files.QFileDialog, "getOpenFileName", lambda *args: (str(text), ""))
    panel.browse_button.click()
    assert panel.input_kind() == "text"
