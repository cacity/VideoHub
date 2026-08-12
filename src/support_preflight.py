"""Generate a shareable, secret-safe VideoHub support preflight report.

The command performs local, read-only checks plus short-lived write probes. It
does not contact external services, call paid APIs, scan media, or print secret
values. Generated report files are ignored by Git by default.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Optional[...] is intentional: this repository supports Python 3.9.
# ruff: noqa: UP045


SCHEMA_VERSION = 1
MIN_PYTHON = (3, 8)
DEFAULT_MIN_FREE_GB = 5.0

REQUIRED_PACKAGES = (
    ("PyQt6", "PyQt6"),
    ("yt-dlp", "yt-dlp"),
    ("requests", "requests"),
    ("Flask", "Flask"),
    ("flask-cors", "Flask-Cors"),
    ("python-dotenv", "python-dotenv"),
    ("psutil", "psutil"),
    ("Pillow", "Pillow"),
    ("numpy", "numpy"),
)

OPTIONAL_PACKAGES = (
    ("openai-whisper", "openai-whisper"),
    ("torch", "torch"),
    ("torchaudio", "torchaudio"),
    ("openai", "openai"),
    ("selenium", "selenium"),
    ("aiohttp", "aiohttp"),
    ("kokoro", "kokoro"),
    ("soundfile", "soundfile"),
)

SECRET_NAMES = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
    "DOUBAO_TTS_APP_ID",
    "DOUBAO_TTS_ACCESS_TOKEN",
)


def check(name: str, status: str, summary: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def sanitize_path(path: str, repo_root: Path, home: Optional[Path] = None) -> str:
    """Hide the repository and home prefixes while preserving useful suffixes."""

    value = str(path)
    comparable_value = value.replace("\\", "/").rstrip("/")
    replacements = ((repo_root, "<repo>"), (home or Path.home(), "<home>"))
    for prefix, marker in replacements:
        try:
            prefix_text = str(prefix.resolve())
        except OSError:
            prefix_text = str(prefix)
        comparable_prefix = prefix_text.replace("\\", "/").rstrip("/")
        if comparable_value.lower() == comparable_prefix.lower():
            return marker
        prefix_with_separator = comparable_prefix + "/"
        if comparable_value.lower().startswith(prefix_with_separator.lower()):
            suffix = comparable_value[len(prefix_with_separator) :]
            return f"{marker}/{suffix}"
    return Path(value).name or value


def package_check(display_name: str, distribution_name: str, required: bool) -> dict[str, Any]:
    try:
        version = importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        status = "fail" if required else "warn"
        kind = "required" if required else "optional"
        return check(
            f"package:{display_name}",
            status,
            f"{kind} package is not installed",
            {"installed": False, "required": required},
        )
    return check(
        f"package:{display_name}",
        "pass",
        f"installed ({version})",
        {"installed": True, "required": required, "version": version},
    )


def executable_check(name: str, args: Iterable[str], repo_root: Path, required: bool = True) -> dict[str, Any]:
    executable = shutil.which(name)
    if not executable:
        return check(
            f"executable:{name}",
            "fail" if required else "warn",
            "not found on PATH",
            {"available": False, "required": required},
        )
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        first_line = (completed.stdout or completed.stderr).splitlines()[0][:240]
        status = "pass" if completed.returncode == 0 else ("fail" if required else "warn")
        summary = first_line or f"returned exit code {completed.returncode}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        status = "fail" if required else "warn"
        summary = f"could not verify: {type(exc).__name__}"
    return check(
        f"executable:{name}",
        status,
        summary,
        {
            "available": True,
            "required": required,
            "path": sanitize_path(executable, repo_root),
        },
    )


def write_probe(directory: Path) -> dict[str, Any]:
    name = f"writable:{directory.name or 'root'}"
    if not directory.exists():
        return check(name, "fail", "directory does not exist", {"writable": False})
    probe_code = (
        "import pathlib,sys,uuid; "
        "p=pathlib.Path(sys.argv[1]) / ('.videohub-preflight-' + uuid.uuid4().hex + '.tmp'); "
        "p.write_bytes(b'videohub'); p.unlink()"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-B", "-c", probe_code, str(directory)],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return check(name, "fail", "write probe timed out after 3 seconds", {"writable": False})
    except OSError as exc:
        return check(name, "fail", f"write probe could not start: {type(exc).__name__}", {"writable": False})
    if completed.returncode != 0:
        error_type = "permission or filesystem error"
        return check(name, "fail", f"write probe failed: {error_type}", {"writable": False})
    return check(name, "pass", "short-lived write probe succeeded", {"writable": True})


def configured_secret_names(dotenv_path: Path, environment: Mapping[str, str]) -> set[str]:
    """Return configured key names without retaining or exposing values."""

    configured = {name for name in SECRET_NAMES if environment.get(name, "").strip()}
    if not dotenv_path.is_file():
        return configured
    name_pattern = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = name_pattern.match(raw_line)
            if not match or match.group(1) not in SECRET_NAMES:
                continue
            raw_value = match.group(2).strip().strip("\"'")
            if raw_value and not raw_value.startswith("${"):
                configured.add(match.group(1))
    except OSError:
        return configured
    return configured


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: sum(item["status"] == status for item in checks) for status in ("pass", "warn", "fail")}
    readiness = "blocked" if counts["fail"] else ("ready_with_warnings" if counts["warn"] else "ready")
    return {"readiness": readiness, "counts": counts}


def collect_report(
    repo_root: Path,
    min_free_gb: float = DEFAULT_MIN_FREE_GB,
    environment: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    environment = environment if environment is not None else os.environ
    checks: list[dict[str, Any]] = []

    python_ok = sys.version_info[:2] >= MIN_PYTHON
    checks.append(
        check(
            "runtime:python",
            "pass" if python_ok else "fail",
            platform.python_version(),
            {
                "version": platform.python_version(),
                "minimum": ".".join(map(str, MIN_PYTHON)),
                "executable": sanitize_path(sys.executable, repo_root),
            },
        )
    )

    for relative_path in ("main.py", "requirements.txt", "src"):
        target = repo_root / relative_path
        present = target.exists()
        checks.append(
            check(
                f"repository:{relative_path}",
                "pass" if present else "fail",
                "present" if present else "missing",
                {"present": present},
            )
        )

    checks.extend(
        (
            executable_check("ffmpeg", ("-version",), repo_root),
            executable_check("ffprobe", ("-version",), repo_root),
        )
    )
    checks.extend(package_check(display, distribution, True) for display, distribution in REQUIRED_PACKAGES)
    checks.extend(package_check(display, distribution, False) for display, distribution in OPTIONAL_PACKAGES)

    checks.append(write_probe(repo_root))
    workspace = repo_root / "workspace"
    checks.append(write_probe(workspace))

    try:
        usage = shutil.disk_usage(repo_root)
        free_gb = round(usage.free / (1024**3), 2)
        disk_status = "pass" if free_gb >= min_free_gb else "fail"
        checks.append(
            check(
                "storage:free_space",
                disk_status,
                f"{free_gb:.2f} GiB free",
                {"free_gib": free_gb, "minimum_gib": min_free_gb},
            )
        )
    except OSError as exc:
        checks.append(check("storage:free_space", "fail", f"could not inspect: {type(exc).__name__}"))

    configured = configured_secret_names(repo_root / ".env", environment)
    credentials = {
        name: {"configured": name in configured, "value_included": False}
        for name in SECRET_NAMES
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "network_calls": False,
            "media_scanned": False,
            "secret_values_included": False,
            "paths_sanitized": True,
        },
        "system": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
        },
        "summary": summarize(checks),
        "checks": checks,
        "credentials": credentials,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# VideoHub Support Preflight",
        "",
        f"Generated: {report['generated_at']}",
        f"Readiness: **{summary['readiness']}**",
        "",
        "This report makes no network calls, scans no media, and includes no secret values.",
        "",
        "## Checks",
        "",
        "| Status | Check | Result |",
        "|---|---|---|",
    ]
    for item in report["checks"]:
        safe_summary = str(item["summary"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['status'].upper()} | `{item['name']}` | {safe_summary} |")
    lines.extend(("", "## Optional credentials", ""))
    for name, state in report["credentials"].items():
        status = "configured" if state["configured"] else "not configured"
        lines.append(f"- `{name}`: {status}; value not included")
    lines.extend(
        (
            "",
            "## Interpretation",
            "",
            "- `blocked`: fix all FAIL checks before scheduling a sample workflow.",
            "- `ready_with_warnings`: base setup is available; optional features may need packages or credentials.",
            "- `ready`: all checked base and optional components are available.",
            "",
        )
    )
    return "\n".join(lines)


def write_reports(report: Mapping[str, Any], json_path: Path, markdown_path: Optional[Path]) -> None:
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        with markdown_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a secret-safe VideoHub support preflight report")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", type=Path, default=Path("videohub_support_report.json"))
    parser.add_argument("--markdown", type=Path, default=Path("videohub_support_report.md"))
    parser.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB)
    args = parser.parse_args()

    report = collect_report(args.repo, min_free_gb=args.min_free_gb)
    write_reports(report, args.json, args.markdown)
    summary = report["summary"]
    print(
        json.dumps(
            {
                "readiness": summary["readiness"],
                "counts": summary["counts"],
                "json_report": str(args.json),
                "markdown_report": str(args.markdown),
                "secret_values_included": False,
            },
            ensure_ascii=False,
        )
    )
    return 1 if summary["readiness"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
