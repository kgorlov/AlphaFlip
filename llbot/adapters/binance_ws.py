"""Binance public WebSocket stream specs and parsers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from llbot.domain.enums import MarketType, Side, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth, ReceiveTimestamp
from llbot.domain.models import Trade

BINANCE_SPOT_WS_BASE = "wss://stream.binance.com:9443"
BINANCE_USDM_WS_BASE = "wss://fstream.binance.com"


@dataclass(frozen=True, slots=True)
class BinanceStreamSpec:
    url: str
    streams: tuple[str, ...]
    reconnect_after_sec: int = 23 * 60 * 60


def book_ticker_stream_name(symbol: str) -> str:
    return f"{symbol.lower()}@bookTicker"


def aggregate_trade_stream_name(symbol: str) -> str:
    return f"{symbol.lower()}@aggTrade"


def partial_depth_stream_name(symbol: str, levels: int = 5, speed_ms: int = 100) -> str:
    if levels not in {5, 10, 20}:
        raise ValueError("Binance partial depth levels must be 5, 10, or 20")
    if speed_ms not in {100, 250, 500, 1000}:
        raise ValueError("Binance partial depth speed_ms must be 100, 250, 500, or 1000")
    return f"{symbol.lower()}@depth{levels}@{speed_ms}ms"


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


def combined_stream_url(
    streams: tuple[str, ...] | list[str],
    market: MarketType,
    time_unit_microsecond: bool = False,
) -> BinanceStreamSpec:
    if not streams:
        raise ValueError("At least one stream is required")
    stream_tuple = tuple(streams)
    base = BINANCE_USDM_WS_BASE if market == MarketType.USDT_PERP else BINANCE_SPOT_WS_BASE
    query = "/".join(stream_tuple)
    suffix = "&timeUnit=MICROSECOND" if time_unit_microsecond and market == MarketType.SPOT else ""
    return BinanceStreamSpec(url=f"{base}/stream?streams={query}{suffix}", streams=stream_tuple)


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


def parse_agg_trade_message(
    message: dict[str, Any],
    market: MarketType,
    received: ReceiveTimestamp | None = None,
) -> Trade | None:
    payload = message.get("data", message)
    if not isinstance(payload, dict):
        return None
    if payload.get("e") not in {"aggTrade", "trade"}:
        return None
    symbol = payload.get("s")
    price = payload.get("p")
    qty = payload.get("q")
    if symbol is None or price is None or qty is None:
        return None
    maker_side = payload.get("m")
    side = None
    if maker_side is not None:
        # Binance m=true means buyer is maker, so aggressive side is sell.
        side = Side.SELL if bool(maker_side) else Side.BUY
    return Trade(
        venue=Venue.BINANCE,
        market=market,
        symbol=str(symbol).upper(),
        price=_dec(price),
        qty=_dec(qty),
        side=side,
        exchange_ts_ms=_int_or_none(payload.get("T") or payload.get("E")),
        local_ts_ms=received.local_ts_ms if received else _int_or_none(payload.get("T") or payload.get("E")) or 0,
        trade_id=str(payload.get("a") or payload.get("t") or ""),
    )


def parse_depth_message(
    message: dict[str, Any],
    market: MarketType,
    received: ReceiveTimestamp | None = None,
) -> OrderBookDepth | None:
    payload = message.get("data", message)
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("e")
    if event_type not in {"depthUpdate", "partialDepth"} and not (
        "bids" in payload or "b" in payload
    ):
        return None
    symbol = payload.get("s")
    bids = payload.get("bids", payload.get("b", []))
    asks = payload.get("asks", payload.get("a", []))
    if symbol is None or not isinstance(bids, list) or not isinstance(asks, list):
        return None
    return OrderBookDepth(
        venue=Venue.BINANCE,
        market=market,
        symbol=str(symbol).upper(),
        bids=_levels(bids),
        asks=_levels(asks),
        timestamp_ms=_int_or_none(payload.get("T") or payload.get("E")),
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        version=_int_or_none(payload.get("u") or payload.get("lastUpdateId")),
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


def _levels(raw: list[Any]) -> tuple[DepthLevel, ...]:
    levels = []
    for level in raw:
        if not isinstance(level, list | tuple) or len(level) < 2:
            continue
        levels.append(DepthLevel(price=_dec(level[0]), qty=_dec(level[1])))
    return tuple(levels)
