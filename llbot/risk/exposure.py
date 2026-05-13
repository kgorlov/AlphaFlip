"""Exposure helpers."""

from decimal import Decimal

from llbot.domain.models import Intent


def intent_notional_usd(intent: Intent) -> Decimal:
    return abs(intent.qty * intent.price_cap)

