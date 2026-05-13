from unittest import TestCase

import asyncio
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from apps.health_check import run as run_health_check
from llbot.adapters.metascalp import MetaScalpConnection, MetaScalpInstance
from llbot.domain.enums import MarketType, Venue
from llbot.domain.models import PortfolioState, Quote
from llbot.monitoring.alerts import alerts_to_risk_metadata, evaluate_quote_latency
from llbot.monitoring.health import (
    FeedHealthDecision,
    build_system_health,
    evaluate_feed_health,
    feed_component_health,
    feed_health_metadata,
    feed_stream_key,
    feed_stream_state_to_dict,
    metascalp_component_health,
    risk_component_health,
    storage_component_health,
    system_health_to_dict,
    update_feed_stream_state,
)
from llbot.storage.duckdb_store import DuckDbExecutionStore


class FeedHealthTests(TestCase):
    def test_updates_stream_state_and_counts_stale_gaps(self) -> None:
        state = update_feed_stream_state(None, "binance", "BTCUSDT", 100, stale_gap_ms=500)
        state = update_feed_stream_state(state, "binance", "BTCUSDT", 800, stale_gap_ms=500)

        self.assertEqual(state.event_count, 2)
        self.assertEqual(state.first_ts_ms, 100)
        self.assertEqual(state.last_ts_ms, 800)
        self.assertEqual(state.max_gap_ms, 700)
        self.assertEqual(state.stale_gap_count, 1)

        payload = feed_stream_state_to_dict(state)
        self.assertEqual(payload["book_ticker_events"], 2)
        self.assertEqual(feed_stream_key("binance", "BTCUSDT"), "binance:BTCUSDT")

    def test_evaluate_feed_health_detects_missing_and_stale_streams(self) -> None:
        streams = {
            "binance:BTCUSDT": update_feed_stream_state(
                None,
                "binance",
                "BTCUSDT",
                100,
            )
        }

        missing = evaluate_feed_health(
            streams,
            ("binance:BTCUSDT", "mexc:BTC_USDT"),
            now_ts_ms=200,
            stale_after_ms=500,
        )
        self.assertFalse(missing.healthy)
        self.assertEqual(missing.reason, "missing_stream")
        self.assertEqual(missing.missing_streams, ("mexc:BTC_USDT",))

        stale = evaluate_feed_health(
            streams,
            ("binance:BTCUSDT",),
            now_ts_ms=1000,
            stale_after_ms=500,
        )
        self.assertFalse(stale.healthy)
        self.assertEqual(stale.reason, "stale_stream")
        self.assertEqual(stale.stale_streams, ("binance:BTCUSDT",))

        healthy = evaluate_feed_health(
            streams,
            ("binance:BTCUSDT",),
            now_ts_ms=200,
            stale_after_ms=500,
        )
        self.assertTrue(healthy.healthy)
        self.assertEqual(healthy.reason, "ok")

    def test_feed_health_metadata_maps_streams_to_risk_flags(self) -> None:
        metadata = feed_health_metadata(
            FeedHealthDecision(
                healthy=False,
                reason="stale_stream",
                stale_streams=("binance:BTCUSDT",),
                missing_streams=("mexc:BTC_USDT",),
            )
        )

        self.assertTrue(metadata["binance_feed_stale"])
        self.assertTrue(metadata["mexc_feed_stale"])
        self.assertEqual(metadata["feed_health_reason"], "stale_stream")
        self.assertEqual(metadata["feed_health_stale_streams"], ["binance:BTCUSDT"])
        self.assertEqual(metadata["feed_health_missing_streams"], ["mexc:BTC_USDT"])

    def test_feed_latency_alert_maps_to_risk_metadata(self) -> None:
        alert = evaluate_quote_latency(_quote(exchange_ts_ms=1000, local_ts_ms=2601), 1500)

        self.assertIsNotNone(alert)
        assert alert is not None
        self.assertEqual(alert.reason, "feed_latency_above_threshold")
        self.assertEqual(alert.metadata["latency_ms"], 1601)

        metadata = alerts_to_risk_metadata([alert])
        self.assertTrue(metadata["feed_latency_high"])
        self.assertEqual(metadata["feed_latency_symbol"], "BTCUSDT")

    def test_feed_latency_alert_ignores_missing_or_healthy_exchange_ts(self) -> None:
        self.assertIsNone(evaluate_quote_latency(_quote(exchange_ts_ms=None, local_ts_ms=2601), 1500))
        self.assertIsNone(evaluate_quote_latency(_quote(exchange_ts_ms=1000, local_ts_ms=2400), 1500))

    def test_component_health_aggregates_feed_metascalp_storage_and_risk(self) -> None:
        feed = feed_component_health(FeedHealthDecision(True, "ok"))
        metascalp = metascalp_component_health(_instance(), _connection())
        storage = storage_component_health({"orders": 1, "fills": 0})
        risk = risk_component_health(
            PortfolioState(
                open_positions=0,
                total_notional_usd=Decimal("0"),
                daily_pnl_usd=Decimal("0"),
            )
        )

        payload = system_health_to_dict(build_system_health([feed, metascalp, storage, risk]))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual([component["name"] for component in payload["components"]], [
            "data_feeds",
            "metascalp",
            "storage",
            "risk",
        ])

    def test_component_health_flags_metascalp_and_risk_failures(self) -> None:
        metascalp = metascalp_component_health(_instance(), _connection(state=0))
        risk = risk_component_health(
            PortfolioState(
                open_positions=0,
                total_notional_usd=Decimal("0"),
                daily_pnl_usd=Decimal("0"),
                metadata={"kill_switch": True, "metascalp_connected": False},
            )
        )

        self.assertEqual(metascalp.status, "critical")
        self.assertEqual(metascalp.reason, "metascalp_disconnected")
        self.assertEqual(risk.status, "critical")
        self.assertEqual(risk.reason, "risk_block_active")
        self.assertEqual(
            risk.metadata["active_blocks"],
            ["manual_kill_switch", "metascalp_disconnected"],
        )

    def test_storage_health_reports_counts_or_probe_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "health.duckdb"
            with DuckDbExecutionStore(db_path) as store:
                healthy = storage_component_health(store.table_counts())

        failed = storage_component_health(None, error="cannot open")

        self.assertEqual(healthy.status, "ok")
        self.assertIn("orders", healthy.metadata["table_counts"])
        self.assertEqual(failed.status, "critical")
        self.assertEqual(failed.reason, "storage_probe_failed")

    def test_health_check_cli_run_reads_runner_summary_without_order_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.json"
            db_path = Path(tmp) / "health.duckdb"
            summary.write_text(
                json.dumps(
                    {
                        "health": {
                            "decision": {
                                "healthy": True,
                                "reason": "ok",
                                "stale_streams": [],
                                "missing_streams": [],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            payload = asyncio.run(
                run_health_check(
                    SimpleNamespace(
                        runner_summary=str(summary),
                        db=str(db_path),
                        discover_metascalp=False,
                        select_demo_mexc=False,
                        open_timeout_sec=0.1,
                        risk_metadata_json=None,
                        open_positions=0,
                        total_notional_usd="0",
                        daily_pnl_usd="0",
                        out=None,
                    )
                )
            )

        self.assertEqual(payload["system"]["status"], "ok")
        self.assertFalse(payload["safety"]["orders_submitted"])
        self.assertFalse(payload["safety"]["orders_cancelled"])
        component_names = [component["name"] for component in payload["system"]["components"]]
        self.assertEqual(component_names, ["data_feeds", "storage", "risk"])


def _quote(exchange_ts_ms: int | None, local_ts_ms: int) -> Quote:
    return Quote(
        venue=Venue.BINANCE,
        market=MarketType.USDT_PERP,
        symbol="BTCUSDT",
        bid=Decimal("100"),
        ask=Decimal("101"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
        exchange_ts_ms=exchange_ts_ms,
        local_ts_ms=local_ts_ms,
    )


def _instance() -> MetaScalpInstance:
    return MetaScalpInstance(host="127.0.0.1", port=17845, ping={"app": "MetaScalp"})


def _connection(state: int = 2, demo_mode: bool = True) -> MetaScalpConnection:
    return MetaScalpConnection(
        id=4,
        name="MEXC: Futures",
        exchange="MEXC",
        exchange_id=8,
        market="Futures",
        market_type=1,
        state=state,
        view_mode=False,
        demo_mode=demo_mode,
    )
