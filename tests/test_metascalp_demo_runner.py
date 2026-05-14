from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase

from apps.runner_metascalp_demo import (
    DEFAULT_STREAM_WAIT_MAX_EVENTS,
    _resolve_max_events,
    _should_stop_live_loop,
)
from llbot.adapters.metascalp import MetaScalpConnection
from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, RuntimeMode, Side, Venue
from llbot.domain.market_data import BookTicker
from llbot.execution.metascalp_executor import GuardedMetaScalpDemoExecutor, MetaScalpExecutorConfig
from llbot.execution.paper_fill import FillModel
from llbot.service.metascalp_demo_runner import (
    DemoSubmitConfig,
    intent_from_audit_record,
    should_submit_demo_record,
    submit_demo_records,
)
from llbot.service.paper_runner import PaperRunnerConfig, build_paper_trading_engine
from llbot.service.replay import ReplayAuditRecord
from llbot.signals.feature_store import quote_from_book_ticker


class MetaScalpDemoRunnerTests(TestCase):
    def test_detects_submit_candidate_and_rebuilds_intent(self) -> None:
        record = _record()

        self.assertTrue(should_submit_demo_record(record))
        intent = intent_from_audit_record(record, MarketProfileName.PERP_TO_PERP)

        self.assertEqual(intent.intent_id, "intent-1")
        self.assertEqual(intent.intent_type, IntentType.ENTER_LONG)
        self.assertEqual(intent.side, Side.BUY)
        self.assertEqual(intent.qty, Decimal("2"))
        self.assertEqual(intent.price_cap, Decimal("100.1"))
        self.assertEqual(intent.order_style, OrderStyle.AGGRESSIVE_LIMIT)

    def test_ignores_non_filled_or_exit_records(self) -> None:
        self.assertFalse(should_submit_demo_record(_record(decision_result="risk_blocked")))
        self.assertFalse(should_submit_demo_record(_record(intent_type=IntentType.EXIT_LONG.value)))

    def test_stop_condition_can_wait_for_required_stream_events(self) -> None:
        config = PaperRunnerConfig()
        engine = build_paper_trading_engine(config)
        for ts_ms in (100, 101, 102):
            engine.on_quote(quote_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", ts_ms)))

        self.assertFalse(
            _should_stop_live_loop(
                engine,
                config,
                target_events=3,
                min_events_per_stream=1,
                max_events=10,
            )
        )

        engine.on_quote(quote_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 103)))

        self.assertTrue(
            _should_stop_live_loop(
                engine,
                config,
                target_events=3,
                min_events_per_stream=1,
                max_events=10,
            )
        )

    def test_stop_condition_honors_hard_max_events(self) -> None:
        config = PaperRunnerConfig()
        engine = build_paper_trading_engine(config)
        for ts_ms in (100, 101, 102):
            engine.on_quote(quote_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", ts_ms)))

        self.assertTrue(
            _should_stop_live_loop(
                engine,
                config,
                target_events=3,
                min_events_per_stream=1,
                max_events=3,
            )
        )

    def test_resolve_max_events_defaults_to_stream_wait_cap_when_needed(self) -> None:
        self.assertEqual(
            _resolve_max_events(
                SimpleNamespace(events=100, min_events_per_stream=1, max_events=None)
            ),
            DEFAULT_STREAM_WAIT_MAX_EVENTS,
        )
        self.assertEqual(
            _resolve_max_events(
                SimpleNamespace(events=100, min_events_per_stream=0, max_events=None)
            ),
            100,
        )
        self.assertEqual(
            _resolve_max_events(
                SimpleNamespace(events=100, min_events_per_stream=1, max_events=500)
            ),
            500,
        )


class MetaScalpDemoSubmitTests(IsolatedAsyncioTestCase):
    async def test_submit_demo_records_uses_guarded_executor_dry_run_by_default(self) -> None:
        executor = GuardedMetaScalpDemoExecutor(
            _client(),
            MetaScalpExecutorConfig(allow_submit=False, runtime_mode=RuntimeMode.PAPER),
        )

        audits, count = await submit_demo_records(
            [_record()],
            executor,
            _connection(),
            "BTC_USDT",
            MarketProfileName.PERP_TO_PERP,
            submitted_count=0,
            config=DemoSubmitConfig(max_demo_orders=1),
        )

        self.assertEqual(count, 1)
        self.assertEqual(len(audits), 1)
        self.assertTrue(audits[0].dry_run)
        self.assertEqual(audits[0].decision_result, "dry_run_planned")
        self.assertEqual(audits[0].request["ticker"], "BTC_USDT")


def _record(decision_result: str = "filled", intent_type: str = IntentType.ENTER_LONG.value) -> ReplayAuditRecord:
    return ReplayAuditRecord(
        event_type="replay_signal_decision",
        timestamp_ms=100,
        mode=RuntimeMode.PAPER,
        symbol="BTCUSDT",
        execution_symbol="BTC_USDT",
        intent_id="intent-1",
        intent_type=intent_type,
        side=Side.BUY.value,
        model="test",
        expected_edge_bps=Decimal("8"),
        decision_result=decision_result,
        skip_reason=None,
        risk_allowed=decision_result == "filled",
        risk_reason="ok",
        fill_model=FillModel.TOUCH,
        fill_filled=decision_result == "filled",
        fill_price=Decimal("100"),
        fill_qty=Decimal("2"),
        fill_reason="touch",
        binance_quote=None,
        mexc_quote=None,
        order_request={
            "symbol": "BTC_USDT",
            "canonical_symbol": "BTCUSDT",
            "side": Side.BUY.value,
            "qty": Decimal("2"),
            "price_cap": Decimal("100.1"),
            "ttl_ms": 3000,
            "order_style": OrderStyle.AGGRESSIVE_LIMIT.value,
        },
        order_response={"paper": True},
    )


def _connection() -> MetaScalpConnection:
    return MetaScalpConnection(
        id=4,
        name="MEXC demo",
        exchange="MEXC",
        exchange_id=8,
        market="Futures",
        market_type=1,
        state=2,
        view_mode=False,
        demo_mode=True,
    )


class _client:
    async def place_order(self, connection_id, payload):
        raise AssertionError("dry-run test must not submit")

    async def cancel_order(self, connection_id, payload):
        raise AssertionError("dry-run test must not cancel")


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
