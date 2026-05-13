"""Normalized public market-data models."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from llbot.domain.enums import MarketType, Venue


@dataclass(frozen=True, slots=True)
class ExchangeSymbolInfo:
    venue: Venue
    market: MarketType
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    trading_enabled: bool
    api_allowed: bool = True
    contract_type: str | None = None
    price_tick: Decimal | None = None
    qty_step: Decimal | None = None
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    min_notional: Decimal | None = None
    contract_size: Decimal | None = None
    maker_fee_rate: Decimal | None = None
    taker_fee_rate: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Stats24h:
    venue: Venue
    market: MarketType
    symbol: str
    quote_volume: Decimal
    base_volume: Decimal | None = None
    last_price: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BookTicker:
    venue: Venue
    market: MarketType
    symbol: str
    bid_price: Decimal
    bid_qty: Decimal | None
    ask_price: Decimal
    ask_qty: Decimal | None
    timestamp_ms: int | None = None
    local_ts_ms: int | None = None
    receive_monotonic_ns: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def mid(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        if self.mid <= 0:
            return Decimal("Infinity")
        return Decimal("10000") * (self.ask_price - self.bid_price) / self.mid


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: Decimal
    qty: Decimal


@dataclass(frozen=True, slots=True)
class OrderBookDepth:
    venue: Venue
    market: MarketType
    symbol: str
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    timestamp_ms: int | None = None
    local_ts_ms: int | None = None
    receive_monotonic_ns: int | None = None
    version: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def top_depth_usd(self, levels: int = 5, contract_size: Decimal | None = None) -> Decimal:
        size_multiplier = contract_size or Decimal("1")
        bid_depth = sum(
            (level.price * level.qty * size_multiplier for level in self.bids[:levels]),
            Decimal("0"),
        )
        ask_depth = sum(
            (level.price * level.qty * size_multiplier for level in self.asks[:levels]),
            Decimal("0"),
        )
        return min(bid_depth, ask_depth)


@dataclass(frozen=True, slots=True)
class ReceiveTimestamp:
    local_ts_ms: int
    monotonic_ns: int

