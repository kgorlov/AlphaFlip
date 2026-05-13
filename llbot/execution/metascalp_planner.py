"""Dry-run MetaScalp order request planning.

This module intentionally does not submit orders. It only validates an intent and
builds the request/audit payload that a later demo executor can use.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from llbot.adapters.metascalp import MetaScalpConnection
from llbot.domain.enums import IntentType, OrderStyle, Side
from llbot.domain.models import Intent, SymbolProfile


@dataclass(frozen=True, slots=True)
class MetaScalpOrderValidation:
    ok: bool
    reason: str = "ok"


@dataclass(frozen=True, slots=True)
class MetaScalpDryRunOrderPlan:
    intent_id: str
    connection_id: int
    client_id: str
    endpoint: str
    payload: dict[str, Any]
    validation: MetaScalpOrderValidation
    dry_run: bool = True


@dataclass(frozen=True, slots=True)
class MetaScalpOrderAuditRecord:
    event_type: str
    intent_id: str
    symbol: str
    connection_id: int
    client_id: str
    endpoint: str
    dry_run: bool
    request: dict[str, Any]
    response: dict[str, Any]
    decision_result: str
    skip_reason: str | None
    client_id_returned: str | None = None
    execution_time_ms: int | None = None
    unknown_status: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_intent_for_symbol(
    intent: Intent,
    profile: SymbolProfile | None = None,
) -> MetaScalpOrderValidation:
    """Validate local quantity/price constraints before any execution attempt."""

    if intent.qty <= 0:
        return MetaScalpOrderValidation(False, "qty_must_be_positive")
    if intent.price_cap <= 0:
        return MetaScalpOrderValidation(False, "price_must_be_positive")

    if profile is None:
        return MetaScalpOrderValidation(True)

    if intent.symbol != profile.canonical_symbol and intent.symbol != profile.lagger_symbol:
        return MetaScalpOrderValidation(False, "symbol_profile_mismatch")

    if profile.min_qty is not None and intent.qty < profile.min_qty:
        return MetaScalpOrderValidation(False, "qty_below_min")
    if profile.qty_step is not None and not _is_multiple(intent.qty, profile.qty_step):
        return MetaScalpOrderValidation(False, "qty_step_mismatch")
    if profile.price_tick is not None and not _is_multiple(intent.price_cap, profile.price_tick):
        return MetaScalpOrderValidation(False, "price_tick_mismatch")
    if profile.min_notional_usd is not None:
        notional = _notional_usd(intent, profile)
        if notional < profile.min_notional_usd:
            return MetaScalpOrderValidation(False, "notional_below_min")

    return MetaScalpOrderValidation(True)


def build_metascalp_dry_run_order_plan(
    intent: Intent,
    connection: MetaScalpConnection,
    execution_symbol: str,
    profile: SymbolProfile | None = None,
) -> MetaScalpDryRunOrderPlan:
    """Build a traceable MetaScalp order request without submitting it."""

    validation = validate_intent_for_symbol(intent, profile)
    client_id = _client_id(intent)
    endpoint = f"/api/connections/{connection.id}/orders"
    payload = {
        "Symbol": execution_symbol,
        "Side": _metascalp_side(intent.side),
        "OrderType": _metascalp_order_type(intent.order_style),
        "Price": str(intent.price_cap),
        "Volume": str(intent.qty),
        "ClientId": client_id,
        "TimeInForce": "GTC",
        "TtlMs": intent.ttl_ms,
        "ReduceOnly": _is_exit(intent),
        "Comment": f"leadlag:{intent.intent_id}",
    }
    return MetaScalpDryRunOrderPlan(
        intent_id=intent.intent_id,
        connection_id=connection.id,
        client_id=client_id,
        endpoint=endpoint,
        payload=payload,
        validation=validation,
    )


def dry_run_order_audit_record(
    plan: MetaScalpDryRunOrderPlan,
    intent: Intent,
) -> MetaScalpOrderAuditRecord:
    if plan.validation.ok:
        decision_result = "dry_run_planned"
        skip_reason = None
    else:
        decision_result = "validation_failed"
        skip_reason = plan.validation.reason

    return MetaScalpOrderAuditRecord(
        event_type="metascalp_order_dry_run",
        intent_id=intent.intent_id,
        symbol=intent.symbol,
        connection_id=plan.connection_id,
        client_id=plan.client_id,
        endpoint=plan.endpoint,
        dry_run=True,
        request=plan.payload,
        response={
            "dry_run": True,
            "ClientId": None,
            "ExecutionTimeMs": None,
            "UnknownStatus": False,
        },
        decision_result=decision_result,
        skip_reason=skip_reason,
        client_id_returned=None,
        execution_time_ms=None,
        unknown_status=False,
        metadata={"validation_reason": plan.validation.reason},
    )


def metascalp_response_audit_record(
    plan: MetaScalpDryRunOrderPlan,
    intent: Intent,
    response: dict[str, Any],
    status_code: int = 200,
) -> MetaScalpOrderAuditRecord:
    """Normalize a future MetaScalp order response into the audit schema."""

    client_id_returned = _get_response_value(response, "ClientId", "clientId", "client_id")
    execution_time_ms = _int_or_none(
        _get_response_value(response, "ExecutionTimeMs", "executionTimeMs", "execution_time_ms")
    )
    unknown_status = status_code >= 500
    accepted = 200 <= status_code < 300 and not unknown_status
    if unknown_status:
        decision_result = "unknown_status"
        skip_reason = "server_error_unknown_order_status"
    elif accepted:
        decision_result = "accepted"
        skip_reason = None
    else:
        decision_result = "rejected"
        skip_reason = str(_get_response_value(response, "Message", "message", default="order_rejected"))

    return MetaScalpOrderAuditRecord(
        event_type="metascalp_order_response",
        intent_id=intent.intent_id,
        symbol=intent.symbol,
        connection_id=plan.connection_id,
        client_id=plan.client_id,
        endpoint=plan.endpoint,
        dry_run=False,
        request=plan.payload,
        response=response,
        decision_result=decision_result,
        skip_reason=skip_reason,
        client_id_returned=str(client_id_returned) if client_id_returned is not None else None,
        execution_time_ms=execution_time_ms,
        unknown_status=unknown_status,
        metadata={"status_code": status_code},
    )


def _client_id(intent: Intent) -> str:
    safe_intent_id = "".join(ch if ch.isalnum() else "-" for ch in intent.intent_id)
    return f"llb-{safe_intent_id}"[:64]


def _metascalp_side(side: Side) -> str:
    return "Buy" if side == Side.BUY else "Sell"


def _metascalp_order_type(order_style: OrderStyle) -> str:
    if order_style == OrderStyle.AGGRESSIVE_LIMIT:
        return "Limit"
    if order_style == OrderStyle.PASSIVE_LIMIT:
        return "Limit"
    raise ValueError(f"Unsupported order style: {order_style}")


def _is_exit(intent: Intent) -> bool:
    return intent.intent_type in {IntentType.EXIT_LONG, IntentType.EXIT_SHORT}


def _notional_usd(intent: Intent, profile: SymbolProfile) -> Decimal:
    contract_size = profile.contract_size or Decimal("1")
    return abs(intent.qty * intent.price_cap * contract_size)


def _is_multiple(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return True
    return value.remainder_near(step) == 0


def _get_response_value(response: dict[str, Any], *keys: str, default: Any = None) -> Any:
    data = response.get("Data", response.get("data"))
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data[key]
    for key in keys:
        if key in response:
            return response[key]
    return default


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
