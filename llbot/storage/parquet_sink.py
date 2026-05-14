"""Parquet sink for replayable market-data events."""

from pathlib import Path
from typing import Iterable

from llbot.storage.audit_jsonl import audit_record_to_dict
from llbot.storage.replay_jsonl import ReplayEvent


def write_replay_events_parquet(
    events: Iterable[ReplayEvent],
    path: str | Path,
) -> dict[str, int | str]:
    """Write replay events to a flat Parquet file for day-level replay storage."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [_event_row(event) for event in events]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=_schema())
    pq.write_table(table, out)
    return {"rows": len(rows), "path": str(out)}


def read_replay_events_parquet(path: str | Path) -> list[dict]:
    """Read Parquet replay rows back as dictionaries for validation/reporting."""

    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def read_replay_events_parquet_events(path: str | Path) -> list[ReplayEvent]:
    """Read Parquet replay rows back into normalized ReplayEvent objects."""

    return [_event_from_row(row) for row in read_replay_events_parquet(path)]


def _event_row(event: ReplayEvent) -> dict:
    payload = event.payload
    return {
        "schema_version": event.schema_version,
        "captured_at_utc": event.captured_at_utc,
        "event_type": event.event_type,
        "venue": event.venue,
        "market": event.market,
        "symbol": event.symbol,
        "local_ts_ms": event.local_ts_ms,
        "exchange_ts_ms": event.exchange_ts_ms,
        "receive_monotonic_ns": event.receive_monotonic_ns,
        "bid_price": payload.get("bid_price"),
        "bid_qty": payload.get("bid_qty"),
        "ask_price": payload.get("ask_price"),
        "ask_qty": payload.get("ask_qty"),
        "depth_version": payload.get("version"),
        "payload_json": _json(payload),
    }


def _event_from_row(row: dict) -> ReplayEvent:
    import json

    return ReplayEvent(
        schema_version=str(row.get("schema_version") or "1.0.0"),
        captured_at_utc=str(row.get("captured_at_utc") or ""),
        event_type=str(row["event_type"]),
        venue=str(row["venue"]),
        market=str(row["market"]),
        symbol=str(row["symbol"]),
        local_ts_ms=row.get("local_ts_ms"),
        exchange_ts_ms=row.get("exchange_ts_ms"),
        receive_monotonic_ns=row.get("receive_monotonic_ns"),
        payload=json.loads(str(row.get("payload_json") or "{}")),
    )


def _schema():
    import pyarrow as pa

    return pa.schema(
        [
            ("schema_version", pa.string()),
            ("captured_at_utc", pa.string()),
            ("event_type", pa.string()),
            ("venue", pa.string()),
            ("market", pa.string()),
            ("symbol", pa.string()),
            ("local_ts_ms", pa.int64()),
            ("exchange_ts_ms", pa.int64()),
            ("receive_monotonic_ns", pa.int64()),
            ("bid_price", pa.string()),
            ("bid_qty", pa.string()),
            ("ask_price", pa.string()),
            ("ask_qty", pa.string()),
            ("depth_version", pa.int64()),
            ("payload_json", pa.string()),
        ]
    )


def _json(value) -> str:
    import json

    return json.dumps(audit_record_to_dict(value), ensure_ascii=True, separators=(",", ":"))
