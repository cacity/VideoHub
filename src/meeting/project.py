"""Portable meeting projects, with separate original and translated captions."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path: Path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def new_project(parent: Path, title: str) -> Path:
    slug = re.sub(r'[^\w-]+', '_', title).strip('._')[:40] or 'meeting'
    root = parent / (datetime.now().strftime('%Y%m%d_%H%M%S_') + slug + '_' + uuid.uuid4().hex[:6])
    root.mkdir(parents=True, exist_ok=False)
    (root / 'subtitles').mkdir()
    (root / 'originals').mkdir()
    return root


def stamp(seconds: float) -> str:
    milliseconds = round(max(0, seconds) * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f'{hours:02}:{minute:02}:{sec:02},{ms:03}'


def srt(rows: list[dict], role='text', offset=0., scale=1., duration=float('inf')) -> str:
    lines = []
    for row in rows:
        text = row.get(role, '').strip()
        start, end = max(0., offset + row['start'] / scale), min(duration, offset + row['end'] / scale)
        if not text or round(end * 1000) <= round(start * 1000):
            continue
        lines.append(f'{len(lines) + 1}\n{stamp(start)} --> {stamp(end)}\n{text}\n')
    return '\n'.join(lines)


def save_live(root: Path, rows: list[dict], offset=0., scale=1., duration=float('inf')):
    atomic_json(root / 'live-captions.json', rows)
    for role, code in [('text', 'source.en'), ('translation', 'target.zh-CN')]:
        path = root / 'subtitles' / f'meeting.live.{code}.srt'
        content = srt(rows, role, offset, scale, duration)
        if content:
            temporary = path.with_suffix('.tmp')
            temporary.write_text(content, encoding='utf-8')
            temporary.replace(path)


def learning_manifest(root: Path, title: str):
    from ..learning.project import MANIFEST, inspect_project, write_manifest

    project = inspect_project(str(root), str(root / 'meeting.mp4'))
    # Keep an existing learning identity when generating full caption versions.
    if (root / MANIFEST).is_file():
        project['id'] = json.loads((root / MANIFEST).read_text(encoding='utf-8'))['id']
    project['title'] = title
    write_manifest(project)


def utc_now():
    return datetime.now(timezone.utc).isoformat()
