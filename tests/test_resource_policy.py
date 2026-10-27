import threading
import time

from src import resource_policy


class FakeCuda:
    def __init__(self, available=True):
        self.available = available
        self.empty_cache_calls = 0
        self.memory_fraction = None

    def is_available(self):
        return self.available

    def empty_cache(self):
        self.empty_cache_calls += 1

    def set_per_process_memory_fraction(self, fraction):
        self.memory_fraction = fraction


class FakeTorch:
    def __init__(self, cuda_available=True):
        self.cuda = FakeCuda(cuda_available)
        self.num_threads = None
        self.num_interop_threads = None

    def set_num_threads(self, count):
        self.num_threads = count

    def set_num_interop_threads(self, count):
        self.num_interop_threads = count


def test_balanced_policy_preserves_half_the_cpu_and_gpu_memory():
    policy = resource_policy.resolve_whisper_resource_policy({}, cpu_count=16)

    assert policy.profile == "balanced"
    assert policy.cpu_threads == 8
    assert policy.gpu_memory_fraction == 0.60
    assert policy.process_priority == "below_normal"


def test_explicit_limits_are_clamped_to_safe_ranges():
    policy = resource_policy.resolve_whisper_resource_policy(
        {
            "WHISPER_RESOURCE_PROFILE": "eco",
            "WHISPER_CPU_THREADS": "99",
            "WHISPER_GPU_MEMORY_PERCENT": "99",
            "WHISPER_DEVICE": "cpu",
        },
        cpu_count=12,
    )

    assert policy.cpu_threads == 12
    assert policy.gpu_memory_fraction == 0.95
    assert policy.device_preference == "cpu"


def test_apply_policy_limits_threads_and_cuda_memory(monkeypatch):
    fake_torch = FakeTorch(cuda_available=True)
    policy = resource_policy.resolve_whisper_resource_policy(
        {"WHISPER_RESOURCE_PROFILE": "balanced"},
        cpu_count=8,
    )
    monkeypatch.setattr(resource_policy, "apply_process_priority", lambda _value: True)

    device = resource_policy.apply_whisper_resource_policy(
        fake_torch,
        policy=policy,
        logger=lambda _message: None,
    )

    assert device == "cuda"
    assert fake_torch.num_threads == 4
    assert fake_torch.num_interop_threads == 2
    assert fake_torch.cuda.empty_cache_calls == 1
    assert fake_torch.cuda.memory_fraction == 0.60


def test_forced_cpu_leaves_cuda_untouched(monkeypatch):
    fake_torch = FakeTorch(cuda_available=True)
    policy = resource_policy.resolve_whisper_resource_policy(
        {
            "WHISPER_RESOURCE_PROFILE": "eco",
            "WHISPER_DEVICE": "cpu",
        },
        cpu_count=8,
    )
    monkeypatch.setattr(resource_policy, "apply_process_priority", lambda _value: True)

    device = resource_policy.apply_whisper_resource_policy(
        fake_torch,
        policy=policy,
        logger=lambda _message: None,
    )

    assert device == "cpu"
    assert fake_torch.cuda.empty_cache_calls == 0
    assert fake_torch.cuda.memory_fraction is None


def test_whisper_execution_slot_serializes_workers():
    entered = []

    def worker(name, delay):
        with resource_policy.whisper_execution_slot(logger=lambda _message: None):
            entered.append(f"{name}-start")
            time.sleep(delay)
            entered.append(f"{name}-end")

    first = threading.Thread(target=worker, args=("first", 0.05))
    second = threading.Thread(target=worker, args=("second", 0.01))
    first.start()
    time.sleep(0.01)
    second.start()
    first.join()
    second.join()

    assert entered == ["first-start", "first-end", "second-start", "second-end"]


def test_whisper_execution_slot_serializes_processes(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    output = tmp_path / 'process-events.jsonl'
    module_root = Path(resource_policy.__file__).parent
    code = '''import sys,time
sys.path.insert(0,sys.argv[1])
from resource_policy import whisper_execution_slot
with whisper_execution_slot(logger=lambda value: None):
    with open(sys.argv[2], 'a') as f:
        f.write(sys.argv[3] + '-start\\n'); f.flush()
        time.sleep(.15)
        f.write(sys.argv[3] + '-end\\n'); f.flush()
'''
    first = subprocess.Popen([sys.executable, '-c', code, str(module_root), str(output), 'first'])
    second = subprocess.Popen([sys.executable, '-c', code, str(module_root), str(output), 'second'])
    assert first.wait(timeout=15) == 0
    assert second.wait(timeout=15) == 0
    events = output.read_text().splitlines()
    assert events in [['first-start', 'first-end', 'second-start', 'second-end'],
                      ['second-start', 'second-end', 'first-start', 'first-end']]
