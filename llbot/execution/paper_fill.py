"""Paper fill models for shadow/paper validation."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from llbot.domain.enums import Side
from llbot.domain.models import Intent, Quote, Trade


class FillModel(str, Enum):
    TOUCH = "touch"
    TRADE_THROUGH = "trade_through"
    QUEUE_AWARE = "queue_aware"


@dataclass(frozen=True, slots=True)
class PaperFill:
    filled: bool
    model: FillModel
    fill_price: Decimal | None = None
    fill_qty: Decimal = Decimal("0")
    reason: str = "not_filled"


def simulate_quote_fill(
    intent: Intent,
    quote: Quote,
    model: FillModel,
    queue_ahead_qty: Decimal = Decimal("0"),
) -> PaperFill:
    if quote.symbol != intent.symbol:
        return PaperFill(False, model, reason="symbol_mismatch")

    if intent.side == Side.BUY:
        touched = quote.ask <= intent.price_cap
        visible_qty = quote.ask_size or Decimal("0")
        fill_price = quote.ask
    else:
        touched = quote.bid >= intent.price_cap
        visible_qty = quote.bid_size or Decimal("0")
        fill_price = quote.bid

    if not touched:
        return PaperFill(False, model, reason="price_not_touched")

    if model == FillModel.TOUCH:
        return PaperFill(True, model, fill_price=fill_price, fill_qty=intent.qty, reason="touch")

    if model == FillModel.QUEUE_AWARE:
        available_after_queue = max(Decimal("0"), visible_qty - queue_ahead_qty)
        if available_after_queue >= intent.qty:
            return PaperFill(
                True,
                model,
                fill_price=fill_price,
                fill_qty=intent.qty,
                reason="queue_available",
            )
        return PaperFill(False, model, reason="queue_not_available")

    return PaperFill(False, model, reason="trade_required")


def simulate_trade_fill(intent: Intent, trade: Trade, model: FillModel) -> PaperFill:
    if trade.symbol != intent.symbol:
        return PaperFill(False, model, reason="symbol_mismatch")
    if model != FillModel.TRADE_THROUGH:
        return PaperFill(False, model, reason="unsupported_trade_model")

    if intent.side == Side.BUY:
        traded_through = trade.price <= intent.price_cap
    else:
        traded_through = trade.price >= intent.price_cap

    if not traded_through:
        return PaperFill(False, model, reason="trade_did_not_cross_limit")

    return PaperFill(
        True,
        model,
        fill_price=trade.price,
        fill_qty=min(intent.qty, trade.qty),
        reason="trade_through",
    )

