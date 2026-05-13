"""Binance USD-M futures public REST market-data adapter."""

from typing import Any

from llbot.adapters.binance_spot import (
    _dec_or_none,
    _filters_by_type,
    _parse_24hr,
    _parse_book_ticker,
    _parse_depth,
    _upper,
)
from llbot.adapters.http_client import AioHttpJsonClient, JsonHttpClient
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, ExchangeSymbolInfo, OrderBookDepth, Stats24h


class BinanceUsdmRestClient:
    def __init__(self, http: JsonHttpClient | None = None) -> None:
        self.http = http or AioHttpJsonClient("https://fapi.binance.com")

    async def exchange_info(self) -> list[ExchangeSymbolInfo]:
        payload = await self.http.get_json("/fapi/v1/exchangeInfo")
        return [_parse_usdm_symbol(item) for item in payload.get("symbols", [])]

    async def ticker_24hr(self) -> dict[str, Stats24h]:
        payload = await self.http.get_json("/fapi/v1/ticker/24hr")
        items = payload if isinstance(payload, list) else [payload]
        return {_upper(item["symbol"]): _parse_24hr(item, MarketType.USDT_PERP) for item in items}

    async def book_ticker(self) -> dict[str, BookTicker]:
        payload = await self.http.get_json("/fapi/v1/ticker/bookTicker")
        items = payload if isinstance(payload, list) else [payload]
        return {_upper(item["symbol"]): _parse_book_ticker(item, MarketType.USDT_PERP) for item in items}

    async def depth(self, symbol: str, limit: int = 5) -> OrderBookDepth:
        payload = await self.http.get_json("/fapi/v1/depth", {"symbol": _upper(symbol), "limit": limit})
        return _parse_depth(_upper(symbol), payload, MarketType.USDT_PERP)


def _parse_usdm_symbol(item: dict[str, Any]) -> ExchangeSymbolInfo:
    filters = _filters_by_type(item)
    price_filter = filters.get("PRICE_FILTER", {})
    lot_size = filters.get("LOT_SIZE", {})
    min_notional = filters.get("MIN_NOTIONAL", {})
    status = str(item.get("status", ""))
    return ExchangeSymbolInfo(
        venue=Venue.BINANCE,
        market=MarketType.USDT_PERP,
        symbol=_upper(item.get("symbol", "")),
        status=status,
        base_asset=str(item.get("baseAsset", "")),
        quote_asset=str(item.get("quoteAsset", "")),
        trading_enabled=status == "TRADING"
        and str(item.get("contractType", "")) == "PERPETUAL"
        and str(item.get("quoteAsset", "")) == "USDT",
        api_allowed=True,
        contract_type=str(item.get("contractType", "")),
        price_tick=_dec_or_none(price_filter.get("tickSize")),
        qty_step=_dec_or_none(lot_size.get("stepSize")),
        min_qty=_dec_or_none(lot_size.get("minQty")),
        max_qty=_dec_or_none(lot_size.get("maxQty")),
        min_notional=_dec_or_none(min_notional.get("notional")),
        raw=item,
    )

