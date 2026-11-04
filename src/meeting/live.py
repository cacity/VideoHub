"""Optional live captions; a failed translator never stops original recording."""
from __future__ import annotations

import json
import queue
import threading

from .project import learning_manifest, srt


class LiveCaptions:
    def __init__(self, on_result, on_status, store, engine_factory=None):
        self.on_result, self.on_status, self.store = on_result, on_status, store
        self.engine_factory = engine_factory
        self.pending = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.active = True
        self.dropped = 0
        self.rows = []
        self.lock = threading.Lock()
        self.segmenter = None
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def feed(self, raw, rate, channels, sample_start):
        if not self.active:
            return
        import numpy as np
        from .engine import Segmenter

        if self.segmenter is None:
            self.segmenter = Segmenter(rate)
            self.segmenter.samples = sample_start
        frame = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768
        chunk, _ = self.segmenter.feed(frame)
        if chunk:
            try:
                self.pending.put_nowait(chunk)
            except queue.Full:
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    pass
                self.dropped += 1
                self.on_status(f'字幕处理稍慢，已跳过{self.dropped}段；原始录音继续完整保存')
                self.pending.put_nowait(chunk)

    def run(self):
        try:
            from .engine import OfflineEngine, resample
            from .translation import TranslationRouter

            engine = self.engine_factory() if self.engine_factory else OfflineEngine()
            translator = TranslationRouter(self.store, engine)
            self.on_status('实时字幕已准备；录音和字幕队列相互独立')
            previous_end = 0.
            while not self.stop_event.is_set():
                try:
                    chunk = self.pending.get(timeout=.2)
                except queue.Empty:
                    continue
                segments, _ = engine.asr.transcribe(resample(chunk), language='en', beam_size=1,
                    temperature=0, condition_on_previous_text=False, vad_filter=True)
                for segment in segments:
                    if self.stop_event.is_set():
                        break
                    base = chunk.start_sample / chunk.rate
                    start, end = base + segment.start, base + segment.end
                    text = segment.text.strip()
                    if end <= previous_end + .05 or not text:
                        continue
                    start = max(start, previous_end)
                    row = {'start': start, 'end': end, 'text': text, 'translation': ''}
                    previous_end = end
                    with self.lock:
                        self.rows.append(row)
                    self.on_result(row)
                    # Publish original even when translation fails.
                    if self.stop_event.is_set():
                        break
                    row['translation'] = translator.translate(text)
                    if not self.stop_event.is_set():
                        self.on_result(row)
        except Exception as error:
            from .translation import TranslationError
            detail = str(error) if isinstance(error, TranslationError) else '请检查本地模型和翻译配置'
            if not self.stop_event.is_set():
                self.on_status('实时字幕已暂停：' + detail + '。录屏和原始录音继续；可在会后完整转写。')
        finally:
            self.active = False

    def snapshot(self):
        with self.lock:
            return [dict(r) for r in self.rows]

    def close(self):
        self.stop_event.set()
        self.active = False
        # Network requests have their own timeout. No late callback may update
        # the recording after stop; raw media never waits for a translation.
        self.worker.join(.5)


def complete_project(root, models, store, cancelled, progress):
    """Re-transcribe the complete original audio; persist immutable full versions."""
    from .engine import OfflineEngine
    from .translation import TranslationRouter
    from ..learning.subtitles import parse
    from ..subtitle_tracks import snapshot_track

    state = json.loads((root / 'meeting.json').read_text(encoding='utf-8'))
    if state['status'] != 'finished':
        raise ValueError('请先停止录制并完成封装，或恢复未完成录制')
    engine = OfflineEngine()
    translator = TranslationRouter(store, engine)
    progress('正在从完整原始录音转写；不会使用实时字幕缺段队列')
    segments, _ = engine.asr.transcribe(str(root / 'originals' / 'system-audio.mka'), language='en', beam_size=3, vad_filter=True)
    rows = []
    for segment in segments:
        if cancelled.is_set():
            raise InterruptedError('已停止会后转写')
        if segment.text.strip():
            rows.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip()})
            progress(f'完整转写至 {segment.end:.0f} 秒')
    if not rows:
        raise ValueError('完整录音未识别到英文发言，原始媒体保留')
    folder = root / 'subtitles'
    def persist(role, code):
        content = srt(rows, 'text' if role == 'source' else 'translation',
                      state['audio_offset'], state['audio_scale'], state['duration'])
        if content:
            snapshot_track(parse(content), folder, 'meeting.full', role, code)
            learning_manifest(root, state['title'])
    persist('source', 'en')
    try:
        for index, row in enumerate(rows):
            if cancelled.is_set():
                raise InterruptedError('已停止译文生成，完整原文已保存')
            progress(f'正在翻译完整原文 {index + 1}/{len(rows)}')
            row['translation'] = translator.translate(row['text'])
        if cancelled.is_set():
            raise InterruptedError('已停止译文生成，完整原文已保存')
        persist('target', 'zh-CN')
    finally:
        learning_manifest(root, state['title'])
    progress('完整原文和译文已保存；学习页可从字幕版本选择 meeting.full 文件')
