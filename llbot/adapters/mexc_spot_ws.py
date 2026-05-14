"""MEXC spot public WebSocket stream specs and protobuf parsers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth, ReceiveTimestamp
from llbot.universe.symbol_mapper import normalize_mexc_spot_symbol

MEXC_SPOT_WS_URL = "wss://wbs-api.mexc.com/ws"

_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LENGTH_DELIMITED = 2
_WIRE_32BIT = 5

_WRAPPER_CHANNEL = 1
_WRAPPER_SYMBOL = 3
_WRAPPER_CREATE_TIME = 5
_WRAPPER_SEND_TIME = 6
_WRAPPER_INCREASE_DEPTH = 302
_WRAPPER_LIMIT_DEPTH = 303
_WRAPPER_BOOK_TICKER = 305
_WRAPPER_BOOK_TICKER_BATCH = 311
_WRAPPER_INCREASE_DEPTH_BATCH = 312
_WRAPPER_AGGRE_DEPTH = 313
_WRAPPER_AGGRE_BOOK_TICKER = 315


@dataclass(frozen=True, slots=True)
class MexcSpotSubscription:
    message: dict[str, Any]


def ping_message() -> dict[str, str]:
    return {"method": "PING"}


def subscribe_book_ticker(symbol: str, speed_ms: int = 100) -> MexcSpotSubscription:
    return MexcSpotSubscription(
        {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.aggre.bookTicker.v3.api.pb@{speed_ms}ms@{_symbol(symbol)}"],
        }
    )


def unsubscribe_book_ticker(symbol: str, speed_ms: int = 100) -> MexcSpotSubscription:
    return MexcSpotSubscription(
        {
            "method": "UNSUBSCRIPTION",
            "params": [f"spot@public.aggre.bookTicker.v3.api.pb@{speed_ms}ms@{_symbol(symbol)}"],
        }
    )


def subscribe_depth(symbol: str, speed_ms: int = 100) -> MexcSpotSubscription:
    return MexcSpotSubscription(
        {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.aggre.depth.v3.api.pb@{speed_ms}ms@{_symbol(symbol)}"],
        }
    )


def unsubscribe_depth(symbol: str, speed_ms: int = 100) -> MexcSpotSubscription:
    return MexcSpotSubscription(
        {
            "method": "UNSUBSCRIPTION",
            "params": [f"spot@public.aggre.depth.v3.api.pb@{speed_ms}ms@{_symbol(symbol)}"],
        }
    )


def subscribe_limit_depth(symbol: str, levels: int = 5) -> MexcSpotSubscription:
    return MexcSpotSubscription(
        {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.limit.depth.v3.api.pb@{_symbol(symbol)}@{levels}"],
        }
    )


def parse_message(
    payload: bytes | bytearray | memoryview | dict[str, Any],
    received: ReceiveTimestamp | None = None,
) -> BookTicker | OrderBookDepth | None:
    if isinstance(payload, dict):
        return None
    fields = _read_message(bytes(payload))
    symbol = _string_first(fields, _WRAPPER_SYMBOL)
    timestamp_ms = _int_first(fields, _WRAPPER_SEND_TIME) or _int_first(fields, _WRAPPER_CREATE_TIME)
    raw = _raw_wrapper(fields)

    for body in _bytes_values(fields, _WRAPPER_BOOK_TICKER, _WRAPPER_AGGRE_BOOK_TICKER):
        return _parse_book_ticker(body, symbol, timestamp_ms, received, raw)

    for body in _bytes_values(fields, _WRAPPER_BOOK_TICKER_BATCH):
        for item in _bytes_values(_read_message(body), 1):
            parsed = _parse_book_ticker(item, symbol, timestamp_ms, received, raw)
            if parsed is not None:
                return parsed

    for body in _bytes_values(fields, _WRAPPER_LIMIT_DEPTH):
        return _parse_depth(body, symbol, timestamp_ms, received, raw, version_field=4)

    for body in _bytes_values(fields, _WRAPPER_INCREASE_DEPTH, _WRAPPER_AGGRE_DEPTH):
        return _parse_depth(body, symbol, timestamp_ms, received, raw, version_field=5)

    for body in _bytes_values(fields, _WRAPPER_INCREASE_DEPTH_BATCH):
        for item in _bytes_values(_read_message(body), 1):
            parsed = _parse_depth(item, symbol, timestamp_ms, received, raw, version_field=4)
            if parsed is not None:
                return parsed

    return None


def _parse_book_ticker(
    payload: bytes,
    symbol: str | None,
    timestamp_ms: int | None,
    received: ReceiveTimestamp | None,
    raw: dict[str, Any],
) -> BookTicker | None:
    fields = _read_message(payload)
    bid = _string_first(fields, 1)
    bid_qty = _string_first(fields, 2)
    ask = _string_first(fields, 3)
    ask_qty = _string_first(fields, 4)
    if symbol is None or bid is None or ask is None:
        return None
    return BookTicker(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=_symbol(symbol),
        bid_price=_dec(bid),
        bid_qty=_dec_or_none(bid_qty),
        ask_price=_dec(ask),
        ask_qty=_dec_or_none(ask_qty),
        timestamp_ms=timestamp_ms,
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        raw=raw,
    )


def _parse_depth(
    payload: bytes,
    symbol: str | None,
    timestamp_ms: int | None,
    received: ReceiveTimestamp | None,
    raw: dict[str, Any],
    *,
    version_field: int,
) -> OrderBookDepth | None:
    fields = _read_message(payload)
    if symbol is None:
        return None
    return OrderBookDepth(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=_symbol(symbol),
        asks=_levels(fields.get(1, [])),
        bids=_levels(fields.get(2, [])),
        timestamp_ms=timestamp_ms,
        local_ts_ms=received.local_ts_ms if received else None,
        receive_monotonic_ns=received.monotonic_ns if received else None,
        version=_int_from_string(_string_first(fields, version_field)),
        raw=raw,
    )


def _levels(items: list[Any]) -> tuple[DepthLevel, ...]:
    levels: list[DepthLevel] = []
    for item in items:
        if not isinstance(item, bytes):
            continue
        fields = _read_message(item)
        price = _string_first(fields, 1)
        qty = _string_first(fields, 2)
        if price is not None and qty is not None:
            levels.append(DepthLevel(price=_dec(price), qty=_dec(qty)))
    return tuple(levels)


def _read_message(payload: bytes) -> dict[int, list[Any]]:
    fields: dict[int, list[Any]] = {}
    offset = 0
    while offset < len(payload):
        key, offset = _read_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        value: Any
        if wire_type == _WIRE_VARINT:
            value, offset = _read_varint(payload, offset)
        elif wire_type == _WIRE_LENGTH_DELIMITED:
            size, offset = _read_varint(payload, offset)
            end = offset + size
            if end > len(payload):
                raise ValueError("Truncated protobuf length-delimited field")
            value = payload[offset:end]
            offset = end
        elif wire_type == _WIRE_64BIT:
            end = offset + 8
            if end > len(payload):
                raise ValueError("Truncated protobuf 64-bit field")
            value = payload[offset:end]
            offset = end
        elif wire_type == _WIRE_32BIT:
            end = offset + 4
            if end > len(payload):
                raise ValueError("Truncated protobuf 32-bit field")
            value = payload[offset:end]
            offset = end
        else:
            raise ValueError(f"Unsupported protobuf wire type: {wire_type}")
        fields.setdefault(field_number, []).append(value)
    return fields


def _read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift >= 64:
            raise ValueError("Protobuf varint is too long")
    raise ValueError("Truncated protobuf varint")


def _bytes_values(fields: dict[int, list[Any]], *field_numbers: int) -> list[bytes]:
    values: list[bytes] = []
    for field_number in field_numbers:
        values.extend(value for value in fields.get(field_number, []) if isinstance(value, bytes))
    return values


def _string_first(fields: dict[int, list[Any]], field_number: int) -> str | None:
    values = fields.get(field_number, [])
    if not values or not isinstance(values[0], bytes):
        return None
    return values[0].decode("utf-8")


def _int_first(fields: dict[int, list[Any]], field_number: int) -> int | None:
    values = fields.get(field_number, [])
    if not values:
        return None
    value = values[0]
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return _int_from_string(value.decode("utf-8"))
    return None


def _int_from_string(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _raw_wrapper(fields: dict[int, list[Any]]) -> dict[str, Any]:
    return {
        "channel": _string_first(fields, _WRAPPER_CHANNEL),
        "symbol": _string_first(fields, _WRAPPER_SYMBOL),
        "symbol_id": _string_first(fields, 4),
        "create_time": _int_first(fields, _WRAPPER_CREATE_TIME),
        "send_time": _int_first(fields, _WRAPPER_SEND_TIME),
    }


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _dec_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return _dec(value)


def _symbol(symbol: str) -> str:
    return normalize_mexc_spot_symbol(symbol)
