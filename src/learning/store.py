"""SQLite storage. Each operation owns its connection and transaction."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "learning.sqlite3"
        with self.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise ValueError("学习数据库来自更新版本，请使用相应版本的 VideoHub")
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, data TEXT NOT NULL,
                    updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks (
                    video_id TEXT NOT NULL REFERENCES videos(id), role TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY(video_id, role));
                CREATE TABLE IF NOT EXISTS progress (
                    video_id TEXT PRIMARY KEY REFERENCES videos(id), data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id),
                    data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id),
                    data TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analyses (
                    cache_key TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def video(self, video_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM videos WHERE id=?", (video_id,)).fetchone()
        if not row:
            raise KeyError("视频未登记")
        return json.loads(row[0])

    def videos(self) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM videos ORDER BY updated DESC")]

    def save_video(self, video: dict):
        with self.connect() as db:
            db.execute(
                "INSERT INTO videos VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path, data=excluded.data, updated=excluded.updated",
                (video["id"], video["path"], encode(video), now()),
            )

    def tracks(self, video_id: str) -> dict:
        with self.connect() as db:
            return {
                row["role"]: json.loads(row["data"])
                for row in db.execute("SELECT role,data FROM tracks WHERE video_id=?", (video_id,))
            }

    def save_tracks(self, video_id: str, tracks: dict):
        with self.connect() as db:
            for role, track in tracks.items():
                db.execute(
                    "INSERT INTO tracks VALUES(?,?,?) ON CONFLICT(video_id,role) DO UPDATE SET data=excluded.data",
                    (video_id, role, encode(track)),
                )

    def progress(self, video_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM progress WHERE video_id=?", (video_id,)).fetchone()
        return (
            json.loads(row[0])
            if row
            else {"time": 0, "rate": 1, "mode": "bilingual", "overlay": "bilingual", "font": 20}
        )

    def save_progress(self, video_id: str, value: dict):
        with self.connect() as db:
            db.execute(
                "INSERT INTO progress VALUES(?,?) ON CONFLICT(video_id) DO UPDATE SET data=excluded.data",
                (video_id, encode(value)),
            )
            db.execute("UPDATE videos SET updated=? WHERE id=?", (now(), video_id))

    def list_items(self, table: str, video_id: str) -> list[dict]:
        assert table in {"notes", "messages"}
        with self.connect() as db:
            rows = db.execute(f"SELECT data FROM {table} WHERE video_id=? ORDER BY rowid", (video_id,))
            return [json.loads(row[0]) for row in rows]

    def save_item(self, table: str, video_id: str, item: dict):
        assert table in {"notes", "messages"}
        with self.connect() as db:
            if table == "notes":
                db.execute(
                    "INSERT INTO notes VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data WHERE notes.video_id=excluded.video_id",
                    (item["id"], video_id, encode(item)),
                )
            else:
                db.execute(
                    "INSERT INTO messages VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data WHERE messages.video_id=excluded.video_id",
                    (item["id"], video_id, encode(item), item["created"]),
                )

    def delete_note(self, video_id: str, note_id: str):
        with self.connect() as db:
            if not db.execute("DELETE FROM notes WHERE id=? AND video_id=?", (note_id, video_id)).rowcount:
                raise KeyError("笔记不存在")

    def cache(self, key: str):
        with self.connect() as db:
            row = db.execute("SELECT data FROM analyses WHERE cache_key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_cache(self, key: str, value: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO analyses VALUES(?,?)", (key, encode(value)))

    def job(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError("任务不存在")
        return json.loads(row[0])

    def save_job(self, job: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES(?,?)", (job["id"], encode(job)))

    def recover_jobs(self):
        with self.connect() as db:
            for row in db.execute("SELECT id,data FROM jobs").fetchall():
                job = json.loads(row["data"])
                if job["status"] in {"queued", "running", "cancelling"}:
                    job.update(status="interrupted", message="服务重启，任务已中断；可重新发起并复用已完成的分析缓存")
                    db.execute("UPDATE jobs SET data=? WHERE id=?", (encode(job), row["id"]))

    def video_jobs(self, video_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT data FROM jobs ORDER BY rowid DESC").fetchall()
        return [item for row in rows if (item := json.loads(row[0]))["video_id"] == video_id][:30]
