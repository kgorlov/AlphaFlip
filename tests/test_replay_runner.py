import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from llbot.config import RiskConfig
from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, Side, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth
from llbot.domain.models import Intent, PortfolioState, Quote, Trade
from llbot.execution.paper_fill import FillModel
from llbot.risk.limits import BasicRiskEngine
from llbot.service.replay import replay_events, replay_paper_events
from llbot.signals.impulse_transfer import ImpulseTransferConfig, ImpulseTransferSignal
from llbot.storage.audit_jsonl import write_audit_records
from llbot.storage.replay_jsonl import (
    JsonlReplayWriter,
    read_replay_events,
    replay_event_from_book_ticker,
    replay_event_from_depth,
)


class ReplayRunnerTests(TestCase):
    def test_replay_sorts_quotes_skips_depth_and_counts_model_intents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            writer = JsonlReplayWriter(path)
            writer.append(replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)))
            writer.append(replay_event_from_depth(_depth("BTC_USDT", 50)))
            writer.append(replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)))
            writer.append(replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)))
            writer.append(replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 100)))

            summary, intents = replay_events(read_replay_events(path), [_impulse_model()])

        self.assertEqual(summary.processed_events, 5)
        self.assertEqual(summary.quotes, 4)
        self.assertEqual(summary.skipped_events, 1)
        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.intent_counts, {"impulse_transfer": 1})
        self.assertEqual(intents[0].side, Side.BUY)
        self.assertEqual(intents[0].created_ts_ms, 100)

    def test_replay_paper_allows_and_fills_signal(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(),
            [_impulse_model()],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.risk_allowed, 1)
        self.assertEqual(summary.risk_blocked, 0)
        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.not_filled, 0)
        self.assertEqual(summary.closed_positions, 0)
        self.assertEqual(summary.open_positions, 1)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("0"))
        self.assertEqual(summary.realized_cost_usd, Decimal("0"))
        self.assertEqual(summary.realized_pnl_usd, Decimal("0"))
        self.assertEqual(summary.gross_unrealized_pnl_usd, Decimal("0"))
        self.assertEqual(summary.unrealized_cost_usd, Decimal("0"))
        self.assertEqual(summary.unrealized_pnl_usd, Decimal("0"))
        self.assertEqual(summary.audit_records, 1)
        self.assertEqual(audit_records[0].decision_result, "filled")
        self.assertIsNone(audit_records[0].skip_reason)
        self.assertEqual(audit_records[0].fill_reason, "touch")
        self.assertEqual(audit_records[0].mexc_quote["symbol"], "BTC_USDT")
        self.assertEqual(audit_records[0].impulse_bps, Decimal("100"))
        self.assertEqual(audit_records[0].lag_bps, Decimal("100"))
        self.assertEqual(audit_records[0].fee_bps, Decimal("0"))
        self.assertEqual(audit_records[0].slippage_bps, Decimal("0"))
        self.assertEqual(audit_records[0].safety_bps, Decimal("0"))

    def test_replay_paper_records_risk_block_reason(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(),
            [_impulse_model()],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(metadata={"kill_switch": True}),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.risk_allowed, 0)
        self.assertEqual(summary.risk_blocked, 1)
        self.assertEqual(summary.fills, 0)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(audit_records[0].decision_result, "risk_blocked")
        self.assertEqual(audit_records[0].skip_reason, "manual_kill_switch")
        self.assertFalse(audit_records[0].risk_allowed)

    def test_replay_paper_audit_records_are_written_as_jsonl(self) -> None:
        _, audit_records = replay_paper_events(
            _impulse_events(),
            [_impulse_model()],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            write_audit_records(path, audit_records)
            payload = json.loads(path.read_text(encoding="utf-8").strip())

        self.assertEqual(payload["event_type"], "replay_signal_decision")
        self.assertEqual(payload["decision_result"], "filled")
        self.assertEqual(payload["fill_model"], "touch")
        self.assertEqual(payload["fill_price"], "100")
        self.assertEqual(payload["order_request"]["symbol"], "BTC_USDT")

    def test_replay_paper_closes_long_on_ttl_and_reports_realized_pnl(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(exit_mid="102"),
            [_impulse_model(ttl_ms=100)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("2"))
        self.assertEqual(summary.realized_cost_usd, Decimal("0"))
        self.assertEqual(summary.realized_pnl_usd, Decimal("2"))
        self.assertEqual(summary.unrealized_pnl_usd, Decimal("0"))
        self.assertEqual(summary.audit_records, 2)

        exit_record = audit_records[-1]
        self.assertEqual(exit_record.event_type, "replay_position_exit")
        self.assertEqual(exit_record.exit_reason, "ttl_exit")
        self.assertEqual(exit_record.gross_pnl_usd, Decimal("2"))
        self.assertEqual(exit_record.cost_usd, Decimal("0"))
        self.assertEqual(exit_record.realized_pnl_usd, Decimal("2"))
        self.assertEqual(exit_record.fill_price, Decimal("102"))
        self.assertEqual(exit_record.order_request["reduce_only"], True)

    def test_replay_paper_closes_short_on_ttl_and_reports_realized_pnl(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(direction="short", exit_mid="98"),
            [_impulse_model(ttl_ms=100)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(summary.realized_pnl_usd, Decimal("2"))

        exit_record = audit_records[-1]
        self.assertEqual(exit_record.event_type, "replay_position_exit")
        self.assertEqual(exit_record.intent_type, "exit_short")
        self.assertEqual(exit_record.side, "buy")
        self.assertEqual(exit_record.realized_pnl_usd, Decimal("2"))

    def test_replay_paper_closes_on_take_profit_before_ttl(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(exit_mid="101"),
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            take_profit_bps=Decimal("50"),
        )

        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("1"))
        self.assertEqual(summary.realized_pnl_usd, Decimal("1"))

        exit_record = audit_records[-1]
        self.assertEqual(exit_record.exit_reason, "take_profit")
        self.assertEqual(exit_record.fill_reason, "take_profit")
        self.assertEqual(exit_record.fill_price, Decimal("101"))

    def test_replay_paper_marks_open_position_to_market_with_costs(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(exit_mid="101"),
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            fee_bps=Decimal("5"),
            slippage_bps=Decimal("5"),
        )

        self.assertEqual(summary.closed_positions, 0)
        self.assertEqual(summary.open_positions, 1)
        self.assertEqual(summary.gross_unrealized_pnl_usd, Decimal("1"))
        self.assertEqual(summary.unrealized_cost_usd, Decimal("0.201"))
        self.assertEqual(summary.unrealized_pnl_usd, Decimal("0.799"))
        self.assertEqual(audit_records[-1].decision_result, "filled")

    def test_replay_paper_realized_pnl_deducts_fee_and_slippage_costs(self) -> None:
        summary, audit_records = replay_paper_events(
            _impulse_events(exit_mid="102"),
            [_impulse_model(ttl_ms=100)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            fee_bps=Decimal("5"),
            slippage_bps=Decimal("5"),
        )

        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("2"))
        self.assertEqual(summary.realized_cost_usd, Decimal("0.202"))
        self.assertEqual(summary.realized_pnl_usd, Decimal("1.798"))

        exit_record = audit_records[-1]
        self.assertEqual(exit_record.gross_pnl_usd, Decimal("2"))
        self.assertEqual(exit_record.cost_usd, Decimal("0.202"))
        self.assertEqual(exit_record.realized_pnl_usd, Decimal("1.798"))

    def test_replay_paper_closes_on_stale_binance_reference_data(self) -> None:
        summary, audit_records = replay_paper_events(
            _stale_exit_events(),
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            stale_feed_ms=500,
        )

        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        self.assertEqual(summary.risk_blocked, 1)
        self.assertEqual(summary.gross_realized_pnl_usd, Decimal("-1"))

        exit_record = [record for record in audit_records if record.exit_reason == "stale_data_stop"][0]
        self.assertEqual(exit_record.event_type, "replay_position_exit")
        self.assertEqual(exit_record.exit_reason, "stale_data_stop")
        self.assertEqual(exit_record.fill_price, Decimal("99"))
        self.assertEqual(exit_record.realized_pnl_usd, Decimal("-1"))

        risk_record = audit_records[-1]
        self.assertEqual(risk_record.decision_result, "risk_blocked")
        self.assertEqual(risk_record.skip_reason, "binance_feed_stale")

    def test_replay_paper_risk_blocks_when_mexc_execution_feed_is_missing(self) -> None:
        summary, audit_records = replay_paper_events(
            [replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 100))],
            [_ImmediateLongSignal()],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
            stale_feed_ms=500,
        )

        self.assertEqual(summary.intents, 1)
        self.assertEqual(summary.risk_allowed, 0)
        self.assertEqual(summary.risk_blocked, 1)
        self.assertEqual(summary.not_filled, 0)
        self.assertEqual(audit_records[0].decision_result, "risk_blocked")
        self.assertEqual(audit_records[0].skip_reason, "mexc_feed_stale")

    def test_replay_paper_closes_on_reversal_signal_before_new_entry(self) -> None:
        summary, audit_records = replay_paper_events(
            _reversal_events(),
            [_impulse_model(ttl_ms=3000)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.intents, 2)
        self.assertEqual(summary.fills, 2)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 1)

        reversal_exit = [record for record in audit_records if record.exit_reason == "reversal_stop"]
        self.assertEqual(len(reversal_exit), 1)
        self.assertEqual(reversal_exit[0].intent_type, "exit_long")
        self.assertEqual(reversal_exit[0].side, "sell")
        self.assertEqual(reversal_exit[0].realized_pnl_usd, Decimal("0"))

        self.assertEqual(audit_records[-1].decision_result, "filled")
        self.assertEqual(audit_records[-1].side, "sell")

    def test_replay_paper_closes_residual_long_on_zscore_mean_reversion(self) -> None:
        summary, audit_records = replay_paper_events(
            _residual_exit_events(exit_binance_mid="100", exit_mexc_mid="100"),
            [_ImmediateResidualSignal(Side.BUY)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(summary.open_positions, 0)
        exit_record = audit_records[-1]
        self.assertEqual(exit_record.exit_reason, "zscore_mean_reversion")
        self.assertEqual(exit_record.order_request["reduce_only"], True)
        self.assertEqual(exit_record.features["entry_features"]["model"], "residual_zscore")
        self.assertEqual(exit_record.rolling_basis_bps, Decimal("-60"))
        self.assertEqual(exit_record.z_score, Decimal("-3"))

    def test_replay_paper_closes_residual_short_on_zscore_mean_reversion(self) -> None:
        summary, audit_records = replay_paper_events(
            _residual_exit_events(exit_binance_mid="100", exit_mexc_mid="100"),
            [_ImmediateResidualSignal(Side.SELL)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(audit_records[-1].exit_reason, "zscore_mean_reversion")
        self.assertEqual(audit_records[-1].intent_type, "exit_short")

    def test_replay_paper_closes_residual_long_on_adverse_move(self) -> None:
        summary, audit_records = replay_paper_events(
            _residual_exit_events(exit_binance_mid="101", exit_mexc_mid="100"),
            [_ImmediateResidualSignal(Side.BUY)],
            risk_engine=BasicRiskEngine(RiskConfig()),
            portfolio_state=_portfolio_state(),
            execution_symbol="BTC_USDT",
            fill_model=FillModel.TOUCH,
        )

        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.closed_positions, 1)
        self.assertEqual(audit_records[-1].exit_reason, "adverse_move_stop")


def _impulse_model(ttl_ms: int = 3000) -> ImpulseTransferSignal:
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


def _impulse_events(direction: str = "long", exit_mid: str | None = None) -> list:
    impulse_mid = "101" if direction == "long" else "99"
    events = [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", impulse_mid, 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
    ]
    if exit_mid is not None:
        events.append(replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", exit_mid, 200)))
    return events


def _stale_exit_events() -> list:
    return [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "99", 1000)),
    ]


def _reversal_events() -> list:
    return [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "101", 100)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "99", 200)),
    ]


