"""
VideoHub 日志浏览器

用法：
    python website/view_logs.py
    python website/view_logs.py --port 8899
    python website/view_logs.py --host root@38.49.57.170
"""

from __future__ import annotations
import argparse
import html
import json
import os
import shlex
import subprocess
import threading
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

DEFAULT_HOST = os.getenv("VIDEOHUB_LOG_HOST", "root@38.49.57.170")
DEFAULT_REMOTE_DB = os.getenv("VIDEOHUB_LOG_DB", "/opt/videohub-site/data/videohub.db")
DEFAULT_PORT = int(os.getenv("VIDEOHUB_LOG_PORT", "8899"))

ACCESS_SQL = """
SELECT id, accessed_at, ip, method, path, status_code, user_agent
FROM access_log
ORDER BY id DESC
LIMIT 1000;
"""

SUBTITLE_SQL = """
SELECT id, created_at, ip, video_url, language, format, success, error
FROM subtitle_log
ORDER BY id DESC
LIMIT 1000;
"""


def run_remote_sql(host: str, remote_db: str, sql: str) -> list[dict]:
    remote_cmd = f"sqlite3 -json {shlex.quote(remote_db)} {shlex.quote(sql)}"
    result = subprocess.run(
        ["ssh", host, remote_cmd],
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if not output:
        return []
    return json.loads(output)


def fetch_logs(host: str, remote_db: str) -> dict[str, Any]:
    access_logs = run_remote_sql(host, remote_db, ACCESS_SQL)
    subtitle_logs = run_remote_sql(host, remote_db, SUBTITLE_SQL)
    return {
        "meta": build_meta(access_logs, subtitle_logs),
        "access": access_logs,
        "subtitles": subtitle_logs,
        "fetched_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_meta(access_logs: list, subtitle_logs: list) -> dict:
    unique_ips = len({row["ip"] for row in access_logs})
    page_views = sum(1 for row in access_logs if row.get("method") == "PAGE")
    api_hits = sum(1 for row in access_logs if row.get("method") != "PAGE")
    subtitle_success = sum(int(row.get("success", 0)) for row in subtitle_logs)
    subtitle_failed = sum(1 for row in subtitle_logs if not row.get("success"))

    top_paths = Counter(row["path"] for row in access_logs if row.get("method") != "PAGE").most_common(10)

    return {
        "access_total": len(access_logs),
        "unique_ips": unique_ips,
        "page_views": page_views,
        "api_hits": api_hits,
        "subtitle_success": subtitle_success,
        "subtitle_failed": subtitle_failed,
        "top_paths": top_paths,
    }


def esc(value) -> str:
    return html.escape(str(value))


def status_badge(status: int) -> str:
    try:
        code = int(status)
    except ValueError:
        code = 0
    cls = "ok" if 200 <= code < 300 else "bad"
    return f'<span class="badge {cls}">{esc(code)}</span>'


def success_badge(success: bool) -> str:
    ok = bool(success)
    return f'<span class="badge {"ok" if ok else "bad"}">{"成功" if ok else "失败"}</span>'


def render_rows(rows: list, kind: str) -> str:
    body = []
    for row in rows:
        if kind == "access":
            body.append(
                f"<tr><td>{esc(row.get('accessed_at', ''))}</td>"
                f"<td>{esc(row.get('ip', ''))}</td>"
                f"<td><span class=\"badge method\">{esc(row.get('method', ''))}</span></td>"
                f"<td class=\"path\">{esc(row.get('path', ''))}</td>"
                f"<td>{status_badge(row.get('status_code', 0))}</td>"
                f"<td class=\"ua\">{esc(row.get('user_agent', ''))}</td></tr>"
            )
        else:
            body.append(
                f"<tr><td>{esc(row.get('created_at', ''))}</td>"
                f"<td>{esc(row.get('ip', ''))}</td>"
                f"<td class=\"path\">{esc(row.get('video_url', ''))}</td>"
                f"<td>{esc(row.get('language', '') or '自动')}</td>"
                f"<td>{esc(row.get('format', ''))}</td>"
                f"<td>{success_badge(row.get('success'))}</td>"
                f"<td>{esc(row.get('error', '') or '')}</td></tr>"
            )
    return "\n".join(body)


def render_page(dataset: dict, error: str | None) -> str:
    meta = dataset.get("meta", {})
    top_paths = "\n".join(
        f"<li><code>{esc(path)}</code><span>{count}</span></li>"
        for path, count in meta.get("top_paths", [])
    )

    error_box = f'<div class="error">{esc(error)}</div>' if error else ""

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>VideoHub 日志浏览器</title>
<style>
:root {{ color-scheme: light; --bg:#f5f1e8; --card:#fffaf0; --ink:#151922; --muted:#667085; --line:rgba(21,25,34,.12); --accent:#1f7f93; --bad:#dc2626; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:"Segoe UI", "Microsoft YaHei UI", sans-serif; background:radial-gradient(circle at top left, rgba(31,127,147,.14), transparent 30%), var(--bg); color:var(--ink); }}
main {{ max-width:1180px; margin:0 auto; padding:32px 20px 56px; }}
header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-end; margin-bottom:24px; }}
h1 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}
p {{ margin:8px 0 0; color:var(--muted); }}
.card {{ border:1px solid var(--line); background:rgba(255,250,240,.86); box-shadow:0 24px 60px rgba(68,54,28,.12); border-radius:24px; padding:18px; backdrop-filter:blur(14px); }}
.stats {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:16px; }}
.stat b {{ display:block; font-size:26px; }}
.stat span {{ color:var(--muted); font-size:13px; }}
.toolbar {{ display:flex; gap:10px; align-items:center; margin:18px 0; }}
input {{ width:100%; border:1px solid var(--line); border-radius:16px; padding:12px 14px; background:white; color:var(--ink); }}
button, a.button {{ border:1px solid var(--line); border-radius:999px; padding:10px 14px; background:white; color:var(--ink); cursor:pointer; text-decoration:none; white-space:nowrap; }}
button.active {{ background:var(--accent); color:white; border-color:transparent; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }}
.path {{ max-width:360px; overflow-wrap:anywhere; }}
.ua {{ max-width:320px; color:var(--muted); overflow-wrap:anywhere; }}
.badge {{ display:inline-flex; border-radius:999px; padding:3px 8px; font-size:12px; background:rgba(31,127,147,.1); color:var(--accent); }}
.badge.ok {{ background:rgba(22,163,74,.1); color:#15803d; }}
.badge.bad {{ background:rgba(220,38,38,.1); color:var(--bad); }}
.badge.method {{ background:rgba(21,25,34,.06); color:var(--ink); }}
.error {{ margin-bottom:16px; border:1px solid rgba(220,38,38,.24); background:rgba(220,38,38,.08); color:var(--bad); border-radius:18px; padding:12px 14px; }}
.top {{ display:grid; grid-template-columns:1fr 320px; gap:16px; margin-bottom:16px; }}
ul {{ margin:10px 0 0; padding:0; list-style:none; }}
li {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line); padding:8px 0; color:var(--muted); }}
code {{ color:var(--ink); }}
.hidden {{ display:none; }}
@media (max-width:900px) {{ .stats,.top {{ grid-template-columns:1fr 1fr; }} header {{ display:block; }} }}
@media (max-width:640px) {{ .stats,.top {{ grid-template-columns:1fr; }} table {{ font-size:12px; }} }}
</style>
</head>
<body>
<main>
<header>
  <div>
    <h1>VideoHub 日志浏览器</h1>
    <p>本地浏览，通过 SSH 读取远程 SQLite 数据</p>
  </div>
  <a class="button" href="/refresh">刷新日志</a>
