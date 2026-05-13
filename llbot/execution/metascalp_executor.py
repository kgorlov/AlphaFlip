"""Guarded MetaScalp demo executor.

The executor defaults to dry-run. It submits only when explicitly allowed and
only to a connected DemoMode connection in `metascalp-demo` runtime mode.
"""

from dataclasses import dataclass

from llbot.adapters.http_client import HttpRequestError
from llbot.adapters.metascalp import MetaScalpClient, MetaScalpConnection
from llbot.domain.enums import RuntimeMode
from llbot.domain.models import Intent, SymbolProfile
from llbot.execution.metascalp_planner import (
    MetaScalpOrderAuditRecord,
    build_metascalp_dry_run_order_plan,
    dry_run_order_audit_record,
    metascalp_response_audit_record,
)
from llbot.execution.order_state import CancelAuditRecord, CancelPlan, cancel_plan_audit_record, cancel_response_audit_record


@dataclass(frozen=True, slots=True)
class MetaScalpExecutorConfig:
    allow_submit: bool = False
    runtime_mode: RuntimeMode = RuntimeMode.PAPER
    require_demo_mode: bool = True
    require_connected: bool = True


class GuardedMetaScalpDemoExecutor:
    def __init__(self, client: MetaScalpClient, config: MetaScalpExecutorConfig | None = None) -> None:
        self.client = client
        self.config = config or MetaScalpExecutorConfig()

    async def submit(
        self,
        intent: Intent,
        connection: MetaScalpConnection,
        execution_symbol: str,
        profile: SymbolProfile | None = None,
    ) -> MetaScalpOrderAuditRecord:
        plan = build_metascalp_dry_run_order_plan(intent, connection, execution_symbol, profile)

        guard_reason = self._guard_reason(connection)
        if guard_reason is not None:
            dry = dry_run_order_audit_record(plan, intent)
            return MetaScalpOrderAuditRecord(
                event_type=dry.event_type,
                intent_id=dry.intent_id,
                symbol=dry.symbol,
                connection_id=dry.connection_id,
                client_id=dry.client_id,
                endpoint=dry.endpoint,
                dry_run=True,
                request=dry.request,
                response=dry.response,
                decision_result="guard_blocked",
                skip_reason=guard_reason,
                client_id_returned=dry.client_id_returned,
                execution_time_ms=dry.execution_time_ms,
                unknown_status=dry.unknown_status,
                metadata={**dry.metadata, "guard_reason": guard_reason},
            )

        if not plan.validation.ok:
            return dry_run_order_audit_record(plan, intent)

        if not self.config.allow_submit:
            return dry_run_order_audit_record(plan, intent)

        try:
            response = await self.client.place_order(connection.id, plan.payload)
        except HttpRequestError as exc:
            return metascalp_response_audit_record(
                plan,
                intent,
                {"Message": str(exc)},
                status_code=_status_code_from_error(str(exc)),
            )

        return metascalp_response_audit_record(plan, intent, response, status_code=200)

    async def cancel(self, plan: CancelPlan, connection: MetaScalpConnection) -> CancelAuditRecord:
        dry = cancel_plan_audit_record(plan)
        guard_reason = self._guard_reason(connection)
        if guard_reason is None and plan.connection_id != connection.id:
            guard_reason = "connection_id_mismatch"
        if guard_reason is not None:
            return CancelAuditRecord(
                event_type=dry.event_type,
                intent_id=dry.intent_id,
                client_order_id=dry.client_order_id,
                connection_id=dry.connection_id,
                endpoint=dry.endpoint,
                dry_run=True,
                request=dry.request,
                response=dry.response,
                decision_result="guard_blocked",
                skip_reason=guard_reason,
                metadata={**dry.metadata, "guard_reason": guard_reason},
            )
        if not self.config.allow_submit:
            return dry

        try:
            response = await self.client.cancel_order(connection.id, plan.request)
        except HttpRequestError as exc:
            return cancel_response_audit_record(
                plan,
                {"Message": str(exc)},
                status_code=_status_code_from_error(str(exc)),
            )

        return cancel_response_audit_record(plan, response, status_code=200)

    def _guard_reason(self, connection: MetaScalpConnection) -> str | None:
        if self.config.runtime_mode == RuntimeMode.LIVE:
            return "live_mode_not_supported"
        if self.config.allow_submit and self.config.runtime_mode != RuntimeMode.METASCALP_DEMO:
            return "submit_requires_metascalp_demo_mode"
        if self.config.require_demo_mode and not connection.demo_mode:
            return "connection_not_demo"
        if self.config.require_connected and not connection.connected:
            return "connection_not_active"
        return None


def _status_code_from_error(message: str) -> int:
    for token in message.replace(":", " ").split():
        if token.isdigit():
            code = int(token)
            if 100 <= code <= 599:
                return code
    return 500
