import json
import tempfile
from pathlib import Path
from unittest import TestCase

from apps.compare_replay_paper_pnl import build_parser, run


class CompareReplayPaperPnlCliTests(TestCase):
    def test_cli_writes_offline_comparison_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            replay = Path(tmp) / "replay.json"
            paper = Path(tmp) / "paper.json"
            replay.write_text(json.dumps(_summary("1.00", fills=1)), encoding="utf-8")
            paper.write_text(json.dumps(_summary("1.25", fills=2)), encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "--replay-summary",
                    str(replay),
                    "--paper-summary",
                    str(paper),
                ]
            )

            result = run(args)

            self.assertFalse(result["matched"])
            self.assertEqual(result["pnl_deltas"]["realized_pnl_usd"], "0.25")
            self.assertEqual(result["count_deltas"]["fills"], 1)
            self.assertEqual(result["offline_only"], True)
            self.assertEqual(result["orders_submitted"], False)


def _summary(realized: str, *, fills: int) -> dict:
    return {
        "processed_events": 10,
        "quotes": 10,
        "intents": 1,
        "skipped_events": 0,
        "risk_allowed": 1,
        "risk_blocked": 0,
        "fills": fills,
        "not_filled": 0,
        "closed_positions": 1,
        "open_positions": 0,
        "gross_realized_pnl_usd": realized,
        "realized_cost_usd": "0",
        "realized_pnl_usd": realized,
        "gross_unrealized_pnl_usd": "0",
        "unrealized_cost_usd": "0",
        "unrealized_pnl_usd": "0",
        "audit_records": 2,
        "intent_counts": {"impulse_transfer": 1},
    }
