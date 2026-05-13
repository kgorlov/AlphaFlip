"""Monitoring alert evaluation helpers."""

from dataclasses import dataclass, field
from typing import Any

from llbot.domain.models import Quote
from llbot.monitoring.health import ComponentHealth, FeedHealthDecision


@dataclass(frozen=True, slots=True)
class AlertEvent:
    alert_type: str
    severity: str
    reason: str
    symbol: str | None = None
    venue: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_quote_latency(
    quote: Quote,
    max_latency_ms: int,
) -> AlertEvent | None:
    """Alert when local receive timestamp lags the exchange timestamp too much."""

    if quote.exchange_ts_ms is None:
        return None
    latency_ms = quote.local_ts_ms - quote.exchange_ts_ms
    if latency_ms <= max_latency_ms:
        return None
    return AlertEvent(
        alert_type="feed_latency",
        severity="warning",
        reason="feed_latency_above_threshold",
        symbol=quote.symbol,
        venue=quote.venue.value,
        metadata={
            "exchange_ts_ms": quote.exchange_ts_ms,
            "local_ts_ms": quote.local_ts_ms,
            "latency_ms": latency_ms,
            "max_latency_ms": max_latency_ms,
        },
    )


def evaluate_feed_health_alerts(decision: FeedHealthDecision) -> list[AlertEvent]:
    """Convert stale or missing required feed decisions into alert events."""

    alerts = []
    for stream in decision.missing_streams:
        venue, symbol = _split_stream_key(stream)
        alerts.append(
            AlertEvent(
                alert_type="feed_missing",
                severity="critical",
                reason="required_feed_missing",
                symbol=symbol,
                venue=venue,
                metadata={"stream": stream, "feed_health_reason": decision.reason},
            )
        )
    for stream in decision.stale_streams:
        venue, symbol = _split_stream_key(stream)
        alerts.append(
            AlertEvent(
                alert_type="feed_stale",
                severity="critical",
                reason="required_feed_stale",
                symbol=symbol,
                venue=venue,
                metadata={"stream": stream, "feed_health_reason": decision.reason},
            )
        )
    return alerts


def evaluate_component_alerts(component: ComponentHealth) -> list[AlertEvent]:
    """Convert critical component health into alert events."""

    if component.status != "critical":
        return []
    if component.name == "metascalp":
        return [
            AlertEvent(
                alert_type="metascalp_disconnect",
                severity="critical",
                reason=component.reason,
                metadata=dict(component.metadata),
            )
        ]
    if component.name == "risk":
        active_blocks = component.metadata.get("active_blocks", [])
        if not isinstance(active_blocks, list):
            active_blocks = []
        return [
            AlertEvent(
                alert_type="risk_stop",
                severity="critical",
                reason=str(reason),
                metadata=dict(component.metadata),
            )
            for reason in active_blocks
        ]
    return [
        AlertEvent(
            alert_type=f"{component.name}_critical",
            severity="critical",
            reason=component.reason,
            metadata=dict(component.metadata),
        )
    ]


def alert_to_dict(alert: AlertEvent) -> dict[str, Any]:
    return {
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "reason": alert.reason,
        "symbol": alert.symbol,
        "venue": alert.venue,
        "metadata": alert.metadata,
    }


def alerts_to_risk_metadata(alerts: list[AlertEvent]) -> dict[str, object]:
    """Map alerts that should block new positions into PortfolioState metadata."""

    metadata: dict[str, object] = {
        "feed_latency_high": False,
        "binance_feed_stale": False,
        "mexc_feed_stale": False,
        "metascalp_connected": True,
    }
    for alert in alerts:
        if alert.alert_type == "feed_latency":
            metadata["feed_latency_high"] = True
            metadata["feed_latency_reason"] = alert.reason
            metadata["feed_latency_ms"] = alert.metadata.get("latency_ms")
            metadata["feed_latency_symbol"] = alert.symbol
            metadata["feed_latency_venue"] = alert.venue
        elif alert.alert_type in {"feed_missing", "feed_stale"}:
            if alert.venue == "binance":
                metadata["binance_feed_stale"] = True
            elif alert.venue == "mexc":
                metadata["mexc_feed_stale"] = True
        elif alert.alert_type == "metascalp_disconnect":
            metadata["metascalp_connected"] = False
        elif alert.alert_type == "risk_stop":
            metadata[str(alert.reason)] = True
    return metadata


def _split_stream_key(stream: str) -> tuple[str | None, str | None]:
    if ":" not in stream:
        return None, stream
    venue, symbol = stream.split(":", 1)
    return venue, symbol
