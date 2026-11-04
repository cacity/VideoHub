"""Local English speech recognition and optional local Chinese translation."""
from __future__ import annotations
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import re
import time
from dataclasses import dataclass
from math import gcd
from pathlib import Path
import numpy as np

ROOT = Path(os.environ.get('VIDEOHUB_MEETING_MODELS', str(Path(__file__).resolve().parents[2] / 'workspace/models/meeting')))


@dataclass
class AudioChunk:
    audio: np.ndarray
    rate: int
    captured_at: float
    overlap: float = 0
    start_sample: int = 0


class Segmenter:
    """100ms frames: pause boundaries, 6s ceiling, short context overlap."""
    def __init__(self, rate, threshold=0.0025, maximum=6.0):
        self.rate, self.threshold, self.maximum = rate, threshold, maximum
        self.frames, self.pre = [], []
        self.length = self.silence = self.overlap = 0
        self.samples = 0

    def feed(self, frame):
        self.samples += len(frame)
        duration = len(frame) / self.rate
        rms = float(np.sqrt(np.mean(frame ** 2))) if len(frame) else 0
        voiced = rms >= self.threshold
        if not self.frames:
            if not voiced:
                self.pre = (self.pre + [frame])[-2:]
                return None, rms
            self.frames = self.pre + [frame]
            self.pre = []
            self.length = sum(len(f) for f in self.frames) / self.rate
        else:
            self.frames.append(frame)
            self.length += duration
        self.silence = 0 if voiced else self.silence + duration
        if self.length < self.maximum and (self.silence < 0.5 or self.length < 1.0):
            return None, rms
        audio = np.concatenate(self.frames)
        chunk = AudioChunk(audio, self.rate, time.monotonic(), self.overlap, self.samples - len(audio))
        continuing = self.silence < 0.5
        tail = audio[-int(self.rate * 0.4):] if continuing else None
        self.frames = [tail] if continuing else []
        self.length = self.overlap = len(tail) / self.rate if continuing else 0
        self.silence = 0
        return chunk, rms


def resample(chunk):
    from scipy.signal import resample_poly
    if chunk.rate == 16000:
        return chunk.audio.astype(np.float32)
    factor = gcd(chunk.rate, 16000)
    return resample_poly(chunk.audio, 16000 // factor, chunk.rate // factor).astype(np.float32)


def trim_overlap(previous, current):
    old, new = previous.split(), current.split()
    clean = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    for count in range(min(12, len(old), len(new)), 1, -1):
        if [clean(w) for w in old[-count:]] == [clean(w) for w in new[:count]]:
            return ' '.join(new[count:])
    return current.strip()


def devices():
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        outputs = list(audio.get_loopback_device_info_generator())
        try:
            default = audio.get_default_wasapi_loopback()['index']
        except OSError:
            default = outputs[0]['index'] if outputs else -1
        return outputs, default


def capture(device, stop, deliver, meter):
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        info = audio.get_device_info_by_index(device)
        if not info.get('isLoopbackDevice'):
            raise ValueError('请选择扬声器或耳机的播放声音。')
        rate, channels = int(info['defaultSampleRate']), int(info['maxInputChannels'])
        segmenter = Segmenter(rate)
        with audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                        input_device_index=device, frames_per_buffer=rate // 10) as stream:
            while not stop.is_set():
                raw = stream.read(rate // 10, exception_on_overflow=False)
                frame = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768
                chunk, level = segmenter.feed(frame)
                meter(level)
                if chunk is not None and not stop.is_set():
                    deliver(chunk)


class OfflineEngine:
    def __init__(self):
        from faster_whisper import WhisperModel
        self.asr = WhisperModel(str(ROOT / 'whisper'), device='cpu', compute_type='int8',
                                cpu_threads=4, num_workers=1, local_files_only=True)
        self.translator = None

    def load_local_translator(self):
        import ctranslate2
        import sentencepiece as spm
        model = ROOT / 'translate'
        self.translator = ctranslate2.Translator(str(model), device='cpu', compute_type='int8',
                                                inter_threads=1, intra_threads=2)
        self.source = spm.SentencePieceProcessor(model_file=str(model / 'source.spm'))
        self.target = spm.SentencePieceProcessor(model_file=str(model / 'target.spm'))

    def recognize(self, audio, overlap=0):
        segments, _ = self.asr.transcribe(audio, language='en', task='transcribe', beam_size=1,
            best_of=1, temperature=0, condition_on_previous_text=False, vad_filter=True,
            vad_parameters={'min_silence_duration_ms': 350}, no_speech_threshold=0.6)
        return ' '.join(s.text.strip() for s in segments if s.end > overlap + 0.05).strip()

    def translate(self, text):
        if not text.strip():
            return ''
        if self.translator is None:
            self.load_local_translator()
        tokens = self.source.encode(text, out_type=str) + ['</s>']
        result = self.translator.translate_batch([tokens], beam_size=2, max_decoding_length=256)[0]
        return self.target.decode([t for t in result.hypotheses[0] if t not in ('</s>', '<s>', '<pad>')])
