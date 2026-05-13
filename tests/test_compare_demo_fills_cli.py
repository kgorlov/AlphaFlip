import json
import tempfile
from pathlib import Path
from unittest import TestCase

from apps.compare_demo_fills import build_parser, run


class CompareDemoFillsCliTests(TestCase):
    def test_cli_writes_comparison_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = Path(tmp) / "paper.jsonl"
            reconciled = Path(tmp) / "reconciled.json"
            out = Path(tmp) / "compare.json"
            paper.write_text(
                json.dumps(
                    {
                        "event_type": "replay_signal_decision",
                        "decision_result": "filled",
                        "fill_filled": True,
                        "fill_qty": "2",
                        "fill_price": "100",
                        "intent_id": "intent-1",
                        "execution_symbol": "BTC_USDT",
                        "order_request": {"ClientId": "llb-intent-1"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            reconciled.write_text(
                json.dumps(
                    {
                        "orders": [
                            {
                                "client_order_id": "llb-intent-1",
                                "symbol": "BTC_USDT",
                                "filled_qty": "2",
                                "avg_fill_price": "100.25",
                                "status": "filled",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                ["--paper-audit", str(paper), "--reconciled", str(reconciled), "--out", str(out)]
            )

            result = run(args)

            self.assertEqual(result["summary"]["matched"], 1)
            self.assertEqual(result["summary"]["price_mismatches"], 1)
            self.assertEqual(result["comparisons"][0]["price_diff"], "0.25")
