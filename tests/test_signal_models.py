from decimal import Decimal
from unittest import TestCase

from llbot.domain.enums import IntentType, MarketProfileName, MarketType, Side, Venue
from llbot.domain.market_data import DepthLevel, OrderBookDepth
from llbot.domain.models import Quote, Trade
from llbot.signals.feature_store import RollingFeatureStore, build_feature_snapshot
from llbot.signals.impulse_transfer import ImpulseTransferConfig, ImpulseTransferSignal
from llbot.signals.residual_zscore import EwmBasisStats, ResidualZScoreConfig, ResidualZScoreSignal


class ResidualZScoreSignalTests(TestCase):
    def test_emits_long_when_binance_moves_up_and_mexc_lags_below_basis(self) -> None:
        model = ResidualZScoreSignal(
            ResidualZScoreConfig(
                canonical_symbol="BTCUSDT",
                leader_symbol="BTCUSDT",
                lagger_symbol="BTC_USDT",
                profile=MarketProfileName.PERP_TO_PERP,
                min_samples=3,
                z_entry=Decimal("1"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
            )
        )
        _seed_flat_basis(model)

        intents = model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "101", 1000))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent_type, IntentType.ENTER_LONG)
        self.assertEqual(intents[0].side, Side.BUY)
        self.assertEqual(intents[0].price_cap, Decimal("100"))
        self.assertEqual(intents[0].created_ts_ms, 1000)
        self.assertEqual(intents[0].features["model"], "residual_zscore")
        self.assertEqual(intents[0].features["basis_ewm_window_ms"], "180000")

    def test_emits_short_when_binance_moves_down_and_mexc_lags_above_basis(self) -> None:
        model = ResidualZScoreSignal(
            ResidualZScoreConfig(
                canonical_symbol="BTCUSDT",
                leader_symbol="BTCUSDT",
                lagger_symbol="BTC_USDT",
                profile=MarketProfileName.PERP_TO_PERP,
                min_samples=3,
                z_entry=Decimal("1"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
            )
        )
        _seed_flat_basis(model)

        intents = model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "99", 1000))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent_type, IntentType.ENTER_SHORT)
        self.assertEqual(intents[0].side, Side.SELL)
        self.assertEqual(intents[0].price_cap, Decimal("100"))
        self.assertEqual(intents[0].created_ts_ms, 1000)
        self.assertEqual(intents[0].features["model"], "residual_zscore")

    def test_ewm_basis_stats_are_time_aware(self) -> None:
        fast = EwmBasisStats(window_ms=1_000)
        slow = EwmBasisStats(window_ms=180_000)

        fast.update(Decimal("0"), 0)
        slow.update(Decimal("0"), 0)
        fast.update(Decimal("10"), 1_000)
        slow.update(Decimal("10"), 1_000)

        self.assertIsNotNone(fast.mean)
        self.assertIsNotNone(slow.mean)
        assert fast.mean is not None
        assert slow.mean is not None
        self.assertGreater(fast.mean, slow.mean)
        self.assertGreater(fast.std_bps, Decimal("0"))
        self.assertGreater(slow.std_bps, Decimal("0"))

    def test_rejects_invalid_ewm_window(self) -> None:
        with self.assertRaises(ValueError):
            ResidualZScoreConfig(
                canonical_symbol="BTCUSDT",
                leader_symbol="BTCUSDT",
                lagger_symbol="BTC_USDT",
                ewm_window_ms=0,
            )


class ImpulseTransferSignalTests(TestCase):
    def test_emits_long_when_positive_binance_impulse_has_not_transferred(self) -> None:
        model = _impulse_model()
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "100", 0))
        model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 0))
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "101", 100))

        intents = model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 100))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent_type, IntentType.ENTER_LONG)
        self.assertEqual(intents[0].side, Side.BUY)
        self.assertEqual(intents[0].price_cap, Decimal("100"))
        self.assertEqual(intents[0].created_ts_ms, 100)
        self.assertEqual(intents[0].features["model"], "impulse_transfer")

    def test_requires_trade_aggression_when_configured(self) -> None:
        model = ImpulseTransferSignal(
            ImpulseTransferConfig(
                canonical_symbol="BTCUSDT",
                leader_symbol="BTCUSDT",
                lagger_symbol="BTC_USDT",
                windows_ms=(100,),
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                min_trade_aggression_qty=Decimal("1"),
            )
        )
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "100", 0))
        model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 0))
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "101", 100))
        self.assertEqual(model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 100)), [])

        model.on_trade(_trade(Side.BUY, "1.5", 100))
        intents = model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 100))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].features["trade_aggression_side"], "buy")
        self.assertEqual(intents[0].features["trade_aggression_qty"], "1.5")

    def test_requires_book_imbalance_when_configured(self) -> None:
        model = ImpulseTransferSignal(
            ImpulseTransferConfig(
                canonical_symbol="BTCUSDT",
                leader_symbol="BTCUSDT",
                lagger_symbol="BTC_USDT",
                windows_ms=(100,),
                min_impulse_bps=Decimal("2"),
                safety_bps=Decimal("0"),
                cooldown_ms=0,
                min_book_imbalance=Decimal("0.2"),
            )
        )
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "100", 0))
        model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 0))
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "101", 100))
        model.on_depth(_depth(bid_qty="10", ask_qty="1", ts_ms=100))

        intents = model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 100))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].features["book_imbalance"], "0.8181818181818181818181818182")


