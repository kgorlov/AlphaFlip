"""Replay-friendly JSONL event capture."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    event_type: str
    venue: str
    market: str
    symbol: str
    local_ts_ms: int | None
    exchange_ts_ms: int | None
    receive_monotonic_ns: int | None
    payload: dict[str, Any]
    schema_version: str = "1.0.0"
    captured_at_utc: str = field(default_factory=lambda: _utc_now())


class JsonlReplayWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ReplayEvent) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=True, separators=(",", ":")))
            f.write("\n")


def replay_event_from_book_ticker(ticker: BookTicker) -> ReplayEvent:
    return ReplayEvent(
        event_type="book_ticker",
        venue=ticker.venue.value,
        market=ticker.market.value,
        symbol=ticker.symbol,
        local_ts_ms=ticker.local_ts_ms,
        exchange_ts_ms=ticker.timestamp_ms,
        receive_monotonic_ns=ticker.receive_monotonic_ns,
        payload={
            "bid_price": str(ticker.bid_price),
            "bid_qty": str(ticker.bid_qty) if ticker.bid_qty is not None else None,
            "ask_price": str(ticker.ask_price),
            "ask_qty": str(ticker.ask_qty) if ticker.ask_qty is not None else None,
            "raw": ticker.raw,
        },
    )


def replay_event_from_depth(depth: OrderBookDepth) -> ReplayEvent:
    return ReplayEvent(
        event_type="orderbook_depth",
        venue=depth.venue.value,
        market=depth.market.value,
        symbol=depth.symbol,
        local_ts_ms=depth.local_ts_ms,
        exchange_ts_ms=depth.timestamp_ms,
        receive_monotonic_ns=depth.receive_monotonic_ns,
        payload={
            "version": depth.version,
            "bids": [[str(level.price), str(level.qty)] for level in depth.bids],
            "asks": [[str(level.price), str(level.qty)] for level in depth.asks],
            "raw": depth.raw,
        },
    )


def read_replay_events(path: str | Path) -> list[ReplayEvent]:
    events: list[ReplayEvent] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            events.append(ReplayEvent(**item))
    return events


def book_ticker_from_replay_event(event: ReplayEvent) -> BookTicker:
    if event.event_type != "book_ticker":
        raise ValueError(f"Expected book_ticker event, got {event.event_type}")
    payload = event.payload
    return BookTicker(
        venue=Venue(event.venue),
        market=MarketType(event.market),
        symbol=event.symbol,
        bid_price=Decimal(str(payload["bid_price"])),
        bid_qty=_optional_decimal(payload.get("bid_qty")),
        ask_price=Decimal(str(payload["ask_price"])),
        ask_qty=_optional_decimal(payload.get("ask_qty")),
        timestamp_ms=event.exchange_ts_ms,
        local_ts_ms=event.local_ts_ms,
        receive_monotonic_ns=event.receive_monotonic_ns,
        raw=payload.get("raw") or {},
    )


def depth_from_replay_event(event: ReplayEvent) -> OrderBookDepth:
    if event.event_type != "orderbook_depth":
        raise ValueError(f"Expected orderbook_depth event, got {event.event_type}")
    payload = event.payload
    return OrderBookDepth(
        venue=Venue(event.venue),
        market=MarketType(event.market),
        symbol=event.symbol,
        bids=tuple(DepthLevel(Decimal(str(price)), Decimal(str(qty))) for price, qty in payload["bids"]),
        asks=tuple(DepthLevel(Decimal(str(price)), Decimal(str(qty))) for price, qty in payload["asks"]),
        timestamp_ms=event.exchange_ts_ms,
        local_ts_ms=event.local_ts_ms,
        receive_monotonic_ns=event.receive_monotonic_ns,
        version=payload.get("version"),
        raw=payload.get("raw") or {},
    )


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
