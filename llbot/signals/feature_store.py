"""Rolling quote storage and market-data conversion helpers."""

from collections import deque
from decimal import Decimal
from typing import Iterable

from llbot.domain.enums import Venue
from llbot.domain.market_data import BookTicker
from llbot.domain.models import Quote


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
