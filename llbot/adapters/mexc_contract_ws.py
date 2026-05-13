"""MEXC futures public WebSocket stream specs and parsers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth, ReceiveTimestamp
from llbot.universe.symbol_mapper import normalize_mexc_contract_symbol

MEXC_CONTRACT_WS_URL = "wss://contract.mexc.com/edge"


@dataclass(frozen=True, slots=True)
class MexcSubscription:
    message: dict[str, Any]


def ping_message() -> dict[str, str]:
    return {"method": "ping"}


def subscribe_ticker(symbol: str) -> MexcSubscription:
    return MexcSubscription(
        {"method": "sub.ticker", "param": {"symbol": normalize_mexc_contract_symbol(symbol)}}
    )


def unsubscribe_ticker(symbol: str) -> MexcSubscription:
    return MexcSubscription(
        {"method": "unsub.ticker", "param": {"symbol": normalize_mexc_contract_symbol(symbol)}}
    )


def subscribe_depth(symbol: str) -> MexcSubscription:
    return MexcSubscription(
        {"method": "sub.depth", "param": {"symbol": normalize_mexc_contract_symbol(symbol)}}
    )


def unsubscribe_depth(symbol: str) -> MexcSubscription:
    return MexcSubscription(
        {"method": "unsub.depth", "param": {"symbol": normalize_mexc_contract_symbol(symbol)}}
    )


def parse_message(
    message: dict[str, Any],
    received: ReceiveTimestamp | None = None,
) -> BookTicker | OrderBookDepth | None:
    channel = str(message.get("channel", ""))
    if channel == "pong":
        return None
    if channel == "push.ticker":
        return _parse_ticker(message, received)
    if channel == "push.depth":
        return _parse_depth(message, received)
    return None


def _parse_ticker(message: dict[str, Any], received: ReceiveTimestamp | None) -> BookTicker | None:
    data = message.get("data", {})
    if not isinstance(data, dict):
        return None
    symbol = data.get("symbol") or message.get("symbol")
    bid = data.get("bid1")
    ask = data.get("ask1")
    if symbol is None or bid is None or ask is None:
        return None
    return BookTicker(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=normalize_mexc_contract_symbol(str(symbol)),
        bid_price=_dec(bid),
        bid_qty=None,
        ask_price=_dec(ask),
        ask_qty=None,
        timestamp_ms=_int_or_none(data.get("timestamp") or message.get("ts")),
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        raw=message,
    )


def _parse_depth(message: dict[str, Any], received: ReceiveTimestamp | None) -> OrderBookDepth | None:
    data = message.get("data", {})
    if not isinstance(data, dict):
        return None
    symbol = message.get("symbol") or data.get("symbol")
    if symbol is None:
        return None
    return OrderBookDepth(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=normalize_mexc_contract_symbol(str(symbol)),
        bids=_levels(data.get("bids", [])),
        asks=_levels(data.get("asks", [])),
        timestamp_ms=_int_or_none(message.get("ts") or data.get("timestamp") or data.get("ct")),
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        version=_int_or_none(data.get("version")),
        raw=message,
    )


def _levels(raw: list[Any]) -> tuple[DepthLevel, ...]:
    levels: list[DepthLevel] = []
    for level in raw:
        if not isinstance(level, list | tuple) or len(level) < 2:
            continue
        levels.append(DepthLevel(price=_dec(level[0]), qty=_dec(level[1])))
    return tuple(levels)


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)