def _residual_exit_events(exit_binance_mid: str, exit_mexc_mid: str) -> list:
    return [
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", "100", 0)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", "100", 100)),
        replay_event_from_book_ticker(_ticker(Venue.BINANCE, "BTCUSDT", exit_binance_mid, 150)),
        replay_event_from_book_ticker(_ticker(Venue.MEXC, "BTC_USDT", exit_mexc_mid, 200)),
    ]


def _portfolio_state(metadata: dict[str, object] | None = None) -> PortfolioState:
    return PortfolioState(
        open_positions=0,
        total_notional_usd=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        metadata=metadata or {"metascalp_connected": True},
    )


class _ImmediateLongSignal:
    def on_quote(self, q: Quote) -> list[Intent]:
        return [
            Intent(
                intent_id=f"immediate-{q.local_ts_ms}",
                symbol="BTCUSDT",
                profile=MarketProfileName.PERP_TO_PERP,
                intent_type=IntentType.ENTER_LONG,
                side=Side.BUY,
                qty=Decimal("1"),
                price_cap=q.ask,
                ttl_ms=3000,
                order_style=OrderStyle.AGGRESSIVE_LIMIT,
                confidence=Decimal("1"),
                expected_edge_bps=Decimal("5"),
                created_ts_ms=q.local_ts_ms,
                features={"model": "immediate"},
            )
        ]

    def on_trade(self, t: Trade) -> list[Intent]:
        return []


