from unittest import TestCase

from llbot.adapters.binance_ws import book_ticker_stream_name
from llbot.domain.enums import MarketType
from llbot.service.ws_runtime import (
    WebSocketRuntimeConfig,
    build_binance_stream_specs,
    build_symbol_stream_shards,
    keepalive_kwargs,
    shard_streams,
    should_reconnect,
)


class WebSocketRuntimeTests(TestCase):
    def test_shard_streams_splits_deterministically(self) -> None:
        shards = shard_streams(("a", "b", "c", "d", "e"), max_streams_per_connection=2)

        self.assertEqual([shard.shard_id for shard in shards], [0, 1, 2])
        self.assertEqual([shard.streams for shard in shards], [("a", "b"), ("c", "d"), ("e",)])

    def test_shard_streams_rejects_invalid_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            shard_streams(("a",), max_streams_per_connection=0)

        with self.assertRaisesRegex(ValueError, "At least one stream"):
            shard_streams((), max_streams_per_connection=10)

    def test_build_symbol_stream_shards_uses_builder(self) -> None:
        shards = build_symbol_stream_shards(
            ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            book_ticker_stream_name,
            max_streams_per_connection=2,
        )

        self.assertEqual(shards[0].streams, ("btcusdt@bookTicker", "ethusdt@bookTicker"))
        self.assertEqual(shards[1].streams, ("solusdt@bookTicker",))

    def test_build_binance_stream_specs_per_shard(self) -> None:
        shards = build_symbol_stream_shards(
            ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
            book_ticker_stream_name,
            max_streams_per_connection=2,
        )

        specs = build_binance_stream_specs(
            shards,
            MarketType.USDT_PERP,
            reconnect_after_sec=3600,
        )

        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].streams, ("btcusdt@bookTicker", "ethusdt@bookTicker"))
        self.assertEqual(specs[0].reconnect_after_sec, 3600)
        self.assertIn("wss://fstream.binance.com/stream?streams=btcusdt@bookTicker", specs[0].url)

    def test_should_reconnect_uses_configured_age(self) -> None:
        self.assertFalse(should_reconnect(100.0, 199.9, 100.0))
        self.assertTrue(should_reconnect(100.0, 200.0, 100.0))

        with self.assertRaisesRegex(ValueError, "positive"):
            should_reconnect(100.0, 200.0, 0)

    def test_keepalive_kwargs_exposes_ping_settings(self) -> None:
        config = WebSocketRuntimeConfig(ping_interval_sec=15.0, ping_timeout_sec=45.0)

        self.assertEqual(
            keepalive_kwargs(config),
            {"ping_interval": 15.0, "ping_timeout": 45.0},
        )
