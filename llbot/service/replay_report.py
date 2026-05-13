"""Research report helpers for replay-paper output."""

from decimal import Decimal
from typing import Iterable

from llbot.monitoring.health import (
    FeedStreamState,
    evaluate_feed_health,
    feed_stream_key,
    feed_stream_state_to_dict,
    update_feed_stream_state,
)
from llbot.service.replay import ReplayAuditRecord, ReplayPaperSummary
from llbot.storage.replay_jsonl import ReplayEvent


def replay_paper_summary_to_dict(summary: ReplayPaperSummary) -> dict[str, object]:
    return {
        "processed_events": summary.processed_events,
        "quotes": summary.quotes,
        "intents": summary.intents,
        "skipped_events": summary.skipped_events,
        "risk_allowed": summary.risk_allowed,
        "risk_blocked": summary.risk_blocked,
        "fills": summary.fills,
        "not_filled": summary.not_filled,
        "closed_positions": summary.closed_positions,
        "open_positions": summary.open_positions,
        "gross_realized_pnl_usd": summary.gross_realized_pnl_usd,
        "realized_cost_usd": summary.realized_cost_usd,
        "realized_pnl_usd": summary.realized_pnl_usd,
        "gross_unrealized_pnl_usd": summary.gross_unrealized_pnl_usd,
        "unrealized_cost_usd": summary.unrealized_cost_usd,
        "unrealized_pnl_usd": summary.unrealized_pnl_usd,
        "audit_records": summary.audit_records,
        "intent_counts": dict(summary.intent_counts),
    }


def build_replay_research_report(
    events: Iterable[ReplayEvent],
    summary: ReplayPaperSummary,
    audit_records: Iterable[ReplayAuditRecord],
    stale_gap_ms: int | None = None,
    fill_model_variants: Iterable[dict[str, object]] | None = None,
    fill_model_variant_records: dict[str, Iterable[ReplayAuditRecord]] | None = None,
) -> dict[str, object]:
    event_list = list(events)
    audit_list = list(audit_records)
    replay_days = _replay_days(event_list)
    fallback_day = replay_days[0] if replay_days else "unknown"
    variant_records = {
        name: list(records)
        for name, records in (fill_model_variant_records or {}).items()
    }
    return {
        "schema_version": "1.0.0",
        "replay_days": replay_days,
        "summary": replay_paper_summary_to_dict(summary),
        "feed_health": build_feed_health(event_list, stale_gap_ms),
        "by_symbol_day": build_symbol_day_slices(audit_list, fallback_day),
        "fill_model_variants": list(fill_model_variants or ()),
        "fill_model_diagnostics": build_fill_model_diagnostics(variant_records),
    }


def build_feed_health(
    events: Iterable[ReplayEvent],
    stale_gap_ms: int | None = None,
) -> dict[str, object]:
    streams: dict[str, FeedStreamState] = {}
    total_book_ticker_events = 0

    for event in sorted(events, key=_event_sort_key):
        if event.event_type != "book_ticker":
            continue
        total_book_ticker_events += 1
        key = feed_stream_key(event.venue, event.symbol)
        ts_ms = _event_ts_ms(event)
        streams[key] = update_feed_stream_state(
            streams.get(key),
            event.venue,
            event.symbol,
            ts_ms,
            stale_gap_ms,
        )

    required_streams = tuple(sorted(streams))
    now_ts_ms = max((state.last_ts_ms for state in streams.values()), default=0)
    if stale_gap_ms is None:
        decision = evaluate_feed_health(streams, required_streams, now_ts_ms, 10**18)
    else:
        decision = evaluate_feed_health(streams, required_streams, now_ts_ms, stale_gap_ms)

    return {
        "stale_gap_ms": stale_gap_ms,
        "total_book_ticker_events": total_book_ticker_events,
        "decision": {
            "healthy": decision.healthy,
            "reason": decision.reason,
            "stale_streams": list(decision.stale_streams),
            "missing_streams": list(decision.missing_streams),
        },
        "streams": {
            key: feed_stream_state_to_dict(state)
            for key, state in streams.items()
        },
    }


