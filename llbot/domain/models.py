"""Core domain models used across adapters, signals, execution, and risk."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, Side, Venue


@dataclass(frozen=True, slots=True)
class SymbolProfile:
    canonical_symbol: str
    leader_symbol: str
    lagger_symbol: str
    profile: MarketProfileName
    leader_venue: Venue
    lagger_venue: Venue
    leader_market: MarketType
    lagger_market: MarketType
    min_qty: Decimal | None = None
    qty_step: Decimal | None = None
    price_tick: Decimal | None = None
    min_notional_usd: Decimal | None = None
    contract_size: Decimal | None = None
    maker_fee_bps: Decimal | None = None
    taker_fee_bps: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Quote:
    venue: Venue
    market: MarketType
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal | None
    ask_size: Decimal | None
    exchange_ts_ms: int | None
    local_ts_ms: int

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        return Decimal("10000") * (self.ask - self.bid) / self.mid


@dataclass(frozen=True, slots=True)
class Trade:
    venue: Venue
    market: MarketType
    symbol: str
    price: Decimal
    qty: Decimal
    side: Side | None
    exchange_ts_ms: int | None
    local_ts_ms: int
    trade_id: str | None = None


@dataclass(frozen=True, slots=True)
class Intent:
    intent_id: str
    symbol: str
    profile: MarketProfileName
    intent_type: IntentType
    side: Side
    qty: Decimal
    price_cap: Decimal
    ttl_ms: int
    order_style: OrderStyle
    confidence: Decimal
    expected_edge_bps: Decimal
    created_ts_ms: int
    features: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionAck:
    intent_id: str
    accepted: bool
    venue_order_id: str | None
    client_order_id: str | None
    execution_time_ms: int | None
    message: str = ""


@dataclass(frozen=True, slots=True)
class PortfolioState:
    open_positions: int
    total_notional_usd: Decimal
    daily_pnl_usd: Decimal
    per_symbol_notional_usd: dict[str, Decimal] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

