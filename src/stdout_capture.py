"""Forward task output without replacing the built-in print used by Numba."""

import sys
import threading

_lock = threading.RLock()
_router = None


class _ThreadStdout:
    def __init__(self, stream):
        self.stream = stream
        self.local = threading.local()
        self.users = 0

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, text):
        result = self.stream.write(text) if self.stream is not None else len(text)
        stack = getattr(self.local, "stack", ())
        if stack and not getattr(self.local, "emitting", False):
            capture = stack[-1]
            capture.pending += text
            while "\n" in capture.pending or "\r" in capture.pending:
                # Both print's newline and progress-style carriage returns end a line.
                positions = [p for p in (capture.pending.find("\n"), capture.pending.find("\r")) if p >= 0]
                end = min(positions)
                line, capture.pending = capture.pending[:end], capture.pending[end + 1:]
                self.emit(capture.callback, line)
        return result

    def emit(self, callback, text):
        self.local.emitting = True
        try:
            callback(text)
        finally:
            self.local.emitting = False

    def flush(self):
        if self.stream is not None:
            self.stream.flush()


class _StdoutCapture:
    def __init__(self, router, callback):
        self.router = router
        self.callback = callback
        self.pending = ""
        self.closed = False

    def close(self):
        """Finish forwarding in the same thread that started this capture."""
        global _router
        if self.closed:
            return
        try:
            if self.pending:
                self.router.emit(self.callback, self.pending)
        finally:
            self.closed = True
            self.router.local.stack.remove(self)
            with _lock:
                self.router.users -= 1
                if self.router.users == 0:
                    if sys.stdout is self.router:
                        sys.stdout = self.router.stream
                    if _router is self.router:
                        _router = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def start_stdout_capture(callback):
    """Tee this thread's stdout to callback; close the handle in a finally block.

    Other threads retain console output, and nested tasks restore their caller's
    callback. Explicit print(file=...) output is left with its chosen stream.
    """
    global _router
    with _lock:
        if _router is None:
            _router = _ThreadStdout(sys.stdout)
            sys.stdout = _router
        capture = _StdoutCapture(_router, callback)
        if not hasattr(_router.local, "stack"):
            _router.local.stack = []
        _router.local.stack.append(capture)
        _router.users += 1
        return capture
