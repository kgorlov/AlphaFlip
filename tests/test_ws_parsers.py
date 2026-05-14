from decimal import Decimal
from unittest import TestCase

from llbot.adapters.binance_ws import (
    aggregate_trade_stream_name,
    combined_book_ticker_url,
    combined_stream_url,
    parse_agg_trade_message,
    parse_book_ticker_message,
    parse_depth_message,
    partial_depth_stream_name,
)
from llbot.adapters.mexc_contract_ws import (
    parse_message,
    subscribe_depth,
    subscribe_ticker,
)
from llbot.adapters.mexc_spot_ws import (
    parse_message as parse_mexc_spot_message,
    subscribe_book_ticker as subscribe_mexc_spot_book_ticker,
    subscribe_depth as subscribe_mexc_spot_depth,
    subscribe_limit_depth as subscribe_mexc_spot_limit_depth,
)
from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker, OrderBookDepth, ReceiveTimestamp
from llbot.domain.models import Trade


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

    def test_binance_trade_and_depth_stream_specs(self) -> None:
        streams = (
            aggregate_trade_stream_name("BTCUSDT"),
            partial_depth_stream_name("BTCUSDT", levels=5, speed_ms=100),
        )
        spec = combined_stream_url(streams, MarketType.USDT_PERP)

        self.assertEqual(streams, ("btcusdt@aggTrade", "btcusdt@depth5@100ms"))
        self.assertIn("btcusdt@aggTrade/btcusdt@depth5@100ms", spec.url)

    def test_binance_aggregate_trade_parser(self) -> None:
        parsed = parse_agg_trade_message(
            {
                "stream": "btcusdt@aggTrade",
                "data": {
                    "e": "aggTrade",
                    "E": 1001,
                    "T": 1000,
                    "s": "BTCUSDT",
                    "a": 42,
                    "p": "100.1",
                    "q": "0.5",
                    "m": False,
                },
            },
            MarketType.USDT_PERP,
            ReceiveTimestamp(local_ts_ms=1100, monotonic_ns=222),
        )

        self.assertIsInstance(parsed, Trade)
        assert isinstance(parsed, Trade)
        self.assertEqual(parsed.symbol, "BTCUSDT")
        self.assertEqual(parsed.price, Decimal("100.1"))
        self.assertEqual(parsed.qty, Decimal("0.5"))
        self.assertEqual(parsed.side.value, "buy")
        self.assertEqual(parsed.trade_id, "42")

    def test_binance_depth_parser(self) -> None:
        parsed = parse_depth_message(
            {
                "stream": "btcusdt@depth5@100ms",
                "data": {
                    "e": "depthUpdate",
                    "E": 1001,
                    "T": 1000,
                    "s": "BTCUSDT",
                    "u": 10,
                    "b": [["100", "2"]],
                    "a": [["101", "3"]],
                },
            },
            MarketType.USDT_PERP,
            ReceiveTimestamp(local_ts_ms=1100, monotonic_ns=222),
        )

        self.assertIsInstance(parsed, OrderBookDepth)
        assert isinstance(parsed, OrderBookDepth)
        self.assertEqual(parsed.venue, Venue.BINANCE)
        self.assertEqual(parsed.symbol, "BTCUSDT")
        self.assertEqual(parsed.version, 10)
        self.assertEqual(parsed.bids[0].qty, Decimal("2"))

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

    def test_mexc_spot_subscriptions(self) -> None:
        self.assertEqual(
            subscribe_mexc_spot_book_ticker("btcusdt").message,
            {
                "method": "SUBSCRIPTION",
                "params": ["spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"],
            },
        )
        self.assertEqual(
            subscribe_mexc_spot_depth("BTCUSDT", speed_ms=10).message,
            {
                "method": "SUBSCRIPTION",
                "params": ["spot@public.aggre.depth.v3.api.pb@10ms@BTCUSDT"],
            },
        )
        self.assertEqual(
            subscribe_mexc_spot_limit_depth("BTCUSDT", levels=5).message,
            {
                "method": "SUBSCRIPTION",
                "params": ["spot@public.limit.depth.v3.api.pb@BTCUSDT@5"],
            },
        )

    def test_mexc_spot_book_ticker_protobuf_parser(self) -> None:
        book_ticker = _pb_message(
            [
                _pb_string(1, "93387.28"),
                _pb_string(2, "3.73485"),
                _pb_string(3, "93387.29"),
                _pb_string(4, "7.669875"),
            ]
        )
        wrapper = _pb_message(
            [
                _pb_string(1, "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"),
                _pb_string(3, "BTCUSDT"),
                _pb_varint(6, 1736412092433),
                _pb_bytes(315, book_ticker),
            ]
        )

        parsed = parse_mexc_spot_message(
            wrapper,
            ReceiveTimestamp(local_ts_ms=1736412092500, monotonic_ns=999),
        )

        self.assertIsInstance(parsed, BookTicker)
        assert isinstance(parsed, BookTicker)
        self.assertEqual(parsed.venue, Venue.MEXC)
        self.assertEqual(parsed.market, MarketType.SPOT)
        self.assertEqual(parsed.symbol, "BTCUSDT")
        self.assertEqual(parsed.bid_price, Decimal("93387.28"))
        self.assertEqual(parsed.bid_qty, Decimal("3.73485"))
        self.assertEqual(parsed.ask_price, Decimal("93387.29"))
        self.assertEqual(parsed.ask_qty, Decimal("7.669875"))
        self.assertEqual(parsed.timestamp_ms, 1736412092433)
        self.assertEqual(parsed.local_ts_ms, 1736412092500)

    def test_mexc_spot_limit_depth_protobuf_parser(self) -> None:
        depth = _pb_message(
            [
                _pb_bytes(1, _depth_level("93180.18", "0.21976424")),
                _pb_bytes(2, _depth_level("93179.98", "2.82651000")),
                _pb_string(3, "spot@public.limit.depth.v3.api.pb"),
                _pb_string(4, "36913565463"),
            ]
        )
        wrapper = _pb_message(
            [
                _pb_string(1, "spot@public.limit.depth.v3.api.pb@BTCUSDT@5"),
                _pb_string(3, "BTCUSDT"),
                _pb_varint(6, 1736411838730),
                _pb_bytes(303, depth),
            ]
        )

        parsed = parse_mexc_spot_message(wrapper, ReceiveTimestamp(local_ts_ms=130, monotonic_ns=456))

        self.assertIsInstance(parsed, OrderBookDepth)
        assert isinstance(parsed, OrderBookDepth)
        self.assertEqual(parsed.venue, Venue.MEXC)
        self.assertEqual(parsed.market, MarketType.SPOT)
        self.assertEqual(parsed.symbol, "BTCUSDT")
        self.assertEqual(parsed.version, 36913565463)
        self.assertEqual(parsed.bids[0].price, Decimal("93179.98"))
        self.assertEqual(parsed.asks[0].qty, Decimal("0.21976424"))

    def test_mexc_spot_aggregated_depth_protobuf_parser(self) -> None:
        depth = _pb_message(
            [
                _pb_bytes(2, _depth_level("92877.58", "0.00000000")),
                _pb_string(3, "spot@public.aggre.depth.v3.api.pb@100ms"),
                _pb_string(4, "10589632359"),
                _pb_string(5, "10589632360"),
            ]
        )
        wrapper = _pb_message(
            [
                _pb_string(1, "spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT"),
                _pb_string(3, "BTCUSDT"),
                _pb_varint(6, 1736411507002),
                _pb_bytes(313, depth),
            ]
        )

        parsed = parse_mexc_spot_message(wrapper)

        self.assertIsInstance(parsed, OrderBookDepth)
        assert isinstance(parsed, OrderBookDepth)
        self.assertEqual(parsed.version, 10589632360)
        self.assertEqual(parsed.bids[0].price, Decimal("92877.58"))
        self.assertEqual(parsed.bids[0].qty, Decimal("0.00000000"))


def _depth_level(price: str, qty: str) -> bytes:
    return _pb_message([_pb_string(1, price), _pb_string(2, qty)])


def _pb_message(fields: list[bytes]) -> bytes:
    return b"".join(fields)


def _pb_string(field_number: int, value: str) -> bytes:
    return _pb_bytes(field_number, value.encode("utf-8"))


def _pb_bytes(field_number: int, value: bytes) -> bytes:
    return _pb_key(field_number, 2) + _pb_varint_value(len(value)) + value


def _pb_varint(field_number: int, value: int) -> bytes:
    return _pb_key(field_number, 0) + _pb_varint_value(value)


def _pb_key(field_number: int, wire_type: int) -> bytes:
    return _pb_varint_value((field_number << 3) | wire_type)


def _pb_varint_value(value: int) -> bytes:
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)
