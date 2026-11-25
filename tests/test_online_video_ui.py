"""Actual online-video form/handler, isolated from services and user settings."""

import ast
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import QtWidgets
from PyQt6.QtCore import QSettings

from src.ui_preferences import ONLINE_VIDEO_CHECKBOX_DEFAULTS, UIPreferences


class URLInput(QtWidgets.QLineEdit):
    def set_cookies_file(self, value):
        pass


class Worker:
    def __init__(self, task_type, params):
        self.task_type, self.params = task_type, params
        self.update_signal = self.finished_signal = SimpleNamespace(connect=lambda slot: None)

    def start(self):
        pass


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def form(app, tmp_path):
    tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
    names = {"create_youtube_tab", "bind_persistent_checkbox", "create_translation_target_combo", "get_combo_data", "process_youtube"}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {name: getattr(QtWidgets, name) for name in dir(QtWidgets) if name.startswith("Q")}
    namespace.update(os=os, URLLineEdit=URLInput, WorkerThread=Worker,
                     ONLINE_VIDEO_CHECKBOX_DEFAULTS=ONLINE_VIDEO_CHECKBOX_DEFAULTS,
                     DEFAULT_SUMMARY_DIR=str(tmp_path), normalize_youtube_video_url=lambda value: value)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(__file__), "exec"), namespace)
    window = namespace["MainWindow"]()
    window.ui_preferences = UIPreferences(QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat))
    for name in ["learn_current_download", "stop_current_task", "add_youtube_to_idle_queue", "browse_cookies_file",
                 "auto_get_cookies", "show_cookies_help", "update_youtube_output", "on_youtube_finished"]:
        setattr(window, name, lambda *args: None)
    window.proxy_input = QtWidgets.QLineEdit()
    window.get_model_and_base_url = lambda: ("synthetic", "https://example.invalid")
    window.is_translation_polish_enabled = lambda: False
    yield window
    window.close()


@pytest.mark.parametrize("transcription,subtitles", [(True, False), (False, True), (False, False)])
def test_unified_option_migrates_legacy_state_and_remembers_explicit_choice(form, transcription, subtitles):
    form.ui_preferences.set_bool("online_video/enable_transcription", transcription)
    form.ui_preferences.set_bool("online_video/generate_subtitles", subtitles)
    tab = form.create_youtube_tab()
    unified = form.enable_transcription_checkbox
    assert unified is form.generate_subtitles_checkbox
    assert unified.isChecked() == (transcription or subtitles)
    assert len([box for box in tab.findChildren(QtWidgets.QCheckBox) if box.text() == "转录并生成字幕"]) == 1
    assert not any(box.text() in {"生成字幕文件", "执行转录（音频转文字）"} for box in tab.findChildren(QtWidgets.QCheckBox))
    unified.setChecked(True)
    unified.setChecked(False)
    # A saved explicit False takes priority over the older True settings.
    reopened = form.create_youtube_tab()
    assert not form.enable_transcription_checkbox.isChecked()
    tab.deleteLater()
    reopened.deleteLater()


@pytest.mark.parametrize("enabled", [True, False])
def test_processing_uses_the_same_value_for_transcription_and_subtitle_generation(form, enabled):
    tab = form.create_youtube_tab()
    form.youtube_url_input.setText("https://www.youtube.com/watch?v=synthetic")
    form.generate_article_checkbox.setChecked(True)
    form.enable_transcription_checkbox.setChecked(enabled)
    form.process_youtube()
    assert form.worker_thread.task_type == "youtube"
    assert form.worker_thread.params["enable_transcription"] is enabled
    assert form.worker_thread.params["generate_subtitles"] is enabled
    tab.deleteLater()
