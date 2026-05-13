import json
import tempfile
from pathlib import Path
from unittest import TestCase

from llbot.monitoring.dashboard import (
    DashboardArtifacts,
    DashboardReportLink,
    load_dashboard_artifacts,
    render_dashboard,
    write_dashboard,
)


class DashboardTests(TestCase):
    def test_render_dashboard_includes_health_feed_metascalp_and_safety(self) -> None:
        html = render_dashboard(
            DashboardArtifacts(
                health={
                    "system": {
                        "status": "ok",
                        "components": [
                            {
                                "name": "data_feeds",
                                "status": "ok",
                                "reason": "ok",
                                "metadata": {},
                            },
                            {
                                "name": "metascalp",
                                "status": "ok",
                                "reason": "ok",
                                "metadata": {"connection_id": 4},
                            },
                        ],
                    },
                    "safety": {
                        "orders_submitted": False,
                        "orders_cancelled": False,
                        "live_trading_enabled": False,
                    },
                },
                runner_summary={
                    "runner_limits": {
                        "stream_event_counts": {
                            "binance:BTCUSDT": 5,
                            "mexc:BTC_USDT": 1,
                        }
                    },
                    "health": {
                        "streams": {
                            "binance:BTCUSDT": {
                                "book_ticker_events": 5,
                                "max_gap_ms": 20,
                                "stale_gap_count": 0,
                            }
                        }
                    },
                    "metascalp": {"connection_id": 4, "submit_allowed": False},
                    "paper_summary": {"quotes": 6, "intents": 0},
                },
                memory={
                    "codex_progress": {
                        "last_completed_milestone": "dashboard smoke",
                        "next_required_step": "keep demo POST guarded",
                    }
                },
                reports=(
                    DashboardReportLink(
                        label="Replay Research",
                        path="reports/replay_research_smoke.json",
                        exists=True,
                        size_bytes=123,
                    ),
                    DashboardReportLink(
                        label="Missing Report",
                        path="reports/missing.json",
                        exists=False,
                    ),
                ),
            )
        )

        self.assertIn("Lead-Lag Ops Dashboard", html)
        self.assertIn("data_feeds", html)
        self.assertIn("metascalp", html)
        self.assertIn("binance:BTCUSDT", html)
        self.assertIn("mexc:BTC_USDT", html)
        self.assertIn("Replay Research", html)
        self.assertIn('href="reports/replay_research_smoke.json"', html)
        self.assertIn("Missing Report", html)
        self.assertIn("missing", html)
        self.assertIn("orders_submitted", html)
        self.assertNotIn("<button", html.lower())
        self.assertNotIn("submit-demo", html)

    def test_write_dashboard_handles_missing_optional_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dashboard.html"

            write_dashboard(out, DashboardArtifacts())

            payload = out.read_text(encoding="utf-8")

        self.assertIn("Lead-Lag Ops Dashboard", payload)
        self.assertIn("No feed stream data", payload)

    def test_load_dashboard_artifacts_reads_json_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            runner = Path(tmp) / "runner.json"
            memory = Path(tmp) / "memory.json"
            health.write_text(json.dumps({"system": {"status": "ok"}}), encoding="utf-8")
            runner.write_text(json.dumps({"paper_summary": {"quotes": 1}}), encoding="utf-8")
            memory.write_text(json.dumps({"codex_progress": {}}), encoding="utf-8")

            artifacts = load_dashboard_artifacts(
                health_path=health,
                runner_summary_path=runner,
                memory_path=memory,
                report_paths={"Replay <Research>": runner, "Missing": Path(tmp) / "missing.json"},
            )

        self.assertEqual(artifacts.health["system"]["status"], "ok")
        self.assertEqual(artifacts.runner_summary["paper_summary"]["quotes"], 1)
        self.assertEqual(artifacts.reports[0].label, "Replay <Research>")
        self.assertTrue(artifacts.reports[0].exists)
        self.assertFalse(artifacts.reports[1].exists)

    def test_report_labels_and_paths_are_escaped(self) -> None:
        html = render_dashboard(
            DashboardArtifacts(
                reports=(
                    DashboardReportLink(
                        label="<script>alert(1)</script>",
                        path='reports/x" onclick="bad.json',
                        exists=True,
                        size_bytes=1,
                    ),
                )
            )
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("reports/x&quot; onclick=&quot;bad.json", html)
        self.assertNotIn("<script>", html)
