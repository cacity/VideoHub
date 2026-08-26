from __future__ import annotations

import os
import sys
from pathlib import Path


def _restore_standard_stream(name: str, file_descriptor: int) -> None:
    current = getattr(sys, name, None)
    if callable(getattr(current, "write", None)):
        return
    try:
        stream = open(  # noqa: SIM115 - the process owns these streams until exit.
            file_descriptor,
            "w",
            encoding="utf-8",
            errors="replace",
            buffering=1,
            closefd=False,
        )
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    setattr(sys, name, stream)


_restore_standard_stream("stdout", 1)
_restore_standard_stream("stderr", 2)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from videohub_desktop.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
