"""Regression coverage for task logs and Whisper's first import in the GUI."""

import builtins
import io
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.stdout_capture import start_stdout_capture


def test_print_semantics_nested_capture_and_exception_cleanup():
    original_print, original_stdout = builtins.print, sys.stdout
    outer, inner = [], []
    target = io.StringIO()
    with pytest.raises(ValueError), start_stdout_capture(outer.append):
        print("a", "b", sep="/", end="")
        print("private", file=target)
        with start_stdout_capture(inner.append):
            print("inner")
        print("!")
        print("partial", end="", flush=True)
        raise ValueError("task failed")
    assert outer == ["a/b!", "partial"]
    assert inner == ["inner"]
    assert target.getvalue() == "private\n"
    assert builtins.print is original_print
    assert sys.stdout is original_stdout


def test_overlapping_workers_do_not_capture_other_threads():
    original_stdout = sys.stdout
    barrier = threading.Barrier(3)
    release = threading.Event()
    rows = [[], []]

    def worker(index):
        with start_stdout_capture(rows[index].append):
            barrier.wait(timeout=5)
            assert release.wait(timeout=5)
            print(f"worker-{index}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, i) for i in range(2)]
        barrier.wait(timeout=5)
        print("main-thread")
        release.set()
        for future in futures:
            future.result(timeout=5)
    assert rows == [["worker-0"], ["worker-1"]]
    assert sys.stdout is original_stdout


def test_gui_worker_can_import_real_whisper_for_the_first_time():
    # A fresh interpreter is essential: cached Numba hides the original failure.
    script = '''
import builtins
import sys
import main

assert 'whisper' not in sys.modules
assert 'numba' not in sys.modules
original_print, original_stdout = builtins.print, sys.stdout

def transcribe(*args, **kwargs):
    import whisper
    assert callable(whisper.load_model)
    assert builtins.print is original_print
    print('whisper-imported', 'successfully', sep='/')
    return 'result.txt'

main.process_local_audio = transcribe
worker = main.WorkerThread('local_audio', {'audio_path': 'unused.wav'})
rows, results = [], []
worker.update_signal.connect(rows.append)
worker.finished_signal.connect(lambda path, ok: results.append((path, ok)))
worker.process_local_audio()
assert results == [('result.txt', True)], (results, rows)
assert 'whisper-imported/successfully' in rows, rows
assert builtins.print is original_print
assert sys.stdout is original_stdout
print('FIRST_WHISPER_IMPORT_OK')
'''
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FIRST_WHISPER_IMPORT_OK" in result.stdout
