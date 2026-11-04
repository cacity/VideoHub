"""python -m src.meeting --help (optional meeting environment required for UI)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='VideoHub meeting recording and live captions')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[2] / 'workspace/meetings')
    parser.add_argument('--models', type=Path, default=Path(os.environ.get('VIDEOHUB_MEETING_MODELS', 'workspace/models/meeting')))
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    os.environ['VIDEOHUB_MEETING_MODELS'] = str(args.models.resolve())
    from .windows import dpi_aware
    dpi_aware()
    from .app import main as run
    return run(args.output.resolve(), args.ffmpeg, args.models.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
