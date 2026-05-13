"""Bridge paper signal decisions into guarded MetaScalp demo submissions."""

from dataclasses import dataclass
from decimal import Decimal

from llbot.adapters.metascalp import MetaScalpConnection
from llbot.domain.enums import IntentType, MarketProfileName, OrderStyle, Side
from llbot.domain.models import Intent, SymbolProfile
from llbot.execution.metascalp_executor import GuardedMetaScalpDemoExecutor
from llbot.execution.metascalp_planner import MetaScalpOrderAuditRecord
from llbot.service.replay import ReplayAuditRecord


@dataclass(frozen=True, slots=True)
class DemoSubmitConfig:
    max_demo_orders: int = 1


def should_submit_demo_record(record: ReplayAuditRecord) -> bool:
    return (
        record.event_type == "replay_signal_decision"
        and record.decision_result == "filled"
        and record.risk_allowed
        and record.intent_type in {IntentType.ENTER_LONG.value, IntentType.ENTER_SHORT.value}
    )


def intent_from_audit_record(record: ReplayAuditRecord, profile: MarketProfileName) -> Intent:
    request = record.order_request
    return Intent(
        intent_id=record.intent_id,
        symbol=record.symbol,
        profile=profile,
        intent_type=IntentType(record.intent_type),
        side=Side(record.side),
        qty=Decimal(str(request["qty"])),
        price_cap=Decimal(str(request["price_cap"])),
        ttl_ms=int(request["ttl_ms"]),
        order_style=OrderStyle(str(request["order_style"])),
        confidence=Decimal("1"),
        expected_edge_bps=Decimal(str(record.expected_edge_bps)),
        created_ts_ms=record.timestamp_ms,
        features=dict(record.features),
    )


async def submit_demo_records(
    records: list[ReplayAuditRecord],
    executor: GuardedMetaScalpDemoExecutor,
    connection: MetaScalpConnection,
    execution_symbol: str,
    profile_name: MarketProfileName,
    submitted_count: int,
    config: DemoSubmitConfig | None = None,
    symbol_profile: SymbolProfile | None = None,
) -> tuple[list[MetaScalpOrderAuditRecord], int]:
    cfg = config or DemoSubmitConfig()
    audits: list[MetaScalpOrderAuditRecord] = []
    count = submitted_count
    for record in records:
        if count >= cfg.max_demo_orders:
            break
        if not should_submit_demo_record(record):
            continue
        intent = intent_from_audit_record(record, profile_name)
        audits.append(await executor.submit(intent, connection, execution_symbol, symbol_profile))
        count += 1
    return audits, count
