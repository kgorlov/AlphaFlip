"""MEXC futures/contract public REST market-data adapter."""

from decimal import Decimal
from typing import Any

from llbot.adapters.http_client import AioHttpJsonClient, JsonHttpClient
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, ExchangeSymbolInfo, OrderBookDepth, Stats24h


class MexcContractRestClient:
    def __init__(self, http: JsonHttpClient | None = None) -> None:
        self.http = http or AioHttpJsonClient("https://contract.mexc.com")

    async def contract_detail(self, symbol: str | None = None) -> list[ExchangeSymbolInfo]:
        path = "/api/v1/contract/detail"
        params = {"symbol": symbol} if symbol else None
        payload = await self.http.get_json(path, params)
        items = _mexc_items(payload)
        return [_parse_contract_detail(item) for item in items]

    async def ticker(self, symbol: str | None = None) -> tuple[dict[str, Stats24h], dict[str, BookTicker]]:
        params = {"symbol": symbol} if symbol else None
        payload = await self.http.get_json("/api/v1/contract/ticker", params)
        items = _mexc_items(payload)
        stats = {_upper(item["symbol"]): _parse_24hr(item) for item in items}
        books = {_upper(item["symbol"]): _parse_book_ticker(item) for item in items}
        return stats, books

    async def depth(self, symbol: str, limit: int = 5) -> OrderBookDepth:
        payload = await self.http.get_json(
            f"/api/v1/contract/depth/{_contract_symbol(symbol)}",
            {"limit": limit},
        )
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        return _parse_depth(_contract_symbol(symbol), data)


def _parse_contract_detail(item: dict[str, Any]) -> ExchangeSymbolInfo:
    state = str(item.get("state", ""))
    return ExchangeSymbolInfo(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=_upper(item.get("symbol", "")),
        status=state,
        base_asset=str(item.get("baseCoin", "")),
        quote_asset=str(item.get("quoteCoin", "")),
        trading_enabled=state == "0",
        api_allowed=bool(item.get("apiAllowed", True)),
        contract_type="PERPETUAL",
        price_tick=_dec_or_none(item.get("priceUnit")),
        qty_step=_dec_or_none(item.get("volUnit")),
        min_qty=_dec_or_none(item.get("minVol")),
        max_qty=_dec_or_none(item.get("maxVol")),
        contract_size=_dec_or_none(item.get("contractSize")),
        maker_fee_rate=_dec_or_none(item.get("makerFeeRate")),
        taker_fee_rate=_dec_or_none(item.get("takerFeeRate")),
        raw=item,
    )


def _parse_24hr(item: dict[str, Any]) -> Stats24h:
    return Stats24h(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=_upper(item.get("symbol", "")),
        quote_volume=_dec(item.get("amount24", "0")),
        base_volume=_dec_or_none(item.get("volume24")),
        last_price=_dec_or_none(item.get("lastPrice")),
        raw=item,
    )


def _parse_book_ticker(item: dict[str, Any]) -> BookTicker:
    return BookTicker(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=_upper(item.get("symbol", "")),
        bid_price=_dec(item.get("bid1", "0")),
        bid_qty=None,
        ask_price=_dec(item.get("ask1", "0")),
        ask_qty=None,
        timestamp_ms=_int_or_none(item.get("timestamp")),
        raw=item,
    )


def _parse_depth(symbol: str, payload: dict[str, Any]) -> OrderBookDepth:
    return OrderBookDepth(
        venue=Venue.MEXC,
        market=MarketType.USDT_PERP,
        symbol=symbol,
        bids=_levels(payload.get("bids", [])),
        asks=_levels(payload.get("asks", [])),
        timestamp_ms=_int_or_none(payload.get("timestamp")),
        raw=payload,
    )


def _levels(raw: list[Any]) -> tuple[DepthLevel, ...]:
    return tuple(DepthLevel(price=_dec(level[0]), qty=_dec(level[1])) for level in raw)


def _mexc_items(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _contract_symbol(symbol: str) -> str:
    symbol = _upper(symbol)
    if "_" not in symbol and symbol.endswith("USDT"):
        return f"{symbol[:-4]}_USDT"
    return symbol


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


def _upper(value: Any) -> str:
    return str(value).upper()

