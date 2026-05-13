import json
import tempfile
from pathlib import Path
from unittest import TestCase

from apps.store_metascalp_reconcile import build_parser, run
from llbot.storage.duckdb_store import DuckDbExecutionStore


class StoreMetaScalpReconcileCliTests(TestCase):
    def test_loads_reconciled_report_into_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "reconciled.json"
            db_path = Path(tmp) / "private.duckdb"
            summary = Path(tmp) / "summary.json"
            report.write_text(json.dumps(_report()), encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "--reconciled",
                    str(report),
                    "--db",
                    str(db_path),
                    "--summary-out",
                    str(summary),
                    "--source",
                    "cli-smoke",
                ]
            )

            result = run(args)

            self.assertEqual(result["inserted"]["orders"], 1)
            self.assertEqual(result["inserted"]["fills"], 1)
            self.assertTrue(result["safety"]["offline_only"])
            self.assertFalse(result["safety"]["submits_orders"])

            with DuckDbExecutionStore(db_path) as store:
                self.assertEqual(result["table_counts"], store.table_counts())
                source = store.query_all("SELECT DISTINCT source FROM metascalp_orders")[0][0]
                self.assertEqual(source, "cli-smoke")


def _report() -> dict:
    return {
        "orders": [
            {
                "intent_id": "intent-1",
                "client_order_id": "llb-1",
                "venue_order_id": "ord-1",
                "symbol": "BTC_USDT",
                "qty": "2",
                "filled_qty": "2",
                "avg_fill_price": "100.1",
                "open": False,
                "status": "filled",
                "last_update_ts_ms": 150,
                "unknown_status": False,
                "metadata": {"connection_id": 11},
            }
        ],
        "audit_records": [],
        "positions": [],
        "balances": [],
    }
