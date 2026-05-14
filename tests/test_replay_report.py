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
    build_research_metrics,
    build_replay_research_report,
    build_symbol_selection,
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
        self.assertIn("research_metrics", report)
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

    def test_research_metrics_measure_catch_up_false_positive_slippage_and_regimes(self) -> None:
        catch_summary, catch_records = replay_paper_events(
            _paper_events(exit_mid="102"),
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            take_profit_bps=Decimal("50"),
            slippage_bps=Decimal("5"),
        )
        loss_summary, loss_records = replay_paper_events(
            _paper_events(exit_mid="99"),
            [_impulse_model(ttl_ms=100)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            slippage_bps=Decimal("5"),
        )

        self.assertEqual(catch_summary.closed_positions, 1)
        self.assertEqual(loss_summary.closed_positions, 1)

        metrics = build_research_metrics([*catch_records, *loss_records])

        self.assertEqual(metrics["catch_up"]["catch_up_exits"], 1)
        self.assertEqual(metrics["catch_up"]["avg_ms"], 100)
        self.assertEqual(metrics["false_positives"]["closed_trades"], 2)
        self.assertEqual(metrics["false_positives"]["false_positives"], 1)
        self.assertEqual(metrics["false_positives"]["false_positive_rate"], Decimal("0.5"))
        hour_bucket = metrics["slippage_by_hour"]["1970-01-01T00:00:00Z"]
        self.assertEqual(hour_bucket["fills"], 5)
        self.assertEqual(hour_bucket["total_slippage_bps"], Decimal("10"))
        self.assertEqual(metrics["performance_by_volatility_regime"]["high"]["closed_trades"], 2)
        self.assertEqual(metrics["performance_by_volatility_regime"]["high"]["winning_trades"], 1)

    def test_symbol_selection_estimates_lag_and_ranks_candidates(self) -> None:
        events = _leadlag_events()

        selection = build_symbol_selection(events, [], top_n=1, candidate_lags_ms=(50, 100, 200))

        top = selection["top_symbols"][0]
        self.assertEqual(top["symbol"], "BTCUSDT")
        self.assertEqual(top["leader"], "binance")
        self.assertEqual(top["lagger"], "mexc")
        self.assertEqual(top["lag_ms"], 100)
        self.assertTrue(top["stable"])
        self.assertGreater(top["selection_score"], Decimal("0"))
        self.assertGreater(top["avg_mexc_top_liquidity_usd"], Decimal("0"))
        self.assertEqual(top["paper_realized_pnl_usd"], Decimal("0"))


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


def _paper_events(exit_mid: str = "102") -> list[ReplayEvent]:
    return [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", exit_mid, 200)),
    ]


def _leadlag_events() -> list[ReplayEvent]:
    mids = ["100", "101", "100.5", "102", "101.5", "103", "102.75", "104"]
    events: list[ReplayEvent] = []
    for idx, mid in enumerate(mids):
        events.append(replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", mid, idx * 100)))
        events.append(
            replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", mid, idx * 100 + 100))
        )
    return events


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
