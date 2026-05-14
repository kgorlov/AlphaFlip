from decimal import Decimal
from unittest import TestCase

from llbot.service.paper_pnl_compare import compare_replay_paper_pnl, summary_snapshot


class PaperPnlCompareTests(TestCase):
    def test_matching_summaries_are_matched(self) -> None:
        report = compare_replay_paper_pnl(_summary(), _summary())

        self.assertTrue(report.matched)
        self.assertEqual(report.summary["mismatch_count"], 0)
        self.assertEqual(report.pnl_deltas["total_net_pnl_usd"], Decimal("0"))
        self.assertEqual(report.count_deltas["fills"], 0)

    def test_reports_pnl_count_and_intent_deltas(self) -> None:
        report = compare_replay_paper_pnl(
            _summary(realized="1.20", fills=2, intent_counts={"impulse_transfer": 2}),
            _summary(realized="1.25", fills=1, intent_counts={"impulse_transfer": 1, "residual_zscore": 1}),
        )

        self.assertFalse(report.matched)
        self.assertEqual(report.pnl_deltas["realized_pnl_usd"], Decimal("0.05"))
        self.assertEqual(report.pnl_deltas["total_net_pnl_usd"], Decimal("0.05"))
        self.assertEqual(report.count_deltas["fills"], -1)
        self.assertEqual(report.intent_count_deltas["impulse_transfer"], -1)
        self.assertEqual(report.intent_count_deltas["residual_zscore"], 1)
        self.assertIn("realized_pnl_usd_delta", report.mismatch_reasons)
        self.assertIn("fills_delta", report.mismatch_reasons)
        self.assertIn("intent_count_delta:residual_zscore", report.mismatch_reasons)

    def test_tolerance_allows_small_pnl_delta_but_not_count_delta(self) -> None:
        report = compare_replay_paper_pnl(
            _summary(realized="1.20", fills=2),
            _summary(realized="1.25", fills=1),
            tolerance_usd=Decimal("0.10"),
        )

        self.assertFalse(report.matched)
        self.assertNotIn("realized_pnl_usd_delta", report.mismatch_reasons)
        self.assertIn("fills_delta", report.mismatch_reasons)

    def test_snapshot_defaults_missing_fields_to_zero(self) -> None:
        snapshot = summary_snapshot("paper", {"intent_counts": {"x": "2"}})

        self.assertEqual(snapshot.pnl["realized_pnl_usd"], Decimal("0"))
        self.assertEqual(snapshot.counts["fills"], 0)
        self.assertEqual(snapshot.intent_counts, {"x": 2})


def _summary(
    *,
    realized: str = "1.20",
    unrealized: str = "0.30",
    fills: int = 2,
    intent_counts: dict[str, int] | None = None,
) -> dict:
    return {
        "processed_events": 10,
        "quotes": 10,
        "intents": 2,
        "skipped_events": 0,
        "risk_allowed": 2,
        "risk_blocked": 0,
        "fills": fills,
        "not_filled": 0,
        "closed_positions": 1,
        "open_positions": 1,
        "gross_realized_pnl_usd": realized,
        "realized_cost_usd": "0",
        "realized_pnl_usd": realized,
        "gross_unrealized_pnl_usd": unrealized,
        "unrealized_cost_usd": "0",
        "unrealized_pnl_usd": unrealized,
        "audit_records": 3,
        "intent_counts": intent_counts or {"impulse_transfer": 2},
    }
