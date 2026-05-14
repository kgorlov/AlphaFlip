"""Research report helpers for replay-paper output."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable

from llbot.domain.enums import Venue
from llbot.monitoring.health import (
    FeedStreamState,
    evaluate_feed_health,
    feed_stream_key,
    feed_stream_state_to_dict,
    update_feed_stream_state,
)
from llbot.service.replay import ReplayAuditRecord, ReplayPaperSummary
from llbot.signals.leadlag import MidpointSample, estimate_leadership
from llbot.storage.replay_jsonl import ReplayEvent, book_ticker_from_replay_event
from llbot.universe.symbol_mapper import mexc_contract_to_binance_usdm, normalize_binance_symbol


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
        "research_metrics": build_research_metrics(audit_list),
        "symbol_selection": build_symbol_selection(event_list, audit_list),
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


def build_research_metrics(audit_records: Iterable[ReplayAuditRecord]) -> dict[str, object]:
    records = list(audit_records)
    exits = [record for record in records if record.event_type == "replay_position_exit"]
    return {
        "catch_up": _catch_up_metrics(exits),
        "false_positives": _false_positive_metrics(exits),
        "slippage_by_hour": _slippage_by_hour(records),
        "performance_by_volatility_regime": _performance_by_regime(exits),
    }


def build_symbol_selection(
    events: Iterable[ReplayEvent],
    audit_records: Iterable[ReplayAuditRecord],
    *,
    top_n: int = 20,
    candidate_lags_ms: tuple[int, ...] = (25, 50, 100, 200, 500, 1000),
) -> dict[str, object]:
    event_list = list(events)
    audit_list = list(audit_records)
    groups = _symbol_quote_groups(event_list)
    paper_pnl = _paper_pnl_by_symbol(audit_list)
    candidates = []
    for symbol in sorted(groups):
        group = groups[symbol]
        result = estimate_leadership(
            group["binance_samples"],
            group["mexc_samples"],
            candidate_lags_ms=candidate_lags_ms,
            min_pairs=3,
        )
        avg_spread = _average(group["mexc_spreads_bps"])
        avg_liquidity = _average(group["mexc_liquidity_usd"])
        pnl = paper_pnl.get(symbol, Decimal("0"))
        score = _selection_score(result.leader_score, result.stable, avg_liquidity, avg_spread, pnl)
        candidates.append(
            {
                "symbol": symbol,
                "leader": result.leader.value if result.leader else None,
                "lagger": result.lagger.value if result.lagger else None,
                "lag_ms": result.lag_ms,
                "leader_score": result.leader_score,
                "stable": result.stable,
                "reason": result.reason,
                "lag_scores": [dict(
                    lag_ms=item.lag_ms,
                    pairs=item.pairs,
                    correlation=item.correlation,
                    sign_agreement=item.sign_agreement,
                    score=item.score,
                ) for item in result.lag_scores],
                "binance_quote_count": len(group["binance_samples"]),
                "mexc_quote_count": len(group["mexc_samples"]),
                "avg_mexc_spread_bps": avg_spread,
                "avg_mexc_top_liquidity_usd": avg_liquidity,
                "paper_realized_pnl_usd": pnl,
                "selection_score": score,
            }
        )

    ranked = sorted(
        candidates,
        key=lambda item: (
            bool(item["stable"]),
            Decimal(str(item["selection_score"])),
            Decimal(str(item["paper_realized_pnl_usd"])),
        ),
        reverse=True,
    )
    return {
        "top_n": top_n,
        "candidate_lags_ms": list(candidate_lags_ms),
        "ranking_inputs": {
            "liquidity": "MEXC bookTicker top-of-book USD proxy",
            "spread": "MEXC bookTicker spread bps average",
            "paper_pnl": "sum of replay-paper realized PnL exits by symbol",
            "lag_stability": "dynamic midpoint leadership score",
        },
        "top_symbols": ranked[:top_n],
        "all_symbols": ranked,
    }


def _catch_up_metrics(exits: list[ReplayAuditRecord]) -> dict[str, object]:
    durations: list[int] = []
    for record in exits:
        if record.exit_reason not in {"take_profit", "zscore_mean_reversion"}:
            continue
        if (record.realized_pnl_usd or Decimal("0")) <= 0:
            continue
        entry_ts = _entry_ts_ms(record)
        if entry_ts is not None and record.timestamp_ms >= entry_ts:
            durations.append(record.timestamp_ms - entry_ts)

    return {
        "catch_up_exits": len(durations),
        "min_ms": min(durations) if durations else None,
        "max_ms": max(durations) if durations else None,
        "avg_ms": _avg_int(durations),
        "p50_ms": _percentile_int(durations, Decimal("0.50")),
        "p90_ms": _percentile_int(durations, Decimal("0.90")),
    }


def _symbol_quote_groups(events: list[ReplayEvent]) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for event in sorted(events, key=_event_sort_key):
        if event.event_type != "book_ticker":
            continue
        ticker = book_ticker_from_replay_event(event)
        symbol = _canonical_symbol(event.venue, event.symbol)
        group = groups.setdefault(
            symbol,
            {
                "binance_samples": [],
                "mexc_samples": [],
                "mexc_spreads_bps": [],
                "mexc_liquidity_usd": [],
            },
        )
        sample = MidpointSample(ticker.local_ts_ms or ticker.timestamp_ms or 0, ticker.mid)
        if ticker.venue == Venue.BINANCE:
            group["binance_samples"].append(sample)
        elif ticker.venue == Venue.MEXC:
            group["mexc_samples"].append(sample)
            group["mexc_spreads_bps"].append(ticker.spread_bps)
            if ticker.bid_qty is not None and ticker.ask_qty is not None:
                bid_liquidity = ticker.bid_price * ticker.bid_qty
                ask_liquidity = ticker.ask_price * ticker.ask_qty
                group["mexc_liquidity_usd"].append(min(bid_liquidity, ask_liquidity))
    return groups


def _paper_pnl_by_symbol(records: list[ReplayAuditRecord]) -> dict[str, Decimal]:
    pnl: dict[str, Decimal] = {}
    for record in records:
        if record.event_type != "replay_position_exit":
            continue
        pnl[record.symbol] = pnl.get(record.symbol, Decimal("0")) + (
            record.realized_pnl_usd or Decimal("0")
        )
    return pnl


def _selection_score(
    leader_score: Decimal,
    stable: bool,
    avg_liquidity_usd: Decimal,
    avg_spread_bps: Decimal,
    paper_pnl_usd: Decimal,
) -> Decimal:
    stability = leader_score if stable else Decimal("0")
    liquidity_component = min(avg_liquidity_usd / Decimal("100000"), Decimal("1"))
    spread_penalty = min(avg_spread_bps / Decimal("20"), Decimal("1"))
    pnl_component = max(Decimal("-1"), min(paper_pnl_usd / Decimal("10"), Decimal("1")))
    return (
        Decimal("0.55") * stability
        + Decimal("0.20") * liquidity_component
        - Decimal("0.15") * spread_penalty
        + Decimal("0.10") * pnl_component
    )


def _canonical_symbol(venue: str, symbol: str) -> str:
    if venue == Venue.MEXC.value and "_" in symbol:
        return mexc_contract_to_binance_usdm(symbol)
    return normalize_binance_symbol(symbol)


def _average(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _false_positive_metrics(exits: list[ReplayAuditRecord]) -> dict[str, object]:
    closed = len(exits)
    false_positive = sum(1 for record in exits if (record.realized_pnl_usd or Decimal("0")) <= 0)
    return {
        "closed_trades": closed,
        "false_positives": false_positive,
        "false_positive_rate": (
            Decimal(false_positive) / Decimal(closed) if closed else Decimal("0")
        ),
    }


def _slippage_by_hour(records: list[ReplayAuditRecord]) -> dict[str, dict[str, object]]:
    buckets: dict[str, dict[str, object]] = {}
    for record in records:
        if not record.fill_filled:
            continue
        hour = _utc_hour(record.timestamp_ms)
        item = buckets.setdefault(
            hour,
            {
                "hour_utc": hour,
                "fills": 0,
                "total_slippage_bps": Decimal("0"),
                "avg_slippage_bps": Decimal("0"),
                "total_cost_usd": Decimal("0"),
            },
        )
        item["fills"] = int(item["fills"]) + 1
        item["total_slippage_bps"] = _decimal(item["total_slippage_bps"]) + (
            record.slippage_bps or _entry_feature_decimal(record, "slippage_bps") or Decimal("0")
        )
        item["total_cost_usd"] = _decimal(item["total_cost_usd"]) + (
            record.cost_usd or Decimal("0")
        )

    for item in buckets.values():
        fills = int(item["fills"])
        item["avg_slippage_bps"] = (
            _decimal(item["total_slippage_bps"]) / Decimal(fills) if fills else Decimal("0")
        )
    return {key: buckets[key] for key in sorted(buckets)}


def _performance_by_regime(exits: list[ReplayAuditRecord]) -> dict[str, dict[str, object]]:
    buckets: dict[str, dict[str, object]] = {}
    for record in exits:
        regime = _volatility_regime(record)
        item = buckets.setdefault(
            regime,
            {
                "regime": regime,
                "closed_trades": 0,
                "winning_trades": 0,
                "realized_pnl_usd": Decimal("0"),
                "avg_realized_pnl_usd": Decimal("0"),
                "win_rate": Decimal("0"),
            },
        )
        pnl = record.realized_pnl_usd or Decimal("0")
        item["closed_trades"] = int(item["closed_trades"]) + 1
        if pnl > 0:
            item["winning_trades"] = int(item["winning_trades"]) + 1
        item["realized_pnl_usd"] = _decimal(item["realized_pnl_usd"]) + pnl

    for item in buckets.values():
        closed = int(item["closed_trades"])
        wins = int(item["winning_trades"])
        item["avg_realized_pnl_usd"] = (
            _decimal(item["realized_pnl_usd"]) / Decimal(closed) if closed else Decimal("0")
        )
        item["win_rate"] = Decimal(wins) / Decimal(closed) if closed else Decimal("0")
    return {key: buckets[key] for key in sorted(buckets)}


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


def _entry_ts_ms(record: ReplayAuditRecord) -> int | None:
    value = record.features.get("entry_ts_ms")
    if value is None:
        return None
    return int(value)


def _entry_feature_decimal(record: ReplayAuditRecord, key: str) -> Decimal | None:
    entry_features = record.features.get("entry_features")
    if not isinstance(entry_features, dict):
        return None
    value = entry_features.get(key)
    if value is None:
        return None
    return Decimal(str(value))


def _volatility_regime(record: ReplayAuditRecord) -> str:
    impulse = record.impulse_bps or _entry_feature_decimal(record, "leader_impulse_bps")
    if impulse is None:
        return "unknown"
    abs_impulse = abs(impulse)
    if abs_impulse < Decimal("5"):
        return "low"
    if abs_impulse < Decimal("20"):
        return "medium"
    return "high"


def _utc_hour(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:00:00Z")


def _avg_int(values: list[int]) -> int | None:
    if not values:
        return None
    return int(sum(values) / len(values))


def _percentile_int(values: list[int], percentile: Decimal) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = int((Decimal(len(ordered) - 1) * percentile).to_integral_value())
    return ordered[rank]


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
