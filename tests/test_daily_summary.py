import tempfile
from pathlib import Path
from unittest import TestCase

from llbot.service.daily_summary import build_daily_summary, load_json_object, write_daily_summary


class DailySummaryTests(TestCase):
    def test_build_daily_summary_combines_report_artifacts(self) -> None:
        summary = build_daily_summary(
            runner_summary={
                "paper_summary": {
                    "quotes": 10,
                    "intents": 2,
                    "fills": 1,
                    "closed_positions": 1,
                    "open_positions": 0,
                    "realized_pnl_usd": "1.2",
                }
            },
            health_report={
                "system": {"status": "ok"},
                "alerts": [{"severity": "critical"}, {"severity": "warning"}],
            },
            research_report={"symbol_days": [{"symbol": "BTCUSDT"}], "fill_model_variants": [1, 2]},
            fill_compare={"matched_fills": 1, "unmatched_paper": [], "unmatched_demo": [1]},
            reconciliation={"orders": [1], "positions": [1], "balances": [], "audit_records": [1, 2]},
        )

        self.assertEqual(summary["paper"]["quotes"], 10)
        self.assertEqual(summary["health"]["critical_alert_count"], 1)
        self.assertEqual(summary["research"]["fill_model_variants"], 2)
        self.assertEqual(summary["demo_fill_compare"]["unmatched_demo"], 1)
        self.assertFalse(summary["safety"]["orders_submitted_by_report"])

    def test_write_and_load_daily_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            write_daily_summary(path, build_daily_summary())
            loaded = load_json_object(path)

        self.assertEqual(loaded["schema_version"], "1.0.0")
        self.assertEqual(loaded["paper"]["quotes"], 0)
