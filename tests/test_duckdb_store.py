import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from llbot.storage.duckdb_store import DuckDbExecutionStore


class DuckDbExecutionStoreTests(TestCase):
    def test_ingests_reconciliation_report_into_queryable_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "private.duckdb"
            with DuckDbExecutionStore(db_path) as store:
                inserted = store.ingest_reconciliation_report(_report(), source="smoke")

                self.assertEqual(
                    inserted,
                    {
                        "orders": 1,
                        "fills": 1,
                        "positions": 1,
                        "balances": 1,
                        "audit_records": 2,
                    },
                )
                self.assertEqual(
                    store.table_counts(),
                    {
                        "orders": 1,
                        "fills": 1,
                        "positions": 1,
                        "balances": 1,
                        "audit_records": 2,
                    },
                )
                order = store.query_all(
                    """
                    SELECT client_order_id, status, filled_qty, avg_fill_price, is_open,
                           connection_id
                    FROM metascalp_orders
                    """
                )[0]
                self.assertEqual(order[0], "llb-1")
                self.assertEqual(order[1], "filled")
                self.assertEqual(order[2], Decimal("2.000000000000000000"))
                self.assertEqual(order[3], Decimal("100.100000000000000000"))
                self.assertFalse(order[4])
                self.assertEqual(order[5], 11)

                fill = store.query_all(
                    "SELECT client_order_id, symbol, filled_qty FROM metascalp_fills"
                )[0]
                self.assertEqual(fill[0], "llb-1")
                self.assertEqual(fill[1], "BTC_USDT")
                self.assertEqual(fill[2], Decimal("2.000000000000000000"))

    def test_replace_source_keeps_smoke_ingestion_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "private.duckdb"
            with DuckDbExecutionStore(db_path) as store:
                store.ingest_reconciliation_report(_report(), source="same-source")
                store.ingest_reconciliation_report(_report(), source="same-source")

                self.assertEqual(
                    store.table_counts(),
                    {
                        "orders": 1,
                        "fills": 1,
                        "positions": 1,
                        "balances": 1,
                        "audit_records": 2,
                    },
                )


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
                "accepted_ts_ms": 100,
                "expires_ts_ms": 200,
                "last_update_ts_ms": 150,
                "unknown_status": False,
                "metadata": {"connection_id": 11, "execution_time_ms": 12},
            }
        ],
        "audit_records": [
            {
                "event_type": "metascalp_order_update",
                "decision_result": "order_reconciled",
                "client_order_id": "llb-1",
                "before_status": "accepted",
                "after_status": "filled",
                "symbol": "BTC_USDT",
                "raw_update": {"Type": "OrderUpdate"},
                "metadata": {"order_event_type": "fill"},
            },
            {
                "event_type": "metascalp_position_update",
                "decision_result": "position_snapshot",
                "client_order_id": None,
                "before_status": None,
                "after_status": None,
                "symbol": "BTC_USDT",
                "raw_update": {"Type": "PositionUpdate"},
                "metadata": {"qty": "0"},
            },
        ],
        "positions": [
            {
                "connection_id": 11,
                "symbol": "BTC_USDT",
                "qty": "0",
                "avg_price": "100.1",
                "raw": {"Symbol": "BTC_USDT"},
            }
        ],
        "balances": [
            {
                "connection_id": 11,
                "asset": "USDT",
                "available": "10",
                "total": "12",
                "raw": {"Asset": "USDT"},
            }
        ],
    }
