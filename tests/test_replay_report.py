from decimal import Decimal
from unittest import TestCase

from llbot.config import RiskConfig
from llbot.domain.enums import MarketProfileName, MarketType, Venue
from llbot.domain.market_data import BookTicker
from llbot.domain.models import PortfolioState
from llbot.execution.paper_fill import FillModel
from llbot.risk.limits import BasicRiskEngine
from llbot.service.replay import replay_paper_events
from llbot.service.replay_report import (
    build_feed_health,
    build_fill_model_diagnostics,
    build_replay_research_report,
)
from llbot.signals.impulse_transfer import ImpulseTransferConfig, ImpulseTransferSignal
from llbot.storage.replay_jsonl import ReplayEvent, replay_event_from_book_ticker


class ReplayReportTests(TestCase):
    def test_feed_health_counts_quote_gaps_per_stream(self) -> None:
        health = build_feed_health(
            [
                _event("binance", "BTCUSDT", 0),
                _event("binance", "BTCUSDT", 100),
                _event("binance", "BTCUSDT", 700),
                _event("mexc", "BTC_USDT", 50),
            ],
            stale_gap_ms=500,
        )

        stream = health["streams"]["binance:BTCUSDT"]
        self.assertEqual(health["total_book_ticker_events"], 4)
        self.assertEqual(stream["book_ticker_events"], 3)
        self.assertEqual(stream["max_gap_ms"], 600)
        self.assertEqual(stream["stale_gap_count"], 1)
        self.assertFalse(health["decision"]["healthy"])
        self.assertEqual(health["decision"]["reason"], "stale_stream")

    def test_research_report_includes_symbol_day_and_fill_model_variants(self) -> None:
        events = _paper_events()
        summary, audit_records = replay_paper_events(
            events,
            [_impulse_model(ttl_ms=100)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        report = build_replay_research_report(
            events,
            summary,
            audit_records,
            stale_gap_ms=500,
            fill_model_variants=[{"fill_model": "touch", "fills": 1}],
            fill_model_variant_records={"touch": audit_records},
        )

        symbol_day = next(iter(report["by_symbol_day"].values()))
        self.assertEqual(report["summary"]["closed_positions"], 1)
        self.assertEqual(symbol_day["symbol"], "BTCUSDT")
        self.assertEqual(symbol_day["signals"], 1)
        self.assertEqual(symbol_day["entry_fills"], 1)
        self.assertEqual(symbol_day["exits"], 1)
        self.assertEqual(symbol_day["realized_pnl_usd"], Decimal("2"))
        self.assertEqual(symbol_day["exit_reasons"], {"ttl_exit": 1})
        self.assertEqual(report["fill_model_variants"][0]["fill_model"], "touch")
        self.assertEqual(report["fill_model_diagnostics"][0]["models"]["touch"]["fill_filled"], True)
        self.assertIn("binance:BTCUSDT", report["feed_health"]["streams"])

    def test_fill_model_diagnostics_flags_candidate_differences(self) -> None:
        events = _paper_events()
        _, touch_records = replay_paper_events(
            events,
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )
        _, trade_records = replay_paper_events(
            events,
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TRADE_THROUGH,
        )

        diagnostics = build_fill_model_diagnostics(
            {"touch": touch_records, "trade_through": trade_records}
        )

        self.assertEqual(len(diagnostics), 1)
        self.assertTrue(diagnostics[0]["has_difference"])
        self.assertTrue(diagnostics[0]["models"]["touch"]["fill_filled"])
        self.assertFalse(diagnostics[0]["models"]["trade_through"]["fill_filled"])
        self.assertEqual(
            diagnostics[0]["models"]["trade_through"]["fill_reason"],
            "trade_required",
        )


def _event(venue: str, symbol: str, ts_ms: int) -> ReplayEvent:
    return ReplayEvent(
        event_type="book_ticker",
        venue=venue,
        market=MarketType.USDT_PERP.value,
        symbol=symbol,
        local_ts_ms=ts_ms,
        exchange_ts_ms=ts_ms,
        receive_monotonic_ns=None,
        payload={},
        captured_at_utc="2026-05-13T00:00:00Z",
    )


def _paper_events() -> list[ReplayEvent]:
    return [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "102", 200)),
    ]


def _impulse_model(ttl_ms: int) -> ImpulseTransferSignal:
    return ImpulseTransferSignal(
        ImpulseTransferConfig(
            canonical_symbol="BTCUSDT",
            leader_symbol="BTCUSDT",
            lagger_symbol="BTC_USDT",
            profile=MarketProfileName.PERP_TO_PERP,
            windows_ms=(100,),
            min_impulse_bps=Decimal("2"),
            safety_bps=Decimal("0"),
            cooldown_ms=0,
            ttl_ms=ttl_ms,
        )
    )


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
        open_positions=0,
        total_notional_usd=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        metadata={"metascalp_connected": True},
    )


def _ticker(venue: Venue, symbol: str, mid: str, ts_ms: int) -> BookTicker:
    price = Decimal(mid)
    return BookTicker(
        venue=venue,
        market=MarketType.USDT_PERP,
        symbol=symbol,
        bid_price=price,
        bid_qty=Decimal("10"),
        ask_price=price,
        ask_qty=Decimal("10"),
        timestamp_ms=ts_ms,
        local_ts_ms=ts_ms,
    )
