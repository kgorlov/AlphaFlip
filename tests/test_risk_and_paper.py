from decimal import Decimal
from unittest import TestCase

from llbot.config import RiskConfig
from llbot.domain.enums import IntentType, MarketProfileName, OrderStyle, Side, Venue, MarketType
from llbot.domain.models import Intent, PortfolioState, Quote, Trade
from llbot.execution.paper_fill import FillModel, PaperFill, simulate_quote_fill, simulate_trade_fill
from llbot.risk.limits import BasicRiskEngine
from llbot.service.replay import PaperPosition, _state_after_exit, _state_after_fill


class RiskAndPaperTests(TestCase):
    def test_risk_allows_healthy_intent(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(_intent(), _state())

        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")

    def test_risk_blocks_non_positive_edge(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(
            _intent(expected_edge_bps=Decimal("0")),
            _state(),
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "non_positive_edge")

    def test_risk_blocks_stale_feed(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(
            _intent(),
            _state(metadata={"binance_feed_stale": True}),
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "binance_feed_stale")

    def test_risk_blocks_same_symbol_same_direction_position(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(
            _intent(),
            _state(metadata={"open_position_direction_counts": {"BTCUSDT:long": 1}}),
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "symbol_direction_position_exists")

    def test_risk_allows_opposite_direction_same_symbol(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(
            _intent(intent_type=IntentType.ENTER_SHORT, side=Side.SELL),
            _state(metadata={"open_position_direction_counts": {"BTCUSDT:long": 1}}),
        )

        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")

    def test_risk_blocks_new_symbol_when_active_symbol_limit_reached(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig(max_active_symbols=1)).allow(
            _intent(symbol="ETHUSDT"),
            _state(per_symbol_notional_usd={"BTCUSDT": Decimal("100")}),
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "max_active_symbols_reached")

    def test_risk_blocks_high_feed_latency_metadata(self) -> None:
        allowed, reason = BasicRiskEngine(RiskConfig()).allow(
            _intent(),
            _state(metadata={"feed_latency_high": True}),
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "feed_latency_high")

    def test_touch_fill_buy(self) -> None:
        fill = simulate_quote_fill(_intent(), _quote(ask=Decimal("100.5")), FillModel.TOUCH)

        self.assertTrue(fill.filled)
        self.assertEqual(fill.fill_price, Decimal("100.5"))

    def test_queue_aware_blocks_when_queue_too_large(self) -> None:
        fill = simulate_quote_fill(
            _intent(qty=Decimal("2")),
            _quote(ask=Decimal("100.5"), ask_size=Decimal("1")),
            FillModel.QUEUE_AWARE,
        )

        self.assertFalse(fill.filled)
        self.assertEqual(fill.reason, "queue_not_available")

    def test_trade_through_fill(self) -> None:
        fill = simulate_trade_fill(
            _intent(price_cap=Decimal("101")),
            Trade(
                venue=Venue.MEXC,
                market=MarketType.USDT_PERP,
                symbol="BTCUSDT",
                price=Decimal("100.8"),
                qty=Decimal("1"),
                side=Side.SELL,
                exchange_ts_ms=1,
                local_ts_ms=2,
            ),
            FillModel.TRADE_THROUGH,
        )

        self.assertTrue(fill.filled)
        self.assertEqual(fill.fill_qty, Decimal("1"))

    def test_paper_state_tracks_direction_counts_across_fill_and_exit(self) -> None:
        intent = _intent()
        state = _state()
        next_state = _state_after_fill(
            state,
            intent,
            PaperFill(True, FillModel.TOUCH, fill_price=Decimal("100"), fill_qty=Decimal("1")),
        )

        self.assertEqual(
            next_state.metadata["open_position_direction_counts"],
            {"BTCUSDT:long": 1},
        )
        self.assertEqual(next_state.metadata["active_symbols"], ["BTCUSDT"])

        closed = _state_after_exit(
            next_state,
            PaperPosition(
                position_id="pos-1",
                entry_intent_id=intent.intent_id,
                symbol=intent.symbol,
                execution_symbol=intent.symbol,
                side=Side.BUY,
                qty=Decimal("1"),
                entry_price=Decimal("100"),
                entry_ts_ms=1,
                expires_ts_ms=2,
                model="test",
            ),
            realized_pnl_usd=Decimal("1"),
        )

        self.assertEqual(closed.metadata["open_position_direction_counts"], {})
        self.assertEqual(closed.metadata["active_symbols"], [])


def _intent(
    symbol: str = "BTCUSDT",
    qty: Decimal = Decimal("1"),
    price_cap: Decimal = Decimal("101"),
    expected_edge_bps: Decimal = Decimal("8"),
    intent_type: IntentType = IntentType.ENTER_LONG,
    side: Side = Side.BUY,
) -> Intent:
    return Intent(
        intent_id="intent-test",
        symbol=symbol,
        profile=MarketProfileName.PERP_TO_PERP,
        intent_type=intent_type,
        side=side,
        qty=qty,
        price_cap=price_cap,
        ttl_ms=3000,
        order_style=OrderStyle.AGGRESSIVE_LIMIT,
        confidence=Decimal("1"),
        expected_edge_bps=expected_edge_bps,
        created_ts_ms=1,
    )


def _state(
    metadata: dict[str, object] | None = None,
    per_symbol_notional_usd: dict[str, Decimal] | None = None,
) -> PortfolioState:
    return PortfolioState(
        open_positions=0,
        total_notional_usd=sum((per_symbol_notional_usd or {}).values(), Decimal("0")),
        daily_pnl_usd=Decimal("0"),
        per_symbol_notional_usd=per_symbol_notional_usd or {},
        metadata=metadata or {},
    )


def _quote(
    bid: Decimal = Decimal("100"),
    ask: Decimal = Decimal("101"),
    ask_size: Decimal = Decimal("5"),
) -> Quote:
    return Quote(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol="BTCUSDT",
        bid=bid,
        ask=ask,
        bid_size=Decimal("5"),
        ask_size=ask_size,
        exchange_ts_ms=1,
        local_ts_ms=2,
    )
