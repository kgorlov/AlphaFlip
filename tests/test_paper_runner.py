import json
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from apps import runner_paper
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker
from llbot.execution.paper_fill import FillModel
from llbot.service.paper_runner import (
    PaperRunnerConfig,
    build_signal_models,
    initial_paper_portfolio_state,
    run_quote_paper,
    run_quote_paper_result,
    run_replay_paper_result,
    run_replay_paper,
)
from llbot.signals.feature_store import quote_from_book_ticker
from llbot.storage.audit_jsonl import JsonlAuditWriter
from llbot.storage.replay_jsonl import replay_event_from_book_ticker


class PaperRunnerServiceTests(TestCase):
    def test_build_signal_models_selects_requested_model(self) -> None:
        models = build_signal_models(PaperRunnerConfig(model="impulse"))

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].__class__.__name__, "ImpulseTransferSignal")

    def test_run_replay_paper_fills_and_closes_on_ttl(self) -> None:
        summary, audit_records = run_replay_paper(
            _impulse_events(exit_mid="102"),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
                fill_model=FillModel.TOUCH,
            ),
        )

        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.risk_allowed, 1)
        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("2"))
        self.assertEqual(audit_records[-1].exit_reason, "ttl_exit")

    def test_run_replay_paper_blocks_stale_execution_feed(self) -> None:
        summary, audit_records = run_replay_paper(
            [
                replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
                replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
                replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 200)),
                replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 300)),
            ],
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                impulse_windows_ms=(100,),
                stale_feed_ms=150,
            ),
            portfolio_state=initial_paper_portfolio_state(),
        )

        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.risk_allowed, 0)
        self.assertEqual(summary.risk_blocked, 1)
        self.assertEqual(summary.fills, 0)
        self.assertEqual(audit_records[0].decision_result, "risk_blocked")
        self.assertEqual(audit_records[0].skip_reason, "mexc_feed_stale")

    def test_run_replay_paper_result_includes_feed_health_report(self) -> None:
        result = run_replay_paper_result(
            _impulse_events(exit_mid="102"),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
                stale_feed_ms=500,
            ),
        )

        self.assertEqual(result.summary.closed_positions, 1)
        self.assertEqual(result.health_report["required_streams"], ["binance:BTCUSDT", "mexc:BTC_USDT"])
        self.assertEqual(result.health_report["decision"]["healthy"], True)
        self.assertEqual(
            result.health_report["streams"]["binance:BTCUSDT"]["book_ticker_events"],
            2,
        )

    def test_jsonl_audit_writer_streams_records(self) -> None:
        result = run_replay_paper_result(
            _impulse_events(exit_mid="102"),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "streamed-audit.jsonl"
            with JsonlAuditWriter(path) as writer:
                for record in result.audit_records:
                    writer.append(record)
            payloads = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["decision_result"], "filled")
        self.assertEqual(payloads[1]["exit_reason"], "ttl_exit")

    def test_paper_summary_payload_reports_cycle_pnl_percent(self) -> None:
        result = run_replay_paper_result(
            _impulse_events(exit_mid="102"),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
            ),
        )

        payload = runner_paper.paper_summary_payload(result.summary, "100")

        self.assertEqual(payload["total_pnl_usd"], Decimal("2"))
        self.assertEqual(payload["starting_balance_usd"], Decimal("100"))
        self.assertEqual(payload["pnl_pct_of_balance"], Decimal("2.00"))


