"""Monitoring alert evaluation helpers."""

from dataclasses import dataclass, field
from typing import Any

from llbot.domain.models import Quote


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


def alerts_to_risk_metadata(alerts: list[AlertEvent]) -> dict[str, object]:
    """Map alerts that should block new positions into PortfolioState metadata."""

    metadata: dict[str, object] = {"feed_latency_high": False}
    for alert in alerts:
        if alert.alert_type == "feed_latency":
            metadata["feed_latency_high"] = True
            metadata["feed_latency_reason"] = alert.reason
            metadata["feed_latency_ms"] = alert.metadata.get("latency_ms")
            metadata["feed_latency_symbol"] = alert.symbol
            metadata["feed_latency_venue"] = alert.venue
    return metadata