class _ImmediateResidualSignal:
    def __init__(self, side: Side) -> None:
        self.side = side
        self.emitted = False

    def on_quote(self, q: Quote) -> list[Intent]:
        if self.emitted or q.venue != Venue.MEXC:
            return []
        self.emitted = True
        intent_type = IntentType.ENTER_LONG if self.side == Side.BUY else IntentType.ENTER_SHORT
        return [
            Intent(
                intent_id=f"residual-immediate-{q.local_ts_ms}",
                symbol="BTCUSDT",
                profile=MarketProfileName.PERP_TO_PERP,
                intent_type=intent_type,
                side=self.side,
                qty=Decimal("1"),
                price_cap=q.ask if self.side == Side.BUY else q.bid,
                ttl_ms=3000,
                order_style=OrderStyle.AGGRESSIVE_LIMIT,
                confidence=Decimal("1"),
                expected_edge_bps=Decimal("5"),
                created_ts_ms=q.local_ts_ms,
                features={
                    "model": "residual_zscore",
                    "leader_symbol": "BTCUSDT",
                    "basis_bps": "-60",
                    "z_score": "-3",
                    "basis_ewm_mean_bps": "0",
                    "basis_ewm_std_bps": "20",
                    "z_exit": "0.4",
                    "adverse_z_stop": "4",
                    "beta": "1",
                },
            )
        ]

    def on_trade(self, t: Trade) -> list[Intent]:
        return []


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


def _depth(symbol: str, ts_ms: int) -> OrderBookDepth:
    return OrderBookDepth(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=symbol,
        bids=(DepthLevel(Decimal("99"), Decimal("1")),),
        asks=(DepthLevel(Decimal("101"), Decimal("1")),),
        timestamp_ms=ts_ms,
        local_ts_ms=ts_ms,
    )
