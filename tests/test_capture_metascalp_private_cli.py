import asyncio
import json
import tempfile
from pathlib import Path
from unittest import TestCase

from apps.capture_metascalp_private import build_parser, run
from llbot.storage.duckdb_store import DuckDbExecutionStore


class CaptureMetaScalpPrivateCliTests(TestCase):
    def test_events_zero_smoke_writes_empty_capture_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "updates.jsonl"
            summary = Path(tmp) / "summary.json"
            args = build_parser().parse_args(
                [
                    "--events",
                    "0",
                    "--out",
                    str(out),
                    "--summary-out",
                    str(summary),
                ]
            )

            result = asyncio.run(run(args))

            self.assertTrue(out.exists())
            self.assertEqual(out.read_text(encoding="utf-8"), "")
            self.assertEqual(result["capture"]["captured"], 0)
            self.assertFalse(result["capture"]["opened_websocket"])
            self.assertFalse(result["capture"]["safety"]["submits_orders"])

    def test_reconciles_existing_captured_file_and_stores_duckdb_when_events_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "updates.jsonl"
            reconcile = Path(tmp) / "reconcile.json"
            db_path = Path(tmp) / "private.duckdb"
            out.write_text(
                json.dumps(
                    {
                        "event_type": "metascalp_private_ws_update",
                        "raw": {
                            "Type": "OrderUpdate",
                            "Data": {
                                "ClientId": "llb-1",
                                "OrderId": "ord-1",
                                "Status": "Filled",
                                "FilledQty": "2",
                                "AvgFillPrice": "100.1",
                                "Timestamp": 100,
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "--events",
                    "0",
                    "--out",
                    str(out),
                    "--read-existing",
                    "--order",
                    "intent-1:llb-1:BTC_USDT:2:11:ord-1",
                    "--reconcile-out",
                    str(reconcile),
                    "--db",
                    str(db_path),
                    "--source",
                    "cli-capture-smoke",
                ]
            )

            result = asyncio.run(run(args))

            self.assertEqual(result["reconciliation"]["updates"], 1)
            self.assertEqual(result["storage"]["inserted"]["fills"], 1)
            self.assertTrue(reconcile.exists())
            with DuckDbExecutionStore(db_path) as store:
                self.assertEqual(store.table_counts()["fills"], 1)
                source = store.query_all("SELECT DISTINCT source FROM metascalp_fills")[0][0]
                self.assertEqual(source, "cli-capture-smoke")
