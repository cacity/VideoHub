"""Keep model SDKs off the window startup path without losing task imports."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

def test_desktop_import_does_not_load_model_libraries():
    root = Path(__file__).resolve().parents[1]
    script = """
import contextlib
import importlib.abc
import io
import json
import sys

heavy = {'torch', 'whisper', 'openai'}
class BlockModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in heavy:
            raise AssertionError('Model dependency imported during startup: ' + fullname)
sys.meta_path.insert(0, BlockModels())
with contextlib.redirect_stdout(io.StringIO()):
    import main
print(json.dumps({'loaded': sorted(heavy.intersection(sys.modules)), 'window_available': callable(main.MainWindow)}))
"""
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", script], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"loaded": [], "window_available": True}


def test_whisper_task_still_loads_model_and_releases_gpu(monkeypatch):
    from src import youtube_transcriber as yt

    calls = []
    model = SimpleNamespace(transcribe=lambda path, **kwargs: {"text": "Hello", "path": path, **kwargs})

    def load(size, device):
        calls.append((size, device))
        return model

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: calls.append("clear"))))
    result, load_time, transcribe_time = yt.run_whisper_transcription("audio.wav", "small", "cuda", {"language": "en"})
    assert result == {"text": "Hello", "path": "audio.wav", "language": "en"}
    assert calls == [("small", "cuda"), "clear"]
    assert load_time >= 0 and transcribe_time >= 0


def test_summary_task_imports_sdk_only_when_called(monkeypatch):
    from src import youtube_transcriber as yt

    calls = []
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="A summary"))])

    def client(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **data: response)))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=client))
    composite = object.__new__(yt.TextSummaryComposite)
    composite.target_api_key, composite.target_api_url, composite.target_model = "test-key", "https://model.example", "test-model"
    assert composite._get_openai_summary("system", "question") == "A summary"
    assert calls == [{"api_key": "test-key", "base_url": "https://model.example"}]


def test_polish_without_sdk_keeps_original_translation(monkeypatch):
    from src import youtube_transcriber as yt

    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    rows = [{"source": "Hello", "translation": "你好"}]
    assert yt.polish_subtitle_translations_with_deepseek(rows) == rows
