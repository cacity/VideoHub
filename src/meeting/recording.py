"""Capture original media independently of recognition/translation queues."""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from collections import deque
from pathlib import Path

from .project import atomic_json, learning_manifest, save_live, utc_now

HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def popen(command, **kwargs):
    return subprocess.Popen(command, creationflags=HIDDEN, **kwargs)


def media_info(ffmpeg: str, path: Path) -> dict:
    probe = str(Path(ffmpeg).with_name('ffprobe' + Path(ffmpeg).suffix))
    result = subprocess.run([probe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, timeout=30, creationflags=HIDDEN)
    if result.returncode:
        raise ValueError('无法读取录制文件；原始媒体已保留，可尝试恢复封装')
    return json.loads(result.stdout)


def finalize(root: Path, ffmpeg: str, state: dict) -> Path:
    """Mux recordings to MP4, correcting start offset and small device clock drift."""
    if not state.get('video_epoch') or not state.get('audio_epoch'):
        raise ValueError('没有完整的音画起点记录；原始媒体保留，不能保证同步')
    video_info = media_info(ffmpeg, root / 'originals' / 'screen.mkv')
    duration = float(video_info['format']['duration'])
    if duration <= 0 or not any(s['codec_type'] == 'video' for s in video_info['streams']):
        raise ValueError('没有录到有效画面，原始文件已保留')
    audio_info = media_info(ffmpeg, root / 'originals' / 'system-audio.mka')
    audio_duration = float(audio_info['format']['duration'])
    elapsed = state.get('audio_elapsed', audio_duration)
    scale = audio_duration / elapsed if elapsed > 0 else 1.
    if not .98 <= scale <= 1.02:
        raise ValueError('录音时钟偏差超过2%，未自动拉伸；请检查设备，原始媒体已保留')
    offset = state['audio_epoch'] - state['video_epoch']
    state.update(audio_offset=offset, audio_scale=scale, duration=duration, status='finalizing')
    atomic_json(root / 'meeting.json', state)
    temporary = root / 'meeting.finalizing.mp4'
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
               '-i', str(root / 'originals' / 'screen.mkv'), '-itsoffset', f'{offset:.6f}', '-i', str(root / 'originals' / 'system-audio.mka'),
               '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
               '-af', f'atempo={scale:.9f},aresample=async=1000:first_pts=0,apad',
               '-t', f'{duration:.6f}', '-movflags', '+faststart', str(temporary)]
    if temporary.exists():
        temporary.unlink()  # Only our unfinished derivative; originals never replaced.
    result = subprocess.run(command, capture_output=True, timeout=max(120, duration * .5), creationflags=HIDDEN)
    if result.returncode:
        raise ValueError('音画封装失败；原始screen.mkv和system-audio.mka已保留，可重试恢复')
    output = root / 'meeting.mp4'
    if output.exists():
        raise ValueError('meeting.mp4已存在，未覆盖')
    temporary.replace(output)
    rows = json.loads((root / 'live-captions.json').read_text(encoding='utf-8')) if (root / 'live-captions.json').is_file() else []
    save_live(root, rows, offset, scale, duration)
    learning_manifest(root, state['title'])
    state.update(status='finished', finished=utc_now())
    atomic_json(root / 'meeting.json', state)
    return output


