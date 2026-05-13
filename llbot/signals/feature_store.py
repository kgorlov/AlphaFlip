"""Rolling quote storage and market-data conversion helpers."""

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from llbot.domain.enums import Venue
from llbot.domain.market_data import BookTicker
from llbot.domain.models import Quote


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    symbol: str
    ts_ms: int
    residual_bps: Decimal | None = None
    impulse_bps: Decimal | None = None
    imbalance: Decimal | None = None
    spread_bps: Decimal | None = None
    volatility_bps: Decimal | None = None
    latency_ms: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class RollingFeatureStore:
    """Bounded in-memory feature store keyed by strategy symbol."""

    def __init__(self, max_samples: int = 2000) -> None:
        self.max_samples = max_samples
        self._features: dict[str, deque[FeatureSnapshot]] = {}

    def add(self, snapshot: FeatureSnapshot) -> None:
        bucket = self._features.setdefault(snapshot.symbol, deque(maxlen=self.max_samples))
        bucket.append(snapshot)

    def latest(self, symbol: str) -> FeatureSnapshot | None:
        bucket = self._features.get(symbol)
        if not bucket:
            return None
        return bucket[-1]

    def samples(self, symbol: str) -> tuple[FeatureSnapshot, ...]:
        return tuple(self._features.get(symbol, ()))


class QuoteWindow:
    """Small in-memory quote window for short-horizon signal calculations."""

    def __init__(self, max_samples: int = 2000) -> None:
        self.max_samples = max_samples
        self._quotes: dict[tuple[Venue, str], deque[Quote]] = {}

    def add(self, quote: Quote) -> None:
        key = (quote.venue, quote.symbol)
        bucket = self._quotes.setdefault(key, deque(maxlen=self.max_samples))
        bucket.append(quote)

    def latest(self, venue: Venue, symbol: str) -> Quote | None:
        bucket = self._quotes.get((venue, symbol))
        if not bucket:
            return None
        return bucket[-1]

    def previous(self, venue: Venue, symbol: str) -> Quote | None:
        bucket = self._quotes.get((venue, symbol))
        if not bucket or len(bucket) < 2:
            return None
        return bucket[-2]

    def at_or_before(self, venue: Venue, symbol: str, ts_ms: int) -> Quote | None:
        bucket = self._quotes.get((venue, symbol))
        if not bucket:
            return None
        for quote in reversed(bucket):
            if quote.local_ts_ms <= ts_ms:
                return quote
        return None

    def samples(self, venue: Venue, symbol: str) -> tuple[Quote, ...]:
        return tuple(self._quotes.get((venue, symbol), ()))


def quote_from_book_ticker(ticker: BookTicker) -> Quote:
    return Quote(
        venue=ticker.venue,
        market=ticker.market,
        symbol=ticker.symbol,
        bid=ticker.bid_price,
        ask=ticker.ask_price,
        bid_size=ticker.bid_qty,
        ask_size=ticker.ask_qty,
        exchange_ts_ms=ticker.timestamp_ms,
        local_ts_ms=ticker.local_ts_ms or ticker.timestamp_ms or 0,
    )


def bps_move(current: Decimal, previous: Decimal) -> Decimal:
    if previous <= 0:
        return Decimal("0")
    return Decimal("10000") * (current - previous) / previous


def mean(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    if not items:
        return Decimal("0")
    return sum(items, Decimal("0")) / Decimal(len(items))


def sample_std(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    if len(items) < 2:
        return Decimal("0")
    avg = mean(items)
    variance = sum(((value - avg) ** 2 for value in items), Decimal("0")) / Decimal(len(items) - 1)
    return variance.sqrt()


def build_feature_snapshot(
    *,
    symbol: str,
    ts_ms: int,
    leader: Quote | None = None,
    lagger: Quote | None = None,
    leader_previous: Quote | None = None,
    lagger_previous: Quote | None = None,
    residual_bps: Decimal | None = None,
    imbalance: Decimal | None = None,
    volatility_bps: Decimal | None = None,
    metadata: dict[str, str] | None = None,
) -> FeatureSnapshot:
    impulse_bps = None
    if leader is not None and leader_previous is not None:
        impulse_bps = bps_move(leader.mid, leader_previous.mid)

    spread_bps = None
    if lagger is not None:
        spread_bps = lagger.spread_bps

    latency_ms = None
    if leader is not None and lagger is not None:
        latency_ms = abs(leader.local_ts_ms - lagger.local_ts_ms)
    elif leader is not None and leader.exchange_ts_ms is not None:
        latency_ms = leader.local_ts_ms - leader.exchange_ts_ms
    elif lagger is not None and lagger.exchange_ts_ms is not None:
        latency_ms = lagger.local_ts_ms - lagger.exchange_ts_ms

    if volatility_bps is None and lagger is not None and lagger_previous is not None:
        volatility_bps = abs(bps_move(lagger.mid, lagger_previous.mid))

    return FeatureSnapshot(
        symbol=symbol,
        ts_ms=ts_ms,
        residual_bps=residual_bps,
        impulse_bps=impulse_bps,
        imbalance=imbalance,
        spread_bps=spread_bps,
        volatility_bps=volatility_bps,
        latency_ms=latency_ms,
        metadata=metadata or {},
    )
