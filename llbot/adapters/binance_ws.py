"""Binance public WebSocket stream specs and parsers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, ReceiveTimestamp

BINANCE_SPOT_WS_BASE = "wss://stream.binance.com:9443"
BINANCE_USDM_WS_BASE = "wss://fstream.binance.com"


@dataclass(frozen=True, slots=True)
class BinanceStreamSpec:
    url: str
    streams: tuple[str, ...]
    reconnect_after_sec: int = 23 * 60 * 60


def book_ticker_stream_name(symbol: str) -> str:
    return f"{symbol.lower()}@bookTicker"


def combined_book_ticker_url(
    symbols: list[str],
    market: MarketType,
    time_unit_microsecond: bool = False,
) -> BinanceStreamSpec:
    if not symbols:
        raise ValueError("At least one symbol is required")
    streams = tuple(book_ticker_stream_name(symbol) for symbol in symbols)
    base = BINANCE_USDM_WS_BASE if market == MarketType.USDT_PERP else BINANCE_SPOT_WS_BASE
    query = "/".join(streams)
    suffix = "&timeUnit=MICROSECOND" if time_unit_microsecond and market == MarketType.SPOT else ""
    return BinanceStreamSpec(url=f"{base}/stream?streams={query}{suffix}", streams=streams)


def parse_book_ticker_message(
    message: dict[str, Any],
    market: MarketType,
    received: ReceiveTimestamp | None = None,
) -> BookTicker | None:
    payload = message.get("data", message)
    if not isinstance(payload, dict):
        return None
    if "serverShutdown" in str(payload.get("e", "")):
        return None
    symbol = payload.get("s")
    bid = payload.get("b")
    ask = payload.get("a")
    if symbol is None or bid is None or ask is None:
        return None
    return BookTicker(
        venue=Venue.BINANCE,
        market=market,
        symbol=str(symbol).upper(),
        bid_price=_dec(bid),
        bid_qty=_dec_or_none(payload.get("B")),
        ask_price=_dec(ask),
        ask_qty=_dec_or_none(payload.get("A")),
        timestamp_ms=_int_or_none(payload.get("T") or payload.get("E")),
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        raw=payload,
    )


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _dec_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return _dec(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)

