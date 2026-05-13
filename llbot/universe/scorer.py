"""Universe scoring."""

from dataclasses import dataclass
from decimal import Decimal

from llbot.universe.filters import UniverseCandidate


@dataclass(frozen=True, slots=True)
class ScoreBounds:
    quote_volume_usd_24h: Decimal = Decimal("100000000")
    top5_depth_usd: Decimal = Decimal("1000000")
    spread_bps: Decimal = Decimal("30")
    tick_size_bps: Decimal = Decimal("10")
    fee_budget_bps: Decimal = Decimal("20")
    volatility_noise_bps: Decimal = Decimal("50")
    subscription_cost: Decimal = Decimal("10")


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    symbol: str
    score: Decimal
    candidate: UniverseCandidate


def score_candidate(
    candidate: UniverseCandidate,
    bounds: ScoreBounds | None = None,
) -> ScoredCandidate:
    bounds = bounds or ScoreBounds()
    score = (
        Decimal("0.30")
        * _positive_norm(
            min(candidate.quote_volume_binance_24h, candidate.quote_volume_mexc_24h),
            bounds.quote_volume_usd_24h,
        )
        + Decimal("0.20")
        * _positive_norm(
            min(candidate.top5_depth_usd_binance, candidate.top5_depth_usd_mexc),
            bounds.top5_depth_usd,
        )
        - Decimal("0.15")
        * _positive_norm(
            max(candidate.spread_bps_binance, candidate.spread_bps_mexc),
            bounds.spread_bps,
        )
        - Decimal("0.10") * _positive_norm(candidate.tick_size_bps_mexc, bounds.tick_size_bps)
        - Decimal("0.10") * _positive_norm(candidate.fee_budget_bps, bounds.fee_budget_bps)
        - Decimal("0.10")
        * _positive_norm(candidate.volatility_noise_bps, bounds.volatility_noise_bps)
        - Decimal("0.05") * _positive_norm(candidate.subscription_cost, bounds.subscription_cost)
    )
    return ScoredCandidate(symbol=candidate.symbol, score=score, candidate=candidate)


def rank_candidates(
    candidates: list[UniverseCandidate],
    bounds: ScoreBounds | None = None,
) -> list[ScoredCandidate]:
    return sorted(
        (score_candidate(candidate, bounds) for candidate in candidates),
        key=lambda item: item.score,
        reverse=True,
    )


def _positive_norm(value: Decimal, upper: Decimal) -> Decimal:
    if upper <= 0:
        raise ValueError("Normalization upper bound must be positive")
    if value <= 0:
        return Decimal("0")
    normalized = value / upper
    if normalized > 1:
        return Decimal("1")
    return normalized

