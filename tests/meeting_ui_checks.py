"""Run separately in the optional PySide environment; no capture or AI calls."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from src.meeting.app import MeetingWindow

class MeetingUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch('src.meeting.app.monitors', return_value=[{'name':'Synthetic screen','x':-1920,'y':0,'width':1920,'height':1080}]),
                        patch('src.meeting.engine.devices', return_value=([{'name':'Synthetic output', 'index':7}],7)),
                        patch('src.meeting.app.DATA', self.root)]
        for p in self.patches: p.start()
        self.window = MeetingWindow(self.root, 'ffmpeg', self.root / 'models')
        self.window.timer.stop()
    def tearDown(self):
        self.window.cancel_countdown = True
        self.window.recorder = None
        self.window.close()
        self.app.processEvents()
        for p in self.patches: p.stop()
        self.temp.cleanup()
    def test_nothing_captured_on_open_and_countdown_can_cancel(self):
        self.assertIsNone(self.window.recorder)
        self.assertFalse(self.window.translate.isChecked())
        self.window.countdown()
        self.assertFalse(self.window.screens.isEnabled())
        self.assertTrue(self.window.stop_button.isEnabled())
        self.assertEqual(list(self.root.iterdir()), [])
        self.window.stop()
        self.assertTrue(self.window.cancel_countdown)
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertIsNone(self.window.recorder)
    def test_region_rejected_before_recording(self):
        self.window.mode.setCurrentIndex(1)
        self.window.coordinates[0].setValue(1900)
        self.window.countdown()
        self.assertIn('超出', self.window.status.text())
        self.assertIsNone(self.window.recorder)
        self.assertTrue(self.window.start_button.isEnabled())
    def test_recording_controls_and_post_meeting_actions(self):
        (self.root / 'meeting.mp4').write_bytes(b'fixture')
        self.window.root = self.root
        self.window.locked(True)
        self.assertFalse(self.window.configure.isEnabled())
        self.assertFalse(self.window.learning.isEnabled())
        self.window.finished(self.root / 'meeting.mp4')
        self.assertTrue(self.window.learning.isEnabled())
        self.assertTrue(self.window.complete.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())
    def test_no_late_caption_after_stop(self):
        self.window.live = object()
        self.window.recorder = None
        self.window.caption({'text':'must not display', 'translation':'过期'})
        self.assertNotIn('must not display',self.window.overlay.text())
        self.window.live = None

    def test_async_start_and_stop_keep_ui_state_and_save_action(self):
        class StubRecorder:
            def __init__(self, root, *args):
                self.root = root
                self.stop_event = threading.Event()
                self.state = {'status':'starting'}
                self.failure = ''
            def start(self, device):
                self.state['status'] = 'recording'
            def finish(self):
                self.stop_event.set()
                path = self.root / 'meeting.mp4'
                path.write_bytes(b'synthetic')
                return path
        self.window.selected_output = self.root
        self.window.selected_region = {'x':0,'y':0,'width':640,'height':360}
        with patch('src.meeting.app.Recorder',StubRecorder), patch('src.meeting.app.exclude_window',return_value=True):
            self.window.begin()
            self.window.task.wait(2000)
            self.app.processEvents()
            self.assertIn('录制中',self.window.clock.text())
            self.assertIsNotNone(self.window.recorder)
            self.window.stop()
            self.window.task.wait(2000)
            self.app.processEvents()
            self.assertIsNone(self.window.recorder)
            self.assertTrue(self.window.learning.isEnabled())

    def test_worker_completion_and_progress_run_in_gui_thread(self):
        threads = []
        self.window.operation(lambda task: task.progress.emit('synthetic progress'),
                              lambda result: threads.append(QThread.currentThread()))
        self.window.task.wait(2000)
        self.app.processEvents()
        self.assertEqual(threads, [self.app.thread()])
        self.assertEqual(self.window.status.text(), 'synthetic progress')

if __name__=='__main__': unittest.main(verbosity=2)