class Recorder:
    """No Qt/ML imports here; raw PCM has its own bounded disk-encoding queue."""
    def __init__(self, root: Path, title: str, ffmpeg: str, region: dict, capture, on_audio=None):
        self.root, self.ffmpeg, self.capture, self.region = root, ffmpeg, capture, region
        self.on_audio = on_audio
        self.stop_event = threading.Event()
        self.audio_ready, self.video_ready = threading.Event(), threading.Event()
        self.pcm = queue.Queue(maxsize=100)  # Ten seconds of PCM, unrelated to ASR's two chunks.
        self.lock = threading.RLock()
        self.errors = deque(maxlen=15)
        self.failure = ''
        self.video = self.audio = None
        self.samples = 0
        self.audio_end = None
        self.state = {'schema_version': 1, 'id': root.name, 'title': title, 'started': utc_now(),
                      'status': 'starting', 'region': region, 'live_partial': True}
        self.save()

    def save(self):
        with self.lock:
            atomic_json(self.root / 'meeting.json', self.state)

    def fail(self, message):
        with self.lock:
            self.failure = message
            self.state.update(status='interrupted', error=message)
            self.stop_event.set()
            self.save()

    def log(self, process, video=False):
        for raw in process.stderr:
            line = raw.decode('utf-8', errors='replace').strip()
            if video and 'demuxer ->' in line and 'type:video' in line and not self.video_ready.is_set():
                # gdigrab's native time base is microseconds. pkt_pts_time is
                # printed with rounded scientific notation for epoch times.
                found = re.search(r'pkt_pts:(-?[0-9]+)', line)
                if found:
                    epoch = int(found[1]) / 1_000_000
                    if epoch > 1_000_000_000:
                        with self.lock:
                            self.state['video_epoch'] = epoch
                            self.save()
                        self.video_ready.set()
            if 'error' in line.lower() or 'failed' in line.lower():
                self.errors.append(line[:300])

    def start(self, device):
        self.audio_thread = threading.Thread(target=self._capture_audio, args=(device,), daemon=True)
        self.audio_thread.start()
        if not self.audio_ready.wait(10) or self.failure:
            self.stop_event.set()
            self.abort()
            raise ValueError(self.failure or '系统声音设备未能启动')
        if self.stop_event.is_set():
            self.abort()
            raise InterruptedError('已取消录制')
        r = self.region
        command = [self.ffmpeg, '-hide_banner', '-loglevel', 'info', '-debug_ts', '-n',
                   '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', '1',
                   '-offset_x', str(r['x']), '-offset_y', str(r['y']), '-video_size', f"{r['width']}x{r['height']}",
                   '-i', 'desktop', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                   '-threads', str(max(1, min(4, (os.cpu_count() or 4) // 2))),
                   '-pix_fmt', 'yuv420p', '-vsync', 'cfr', str(self.root / 'originals' / 'screen.mkv')]
        try:
            self.video = popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            threading.Thread(target=self.log, args=(self.video, True), daemon=True).start()
            if not self.video_ready.wait(10) or self.video.poll() is not None:
                raise ValueError('屏幕采集未能启动，请检查屏幕区域和FFmpeg；原始文件保留')
            if self.stop_event.is_set():
                raise InterruptedError('已取消录制')
            self.state['status'] = 'recording'
            self.save()
        except Exception:
            self.abort()
            raise

    def _capture_audio(self, device):
        try:
            self.capture(device, self.stop_event, self._frame, self._ready)
        except Exception:
            self.fail('系统声音采集中断，录制已停止；请检查设备。已录媒体保留，可恢复封装。')
        finally:
            self.audio_ready.set()

    def _ready(self, rate, channels):
        self.state.update(sample_rate=rate, channels=channels)
        self.audio = popen([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-n',
                            '-f', 's16le', '-ar', str(rate), '-ac', str(channels), '-i', 'pipe:0',
                            '-c:a', 'flac', str(self.root / 'originals' / 'system-audio.mka')],
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        threading.Thread(target=self.log, args=(self.audio,), daemon=True).start()
        self.writer = threading.Thread(target=self._write_audio, daemon=True)
        self.writer.start()
        self.audio_ready.set()

    def _frame(self, raw, epoch):
        rate, channels = self.state['sample_rate'], self.state['channels']
        frames = len(raw) // (2 * channels)
        with self.lock:
            if not self.samples:
                self.state['audio_epoch'] = epoch
                self.save()
            sample_start = self.samples
            self.samples += frames
            self.audio_end = epoch + frames / rate
        try:
            self.pcm.put_nowait(raw)
        except queue.Full:
            self.fail('录音写入跟不上，已停止录制并保留媒体；没有把缺段录音当作完整记录')
            return
        if self.on_audio:
            try:
                self.on_audio(raw, rate, channels, sample_start)
            except Exception:
                self.on_audio = None
                self.state['caption_warning'] = '字幕处理已暂停，原始录音继续保存'

    def _write_audio(self):
        try:
            while True:
                raw = self.pcm.get()
                if raw is None:
                    break
                self.audio.stdin.write(raw)
            self.audio.stdin.close()
        except (OSError, ValueError):
            self.fail('录音编码或磁盘写入失败，已停止录制，原始媒体保留')

    @staticmethod
    def close_process(process):
        if process and process.poll() is None:
            try:
                process.stdin.write(b'q\n')
                process.stdin.flush()
            except (OSError, ValueError):
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def stop_capture(self):
        self.stop_event.set()
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(4)
            if self.audio_thread.is_alive():
                self.failure = '声音设备未及时释放，原始媒体保留，请恢复封装后检查设备'
        self.close_process(self.video)
        if hasattr(self, 'writer'):
            try:
                self.pcm.put(None, timeout=3)
            except queue.Full:
                self.close_process(self.audio)
            self.writer.join(10)
            if self.writer.is_alive() and self.audio:
                self.audio.kill()
                self.writer.join(3)
                self.failure = '录音写入未正常结束，原始媒体保留，请恢复封装'
        if self.audio and self.audio.poll() is None:
            try:
                self.audio.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.audio.kill()
                self.audio.wait(timeout=5)
        if self.audio_end and self.state.get('audio_epoch'):
            self.state['audio_elapsed'] = self.audio_end - self.state['audio_epoch']
        self.state['samples'] = self.samples
        self.save()

    def finish(self):
        self.stop_capture()
        if self.failure:
            raise ValueError(self.failure)
        return finalize(self.root, self.ffmpeg, self.state)

    def abort(self):
        self.stop_capture()
        self.state.update(status='interrupted', error=self.failure or '录制未正常结束，原始媒体保留')
        self.save()