</header>
{error_box}
<section class="stats">
  <div class="card stat"><b>{esc(meta.get('access_total', 0))}</b><span>访问记录</span></div>
  <div class="card stat"><b>{esc(meta.get('unique_ips', 0))}</b><span>独立 IP</span></div>
  <div class="card stat"><b>{esc(meta.get('page_views', 0))}</b><span>页面浏览</span></div>
  <div class="card stat"><b>{esc(meta.get('api_hits', 0))}</b><span>API 请求</span></div>
  <div class="card stat"><b>{esc(meta.get('subtitle_success', 0))}</b><span>字幕成功</span></div>
  <div class="card stat"><b>{esc(meta.get('subtitle_failed', 0))}</b><span>字幕失败</span></div>
</section>
<section class="top">
  <div class="card">
    <div class="toolbar">
      <button class="active" data-tab="access">访问日志</button>
      <button data-tab="subtitles">字幕下载日志</button>
      <input id="q" placeholder="搜索 IP、路径、URL 或 User-Agent" />
    </div>
  </div>
  <div class="card">
    <strong>热门路径</strong>
    <ul>{top_paths}</ul>
  </div>
</section>
<section id="access" class="card tab">
  <table data-table="access"><thead><tr><th>时间</th><th>IP</th><th>方法</th><th>路径</th><th>状态</th><th>User-Agent</th></tr></thead><tbody>
{render_rows(dataset.get('access', []), 'access')}
  </tbody></table>
