"""Meeting pipeline regression tests; no screen, microphone or paid API access."""
import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.meeting.project import new_project, save_live, srt
from src.meeting.recording import Recorder, finalize
from src.meeting.windows import region_for


def test_project_separates_languages_and_calibrates_timeline(tmp_path):
    root = new_project(tmp_path, '../会议:课程')
    assert root.parent == tmp_path and (root / 'originals').is_dir()
    rows = [{'start': 1, 'end': 4, 'text': 'English', 'translation': '中文'},
            {'start': 20, 'end': 22, 'text': 'past end', 'translation': ''}]
    save_live(root, rows, offset=-.5, duration=5)
    source = (root / 'subtitles/meeting.live.source.en.srt').read_text(encoding='utf-8')
    target = (root / 'subtitles/meeting.live.target.zh-CN.srt').read_text(encoding='utf-8')
    assert '00:00:00,500 --> 00:00:03,500' in source
    assert '中文' not in source and 'English' not in target and 'past end' not in source
    assert srt([{'start': 0, 'end': .1, 'text': 'before video'}], offset=-1) == ''
    assert srt([{'start': 1., 'end': 1.0004, 'text': 'less than one millisecond'}]) == ''


def test_monitor_coordinates_support_negative_origin_and_dpi_independent_pixels():
    monitor = {'x': -2560, 'y': -200, 'width': 2560, 'height': 1440}
    assert region_for(monitor, 20, 40, 641, 361) == {'x': -2540, 'y': -160, 'width': 640, 'height': 360}
    for invalid in [(0, 0, 100, 720), (-1, 0, 640, 360), (2500, 0, 640, 360)]:
        with pytest.raises(ValueError):
            region_for(monitor, *invalid)


def test_caption_failure_does_not_stop_or_drop_original_pcm(tmp_path):
    root = new_project(tmp_path, 'fixture')
    def bad_caption(*args):
        raise RuntimeError('synthetic ASR failure')
    recorder = Recorder(root, 'fixture', 'ffmpeg', {}, lambda *args: None, bad_caption)
    recorder.state.update(sample_rate=16000, channels=1)
    recorder._frame(b'\x00\x00' * 1600, 100.)
    recorder._frame(b'\x01\x00' * 1600, 100.1)
    assert not recorder.stop_event.is_set() and recorder.samples == 3200
    assert recorder.pcm.qsize() == 2 and recorder.on_audio is None
    assert '暂停' in recorder.state['caption_warning']


def test_recording_queue_overflow_is_visible_and_never_claims_complete(tmp_path):
    root = new_project(tmp_path, 'fixture')
    recorder = Recorder(root, 'fixture', 'ffmpeg', {}, lambda *args: None)
    recorder.state.update(sample_rate=16000, channels=1)
    recorder.pcm = queue.Queue(maxsize=1)
    recorder._frame(b'\x00\x00' * 1600, 100.)
    recorder._frame(b'\x00\x00' * 1600, 100.1)
    assert recorder.stop_event.is_set() and recorder.failure
    assert json.loads((root / 'meeting.json').read_text(encoding='utf-8'))['status'] == 'interrupted'


def test_capture_clock_uses_native_microseconds_not_rounded_scientific_time(tmp_path):
    root = new_project(tmp_path, 'clock')
    recorder = Recorder(root, 'fixture', 'ffmpeg', {}, lambda *args: None)
    line = b'demuxer -> ist_index:0 type:video pkt_pts:1793755126123456 pkt_pts_time:1.79376e+09\n'
    recorder.log(SimpleNamespace(stderr=[line]), video=True)
    assert recorder.video_ready.is_set()
    assert abs(recorder.state['video_epoch'] - 1793755126.123456) < .000001


def test_finalization_preserves_originals_and_generates_learning_project(tmp_path, monkeypatch):
    root = new_project(tmp_path, 'fixture')
    (root / 'originals/screen.mkv').write_bytes(b'original video')
    (root / 'originals/system-audio.mka').write_bytes(b'original audio')
    rows = [{'start': 1., 'end': 2., 'text': 'English', 'translation': '中文'}]
    save_live(root, rows)
    state = {'title': 'Meeting fixture', 'audio_epoch': 100.1, 'video_epoch': 100., 'audio_elapsed': 5.}
    monkeypatch.setattr('src.meeting.recording.media_info', lambda *a: {'format': {'duration': '5'}, 'streams': [{'codec_type': 'video'}]})
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b'muxed')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('src.meeting.recording.subprocess.run', run)
    assert finalize(root, 'ffmpeg', state) == root / 'meeting.mp4'
    assert (root / 'originals/screen.mkv').read_bytes() == b'original video'
    assert (root / 'originals/system-audio.mka').read_bytes() == b'original audio'
    manifest = json.loads((root / 'videohub_learning.json').read_text(encoding='utf-8'))
    assert manifest['video'] == 'meeting.mp4' and len(manifest['subtitles']) == 2
    assert {t['role'] for t in manifest['subtitles']} == {'source', 'target'}
    assert '0.100000' in commands[0]
    assert '00:00:01,100' in (root / 'subtitles/meeting.live.source.en.srt').read_text(encoding='utf-8')
    assert state['status'] == 'finished'


