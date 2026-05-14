"""Execution planning helpers."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from llbot.domain.enums import IntentType, MarketProfileName, OrderStyle, Side
from llbot.domain.models import Intent


@dataclass(frozen=True, slots=True)
class EntryPlan:
    symbol: str
    profile: MarketProfileName
    direction: IntentType
    qty: Decimal
    price_cap: Decimal
    ttl_ms: int
    expected_edge_bps: Decimal
    confidence: Decimal = Decimal("1")
    order_style: OrderStyle = OrderStyle.AGGRESSIVE_LIMIT


@dataclass(frozen=True, slots=True)
class EdgeOrderStyleDecision:
    allowed: bool
    order_style: OrderStyle | None
    reason: str


def select_order_style_for_edge(
    expected_edge_bps: Decimal,
    *,
    taker_min_edge_bps: Decimal,
    maker_min_edge_bps: Decimal,
) -> EdgeOrderStyleDecision:
    if expected_edge_bps >= maker_min_edge_bps:
        return EdgeOrderStyleDecision(True, OrderStyle.PASSIVE_LIMIT, "maker_edge_met")
    if expected_edge_bps >= taker_min_edge_bps:
        return EdgeOrderStyleDecision(True, OrderStyle.AGGRESSIVE_LIMIT, "taker_edge_met")
    return EdgeOrderStyleDecision(False, None, "edge_below_taker_threshold")


def apply_edge_order_style(
    plan: EntryPlan,
    *,
    taker_min_edge_bps: Decimal,
    maker_min_edge_bps: Decimal,
) -> EntryPlan:
    decision = select_order_style_for_edge(
        plan.expected_edge_bps,
        taker_min_edge_bps=taker_min_edge_bps,
        maker_min_edge_bps=maker_min_edge_bps,
    )
    if not decision.allowed or decision.order_style is None:
        raise ValueError(decision.reason)
    return EntryPlan(
        symbol=plan.symbol,
        profile=plan.profile,
        direction=plan.direction,
        qty=plan.qty,
        price_cap=plan.price_cap,
        ttl_ms=plan.ttl_ms,
        expected_edge_bps=plan.expected_edge_bps,
        confidence=plan.confidence,
        order_style=decision.order_style,
    )


def build_entry_intent(plan: EntryPlan, created_ts_ms: int) -> Intent:
    if plan.direction == IntentType.ENTER_LONG:
        side = Side.BUY
    elif plan.direction == IntentType.ENTER_SHORT:
        side = Side.SELL
    else:
        raise ValueError(f"Unsupported entry direction: {plan.direction}")

    return Intent(
        intent_id=f"intent-{uuid4().hex}",
        symbol=plan.symbol,
        profile=plan.profile,
        intent_type=plan.direction,
        side=side,
        qty=plan.qty,
        price_cap=plan.price_cap,
        ttl_ms=plan.ttl_ms,
        order_style=plan.order_style,
        confidence=plan.confidence,
        expected_edge_bps=plan.expected_edge_bps,
        created_ts_ms=created_ts_ms,
    )
