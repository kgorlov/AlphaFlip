"""Universe hard filters."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    symbol: str
    leader_trading_enabled: bool
    lagger_trading_enabled: bool
    lagger_api_allowed: bool
    quote_volume_binance_24h: Decimal
    quote_volume_mexc_24h: Decimal
    top5_depth_usd_binance: Decimal
    top5_depth_usd_mexc: Decimal
    spread_bps_binance: Decimal
    spread_bps_mexc: Decimal
    tick_size_bps_mexc: Decimal
    fee_budget_bps: Decimal
    volatility_noise_bps: Decimal
    subscription_cost: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class UniverseFilterConfig:
    min_quote_volume_usd_24h: Decimal
    max_spread_bps: Decimal
    min_top5_depth_usd: Decimal
    max_tick_bps: Decimal


@dataclass(frozen=True, slots=True)
class FilterDecision:
    allowed: bool
    reason: str = "ok"


def evaluate_candidate(candidate: UniverseCandidate, config: UniverseFilterConfig) -> FilterDecision:
    if not candidate.leader_trading_enabled:
        return FilterDecision(False, "leader_trading_disabled")
    if not candidate.lagger_trading_enabled:
        return FilterDecision(False, "lagger_trading_disabled")
    if not candidate.lagger_api_allowed:
        return FilterDecision(False, "lagger_api_not_allowed")
    if min(candidate.quote_volume_binance_24h, candidate.quote_volume_mexc_24h) < (
        config.min_quote_volume_usd_24h
    ):
        return FilterDecision(False, "quote_volume_too_low")
    if max(candidate.spread_bps_binance, candidate.spread_bps_mexc) > config.max_spread_bps:
        return FilterDecision(False, "spread_too_wide")
    if min(candidate.top5_depth_usd_binance, candidate.top5_depth_usd_mexc) < (
        config.min_top5_depth_usd
    ):
        return FilterDecision(False, "top5_depth_too_low")
    if candidate.tick_size_bps_mexc > config.max_tick_bps:
        return FilterDecision(False, "mexc_tick_too_coarse")
    return FilterDecision(True)

