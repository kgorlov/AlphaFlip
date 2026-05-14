"""Reusable feed-health gates for replay, paper, and live runners."""

from dataclasses import dataclass
from typing import Any

from llbot.adapters.metascalp import MetaScalpConnection, MetaScalpInstance
from llbot.domain.models import PortfolioState, SymbolProfile


HEALTH_OK = "ok"
HEALTH_WARN = "warn"
HEALTH_CRITICAL = "critical"
HEALTH_UNKNOWN = "unknown"

RISK_HEALTH_BLOCKS = {
    "kill_switch": "manual_kill_switch",
    "binance_feed_stale": "binance_feed_stale",
    "mexc_feed_stale": "mexc_feed_stale",
    "feed_latency_high": "feed_latency_high",
    "reconnect_storm": "reconnect_storm",
    "book_desync": "book_desync",
    "abnormal_cancel_ratio": "abnormal_cancel_ratio",
    "repeated_order_errors": "repeated_order_errors",
    "high_slippage": "high_slippage",
    "position_mismatch": "position_mismatch",
    "balance_mismatch": "balance_mismatch",
    "metascalp_connected": "metascalp_disconnected",
}


@dataclass(frozen=True, slots=True)
class FeedStreamState:
    venue: str
    symbol: str
    event_count: int
    first_ts_ms: int
    last_ts_ms: int
    max_gap_ms: int = 0
    stale_gap_count: int = 0


@dataclass(frozen=True, slots=True)
class FeedHealthDecision:
    healthy: bool
    reason: str
    stale_streams: tuple[str, ...] = ()
    missing_streams: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    name: str
    status: str
    reason: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SystemHealth:
    status: str
    components: tuple[ComponentHealth, ...]


def update_feed_stream_state(
    state: FeedStreamState | None,
    venue: str,
    symbol: str,
    ts_ms: int,
    stale_gap_ms: int | None = None,
) -> FeedStreamState:
    if state is None:
        return FeedStreamState(
            venue=venue,
            symbol=symbol,
            event_count=1,
            first_ts_ms=ts_ms,
            last_ts_ms=ts_ms,
        )

    gap_ms = max(0, ts_ms - state.last_ts_ms)
    stale_gap_count = state.stale_gap_count
    if stale_gap_ms is not None and gap_ms > stale_gap_ms:
        stale_gap_count += 1

    return FeedStreamState(
        venue=state.venue,
        symbol=state.symbol,
        event_count=state.event_count + 1,
        first_ts_ms=state.first_ts_ms,
        last_ts_ms=ts_ms,
        max_gap_ms=max(state.max_gap_ms, gap_ms),
        stale_gap_count=stale_gap_count,
    )


def evaluate_feed_health(
    streams: dict[str, FeedStreamState],
    required_streams: tuple[str, ...],
    now_ts_ms: int,
    stale_after_ms: int,
) -> FeedHealthDecision:
    missing = tuple(key for key in required_streams if key not in streams)
    if missing:
        return FeedHealthDecision(False, "missing_stream", missing_streams=missing)

    stale = tuple(
        key
        for key in required_streams
        if now_ts_ms - streams[key].last_ts_ms > stale_after_ms
    )
    if stale:
        return FeedHealthDecision(False, "stale_stream", stale_streams=stale)

    return FeedHealthDecision(True, "ok")


def required_profile_streams(profile: SymbolProfile) -> tuple[str, str]:
    """Return required venue/symbol feed keys for one strategy profile."""

    return (
        feed_stream_key(profile.leader_venue.value, profile.leader_symbol),
        feed_stream_key(profile.lagger_venue.value, profile.lagger_symbol),
    )


def evaluate_profile_feed_health(
    streams: dict[str, FeedStreamState],
    profile: SymbolProfile,
    now_ts_ms: int,
    stale_after_ms: int,
) -> FeedHealthDecision:
    """Evaluate per-symbol, per-venue freshness for a strategy profile."""

    return evaluate_feed_health(
        streams,
        required_profile_streams(profile),
        now_ts_ms,
        stale_after_ms,
    )


def feed_health_metadata(decision: FeedHealthDecision) -> dict[str, object]:
    metadata: dict[str, object] = {
        "binance_feed_stale": False,
        "mexc_feed_stale": False,
        "feed_health_reason": decision.reason,
        "feed_health_stale_streams": list(decision.stale_streams),
        "feed_health_missing_streams": list(decision.missing_streams),
    }
    for stream_key in (*decision.stale_streams, *decision.missing_streams):
        venue = stream_key.split(":", 1)[0]
        if venue == "binance":
            metadata["binance_feed_stale"] = True
        elif venue == "mexc":
            metadata["mexc_feed_stale"] = True
    return metadata


def feed_component_health(
    decision: FeedHealthDecision,
    *,
    component_name: str = "data_feeds",
) -> ComponentHealth:
    return ComponentHealth(
        name=component_name,
        status=HEALTH_OK if decision.healthy else HEALTH_CRITICAL,
        reason=decision.reason,
        metadata={
            "stale_streams": list(decision.stale_streams),
            "missing_streams": list(decision.missing_streams),
        },
    )


