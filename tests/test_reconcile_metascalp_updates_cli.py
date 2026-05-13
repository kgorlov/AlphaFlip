import json
import tempfile
from pathlib import Path
from unittest import TestCase

from apps.reconcile_metascalp_updates import build_parser, run


class ReconcileMetaScalpUpdatesCliTests(TestCase):
    def test_replays_jsonl_updates_into_inline_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            updates = Path(tmp) / "updates.jsonl"
            out = Path(tmp) / "report.json"
            updates.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "Type": "OrderUpdate",
                                "Data": {
                                    "ClientId": "llb-1",
                                    "OrderId": "ord-1",
                                    "Status": "Filled",
                                    "FilledQty": "2",
                                    "AvgFillPrice": "100.1",
                                    "Timestamp": 100,
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "Type": "PositionUpdate",
                                "Data": {"ConnectionId": 11, "Symbol": "BTC_USDT", "Qty": "0"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "--order",
                    "intent-1:llb-1:BTC_USDT:2:11",
                    "--updates",
                    str(updates),
                    "--out",
                    str(out),
                ]
            )

            result = run(args)

            self.assertEqual(result["summary"]["updates"], 2)
            self.assertEqual(result["summary"]["positions"], 1)
            self.assertEqual(result["orders"][0]["status"], "filled")
            self.assertFalse(result["orders"][0]["open"])
