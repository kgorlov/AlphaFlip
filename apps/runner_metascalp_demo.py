"""Run bounded live-paper signals and optionally submit them to MetaScalp demo."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.runner_paper import _live_ws_quotes, _paper_config
from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.metascalp import MetaScalpClient, discover_metascalp
from llbot.domain.enums import MarketProfileName, RuntimeMode, Venue
from llbot.execution.metascalp_executor import GuardedMetaScalpDemoExecutor, MetaScalpExecutorConfig
from llbot.monitoring.health import feed_stream_key
from llbot.service.metascalp_demo_runner import DemoSubmitConfig, submit_demo_records
from llbot.service.paper_runner import build_paper_health_report, build_paper_trading_engine
from llbot.service.replay_report import replay_paper_summary_to_dict
from llbot.storage.audit_jsonl import JsonlAuditWriter, audit_record_to_dict, write_json


CONFIRM = "METASCALP_DEMO_ORDER"
DEFAULT_STREAM_WAIT_MAX_EVENTS = 50000


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run(args))
    if args.summary_out:
        write_json(args.summary_out, result)
    print(json.dumps(audit_record_to_dict(result), ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run live public Binance/MEXC paper signals and bridge filled paper entries "
            "to guarded MetaScalp demo order submission."
        )
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--leader-symbol", default="BTCUSDT")
    parser.add_argument("--lagger-symbol", default="BTC_USDT")
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in MarketProfileName],
        default=MarketProfileName.PERP_TO_PERP.value,
    )
    parser.add_argument("--model", choices=["residual", "impulse", "both"], default="both")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--z-entry", default="2.2")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--min-impulse-bps", default="2")
    parser.add_argument("--safety-bps", default="2")
    parser.add_argument("--ttl-ms", type=int, default=3000)
    parser.add_argument("--cooldown-ms", type=int, default=1000)
    parser.add_argument("--fee-bps", default="0")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--take-profit-bps")
    parser.add_argument("--stale-feed-ms", type=int, default=1500)
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument(
        "--min-events-per-stream",
        type=int,
        default=0,
        help="Continue past --events until each required public stream has at least this many quotes.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        help=(
            "Hard quote cap for live public WebSocket runs. Defaults to --events unless "
            "--min-events-per-stream is set, then defaults to 50000."
        ),
    )
    parser.add_argument("--open-timeout-sec", type=float, default=20.0)
    parser.add_argument("--fill-model", choices=["touch", "trade_through", "queue_aware"], default="touch")
    parser.add_argument("--max-demo-orders", type=int, default=1)
    parser.add_argument("--connection-id", type=int, help="Use a specific MetaScalp demo connection.")
    parser.add_argument("--submit-demo", action="store_true", help="Actually POST demo orders.")
    parser.add_argument("--confirm-demo-submit", help=f"Must equal {CONFIRM} to submit demo orders.")
    parser.add_argument("--paper-audit-out", help="Stream paper audit records to JSONL.")
    parser.add_argument("--metascalp-audit-out", help="Stream MetaScalp order audit records to JSONL.")
    parser.add_argument("--summary-out", help="Write runner summary JSON.")
    return parser


async def run(args: argparse.Namespace) -> dict:
    if args.profile != MarketProfileName.PERP_TO_PERP.value:
        raise SystemExit("runner_metascalp_demo currently supports only perp_to_perp")
    _validate_bounds(args)

    paper_config = _paper_config(args)
    engine = build_paper_trading_engine(paper_config)
    max_events = _resolve_max_events(args)
    instance = await discover_metascalp(timeout_sec=args.open_timeout_sec)
    if instance is None:
        raise SystemExit("MetaScalp discovery failed; start MetaScalp first")

    client = MetaScalpClient(AioHttpJsonClient(instance.base_url, timeout_sec=args.open_timeout_sec))
    connections = await client.connections()
    connection = _select_connection(connections, args.connection_id)
    allow_submit = bool(args.submit_demo and args.confirm_demo_submit == CONFIRM)
    executor = GuardedMetaScalpDemoExecutor(
        client,
        MetaScalpExecutorConfig(
            allow_submit=allow_submit,
            runtime_mode=RuntimeMode.METASCALP_DEMO if allow_submit else RuntimeMode.PAPER,
            require_demo_mode=True,
            require_connected=True,
        ),
    )

    submitted_count = 0
    metascalp_audits = []
    paper_writer = JsonlAuditWriter(args.paper_audit_out) if args.paper_audit_out else None
    metascalp_writer = JsonlAuditWriter(args.metascalp_audit_out) if args.metascalp_audit_out else None

    if args.events <= 0:
        if paper_writer is not None:
            with paper_writer:
                pass
        if metascalp_writer is not None:
            with metascalp_writer:
                pass
        return _result_payload(
            args,
            instance,
            connection,
            allow_submit,
            engine,
            paper_config,
            metascalp_audits,
            max_events,
        )

    async def _loop() -> None:
        nonlocal submitted_count, metascalp_audits
        async for quote in _live_ws_quotes(args):
            records = engine.on_quote(quote)
            if paper_writer is not None:
                for record in records:
                    paper_writer.append(record)
            audits, submitted_count = await submit_demo_records(
                records,
                executor,
                connection,
                args.lagger_symbol,
                MarketProfileName(args.profile),
                submitted_count,
                DemoSubmitConfig(max_demo_orders=args.max_demo_orders),
            )
            metascalp_audits.extend(audits)
            if metascalp_writer is not None:
                for audit in audits:
                    metascalp_writer.append(audit)
            if _should_stop_live_loop(
                engine,
                paper_config,
                args.events,
                args.min_events_per_stream,
                max_events,
            ):
                return

    if paper_writer is not None and metascalp_writer is not None:
        with paper_writer, metascalp_writer:
            await _loop()
    elif paper_writer is not None:
        with paper_writer:
            await _loop()
    elif metascalp_writer is not None:
        with metascalp_writer:
            await _loop()
    else:
        await _loop()

    return _result_payload(
        args,
        instance,
        connection,
        allow_submit,
        engine,
        paper_config,
        metascalp_audits,
        max_events,
    )


def _result_payload(
    args,
    instance,
    connection,
    allow_submit,
    engine,
    paper_config,
    metascalp_audits,
    max_events: int,
) -> dict:
    summary = replay_paper_summary_to_dict(engine.summary())
    return {
        "mode": RuntimeMode.METASCALP_DEMO.value if allow_submit else "dry-run",
        "runner_limits": {
            "target_events": args.events,
            "max_events": max_events,
            "min_events_per_stream": args.min_events_per_stream,
            "stream_event_counts": _required_stream_event_counts(engine, paper_config),
        },
        "metascalp": {
            "base_url": instance.base_url,
            "connection_id": connection.id,
            "connection_name": connection.name,
            "demo_mode": connection.demo_mode,
            "connected": connection.connected,
            "submit_allowed": allow_submit,
        },
        "paper_summary": summary,
        "health": build_paper_health_report(engine, paper_config),
        "demo_order_audits": [audit_record_to_dict(audit) for audit in metascalp_audits],
    }


def _select_connection(connections, connection_id: int | None):
    for connection in connections:
        if connection_id is not None and connection.id != connection_id:
            continue
        if "mexc" not in connection.exchange.lower():
            continue
        if not connection.demo_mode or not connection.connected:
            continue
        return connection
    raise SystemExit("No connected MEXC DemoMode MetaScalp connection found")


def _validate_bounds(args: argparse.Namespace) -> None:
    if args.events < 0:
        raise SystemExit("--events must be >= 0")
    if args.min_events_per_stream < 0:
        raise SystemExit("--min-events-per-stream must be >= 0")
    if args.max_events is not None:
        if args.max_events <= 0:
            raise SystemExit("--max-events must be > 0")
        if args.max_events < args.events:
            raise SystemExit("--max-events must be >= --events")


def _resolve_max_events(args: argparse.Namespace) -> int:
    if args.max_events is not None:
        return args.max_events
    if args.min_events_per_stream > 0:
        return max(args.events, DEFAULT_STREAM_WAIT_MAX_EVENTS)
    return args.events


def _should_stop_live_loop(
    engine,
    paper_config,
    target_events: int,
    min_events_per_stream: int,
    max_events: int,
) -> bool:
    if engine.quote_count >= max_events:
        return True
    if engine.quote_count < target_events:
        return False
    if min_events_per_stream <= 0:
        return True
    return all(
        count >= min_events_per_stream
        for count in _required_stream_event_counts(engine, paper_config).values()
    )


def _required_stream_event_counts(engine, paper_config) -> dict[str, int]:
    streams = engine.feed_streams_snapshot()
    return {
        key: streams[key].event_count if key in streams else 0
        for key in _required_stream_keys(paper_config)
    }


def _required_stream_keys(paper_config) -> tuple[str, str]:
    return (
        feed_stream_key(Venue.BINANCE.value, paper_config.leader_symbol),
        feed_stream_key(Venue.MEXC.value, paper_config.lagger_symbol),
    )


if __name__ == "__main__":
    main()