class FeatureStoreTests(TestCase):
    def test_builds_and_stores_signal_feature_snapshot(self) -> None:
        leader_prev = _quote(Venue.BINANCE, "BTCUSDT", "100", 0)
        leader = _quote(Venue.BINANCE, "BTCUSDT", "101", 100)
        lagger_prev = _quote(Venue.MEXC, "BTC_USDT", "100", 0)
        lagger = _quote(Venue.MEXC, "BTC_USDT", "100.2", 120)
        store = RollingFeatureStore(max_samples=2)

        snapshot = build_feature_snapshot(
            symbol="BTCUSDT",
            ts_ms=120,
            leader=leader,
            lagger=lagger,
            leader_previous=leader_prev,
            lagger_previous=lagger_prev,
            residual_bps=Decimal("-3"),
            imbalance=Decimal("0.25"),
            metadata={"model": "test"},
        )
        store.add(snapshot)

        latest = store.latest("BTCUSDT")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.residual_bps, Decimal("-3"))
        self.assertEqual(latest.impulse_bps, Decimal("100"))
        self.assertEqual(latest.imbalance, Decimal("0.25"))
        self.assertEqual(latest.volatility_bps, Decimal("20.0"))
        self.assertEqual(latest.latency_ms, 20)
        self.assertEqual(latest.metadata["model"], "test")

    def test_emits_short_when_negative_binance_impulse_has_not_transferred(self) -> None:
        model = _impulse_model()
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "100", 0))
        model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 0))
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "99", 100))

        intents = model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", 100))

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].intent_type, IntentType.ENTER_SHORT)
        self.assertEqual(intents[0].side, Side.SELL)
        self.assertEqual(intents[0].price_cap, Decimal("100"))
        self.assertEqual(intents[0].created_ts_ms, 100)
        self.assertEqual(intents[0].features["model"], "impulse_transfer")


def _seed_flat_basis(model: ResidualZScoreSignal) -> None:
    for ts in (0, 100, 200, 300):
        model.on_quote(_quote(Venue.BINANCE, "BTCUSDT", "100", ts))
        model.on_quote(_quote(Venue.MEXC, "BTC_USDT", "100", ts))


def _impulse_model() -> ImpulseTransferSignal:
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
        )
    )


def _quote(venue: Venue, symbol: str, mid: str, ts_ms: int) -> Quote:
    price = Decimal(mid)
    return Quote(
        venue=venue,
        market=MarketType.USDT_PERP,
        symbol=symbol,
        bid=price,
        ask=price,
        bid_size=Decimal("10"),
        ask_size=Decimal("10"),
        exchange_ts_ms=ts_ms,
        local_ts_ms=ts_ms,
    )


def _trade(side: Side, qty: str, ts_ms: int) -> Trade:
    return Trade(
        venue=Venue.BINANCE,
        market=MarketType.USDT_PERP,
        symbol="BTCUSDT",
        price=Decimal("101"),
        qty=Decimal(qty),
        side=side,
        exchange_ts_ms=ts_ms,
        local_ts_ms=ts_ms,
        trade_id="t1",
    )


def _depth(bid_qty: str, ask_qty: str, ts_ms: int) -> OrderBookDepth:
    return OrderBookDepth(
        venue=Venue.BINANCE,
        market=MarketType.USDT_PERP,
        symbol="BTCUSDT",
        bids=(DepthLevel(Decimal("100"), Decimal(bid_qty)),),
        asks=(DepthLevel(Decimal("101"), Decimal(ask_qty)),),
        timestamp_ms=ts_ms,
        local_ts_ms=ts_ms,
        version=1,
    )
