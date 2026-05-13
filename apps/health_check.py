"""Build a safe local health report without submitting or cancelling orders."""

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.metascalp import MetaScalpClient, discover_metascalp
from llbot.domain.models import PortfolioState
from llbot.monitoring.alerts import alert_to_dict, evaluate_component_alerts, evaluate_feed_health_alerts
from llbot.monitoring.health import (
    FeedHealthDecision,
    build_system_health,
    feed_component_health,
    metascalp_component_health,
    risk_component_health,
    storage_component_health,
    system_health_to_dict,
)
from llbot.storage.audit_jsonl import write_json
from llbot.storage.duckdb_store import DuckDbExecutionStore


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    payload = asyncio.run(run(args))
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build safe local component health checks for the lead-lag bot."
    )
    parser.add_argument("--runner-summary", help="Read feed health from a runner summary JSON.")
    parser.add_argument("--db", help="Open a DuckDB execution store and report table counts.")
    parser.add_argument("--discover-metascalp", action="store_true", help="Probe local MetaScalp REST API.")
    parser.add_argument(
        "--select-demo-mexc",
        action="store_true",
        help="When probing MetaScalp, require connected MEXC DemoMode connection.",
    )
    parser.add_argument("--open-timeout-sec", type=float, default=2.0)
    parser.add_argument("--risk-metadata-json", help="Optional JSON object of risk metadata flags.")
    parser.add_argument("--open-positions", type=int, default=0)
    parser.add_argument("--total-notional-usd", default="0")
    parser.add_argument("--daily-pnl-usd", default="0")
    parser.add_argument("--out", help="Write health report JSON.")
    return parser


async def run(args: argparse.Namespace) -> dict[str, Any]:
    components = []
    safety = {
        "orders_submitted": False,
        "orders_cancelled": False,
        "secrets_read": False,
        "live_trading_enabled": False,
    }

    if args.runner_summary:
        feed_decision = feed_decision_from_runner_summary(args.runner_summary)
        components.append(feed_component_health(feed_decision))
    else:
        feed_decision = None

    if args.discover_metascalp:
        components.append(
            await _probe_metascalp(
                timeout_sec=args.open_timeout_sec,
                select_demo_mexc=args.select_demo_mexc,
            )
        )

    if args.db:
        components.append(_probe_storage(args.db))

    components.append(risk_component_health(_risk_state_from_args(args)))
    alerts = []
    if feed_decision is not None:
        alerts.extend(evaluate_feed_health_alerts(feed_decision))
    for component in components:
        alerts.extend(evaluate_component_alerts(component))
    return {
        "system": system_health_to_dict(build_system_health(components)),
        "alerts": [alert_to_dict(alert) for alert in alerts],
        "safety": safety,
    }


def feed_decision_from_runner_summary(path: str | Path) -> FeedHealthDecision:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    health = payload.get("health", {})
    if not isinstance(health, dict):
        raise ValueError("runner summary health must be a JSON object")
    decision = health.get("decision", {})
    if not isinstance(decision, dict):
        raise ValueError("runner summary health.decision must be a JSON object")
    healthy = decision.get("healthy")
    if healthy is None:
        return FeedHealthDecision(
            healthy=False,
            reason="feed_health_unknown",
            stale_streams=(),
            missing_streams=(),
        )
    return FeedHealthDecision(
        healthy=bool(healthy),
        reason=str(decision.get("reason", "unknown")),
        stale_streams=tuple(str(item) for item in _list(decision.get("stale_streams"))),
        missing_streams=tuple(str(item) for item in _list(decision.get("missing_streams"))),
    )


async def _probe_metascalp(timeout_sec: float, select_demo_mexc: bool):
    instance = await discover_metascalp(timeout_sec=timeout_sec)
    if instance is None:
        return metascalp_component_health(None, None)
    if not select_demo_mexc:
        return metascalp_component_health(instance, None, require_demo_mode=False, require_connected=False)

    client = MetaScalpClient(AioHttpJsonClient(instance.base_url, timeout_sec=timeout_sec))
    connection = await client.select_connection(
        exchange="mexc",
        market_contains="futures",
        require_demo_mode=True,
        require_connected=True,
    )
    return metascalp_component_health(instance, connection)


def _probe_storage(path: str):
    try:
        with DuckDbExecutionStore(path) as store:
            counts = store.table_counts()
    except Exception as exc:
        return storage_component_health(None, error=str(exc))
    return storage_component_health(counts)


def _risk_state_from_args(args: argparse.Namespace) -> PortfolioState:
    metadata = {}
    if args.risk_metadata_json:
        loaded = json.loads(args.risk_metadata_json)
        if not isinstance(loaded, dict):
            raise ValueError("--risk-metadata-json must be a JSON object")
        metadata.update(loaded)
    return PortfolioState(
        open_positions=args.open_positions,
        total_notional_usd=Decimal(str(args.total_notional_usd)),
        daily_pnl_usd=Decimal(str(args.daily_pnl_usd)),
        metadata=metadata,
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    main()
