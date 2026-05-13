from decimal import Decimal
from unittest import TestCase

from llbot.domain.enums import IntentType, MarketProfileName, MarketType, Side, Venue
from llbot.domain.models import Quote
from llbot.signals.impulse_transfer import ImpulseTransferConfig, ImpulseTransferSignal
from llbot.signals.residual_zscore import ResidualZScoreConfig, ResidualZScoreSignal


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
