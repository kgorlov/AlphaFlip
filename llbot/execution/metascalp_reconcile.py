"""MetaScalp private update normalization and offline reconciliation."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from llbot.execution.order_state import OrderReconciliationEvent, OrderState, reconcile_order_state


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    connection_id: int | None
    symbol: str
    qty: Decimal
    avg_price: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    connection_id: int | None
    asset: str
    available: Decimal | None = None
    total: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetaScalpPrivateUpdate:
    update_type: str
    order_event: OrderReconciliationEvent | None = None
    position: PositionSnapshot | None = None
    balance: BalanceSnapshot | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReconciliationAuditRecord:
    event_type: str
    decision_result: str
    client_order_id: str | None
    before_status: str | None
    after_status: str | None
    symbol: str | None
    raw_update: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    orders: list[OrderState]
    audit_records: list[ReconciliationAuditRecord]
    positions: list[PositionSnapshot]
    balances: list[BalanceSnapshot]
    unmatched_updates: int = 0
    unknown_updates: int = 0


def normalize_metascalp_update(raw: dict[str, Any]) -> MetaScalpPrivateUpdate:
    payload = _payload(raw)
    kind = _kind(raw, payload)
    if kind == "position":
        return MetaScalpPrivateUpdate(update_type="position", position=_position(payload), raw=raw)
    if kind == "balance":
        return MetaScalpPrivateUpdate(update_type="balance", balance=_balance(payload), raw=raw)

    order = _order_event(payload)
    if order is not None:
        return MetaScalpPrivateUpdate(update_type="order", order_event=order, raw=raw)
    return MetaScalpPrivateUpdate(update_type="unknown", raw=raw)


def expand_metascalp_update(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Split documented MetaScalp list payloads into single-row updates."""

    payload = _payload(raw)
    type_value = raw.get("Type", raw.get("type"))
    for key in ("Orders", "orders", "Positions", "positions", "Balances", "balances", "Finreses", "finreses"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        expanded: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            next_payload = dict(item)
            for inherited in ("ConnectionId", "connectionId"):
                if inherited in payload and inherited not in next_payload:
                    next_payload[inherited] = payload[inherited]
            expanded.append({"Type": type_value, "Data": next_payload})
        return expanded or [raw]
    return [raw]


def reconcile_metascalp_updates(
    orders: Iterable[OrderState],
    raw_updates: Iterable[dict[str, Any]],
) -> ReconciliationResult:
    by_client_id = {order.client_order_id: order for order in orders}
    audit_records: list[ReconciliationAuditRecord] = []
    positions: list[PositionSnapshot] = []
    balances: list[BalanceSnapshot] = []
    unmatched = 0
    unknown = 0

    for source_raw in raw_updates:
        for raw in expand_metascalp_update(source_raw):
            update = normalize_metascalp_update(raw)
            if update.update_type == "position" and update.position is not None:
                positions.append(update.position)
                audit_records.append(
                    ReconciliationAuditRecord(
                        event_type="metascalp_position_update",
                        decision_result="position_snapshot",
                        client_order_id=None,
                        before_status=None,
                        after_status=None,
                        symbol=update.position.symbol,
                        raw_update=raw,
                        metadata={"qty": str(update.position.qty)},
                    )
                )
                continue
            if update.update_type == "balance" and update.balance is not None:
                balances.append(update.balance)
                audit_records.append(
                    ReconciliationAuditRecord(
                        event_type="metascalp_balance_update",
                        decision_result="balance_snapshot",
                        client_order_id=None,
                        before_status=None,
                        after_status=None,
                        symbol=None,
                        raw_update=raw,
                        metadata={"asset": update.balance.asset},
                    )
                )
                continue
            if update.order_event is None:
                unknown += 1
                audit_records.append(
                    ReconciliationAuditRecord(
                        event_type="metascalp_unknown_update",
                        decision_result="unknown_update",
                        client_order_id=None,
                        before_status=None,
                        after_status=None,
                        symbol=None,
                        raw_update=raw,
                    )
                )
                continue

            event = update.order_event
            state = by_client_id.get(event.client_order_id)
            if state is None:
                unmatched += 1
                audit_records.append(
                    ReconciliationAuditRecord(
                        event_type="metascalp_order_update",
                        decision_result="unmatched_order_update",
                        client_order_id=event.client_order_id,
                        before_status=None,
                        after_status=None,
                        symbol=None,
                        raw_update=raw,
                        metadata={"order_event_type": event.event_type},
                    )
                )
                continue

            next_state = reconcile_order_state(state, event)
            by_client_id[event.client_order_id] = next_state
            audit_records.append(
                ReconciliationAuditRecord(
                    event_type="metascalp_order_update",
                    decision_result="order_reconciled",
                    client_order_id=event.client_order_id,
                    before_status=state.status.value,
                    after_status=next_state.status.value,
                    symbol=next_state.symbol,
                    raw_update=raw,
                    metadata={"order_event_type": event.event_type},
                )
            )

    return ReconciliationResult(
        orders=list(by_client_id.values()),
        audit_records=audit_records,
        positions=positions,
        balances=balances,
        unmatched_updates=unmatched,
        unknown_updates=unknown,
    )


def _payload(raw: dict[str, Any]) -> dict[str, Any]:
    for key in ("Data", "data", "Payload", "payload"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return raw


def _kind(raw: dict[str, Any], payload: dict[str, Any]) -> str | None:
    text = " ".join(
        str(value).lower()
        for value in (
            raw.get("Type"),
            raw.get("type"),
            raw.get("Event"),
            raw.get("event"),
            raw.get("Channel"),
            raw.get("channel"),
            payload.get("Type"),
            payload.get("type"),
        )
        if value is not None
    )
    if "position" in text:
        return "position"
    if "balance" in text or "wallet" in text:
        return "balance"
    if "order" in text or "execution" in text or "fill" in text:
        return "order"
    return None


def _order_event(payload: dict[str, Any]) -> OrderReconciliationEvent | None:
    client_id = _str_or_none(_get(payload, "ClientId", "clientId", "client_id", "ClientOrderId", "clientOrderId"))
    if client_id is None:
        return None
    status_raw = _get(payload, "Status", "status", "State", "state", "Event", "event", default="")
    event_type = _order_event_type(status_raw, payload)
    if event_type is None:
        return None
    return OrderReconciliationEvent(
        event_type=event_type,
        client_order_id=client_id,
        venue_order_id=_str_or_none(_get(payload, "OrderId", "orderId", "VenueOrderId", "venueOrderId", "Id", "id")),
        ts_ms=_int_or_default(_get(payload, "Timestamp", "timestamp", "Time", "time", "Ts", "ts"), 0),
        filled_qty=_decimal_or_default(
            _get(payload, "FilledQty", "filledQty", "FilledVolume", "filledVolume", "ExecutedQty", "executedQty", "FilledSize", "filledSize"),
            Decimal("0"),
        ),
        avg_fill_price=_decimal_or_none(
            _get(payload, "AvgFillPrice", "avgFillPrice", "AveragePrice", "averagePrice", "Price", "price", "FilledPrice", "filledPrice")
        ),
        reason=_str_or_none(_get(payload, "Reason", "reason", "Message", "message")),
        raw=payload,
    )


def _order_event_type(status: Any, payload: dict[str, Any]) -> str | None:
    status_text = str(status).lower()
    filled_value = _get(payload, "FilledQty", "filledQty", "FilledVolume", "filledVolume", "ExecutedQty", "executedQty", "FilledSize", "filledSize")
    if _decimal_or_default(filled_value, Decimal("0")) > 0:
        return "fill"
    if status_text in {"0", "accepted", "new", "open", "working", "placed"}:
        return "accepted"
    if status_text in {"cancelled", "canceled", "cancel"}:
        return "cancelled"
    if status_text in {"rejected", "reject", "error", "failed"}:
        return "rejected"
    if status_text in {"2", "filled", "partially_filled", "partial_fill", "fill", "execution", "closed"}:
        return "fill"
    if status_text == "1":
        return "accepted"
    return None


def _position(payload: dict[str, Any]) -> PositionSnapshot:
    return PositionSnapshot(
        connection_id=_int_or_none(_get(payload, "ConnectionId", "connectionId", "connection_id")),
        symbol=str(_get(payload, "Symbol", "symbol", "Ticker", "ticker", default="")),
        qty=_decimal_or_default(_get(payload, "Qty", "qty", "Volume", "volume", "Position", "position", "Size", "size"), Decimal("0")),
        avg_price=_decimal_or_none(_get(payload, "AvgPrice", "avgPrice", "EntryPrice", "entryPrice", "Price", "price")),
        raw=payload,
    )


def _balance(payload: dict[str, Any]) -> BalanceSnapshot:
    return BalanceSnapshot(
        connection_id=_int_or_none(_get(payload, "ConnectionId", "connectionId", "connection_id")),
        asset=str(_get(payload, "Asset", "asset", "Currency", "currency", "Coin", "coin", default="")),
        available=_decimal_or_none(_get(payload, "Available", "available", "Free", "free", "AvailableBalance", "availableBalance")),
        total=_decimal_or_none(_get(payload, "Total", "total", "Balance", "balance", "Equity", "equity")),
        raw=payload,
    )


def _get(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _int_or_default(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    return default if parsed is None else parsed


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _decimal_or_default(value: Any, default: Decimal) -> Decimal:
    parsed = _decimal_or_none(value)
    return default if parsed is None else parsed
