"""Reusable public WebSocket runtime helpers."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from llbot.adapters.binance_ws import BinanceStreamSpec, combined_stream_url
from llbot.domain.enums import MarketType


@dataclass(frozen=True, slots=True)
class WebSocketRuntimeConfig:
    max_streams_per_connection: int = 100
    reconnect_after_sec: int = 23 * 60 * 60
    ping_interval_sec: float | None = 20.0
    ping_timeout_sec: float | None = 60.0


@dataclass(frozen=True, slots=True)
class WebSocketShard:
    shard_id: int
    streams: tuple[str, ...]


def shard_streams(streams: Iterable[str], max_streams_per_connection: int) -> tuple[WebSocketShard, ...]:
    if max_streams_per_connection <= 0:
        raise ValueError("max_streams_per_connection must be positive")
    stream_tuple = tuple(streams)
    if not stream_tuple:
        raise ValueError("At least one stream is required")
    return tuple(
        WebSocketShard(shard_id=index, streams=stream_tuple[start : start + max_streams_per_connection])
        for index, start in enumerate(range(0, len(stream_tuple), max_streams_per_connection))
    )


def build_symbol_stream_shards(
    symbols: Iterable[str],
    stream_name_builder: Callable[[str], str],
    max_streams_per_connection: int,
) -> tuple[WebSocketShard, ...]:
    streams = tuple(stream_name_builder(symbol) for symbol in symbols)
    return shard_streams(streams, max_streams_per_connection)


def build_binance_stream_specs(
    shards: Iterable[WebSocketShard],
    market: MarketType,
    reconnect_after_sec: int = 23 * 60 * 60,
    time_unit_microsecond: bool = False,
) -> tuple[BinanceStreamSpec, ...]:
    specs: list[BinanceStreamSpec] = []
    for shard in shards:
        spec = combined_stream_url(shard.streams, market, time_unit_microsecond=time_unit_microsecond)
        specs.append(
            BinanceStreamSpec(
                url=spec.url,
                streams=spec.streams,
                reconnect_after_sec=reconnect_after_sec,
            )
        )
    if not specs:
        raise ValueError("At least one shard is required")
    return tuple(specs)


def should_reconnect(
    opened_monotonic_sec: float,
    now_monotonic_sec: float,
    reconnect_after_sec: float,
) -> bool:
    if reconnect_after_sec <= 0:
        raise ValueError("reconnect_after_sec must be positive")
    return now_monotonic_sec - opened_monotonic_sec >= reconnect_after_sec


def keepalive_kwargs(config: WebSocketRuntimeConfig) -> dict[str, float | None]:
    return {
        "ping_interval": config.ping_interval_sec,
        "ping_timeout": config.ping_timeout_sec,
    }
