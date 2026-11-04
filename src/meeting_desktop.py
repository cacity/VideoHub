"""Launch the optional meeting app without mixing PyQt6 and PySide6 runtimes."""
from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def meeting_runtime():
    explicit = os.environ.get('VIDEOHUB_MEETING_PYTHON', '').strip()
    candidates = [Path(explicit)] if explicit else [ROOT / '.venv-meeting/Scripts/pythonw.exe']
    if not explicit:
        candidates.extend(parent / 'MeetingCaption/.venv/Scripts/pythonw.exe' for parent in ROOT.parents)
    python = next((p for p in candidates if p.is_file()), None)
    if not python:
        raise ValueError('未找到会议模块环境。请安装requirements-meeting.txt到.venv-meeting，或设置VIDEOHUB_MEETING_PYTHON。')
    existing_models = (python.parents[2] if len(python.parents) > 2 else ROOT) / 'models'
    default_models = existing_models if (existing_models / 'whisper').is_dir() else ROOT / 'workspace/models/meeting'
    models = Path(os.environ.get('VIDEOHUB_MEETING_MODELS', str(default_models)))
    return python, models


def launch_meeting():
    python, models = meeting_runtime()
    check_python = python.with_name('python.exe') if python.name.lower() == 'pythonw.exe' else python
    try:
        check = subprocess.run([str(check_python), '-c',
            'import importlib.util,json; print(json.dumps([n for n in ("PySide6","pyaudiowpatch","faster_whisper","flask") if importlib.util.find_spec(n) is None]))'],
            capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.SubprocessError:
        raise ValueError('会议环境检查超时，请检查VIDEOHUB_MEETING_PYTHON所指向的Python环境') from None
    try:
        missing = json.loads(check.stdout)
    except ValueError:
        raise ValueError('会议环境检查失败，请使用Python.exe并安装requirements-meeting.txt') from None
    if check.returncode or missing:
        raise ValueError('会议环境缺少组件：' + ', '.join(missing) + '。请安装requirements-meeting.txt。')
    from .ffmpeg_manager import get_ffmpeg_manager
    from .paths_config import MEETINGS_DIR
    from .learning_desktop import learning_url
    ffmpeg = get_ffmpeg_manager().get_ffmpeg_exe()
    if not ffmpeg:
        raise ValueError('会议录屏需要FFmpeg可执行文件，请先在FFmpeg设置中配置')
    learning_url()  # The desktop owns the service, so closing the meeting window cannot kill it.
    environment = os.environ.copy()
    environment['VIDEOHUB_MEETING_MODELS'] = str(models)
    subprocess.Popen([str(python), '-m', 'src.meeting', '--models', str(models), '--output', MEETINGS_DIR, '--ffmpeg', ffmpeg],
                     cwd=str(ROOT), env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def open_project(directory):
    """Standalone meeting mode needs a learning service that outlives its UI."""
    import sys
    import time
    import requests
    from .learning_desktop import BASE_URL, learning_url

    try:
        healthy = requests.get(BASE_URL + '/api/learning/health', timeout=1).json().get('service') == 'videohub-learning'
    except (requests.RequestException, ValueError):
        healthy = False
    if not healthy:
        subprocess.Popen([sys.executable, '-m', 'src.learning_server'], cwd=str(ROOT),
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(30):
            try:
                if requests.get(BASE_URL + '/api/learning/health', timeout=.5).json().get('service') == 'videohub-learning':
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(.2)
        else:
            raise ValueError('学习服务未能启动，请在VideoHub中先打开学习资料库')
    return learning_url(directory=str(directory))
