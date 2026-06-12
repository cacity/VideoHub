from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    accessed_at TEXT DEFAULT (datetime('now')),
    ip          TEXT NOT NULL,
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status_code INTEGER,
    user_agent  TEXT
);

CREATE TABLE IF NOT EXISTS subtitle_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT DEFAULT (datetime('now')),
    ip          TEXT NOT NULL,
    video_url   TEXT NOT NULL,
    language    TEXT,
    format      TEXT NOT NULL,
    success     INTEGER NOT NULL,
    error       TEXT
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def log_access(self, ip: str, method: str, path: str, status_code: int, user_agent: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO access_log (ip, method, path, status_code, user_agent) VALUES (?, ?, ?, ?, ?)",
                (ip, method, path, status_code, user_agent),
            )

    def log_subtitle_request(self, ip: str, video_url: str, language: str, output_format: str, success: bool, error: str | None):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO subtitle_log (ip, video_url, language, format, success, error) VALUES (?, ?, ?, ?, ?, ?)",
                (ip, video_url, language, output_format, int(success), error),
            )
