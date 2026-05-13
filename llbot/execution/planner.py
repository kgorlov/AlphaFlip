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

