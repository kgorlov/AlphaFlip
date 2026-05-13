from decimal import Decimal
from unittest import TestCase

from llbot.universe.filters import UniverseCandidate, UniverseFilterConfig, evaluate_candidate
from llbot.universe.rotator import select_live_symbols
from llbot.universe.scorer import rank_candidates, score_candidate


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

