from decimal import Decimal
from unittest import TestCase

from llbot.universe.filters import UniverseCandidate, UniverseFilterConfig, evaluate_candidate
from llbot.universe.rotator import plan_live_universe_rotation, select_live_profiles, select_live_symbols
from llbot.universe.scorer import rank_candidates, score_candidate
from llbot.universe.symbol_mapper import SymbolMapper
from llbot.domain.enums import MarketProfileName


class UniverseTests(TestCase):
    def test_filter_accepts_healthy_candidate(self) -> None:
        decision = evaluate_candidate(_candidate("BTCUSDT"), _filter_config())
        self.assertTrue(decision.allowed)

    def test_filter_blocks_wide_spread(self) -> None:
        candidate = _candidate("ALTUSDT", spread_bps_mexc=Decimal("20"))
        decision = evaluate_candidate(candidate, _filter_config())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "spread_too_wide")

    def test_score_and_rotation(self) -> None:
        first = _candidate("BTCUSDT", quote_volume_binance_24h=Decimal("50000000"))
        second = _candidate("THINUSDT", quote_volume_binance_24h=Decimal("3000000"))

        ranked = rank_candidates([second, first])

        self.assertEqual(ranked[0].symbol, "BTCUSDT")
        self.assertGreater(score_candidate(first).score, score_candidate(second).score)
        self.assertEqual(select_live_symbols(ranked, top_n=1), ["BTCUSDT"])

    def test_select_live_profiles_limits_top_n_and_builds_streams(self) -> None:
        selection = select_live_profiles(
            [
                _profile("ETHUSDT", "0.4"),
                _profile("BTCUSDT", "0.9"),
                _profile("SOLUSDT", "0.2"),
            ],
            top_n=3,
            max_active_symbols=2,
        )

        self.assertEqual(selection.canonical_symbols, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(selection.binance_streams, ("btcusdt@bookTicker", "ethusdt@bookTicker"))
        self.assertEqual(
            selection.mexc_subscriptions[0],
            {"method": "sub.ticker", "param": {"symbol": "BTC_USDT"}},
        )

    def test_plan_live_universe_rotation_builds_deltas(self) -> None:
        plan = plan_live_universe_rotation(
            current_symbols=("BTCUSDT", "OLDUSDT"),
            ranked_profiles=[
                _profile("ETHUSDT", "0.8"),
                _profile("BTCUSDT", "0.7"),
                _profile("SOLUSDT", "0.6"),
            ],
            top_n=2,
        )

        self.assertEqual(plan.selected.canonical_symbols, ("ETHUSDT", "BTCUSDT"))
        self.assertEqual(plan.keep_symbols, ("BTCUSDT",))
        self.assertEqual(plan.subscribe_symbols, ("ETHUSDT",))
        self.assertEqual(plan.unsubscribe_symbols, ("OLDUSDT",))
        self.assertEqual(plan.binance_subscribe_streams, ("ethusdt@bookTicker",))
        self.assertEqual(plan.binance_unsubscribe_streams, ("oldusdt@bookTicker",))
        self.assertEqual(
            plan.mexc_subscriptions,
            ({"method": "sub.ticker", "param": {"symbol": "ETH_USDT"}},),
        )
        self.assertEqual(
            plan.mexc_unsubscriptions,
            ({"method": "unsub.ticker", "param": {"symbol": "OLD_USDT"}},),
        )

    def test_spot_profile_rotation_uses_mexc_spot_pb_book_ticker(self) -> None:
        plan = plan_live_universe_rotation(
            current_symbols=("OLDUSDT",),
            ranked_profiles=[_spot_profile("SOLUSDT", "0.9")],
            top_n=1,
        )

        self.assertEqual(plan.selected.canonical_symbols, ("SOLUSDT",))
        self.assertEqual(plan.binance_subscribe_streams, ("solusdt@bookTicker",))
        self.assertEqual(
            plan.mexc_subscriptions,
            (
                {
                    "method": "SUBSCRIPTION",
                    "params": ["spot@public.aggre.bookTicker.v3.api.pb@100ms@SOLUSDT"],
                },
            ),
        )
        self.assertEqual(
            plan.mexc_unsubscriptions,
            (
                {
                    "method": "UNSUBSCRIPTION",
                    "params": ["spot@public.aggre.bookTicker.v3.api.pb@100ms@OLDUSDT"],
                },
            ),
        )


def _filter_config() -> UniverseFilterConfig:
    return UniverseFilterConfig(
        min_quote_volume_usd_24h=Decimal("2000000"),
        max_spread_bps=Decimal("12"),
        min_top5_depth_usd=Decimal("25000"),
        max_tick_bps=Decimal("4"),
    )


def _candidate(
    symbol: str,
    quote_volume_binance_24h: Decimal = Decimal("10000000"),
    quote_volume_mexc_24h: Decimal = Decimal("8000000"),
    spread_bps_mexc: Decimal = Decimal("5"),
) -> UniverseCandidate:
    return UniverseCandidate(
        symbol=symbol,
        leader_trading_enabled=True,
        lagger_trading_enabled=True,
        lagger_api_allowed=True,
        quote_volume_binance_24h=quote_volume_binance_24h,
        quote_volume_mexc_24h=quote_volume_mexc_24h,
        top5_depth_usd_binance=Decimal("100000"),
        top5_depth_usd_mexc=Decimal("80000"),
        spread_bps_binance=Decimal("3"),
        spread_bps_mexc=spread_bps_mexc,
        tick_size_bps_mexc=Decimal("1"),
        fee_budget_bps=Decimal("8"),
        volatility_noise_bps=Decimal("15"),
    )


def _profile(symbol: str, score: str):
    profile = SymbolMapper(MarketProfileName.PERP_TO_PERP).build_profile(symbol)
    return type(profile)(
        canonical_symbol=profile.canonical_symbol,
        leader_symbol=profile.leader_symbol,
        lagger_symbol=profile.lagger_symbol,
        profile=profile.profile,
        leader_venue=profile.leader_venue,
        lagger_venue=profile.lagger_venue,
        leader_market=profile.leader_market,
        lagger_market=profile.lagger_market,
        metadata={"universe_score": score},
    )


def _spot_profile(symbol: str, score: str):
    profile = SymbolMapper(MarketProfileName.SPOT_TO_SPOT).build_profile(symbol)
    return type(profile)(
        canonical_symbol=profile.canonical_symbol,
        leader_symbol=profile.leader_symbol,
        lagger_symbol=profile.lagger_symbol,
        profile=profile.profile,
        leader_venue=profile.leader_venue,
        lagger_venue=profile.lagger_venue,
        leader_market=profile.leader_market,
        lagger_market=profile.lagger_market,
        metadata={"universe_score": score},
    )