def build_symbol_day_slices(
    audit_records: Iterable[ReplayAuditRecord],
    fallback_day: str = "unknown",
) -> dict[str, dict[str, object]]:
    slices: dict[str, dict[str, object]] = {}
    for record in audit_records:
        day = fallback_day
        key = f"{record.symbol}|{day}"
        item = slices.setdefault(
            key,
            {
                "symbol": record.symbol,
                "day": day,
                "records": 0,
                "signals": 0,
                "entry_fills": 0,
                "risk_blocked": 0,
                "exits": 0,
                "gross_realized_pnl_usd": Decimal("0"),
                "realized_cost_usd": Decimal("0"),
                "realized_pnl_usd": Decimal("0"),
                "exit_reasons": {},
                "models": {},
            },
        )
        item["records"] = int(item["records"]) + 1
        models = item["models"]
        if isinstance(models, dict):
            models[record.model] = int(models.get(record.model, 0)) + 1

        if record.event_type == "replay_signal_decision":
            item["signals"] = int(item["signals"]) + 1
            if record.risk_allowed is False:
                item["risk_blocked"] = int(item["risk_blocked"]) + 1
            if record.fill_filled:
                item["entry_fills"] = int(item["entry_fills"]) + 1
            continue

        if record.event_type == "replay_position_exit":
            item["exits"] = int(item["exits"]) + 1
            item["gross_realized_pnl_usd"] = _decimal(item["gross_realized_pnl_usd"]) + (
                record.gross_pnl_usd or Decimal("0")
            )
            item["realized_cost_usd"] = _decimal(item["realized_cost_usd"]) + (
                record.cost_usd or Decimal("0")
            )
            item["realized_pnl_usd"] = _decimal(item["realized_pnl_usd"]) + (
                record.realized_pnl_usd or Decimal("0")
            )
            reasons = item["exit_reasons"]
            if isinstance(reasons, dict):
                reason = record.exit_reason or "unknown"
                reasons[reason] = int(reasons.get(reason, 0)) + 1
    return slices


def build_fill_model_diagnostics(
    variant_records: dict[str, Iterable[ReplayAuditRecord]],
) -> list[dict[str, object]]:
    by_intent: dict[str, dict[str, ReplayAuditRecord]] = {}
    for fill_model, records in variant_records.items():
        for record in records:
            if record.event_type != "replay_signal_decision":
                continue
            by_intent.setdefault(record.intent_id, {})[fill_model] = record

    diagnostics: list[dict[str, object]] = []
    for intent_id in sorted(by_intent):
        records_by_model = by_intent[intent_id]
        model_results = {
            fill_model: _candidate_result(record)
            for fill_model, record in sorted(records_by_model.items())
        }
        filled_values = {
            bool(result["fill_filled"])
            for result in model_results.values()
        }
        fill_prices = {
            str(result["fill_price"])
            for result in model_results.values()
            if result["fill_price"] is not None
        }
        diagnostics.append(
            {
                "intent_id": intent_id,
                "symbol": next(iter(records_by_model.values())).symbol,
                "has_difference": len(filled_values) > 1 or len(fill_prices) > 1,
                "models": model_results,
            }
        )
    return diagnostics


def _candidate_result(record: ReplayAuditRecord) -> dict[str, object]:
    return {
        "decision_result": record.decision_result,
        "risk_allowed": record.risk_allowed,
        "fill_filled": record.fill_filled,
        "fill_price": record.fill_price,
        "fill_qty": record.fill_qty,
        "fill_reason": record.fill_reason,
        "skip_reason": record.skip_reason,
    }


def _event_sort_key(event: ReplayEvent) -> tuple[int, int, str, str]:
    ts = _event_ts_ms(event)
    exchange_ts = event.exchange_ts_ms or 0
    return (ts, exchange_ts, event.venue, event.symbol)


def _event_ts_ms(event: ReplayEvent) -> int:
    return event.local_ts_ms or event.exchange_ts_ms or 0


def _replay_days(events: list[ReplayEvent]) -> list[str]:
    days = sorted(
        {
            event.captured_at_utc[:10]
            for event in events
            if isinstance(event.captured_at_utc, str) and len(event.captured_at_utc) >= 10
        }
    )
    return days


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