def metascalp_component_health(
    instance: MetaScalpInstance | None,
    connection: MetaScalpConnection | None,
    *,
    require_demo_mode: bool = True,
    require_connected: bool = True,
) -> ComponentHealth:
    if instance is None:
        return ComponentHealth(
            name="metascalp",
            status=HEALTH_CRITICAL,
            reason="metascalp_not_found",
            metadata={},
        )
    if connection is None:
        if not require_connected and not require_demo_mode:
            return ComponentHealth(
                name="metascalp",
                status=HEALTH_OK,
                reason="metascalp_found",
                metadata={"base_url": instance.base_url, "ping": instance.ping},
            )
        return ComponentHealth(
            name="metascalp",
            status=HEALTH_CRITICAL,
            reason="metascalp_connection_not_found",
            metadata={"base_url": instance.base_url},
        )
    if require_connected and not connection.connected:
        return ComponentHealth(
            name="metascalp",
            status=HEALTH_CRITICAL,
            reason="metascalp_disconnected",
            metadata=_metascalp_metadata(instance, connection),
        )
    if require_demo_mode and not connection.demo_mode:
        return ComponentHealth(
            name="metascalp",
            status=HEALTH_CRITICAL,
            reason="metascalp_not_demo_mode",
            metadata=_metascalp_metadata(instance, connection),
        )
    return ComponentHealth(
        name="metascalp",
        status=HEALTH_OK,
        reason="ok",
        metadata=_metascalp_metadata(instance, connection),
    )


def storage_component_health(
    table_counts: dict[str, int] | None,
    *,
    error: str | None = None,
    component_name: str = "storage",
) -> ComponentHealth:
    if error is not None:
        return ComponentHealth(
            name=component_name,
            status=HEALTH_CRITICAL,
            reason="storage_probe_failed",
            metadata={"error": error},
        )
    if table_counts is None:
        return ComponentHealth(
            name=component_name,
            status=HEALTH_UNKNOWN,
            reason="storage_not_checked",
            metadata={},
        )
    return ComponentHealth(
        name=component_name,
        status=HEALTH_OK,
        reason="ok",
        metadata={"table_counts": dict(table_counts)},
    )


def risk_component_health(state: PortfolioState) -> ComponentHealth:
    active_blocks = []
    for key, reason in RISK_HEALTH_BLOCKS.items():
        value = state.metadata.get(key)
        if key == "metascalp_connected":
            blocked = value is False
        else:
            blocked = bool(value)
        if blocked:
            active_blocks.append(reason)

    if active_blocks:
        return ComponentHealth(
            name="risk",
            status=HEALTH_CRITICAL,
            reason="risk_block_active",
            metadata={
                "active_blocks": active_blocks,
                "open_positions": state.open_positions,
                "daily_pnl_usd": str(state.daily_pnl_usd),
                "total_notional_usd": str(state.total_notional_usd),
            },
        )
    return ComponentHealth(
        name="risk",
        status=HEALTH_OK,
        reason="ok",
        metadata={
            "open_positions": state.open_positions,
            "daily_pnl_usd": str(state.daily_pnl_usd),
            "total_notional_usd": str(state.total_notional_usd),
        },
    )


def build_system_health(components: list[ComponentHealth] | tuple[ComponentHealth, ...]) -> SystemHealth:
    component_tuple = tuple(components)
    statuses = {component.status for component in component_tuple}
    if HEALTH_CRITICAL in statuses:
        status = HEALTH_CRITICAL
    elif HEALTH_WARN in statuses:
        status = HEALTH_WARN
    elif HEALTH_UNKNOWN in statuses:
        status = HEALTH_UNKNOWN
    else:
        status = HEALTH_OK
    return SystemHealth(status=status, components=component_tuple)


def component_health_to_dict(component: ComponentHealth) -> dict[str, Any]:
    return {
        "name": component.name,
        "status": component.status,
        "reason": component.reason,
        "metadata": component.metadata,
    }


def system_health_to_dict(health: SystemHealth) -> dict[str, Any]:
    return {
        "status": health.status,
        "components": [component_health_to_dict(component) for component in health.components],
    }


def feed_stream_key(venue: str, symbol: str) -> str:
    return f"{venue}:{symbol}"


def feed_stream_state_to_dict(state: FeedStreamState) -> dict[str, object]:
    return {
        "venue": state.venue,
        "symbol": state.symbol,
        "book_ticker_events": state.event_count,
        "first_ts_ms": state.first_ts_ms,
        "last_ts_ms": state.last_ts_ms,
        "max_gap_ms": state.max_gap_ms,
        "stale_gap_count": state.stale_gap_count,
    }


def _metascalp_metadata(
    instance: MetaScalpInstance,
    connection: MetaScalpConnection,
) -> dict[str, Any]:
    return {
        "base_url": instance.base_url,
        "connection_id": connection.id,
        "connection_name": connection.name,
        "exchange": connection.exchange,
        "market": connection.market,
        "state": connection.state,
        "connected": connection.connected,
        "demo_mode": connection.demo_mode,
    }
