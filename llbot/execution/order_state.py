"""Order state, reconciliation, and cancel planning models."""

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Any

from llbot.execution.metascalp_planner import MetaScalpOrderAuditRecord


class OrderLifecycleStatus(str, Enum):
    PLANNED = "planned"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PLANNED = "cancel_planned"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class OrderState:
    intent_id: str
    client_order_id: str
    venue_order_id: str | None
    symbol: str
    qty: Decimal
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    open: bool = True
    status: OrderLifecycleStatus = OrderLifecycleStatus.PLANNED
    accepted_ts_ms: int | None = None
    expires_ts_ms: int | None = None
    last_update_ts_ms: int | None = None
    unknown_status: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrderReconciliationEvent:
    event_type: str
    client_order_id: str
    ts_ms: int
    venue_order_id: str | None = None
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CancelPlan:
    intent_id: str
    client_order_id: str
    connection_id: int
    endpoint: str
    request: dict[str, Any]
    reason: str
    due_ts_ms: int
    dry_run: bool = True


@dataclass(frozen=True, slots=True)
class CancelAuditRecord:
    event_type: str
    intent_id: str
    client_order_id: str
    connection_id: int
    endpoint: str
    dry_run: bool
    request: dict[str, Any]
    response: dict[str, Any]
    decision_result: str
    skip_reason: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def order_state_from_submit_audit(
    audit: MetaScalpOrderAuditRecord,
    qty: Decimal,
    now_ts_ms: int,
    ttl_ms: int,
) -> OrderState:
    if audit.unknown_status:
        status = OrderLifecycleStatus.UNKNOWN
        open_order = True
    elif audit.decision_result == "accepted":
        status = OrderLifecycleStatus.ACCEPTED
        open_order = True
    elif audit.decision_result == "dry_run_planned":
        status = OrderLifecycleStatus.PLANNED
        open_order = False
    else:
        status = OrderLifecycleStatus.REJECTED
        open_order = False

    return OrderState(
        intent_id=audit.intent_id,
        client_order_id=audit.client_id_returned or audit.client_id,
        venue_order_id=_venue_order_id(audit.response),
        symbol=audit.request.get("Symbol", audit.symbol),
        qty=qty,
        open=open_order,
        status=status,
        accepted_ts_ms=now_ts_ms if open_order else None,
        expires_ts_ms=now_ts_ms + ttl_ms if open_order else None,
        last_update_ts_ms=now_ts_ms,
        unknown_status=audit.unknown_status,
        metadata={
            "connection_id": audit.connection_id,
            "execution_time_ms": audit.execution_time_ms,
            "submit_decision": audit.decision_result,
        },
    )


def reconcile_order_state(
    state: OrderState,
    event: OrderReconciliationEvent,
) -> OrderState:
    if event.client_order_id != state.client_order_id:
        return state

    if event.event_type == "accepted":
        return replace(
            state,
            status=OrderLifecycleStatus.ACCEPTED,
            venue_order_id=event.venue_order_id or state.venue_order_id,
            open=True,
            unknown_status=False,
            last_update_ts_ms=event.ts_ms,
        )
    if event.event_type == "fill":
        filled_qty = max(state.filled_qty, event.filled_qty)
        status = OrderLifecycleStatus.FILLED if filled_qty >= state.qty else OrderLifecycleStatus.PARTIALLY_FILLED
        return replace(
            state,
            status=status,
            venue_order_id=event.venue_order_id or state.venue_order_id,
            filled_qty=filled_qty,
            avg_fill_price=event.avg_fill_price or state.avg_fill_price,
            open=status != OrderLifecycleStatus.FILLED,
            unknown_status=False,
            last_update_ts_ms=event.ts_ms,
        )
    if event.event_type == "cancelled":
        return replace(
            state,
            status=OrderLifecycleStatus.CANCELLED,
            venue_order_id=event.venue_order_id or state.venue_order_id,
            open=False,
            unknown_status=False,
            last_update_ts_ms=event.ts_ms,
        )
    if event.event_type == "rejected":
        return replace(
            state,
            status=OrderLifecycleStatus.REJECTED,
            open=False,
            unknown_status=False,
            last_update_ts_ms=event.ts_ms,
            metadata={**state.metadata, "reject_reason": event.reason},
        )

    return replace(state, last_update_ts_ms=event.ts_ms)


def build_ttl_cancel_plan(
    state: OrderState,
    connection_id: int,
    now_ts_ms: int,
    reason: str = "ttl_expired",
) -> CancelPlan | None:
    if not state.open:
        return None
    if state.expires_ts_ms is None or now_ts_ms < state.expires_ts_ms:
        return None

    endpoint = f"/api/connections/{connection_id}/orders/cancel"
    request = {
        "ClientId": state.client_order_id,
        "OrderId": state.venue_order_id,
        "Symbol": state.symbol,
        "Reason": reason,
    }
    return CancelPlan(
        intent_id=state.intent_id,
        client_order_id=state.client_order_id,
        connection_id=connection_id,
        endpoint=endpoint,
        request=request,
        reason=reason,
        due_ts_ms=now_ts_ms,
    )


def cancel_plan_audit_record(plan: CancelPlan) -> CancelAuditRecord:
    return CancelAuditRecord(
        event_type="metascalp_cancel_dry_run",
        intent_id=plan.intent_id,
        client_order_id=plan.client_order_id,
        connection_id=plan.connection_id,
        endpoint=plan.endpoint,
        dry_run=plan.dry_run,
        request=plan.request,
        response={"dry_run": True, "cancelled": None},
        decision_result="cancel_dry_run_planned",
        skip_reason=None,
        metadata={"reason": plan.reason, "due_ts_ms": plan.due_ts_ms},
    )


def cancel_response_audit_record(
    plan: CancelPlan,
    response: dict[str, Any],
    status_code: int = 200,
) -> CancelAuditRecord:
    unknown_status = status_code >= 500
    return CancelAuditRecord(
        event_type="metascalp_cancel_response",
        intent_id=plan.intent_id,
        client_order_id=plan.client_order_id,
        connection_id=plan.connection_id,
        endpoint=plan.endpoint,
        dry_run=False,
        request=plan.request,
        response=response,
        decision_result="cancel_unknown_status" if unknown_status else "cancel_accepted",
        skip_reason="server_error_unknown_cancel_status" if unknown_status else None,
        metadata={
            "reason": plan.reason,
            "due_ts_ms": plan.due_ts_ms,
            "status_code": status_code,
            "unknown_status": unknown_status,
        },
    )


def mark_cancel_planned(state: OrderState, plan: CancelPlan) -> OrderState:
    return replace(
        state,
        status=OrderLifecycleStatus.CANCEL_PLANNED,
        last_update_ts_ms=plan.due_ts_ms,
        metadata={**state.metadata, "cancel_reason": plan.reason},
    )


def _venue_order_id(response: dict[str, Any]) -> str | None:
    data = response.get("Data", response.get("data"))
    if isinstance(data, dict):
        value = data.get("OrderId") or data.get("orderId") or data.get("VenueOrderId")
        return str(value) if value is not None else None
    value = response.get("OrderId") or response.get("orderId") or response.get("VenueOrderId")
    return str(value) if value is not None else None
