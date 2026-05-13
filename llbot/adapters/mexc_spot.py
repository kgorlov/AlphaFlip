"""MEXC spot public REST market-data adapter.

MEXC spot WebSocket uses protobuf payloads, so keep protobuf parser code isolated from this
REST adapter when the streaming layer is added.
"""

from decimal import Decimal
from typing import Any

from llbot.adapters.http_client import AioHttpJsonClient, JsonHttpClient
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, ExchangeSymbolInfo, OrderBookDepth, Stats24h


class MexcSpotRestClient:
    def __init__(self, http: JsonHttpClient | None = None) -> None:
        self.http = http or AioHttpJsonClient("https://api.mexc.com")

    async def exchange_info(self) -> list[ExchangeSymbolInfo]:
        payload = await self.http.get_json("/api/v3/exchangeInfo")
        return [_parse_symbol(item) for item in payload.get("symbols", [])]

    async def ticker_24hr(self) -> dict[str, Stats24h]:
        payload = await self.http.get_json("/api/v3/ticker/24hr")
        items = payload if isinstance(payload, list) else [payload]
        return {_upper(item["symbol"]): _parse_24hr(item) for item in items}

    async def book_ticker(self) -> dict[str, BookTicker]:
        payload = await self.http.get_json("/api/v3/ticker/bookTicker")
        items = payload if isinstance(payload, list) else [payload]
        return {_upper(item["symbol"]): _parse_book_ticker(item) for item in items}

    async def depth(self, symbol: str, limit: int = 5) -> OrderBookDepth:
        payload = await self.http.get_json("/api/v3/depth", {"symbol": _upper(symbol), "limit": limit})
        return _parse_depth(_upper(symbol), payload)


def _parse_symbol(item: dict[str, Any]) -> ExchangeSymbolInfo:
    status = str(item.get("status", ""))
    filters = {str(f.get("filterType")): f for f in item.get("filters", []) if isinstance(f, dict)}
    price_filter = filters.get("PRICE_FILTER", {})
    lot_size = filters.get("LOT_SIZE", {})
    min_notional = filters.get("MIN_NOTIONAL", {}) or filters.get("NOTIONAL", {})
    return ExchangeSymbolInfo(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=_upper(item.get("symbol", "")),
        status=status,
        base_asset=str(item.get("baseAsset", "")),
        quote_asset=str(item.get("quoteAsset", "")),
        trading_enabled=status in {"1", "TRADING", "ENABLED"} and bool(
            item.get("isSpotTradingAllowed", True)
        ),
        api_allowed=bool(item.get("apiAllowed", True)),
        price_tick=_dec_or_none(price_filter.get("tickSize")),
        qty_step=_dec_or_none(lot_size.get("stepSize")),
        min_qty=_dec_or_none(lot_size.get("minQty")),
        max_qty=_dec_or_none(lot_size.get("maxQty")),
        min_notional=_dec_or_none(min_notional.get("minNotional") or min_notional.get("notional")),
        raw=item,
    )


def _parse_24hr(item: dict[str, Any]) -> Stats24h:
    return Stats24h(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=_upper(item.get("symbol", "")),
        quote_volume=_dec(item.get("quoteVolume", "0")),
        base_volume=_dec_or_none(item.get("volume")),
        last_price=_dec_or_none(item.get("lastPrice")),
        raw=item,
    )


def _parse_book_ticker(item: dict[str, Any]) -> BookTicker:
    return BookTicker(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=_upper(item.get("symbol", "")),
        bid_price=_dec(item.get("bidPrice", "0")),
        bid_qty=_dec_or_none(item.get("bidQty")),
        ask_price=_dec(item.get("askPrice", "0")),
        ask_qty=_dec_or_none(item.get("askQty")),
        raw=item,
    )


def _parse_depth(symbol: str, payload: dict[str, Any]) -> OrderBookDepth:
    return OrderBookDepth(
        venue=Venue.MEXC,
        market=MarketType.SPOT,
        symbol=symbol,
        bids=_levels(payload.get("bids", [])),
        asks=_levels(payload.get("asks", [])),
        raw=payload,
    )


def _levels(raw: list[Any]) -> tuple[DepthLevel, ...]:
    return tuple(DepthLevel(price=_dec(level[0]), qty=_dec(level[1])) for level in raw)


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _dec_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return _dec(value)


def _upper(value: Any) -> str:
    return str(value).upper()

