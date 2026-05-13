from decimal import Decimal
from unittest import TestCase

from llbot.adapters.binance_ws import combined_book_ticker_url, parse_book_ticker_message
from llbot.adapters.mexc_contract_ws import (
    parse_message,
    subscribe_depth,
    subscribe_ticker,
)
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, OrderBookDepth, ReceiveTimestamp


class WebSocketParserTests(TestCase):
    def test_binance_usdm_combined_book_ticker_parser(self) -> None:
        message = {
            "stream": "btcusdt@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 1,
                "E": 1001,
                "T": 1000,
                "s": "BTCUSDT",
                "b": "100.1",
                "B": "2",
                "a": "100.2",
                "A": "3",
            },
        }

        ticker = parse_book_ticker_message(
            message,
            MarketType.USDT_PERP,
            ReceiveTimestamp(local_ts_ms=1100, monotonic_ns=222),
        )

        self.assertIsNotNone(ticker)
        assert ticker is not None
        self.assertEqual(ticker.venue, Venue.BINANCE)
        self.assertEqual(ticker.symbol, "BTCUSDT")
        self.assertEqual(ticker.bid_price, Decimal("100.1"))
        self.assertEqual(ticker.ask_qty, Decimal("3"))
        self.assertEqual(ticker.timestamp_ms, 1000)
        self.assertEqual(ticker.local_ts_ms, 1100)

    def test_binance_stream_spec(self) -> None:
        spec = combined_book_ticker_url(["BTCUSDT", "ETHUSDT"], MarketType.USDT_PERP)

        self.assertIn("wss://fstream.binance.com/stream?streams=", spec.url)
        self.assertEqual(spec.streams, ("btcusdt@bookTicker", "ethusdt@bookTicker"))

    def test_mexc_subscriptions(self) -> None:
        self.assertEqual(
            subscribe_ticker("BTCUSDT").message,
            {"method": "sub.ticker", "param": {"symbol": "BTC_USDT"}},
        )
        self.assertEqual(
            subscribe_depth("BTC_USDT").message,
            {"method": "sub.depth", "param": {"symbol": "BTC_USDT"}},
        )

    def test_mexc_ticker_parser(self) -> None:
        parsed = parse_message(
            {
                "channel": "push.ticker",
                "data": {
                    "symbol": "BTC_USDT",
                    "bid1": 100,
                    "ask1": 101,
                    "timestamp": 123,
                },
                "symbol": "BTC_USDT",
            },
            ReceiveTimestamp(local_ts_ms=130, monotonic_ns=456),
        )

        self.assertIsInstance(parsed, BookTicker)
        assert isinstance(parsed, BookTicker)
        self.assertEqual(parsed.venue, Venue.MEXC)
        self.assertEqual(parsed.symbol, "BTC_USDT")
        self.assertEqual(parsed.ask_price, Decimal("101"))
        self.assertEqual(parsed.local_ts_ms, 130)

    def test_mexc_depth_parser(self) -> None:
        parsed = parse_message(
            {
                "channel": "push.depth",
                "data": {"asks": [[101, 10, 1]], "bids": [[100, 20, 1]], "version": 7},
                "symbol": "BTC_USDT",
                "ts": 123,
            },
            ReceiveTimestamp(local_ts_ms=130, monotonic_ns=456),
        )

        self.assertIsInstance(parsed, OrderBookDepth)
        assert isinstance(parsed, OrderBookDepth)
        self.assertEqual(parsed.version, 7)
        self.assertEqual(parsed.bids[0].price, Decimal("100"))
        self.assertEqual(parsed.asks[0].qty, Decimal("10"))

