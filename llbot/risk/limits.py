"""Risk limits and mandatory pre-trade gates."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from llbot.config import RiskConfig
from llbot.domain.enums import IntentType
from llbot.domain.models import Intent, PortfolioState


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str = "ok"


class BasicRiskEngine:
    """Deterministic risk gate for paper/live-ready execution paths."""

    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def allow(self, intent: Intent, state: PortfolioState) -> tuple[bool, str]:
        decision = self.evaluate(intent, state)
        return decision.allowed, decision.reason

    def evaluate(self, intent: Intent, state: PortfolioState) -> RiskDecision:
        metadata = state.metadata
        for key, reason in _METADATA_BLOCKS:
            if bool(metadata.get(key, False)):
                return RiskDecision(False, reason)

        if not bool(metadata.get("metascalp_connected", True)):
            return RiskDecision(False, "metascalp_disconnected")

        if intent.expected_edge_bps <= 0:
            return RiskDecision(False, "non_positive_edge")

        if state.daily_pnl_usd <= -self.config.max_daily_loss_usd:
            return RiskDecision(False, "max_daily_loss_reached")

        if state.open_positions >= self.config.max_open_positions:
            return RiskDecision(False, "max_open_positions_reached")

        if _is_entry(intent) and _open_direction_count(state.metadata, intent) > 0:
            return RiskDecision(False, "symbol_direction_position_exists")

        active_symbols = {
            symbol
            for symbol, notional in state.per_symbol_notional_usd.items()
            if notional > 0
        }
        if (
            _is_entry(intent)
            and intent.symbol not in active_symbols
            and len(active_symbols) >= self.config.max_active_symbols
        ):
            return RiskDecision(False, "max_active_symbols_reached")

        intent_notional = _intent_notional(intent)
        if state.total_notional_usd + intent_notional > self.config.max_total_notional_usd:
            return RiskDecision(False, "max_total_notional_reached")

        current_symbol_notional = state.per_symbol_notional_usd.get(intent.symbol, Decimal("0"))
        if current_symbol_notional + intent_notional > self.config.max_notional_per_symbol_usd:
            return RiskDecision(False, "max_symbol_notional_reached")

        return RiskDecision(True)


def _intent_notional(intent: Intent) -> Decimal:
    return abs(intent.qty * intent.price_cap)


def _is_entry(intent: Intent) -> bool:
    return intent.intent_type in {IntentType.ENTER_LONG, IntentType.ENTER_SHORT}


def _position_direction(intent: Intent) -> str:
    if intent.intent_type == IntentType.ENTER_SHORT:
        return "short"
    return "long"


def _position_direction_key(symbol: str, direction: str) -> str:
    return f"{symbol}:{direction}"


def _open_direction_count(metadata: dict[str, Any], intent: Intent) -> int:
    counts = metadata.get("open_position_direction_counts", {})
    if not isinstance(counts, dict):
        return 0
    key = _position_direction_key(intent.symbol, _position_direction(intent))
    return int(counts.get(key, 0) or 0)


_METADATA_BLOCKS = (
    ("kill_switch", "manual_kill_switch"),
    ("binance_feed_stale", "binance_feed_stale"),
    ("mexc_feed_stale", "mexc_feed_stale"),
    ("feed_latency_high", "feed_latency_high"),
    ("reconnect_storm", "reconnect_storm"),
    ("book_desync", "book_desync"),
    ("abnormal_cancel_ratio", "abnormal_cancel_ratio"),
    ("repeated_order_errors", "repeated_order_errors"),
    ("high_slippage", "high_slippage"),
    ("position_mismatch", "position_mismatch"),
    ("balance_mismatch", "balance_mismatch"),
)
