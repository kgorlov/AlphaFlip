import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from llbot.storage.duckdb_store import DuckDbExecutionStore
from llbot.storage.replay_jsonl import replay_event_from_book_ticker
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker


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
                        "market_quotes": 0,
                        "market_trades": 0,
                        "signal_intents": 0,
                        "order_facts": 0,
                        "fill_facts": 0,
                        "pnl_facts": 0,
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
                        "market_quotes": 0,
                        "market_trades": 0,
                        "signal_intents": 0,
                        "order_facts": 0,
                        "fill_facts": 0,
                        "pnl_facts": 0,
                    },
                )

    def test_broad_schema_ingests_market_and_audit_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "facts.duckdb"
            with DuckDbExecutionStore(db_path) as store:
                market = store.ingest_replay_events([_book_event()], source="market")
                audit = store.ingest_audit_records([_signal_record(), _exit_record()], source="audit")

                self.assertEqual(market, {"market_quotes": 1, "market_trades": 0})
                self.assertEqual(
                    audit,
                    {"signal_intents": 1, "order_facts": 1, "fill_facts": 1, "pnl_facts": 1},
                )
                self.assertEqual(store.query_all("SELECT symbol, bid_price FROM market_quotes")[0][0], "BTCUSDT")
                self.assertEqual(store.query_all("SELECT intent_id FROM signal_intents")[0][0], "intent-1")
                self.assertEqual(store.query_all("SELECT net_pnl_usd FROM pnl_facts")[0][0], Decimal("1.230000000000000000"))


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


def _book_event():
    return replay_event_from_book_ticker(
        BookTicker(
            venue=Venue.BINANCE,
            market=MarketType.USDT_PERP,
            symbol="BTCUSDT",
            bid_price=Decimal("100"),
            bid_qty=Decimal("1"),
            ask_price=Decimal("101"),
            ask_qty=Decimal("2"),
            timestamp_ms=10,
            local_ts_ms=11,
            raw={},
        )
    )


def _signal_record() -> dict:
    return {
        "event_type": "replay_signal_decision",
        "intent_id": "intent-1",
        "symbol": "BTCUSDT",
        "mode": "paper",
        "intent_type": "enter_long",
        "side": "buy",
        "model": "impulse",
        "expected_edge_bps": "8",
        "decision_result": "filled",
        "risk_allowed": True,
        "risk_reason": "ok",
        "fill_filled": True,
        "fill_qty": "1",
        "fill_price": "100.5",
        "fill_reason": "touch",
        "order_request": {
            "symbol": "BTC_USDT",
            "side": "buy",
            "qty": "1",
            "price_cap": "100.5",
        },
        "order_response": {"client_order_id": "llb-1"},
    }


def _exit_record() -> dict:
    return {
        "event_type": "replay_position_exit",
        "symbol": "BTCUSDT",
        "exit_reason": "ttl_exit",
        "gross_pnl_usd": "1.5",
        "cost_usd": "0.27",
        "realized_pnl_usd": "1.23",
    }