class LivePaperRunnerServiceTests(IsolatedAsyncioTestCase):
    async def test_run_quote_paper_consumes_async_quote_stream(self) -> None:
        summary, audit_records = await run_quote_paper(
            _quote_stream(_impulse_tickers(exit_mid="102")),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
                fill_model=FillModel.TOUCH,
            ),
        )

        self.assertEqual(summary.processed_events, 5)
        self.assertEqual(summary.skipped_events, 0)
        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("2"))
        self.assertEqual(audit_records[-1].exit_reason, "ttl_exit")

    async def test_run_quote_paper_result_streams_audit_and_reports_health(self) -> None:
        streamed = []
        summaries = []
        result = await run_quote_paper_result(
            _quote_stream(_impulse_tickers(exit_mid="102")),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
                stale_feed_ms=500,
            ),
            audit_sink=streamed.append,
            summary_sink=summaries.append,
            summary_interval_quotes=2,
        )

        self.assertEqual(result.summary.closed_positions, 1)
        self.assertEqual(len(streamed), 2)
        self.assertGreaterEqual(len(summaries), 2)
        self.assertEqual(summaries[-1].closed_positions, 1)
        self.assertEqual([record.event_type for record in streamed], [
            "replay_signal_decision",
            "replay_position_exit",
        ])
        self.assertEqual(result.health_report["decision"]["healthy"], True)
        self.assertEqual(
            result.health_report["streams"]["mexc:BTC_USDT"]["book_ticker_events"],
            3,
        )

    async def test_run_quote_paper_result_stops_at_closed_trade_target(self) -> None:
        result = await run_quote_paper_result(
            _quote_stream(_impulse_tickers(exit_mid="102") + [_ticker(Venue.BINANCE, "BTCUSDT", "103", 300)]),
            PaperRunnerConfig(
                model="impulse",
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                ttl_ms=100,
                impulse_windows_ms=(100,),
                fill_model=FillModel.TOUCH,
            ),
            max_closed_positions=1,
            max_quotes=100,
        )

        self.assertEqual(result.summary.closed_positions, 1)
        self.assertEqual(result.summary.quotes, 5)

    def test_paper_summary_payload_reports_target_stop_reason(self) -> None:
        args = SimpleNamespace(live_ws=True, events=100, target_closed_trades=1)
        payload = {"closed_positions": 1, "quotes": 5}

        reason = runner_paper._stop_reason(payload, args)

        self.assertEqual(reason, "target_closed_trades_reached")

    async def test_live_ws_quotes_tolerates_single_stream_open_failure(self) -> None:
        async def failing_pump(symbol, open_timeout_sec, queue, stop, reconnect_delay_sec=0, max_reconnects=0):
            exc = TimeoutError("timed out during opening handshake")
            await queue.put(exc)
            raise exc

        async def healthy_pump(symbol, open_timeout_sec, queue, stop, reconnect_delay_sec=0, max_reconnects=0):
            await queue.put(quote_from_book_ticker(_ticker(Venue.BINANCE, symbol, "100", 1)))
            await stop.wait()

        args = SimpleNamespace(
            leader_symbol="BTCUSDT",
            lagger_symbol="BTC_USDT",
            open_timeout_sec=0.01,
            ws_reconnect_delay_sec=0,
            ws_max_reconnects=1,
        )

        with patch.object(runner_paper, "_pump_binance_usdm", healthy_pump), patch.object(
            runner_paper,
            "_pump_mexc_contract",
            failing_pump,
        ):
            stream = runner_paper._live_ws_quotes(args)
            quote = await anext(stream)
            await stream.aclose()

        self.assertEqual(quote.symbol, "BTCUSDT")
        self.assertEqual(quote.venue, Venue.BINANCE)


def _impulse_events(exit_mid: str | None = None) -> list:
    return [replay_event_from_book_ticker(ticker) for ticker in _impulse_tickers(exit_mid)]


def _impulse_tickers(exit_mid: str | None = None) -> list[BookTicker]:
    events = [
        _ticker(Venue.BINANCE, "BTCUSDT", "100", 0),
        _ticker(Venue.MEXC, "BTC_USDT", "100", 0),
        _ticker(Venue.BINANCE, "BTCUSDT", "101", 100),
        _ticker(Venue.MEXC, "BTC_USDT", "100", 100),
    ]
    if exit_mid is not None:
        events.append(_ticker(Venue.MEXC, "BTC_USDT", exit_mid, 200))
    return events


async def _quote_stream(tickers: list[BookTicker]):
    for ticker in tickers:
        yield quote_from_book_ticker(ticker)


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
