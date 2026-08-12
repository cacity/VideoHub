from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from support_preflight import (  # noqa: E402
    SECRET_NAMES,
    collect_report,
    configured_secret_names,
    render_markdown,
    sanitize_path,
    summarize,
)


class SupportPreflightTests(unittest.TestCase):
    def collect_fast_report(self, environment: dict[str, str]) -> dict:
        executable_result = {
            "name": "executable:mock",
            "status": "pass",
            "summary": "mocked",
            "details": {},
        }
        package_result = {
            "name": "package:mock",
            "status": "pass",
            "summary": "mocked",
            "details": {},
        }
        write_result = {
            "name": "writable:mock",
            "status": "pass",
            "summary": "mocked",
            "details": {},
        }
        with (
            unittest.mock.patch("support_preflight.executable_check", return_value=executable_result),
            unittest.mock.patch("support_preflight.package_check", return_value=package_result),
            unittest.mock.patch("support_preflight.write_probe", return_value=write_result),
            unittest.mock.patch("support_preflight.shutil.disk_usage") as disk_usage,
        ):
            disk_usage.return_value = type("Usage", (), {"free": 20 * 1024**3})()
            return collect_report(ROOT, min_free_gb=0, environment=environment)

    def test_sanitize_path_hides_repo_and_home_prefixes(self) -> None:
        repo = Path("C:/work/VideoHub")
        home = Path("C:/Users/example")
        self.assertEqual(sanitize_path("C:/work/VideoHub/src/tool.py", repo, home), "<repo>/src/tool.py")
        self.assertEqual(sanitize_path("C:/Users/example/bin/python.exe", repo, home), "<home>/bin/python.exe")

    def test_dotenv_detection_never_returns_values(self) -> None:
        sentinel = "TOP-SECRET-SENTINEL"
        with TemporaryDirectory(prefix="videohub-preflight-") as temp_dir:
            dotenv = Path(temp_dir) / ".env"
            dotenv.write_text(f"OPENAI_API_KEY={sentinel}\nUNRELATED=visible\n", encoding="utf-8")
            configured = configured_secret_names(dotenv, {})
        self.assertEqual(configured, {"OPENAI_API_KEY"})
        self.assertNotIn(sentinel, json.dumps(sorted(configured)))

    def test_summary_prioritizes_fail_then_warn(self) -> None:
        self.assertEqual(summarize([{"status": "pass"}])["readiness"], "ready")
        self.assertEqual(summarize([{"status": "warn"}])["readiness"], "ready_with_warnings")
        self.assertEqual(summarize([{"status": "fail"}, {"status": "warn"}])["readiness"], "blocked")

    def test_report_contains_only_secret_presence_flags(self) -> None:
        sentinel = "NEVER-PRINT-THIS-SECRET"
        report = self.collect_fast_report({"OPENAI_API_KEY": sentinel})
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(sentinel, serialized)
        self.assertTrue(report["credentials"]["OPENAI_API_KEY"]["configured"])
        self.assertTrue(all(not state["value_included"] for state in report["credentials"].values()))
        self.assertEqual(set(report["credentials"]), set(SECRET_NAMES))

    def test_markdown_states_privacy_and_has_check_table(self) -> None:
        report = self.collect_fast_report({})
        markdown = render_markdown(report)
        self.assertIn("includes no secret values", markdown)
        self.assertIn("| Status | Check | Result |", markdown)
        self.assertIn("`OPENAI_API_KEY`", markdown)
