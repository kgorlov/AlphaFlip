"""Offline day-level replay from Parquet or DuckDB artifacts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from llbot.service.paper_runner import PaperRunnerConfig, PaperRunResult, run_replay_paper_result
from llbot.service.replay_report import build_replay_research_report, replay_paper_summary_to_dict
from llbot.storage.audit_jsonl import audit_record_to_dict
from llbot.storage.duckdb_store import DuckDbExecutionStore
from llbot.storage.parquet_sink import read_replay_events_parquet_events
from llbot.storage.replay_jsonl import ReplayEvent


@dataclass(frozen=True, slots=True)
class DayReplayResult:
    day: str
    source_kind: str
    input_events: int
    replayed_events: int
    paper: PaperRunResult
    research_report: dict[str, object]


def run_day_replay(
    *,
    day: str,
    config: PaperRunnerConfig,
    parquet_paths: Iterable[str | Path] = (),
    duckdb_path: str | Path | None = None,
    duckdb_source: str | None = None,
) -> DayReplayResult:
    events: list[ReplayEvent] = []
    source_kinds: list[str] = []
    for path in parquet_paths:
        events.extend(read_replay_events_parquet_events(path))
        source_kinds.append("parquet")
    if duckdb_path is not None:
        with DuckDbExecutionStore(duckdb_path) as store:
            events.extend(store.load_replay_events(source=duckdb_source, day=day))
        source_kinds.append("duckdb")
    if not source_kinds:
        raise ValueError("At least one Parquet path or DuckDB path is required")

    day_events = _filter_day(events, day)
    paper = run_replay_paper_result(day_events, config)
    research = build_replay_research_report(
        day_events,
        paper.summary,
        paper.audit_records,
        stale_gap_ms=config.stale_feed_ms,
    )
    return DayReplayResult(
        day=day,
        source_kind="+".join(sorted(set(source_kinds))),
        input_events=len(events),
        replayed_events=len(day_events),
        paper=paper,
        research_report=research,
    )


def day_replay_result_to_dict(result: DayReplayResult) -> dict[str, object]:
    return {
        "day": result.day,
        "source_kind": result.source_kind,
        "input_events": result.input_events,
        "replayed_events": result.replayed_events,
        "paper_summary": replay_paper_summary_to_dict(result.paper.summary),
        "health_report": result.paper.health_report,
        "research_report": result.research_report,
        "offline_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "secrets_read": False,
        "live_trading_enabled": False,
    }


def _filter_day(events: Iterable[ReplayEvent], day: str) -> list[ReplayEvent]:
    return [
        event for event in events
        if isinstance(event.captured_at_utc, str) and event.captured_at_utc.startswith(day)
    ]
