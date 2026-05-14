from unittest import TestCase
from unittest.mock import patch

from apps.refresh_dashboard import build_parser as build_refresh_parser
from apps.refresh_dashboard import refresh_commands, refresh_dashboard
from apps.serve_dashboard import build_parser as build_serve_parser
from apps.serve_dashboard import validate_local_host


class DashboardRefreshTests(TestCase):
    def test_refresh_commands_are_read_only_and_preserve_report_links(self) -> None:
        args = build_refresh_parser().parse_args(
            [
                "--runner-summary",
                "reports/runner.json",
                "--health-out",
                "reports/health.json",
                "--dashboard-out",
                "reports/dashboard.html",
                "--report-link",
                "Daily=reports/daily.json",
                "--history-report",
                "Run=reports/run.json",
            ]
        )

        health_cmd, dashboard_cmd = refresh_commands(args)

        self.assertIn("health_check.py", health_cmd[1])
        self.assertIn("--runner-summary", health_cmd)
        self.assertIn("--db", health_cmd)
        self.assertNotIn("--submit-demo", health_cmd)
        self.assertNotIn("--confirm-demo-submit", health_cmd)
        self.assertIn("build_dashboard.py", dashboard_cmd[1])
        self.assertIn("Daily=reports/daily.json", dashboard_cmd)
        self.assertIn("Run=reports/run.json", dashboard_cmd)

    def test_refresh_runs_two_commands_and_reports_safety_flags(self) -> None:
        args = build_refresh_parser().parse_args([])

        with patch("apps.refresh_dashboard.subprocess.run") as run:
            payload = refresh_dashboard(args)

        self.assertEqual(run.call_count, 2)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["orders_submitted"])
        self.assertFalse(payload["orders_cancelled"])
        self.assertFalse(payload["live_trading_enabled"])


class DashboardServerTests(TestCase):
    def test_server_defaults_to_localhost(self) -> None:
        args = build_serve_parser().parse_args([])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8765)

    def test_rejects_non_local_host(self) -> None:
        with self.assertRaises(SystemExit):
            validate_local_host("0.0.0.0")

    def test_accepts_local_host_names(self) -> None:
        for host in ("127.0.0.1", "localhost", "::1"):
            validate_local_host(host)
