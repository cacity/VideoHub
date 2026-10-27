"""Bounded background work with durable snapshots, cancellation and recovery."""

from __future__ import annotations

import logging
import threading

from .store import Store, new_id, now


class JobManager:
    def __init__(self, store: Store):
        self.store = store
        self.store.recover_jobs()
        self.lock = threading.Lock()
        self.active: dict[str, tuple[str, threading.Event]] = {}

    def start(self, video_id: str, kind: str, operation) -> dict:
        with self.lock:
            if len(self.active) >= 2:
                raise ValueError("已有两个后台任务，请等待完成或停止其中一个")
            if any(v == video_id for v, _ in self.active.values()):
                raise ValueError("此视频已有任务运行，请先等待或停止")
            job = {
                "id": new_id(),
                "video_id": video_id,
                "kind": kind,
                "status": "queued",
                "progress": 0,
                "message": "正在准备",
                "text": "",
                "created": now(),
            }
            cancelled = threading.Event()
            self.active[job["id"]] = (video_id, cancelled)
            self.store.save_job(job)

        def update(**changes):
            with self.lock:
                job.update(changes, updated=now())
                self.store.save_job(job)

        def work():
            try:
                update(status="running")
                result = operation(cancelled, update)
                if cancelled.is_set():
                    raise InterruptedError("任务已停止")
                update(status="finished", progress=100, message="完成", result=result)
            except InterruptedError:
                update(status="cancelled", message="任务已停止，已完成的缓存保留")
            except (ValueError, KeyError, FileNotFoundError) as error:
                update(status="failed", message=str(error).strip("'"))
            except Exception:
                # Do not serialize provider exception bodies: they may contain credentials.
                logging.getLogger(__name__).error("Learning job failed: %s", kind)
                update(status="failed", message="任务失败，请检查服务配置、网络或本地依赖后重试")
            finally:
                with self.lock:
                    self.active.pop(job["id"], None)

        threading.Thread(target=work, name=f"learning-{kind}", daemon=True).start()
        return dict(job)

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            job = self.store.job(job_id)
            active = self.active.get(job_id)
            if active:
                active[1].set()
                job.update(status="cancelling", message="正在停止，请稍候")
                self.store.save_job(job)
        return job