def test_finalization_failure_retains_recovery_media(tmp_path, monkeypatch):
    root = new_project(tmp_path, 'fixture')
    monkeypatch.setattr('src.meeting.recording.media_info', lambda *a: {'format': {'duration': '5'}, 'streams': [{'codec_type': 'video'}]})
    monkeypatch.setattr('src.meeting.recording.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match='原始'):
        finalize(root, 'ffmpeg', {'title': 'fixture', 'audio_epoch': 100., 'video_epoch': 100.})
    assert not (root / 'meeting.mp4').exists()


def test_learning_import_of_recording_has_independent_language_tracks(tmp_path, monkeypatch):
    from src.learning_server import create_app
    from src.learning import media
    root = new_project(tmp_path, 'fixture')
    (root / 'meeting.mp4').write_bytes(b'video')
    save_live(root, [{'start': 0, 'end': 2, 'text': 'A meeting', 'translation': '会议'}])
    monkeypatch.setattr(media, 'probe', lambda p: {'duration': 5, 'browser_ready': True,
                       'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns, 'codec': 'h264'})
    client = create_app(tmp_path / 'learning-store').test_client()
    token = client.get('/api/learning/session').json['token']
    imported = client.post('/api/learning/imports/project', headers={'X-Learning-Token': token}, json={'directory': str(root)})
    assert imported.status_code == 200, imported.json
    detail = imported.json['video']
    assert detail['has_source'] and detail['has_target']
    assert detail['playback_cues']['source'][0]['text'] == 'A meeting'
    assert detail['playback_cues']['target'][0]['text'] == '会议'


def test_desktop_launcher_is_optional_and_does_not_import_qt(tmp_path, monkeypatch):
    from src import meeting_desktop
    python = tmp_path / 'runtime/.venv/Scripts/pythonw.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / 'runtime/models/whisper').mkdir(parents=True)
    monkeypatch.setenv('VIDEOHUB_MEETING_PYTHON', str(python))
    monkeypatch.delenv('VIDEOHUB_MEETING_MODELS', raising=False)
    runtime, models = meeting_desktop.meeting_runtime()
    assert runtime == python and models == tmp_path / 'runtime/models'
    monkeypatch.setenv('VIDEOHUB_MEETING_PYTHON', str(tmp_path / 'missing.exe'))
    with pytest.raises(ValueError, match='环境'):
        meeting_desktop.meeting_runtime()


def test_translation_error_pauses_only_captions_and_retains_original_pcm(tmp_path, monkeypatch):
    from src.meeting.live import LiveCaptions
    from src.meeting.translation import TranslationError
    finished = threading.Event()
    statuses = []
    def status(message):
        statuses.append(message)
        if '暂停' in message:
            finished.set()
    engine = SimpleNamespace(asr=SimpleNamespace(transcribe=lambda *a, **k:
            ([SimpleNamespace(start=.1, end=1., text='Synthetic English')], None)))
    class FailingTranslator:
        def translate(self, text):
            raise TranslationError('模拟网络失败')
    monkeypatch.setattr('src.meeting.translation.TranslationRouter', lambda *a: FailingTranslator())
    live = LiveCaptions(lambda row: None, status, object(), engine_factory=lambda: engine)
    root = new_project(tmp_path, 'translation-failure')
    recorder = Recorder(root, 'fixture', 'ffmpeg', {}, lambda *a: None, live.feed)
    recorder.state.update(sample_rate=16000, channels=1)
    for index in range(65):
        recorder._frame(b'\x00\x20' * 1600, 100 + index / 10)
    assert finished.wait(3), statuses
    assert not recorder.stop_event.is_set() and recorder.pcm.qsize() == 65
    assert live.snapshot()[0]['text'] == 'Synthetic English'
    assert live.snapshot()[0]['translation'] == ''
    live.close()
