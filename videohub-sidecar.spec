import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT / "src"))
datas = []
story_frontend = ROOT / "frontend" / "dist"
if story_frontend.is_dir():
    datas.append((str(story_frontend), "frontend/dist"))
hiddenimports = collect_submodules("videohub_desktop")
hiddenimports += collect_submodules("douyin")
hiddenimports += collect_submodules("keyring.backends")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "audio_utils",
    "chinese_tts",
    "cosyvoice_tts_client",
    "doubao_tts_client",
    "douyin_cli",
    "dubbing_engine",
    "koushare_downloader",
    "minimax_tts_client",
    "paths_config",
    "series_project",
    "subtitle_utils",
    "support_preflight",
    "story_timeline_server",
    "youtube_transcriber",
    "ytdlp_manager",
]

analysis = Analysis(
    [str(ROOT / "sidecar_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "matplotlib",
        "notebook",
        "pytest",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="videohub-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