</section>
<section id="subtitles" class="card tab hidden">
  <table data-table="subtitles"><thead><tr><th>时间</th><th>IP</th><th>视频 URL</th><th>语言</th><th>格式</th><th>成功</th><th>错误</th></tr></thead><tbody>
{render_rows(dataset.get('subtitles', []), 'subtitles')}
  </tbody></table>
</section>
</main>
<script>
const buttons = [...document.querySelectorAll('button[data-tab]')];
const tabs = [...document.querySelectorAll('.tab')];
const q = document.querySelector('#q');
function showTab(id) {{
  buttons.forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  tabs.forEach(t => t.classList.toggle('hidden', t.id !== id));
  filterRows();
}}
function filterRows() {{
  const term = q.value.trim().toLowerCase();
  const active = document.querySelector('.tab:not(.hidden)');
  active.querySelectorAll('tbody tr').forEach(row => {{
    row.style.display = row.innerText.toLowerCase().includes(term) ? '' : 'none';
  }});
}}
buttons.forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
q.addEventListener('input', filterRows);
</script>
</body>
</html>"""
    return page


class LogServer(BaseHTTPRequestHandler):
    dataset: dict[str, Any] = {}
    host: str = DEFAULT_HOST
    remote_db: str = DEFAULT_REMOTE_DB
    last_error: str | None = None

    def do_GET(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)

        if parsed.path in {"/data.json", "/refresh"}:
            self.refresh()

        if parsed.path == "/data.json":
            self.send_json(self.dataset)
            return

        if parsed.path == "/refresh":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path != "/":
            self.send_error(404)
            return

        body = render_page(self.dataset, self.last_error)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass

    @classmethod
    def refresh(cls):
        try:
            cls.dataset = fetch_logs(cls.host, cls.remote_db)
            cls.last_error = None
        except Exception as e:
            cls.last_error = str(e)

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args():
    parser = argparse.ArgumentParser(description="VideoHub local log browser")
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host")
    parser.add_argument("--remote-db", default=DEFAULT_REMOTE_DB, help="Remote SQLite path")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local browser port")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    return parser.parse_args()


def main():
    args = parse_args()
    LogServer.host = args.host
    LogServer.remote_db = args.remote_db
    LogServer.refresh()

    print(f"VideoHub 日志浏览器: http://127.0.0.1:{args.port}")
    print(f"远程数据库: {args.host}:{args.remote_db}")
    if LogServer.last_error:
        print(f"获取日志失败: {LogServer.last_error}")

    server = HTTPServer(("127.0.0.1", args.port), LogServer)
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
