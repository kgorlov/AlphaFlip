import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from llbot.domain.enums import MarketType, Side, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, OrderBookDepth
from llbot.domain.models import Trade
from llbot.storage.replay_jsonl import (
    JsonlReplayWriter,
    read_replay_events,
    replay_event_from_book_ticker,
    replay_event_from_depth,
    replay_event_from_trade,
    trade_from_replay_event,
)


class ReplayJsonlTests(TestCase):
    def test_write_and_read_book_ticker_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            writer = JsonlReplayWriter(path)
            writer.append(
                replay_event_from_book_ticker(
                    BookTicker(
                        venue=Venue.BINANCE,
                        market=MarketType.USDT_PERP,
                        symbol="BTCUSDT",
                        bid_price=Decimal("100"),
                        bid_qty=Decimal("2"),
                        ask_price=Decimal("101"),
                        ask_qty=Decimal("3"),
                        timestamp_ms=10,
                        local_ts_ms=11,
                        receive_monotonic_ns=12,
                        raw={"s": "BTCUSDT"},
                    )
                )
            )

            events = read_replay_events(path)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "book_ticker")
            self.assertEqual(events[0].payload["bid_price"], "100")

    def test_write_depth_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            writer = JsonlReplayWriter(path)
            writer.append(
                replay_event_from_depth(
                    OrderBookDepth(
                        venue=Venue.MEXC,
                        market=MarketType.USDT_PERP,
                        symbol="BTC_USDT",
                        bids=(DepthLevel(Decimal("100"), Decimal("1")),),
                        asks=(DepthLevel(Decimal("101"), Decimal("2")),),
                        timestamp_ms=10,
                        local_ts_ms=11,
                        receive_monotonic_ns=12,
                        version=5,
                        raw={"channel": "push.depth"},
                    )
                )
            )

            events = read_replay_events(path)

            self.assertEqual(events[0].event_type, "orderbook_depth")
            self.assertEqual(events[0].payload["version"], 5)
            self.assertEqual(events[0].payload["asks"], [["101", "2"]])

    def test_write_and_read_trade_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            writer = JsonlReplayWriter(path)
            writer.append(
                replay_event_from_trade(
                    Trade(
                        venue=Venue.BINANCE,
                        market=MarketType.USDT_PERP,
                        symbol="BTCUSDT",
                        price=Decimal("100.5"),
                        qty=Decimal("0.3"),
                        side=Side.BUY,
                        exchange_ts_ms=10,
                        local_ts_ms=11,
                        trade_id="42",
                    )
                )
            )

            event = read_replay_events(path)[0]
            trade = trade_from_replay_event(event)

        self.assertEqual(event.event_type, "trade")
        self.assertEqual(trade.price, Decimal("100.5"))
        self.assertEqual(trade.side, Side.BUY)
