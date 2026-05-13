"""Capture MetaScalp private WebSocket updates for offline reconciliation."""

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
from llbot.adapters.metascalp_ws import (
    capture_metascalp_private_updates,
    metascalp_ws_url,
    parse_subscription_json,
    read_captured_raw,
    subscribe_connection_message,
)
from llbot.execution.metascalp_reconcile import reconcile_metascalp_updates
from llbot.execution.order_state import OrderLifecycleStatus, OrderState
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json
from llbot.storage.duckdb_store import DuckDbExecutionStore


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run(args))
    if args.summary_out:
        write_json(args.summary_out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture MetaScalp private WebSocket updates to JSONL, then optionally "
            "reconcile and store them locally."
        )
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--ws-url", help="Explicit MetaScalp private WebSocket URL.")
    source.add_argument(
        "--discover",
        action="store_true",
        help="Discover local MetaScalp HTTP instance and convert it to a WebSocket URL.",
    )
    parser.add_argument(
        "--ws-path",
        default="/",
        help="WebSocket path used with --discover. Official MetaScalp local API uses '/'.",
    )
    parser.add_argument(
        "--connection-id",
        type=int,
        help="MetaScalp connectionId to subscribe for order/position/balance/finres updates.",
    )
    parser.add_argument(
        "--select-demo-mexc",
        action="store_true",
        help="With --discover, select the first connected MEXC DemoMode connection and subscribe it.",
    )
    parser.add_argument("--events", type=int, default=10, help="Number of private updates to capture.")
    parser.add_argument("--out", required=True, help="Raw captured update JSONL output path.")
    parser.add_argument(
        "--read-existing",
        action="store_true",
        help="Skip WebSocket capture and read the existing --out JSONL for reconciliation/storage.",
    )
    parser.add_argument(
        "--subscription-json",
        action="append",
        default=[],
        help="Subscription message JSON object to send after connect. May be repeated.",
    )
    parser.add_argument("--open-timeout-sec", type=float, default=20.0)
    parser.add_argument(
        "--idle-timeout-sec",
        type=float,
        help="Stop capture after this many seconds without a WebSocket message.",
    )
    parser.add_argument("--order", action="append", default=[], help=_ORDER_HELP)
    parser.add_argument("--orders", help="JSON file with open order states to reconcile.")
    parser.add_argument("--reconcile-out", help="Write reconciliation report JSON.")
    parser.add_argument("--db", help="DuckDB file to load reconciliation output into.")
    parser.add_argument("--source", help="Logical source label for DuckDB rows.")
    parser.add_argument("--summary-out", help="Write capture summary JSON.")
    return parser


async def run(args: argparse.Namespace) -> dict[str, Any]:
    subscriptions = parse_subscription_json(args.subscription_json)
    if args.read_existing:
        capture = {
            "ws_url": None,
            "out": str(Path(args.out)),
            "captured": len(read_captured_raw(args.out)),
            "subscriptions_sent": 0,
            "opened_websocket": False,
            "safety": {
                "submits_orders": False,
                "cancels_orders": False,
                "reads_secrets": False,
            },
        }
    else:
        ws_url, selected_connection_id = await _resolve_capture_target(args)
        connection_id = args.connection_id or selected_connection_id
        if connection_id is not None:
            subscriptions.insert(0, subscribe_connection_message(connection_id))
        capture = await capture_metascalp_private_updates(
            ws_url or "",
            events=args.events,
            out=args.out,
            subscriptions=subscriptions,
            open_timeout_sec=args.open_timeout_sec,
            idle_timeout_sec=args.idle_timeout_sec,
        )
    result: dict[str, Any] = {
        "capture": audit_record_to_dict(capture),
        "reconciliation": None,
        "storage": None,
    }

    if args.reconcile_out or args.db:
        updates = read_captured_raw(args.out)
        orders = _read_orders(args.orders) + [_order_from_inline(value) for value in args.order]
        reconciled = reconcile_metascalp_updates(orders, updates)
        report = {
            "orders": [audit_record_to_dict(order) for order in reconciled.orders],
            "audit_records": [audit_record_to_dict(record) for record in reconciled.audit_records],
            "positions": [audit_record_to_dict(position) for position in reconciled.positions],
            "balances": [audit_record_to_dict(balance) for balance in reconciled.balances],
            "summary": {
                "orders": len(reconciled.orders),
                "updates": len(updates),
                "audit_records": len(reconciled.audit_records),
                "positions": len(reconciled.positions),
                "balances": len(reconciled.balances),
                "unmatched_updates": reconciled.unmatched_updates,
                "unknown_updates": reconciled.unknown_updates,
            },
        }
        if args.reconcile_out:
            write_json(args.reconcile_out, report)
        result["reconciliation"] = report["summary"]
        if args.db:
            source = args.source or str(Path(args.out))
            with DuckDbExecutionStore(args.db) as store:
                inserted = store.ingest_reconciliation_report(report, source=source)
                result["storage"] = {
                    "db": str(Path(args.db)),
                    "source": source,
                    "inserted": inserted,
                    "table_counts": store.table_counts(),
                }

    return result


async def _resolve_capture_target(args: argparse.Namespace) -> tuple[str | None, int | None]:
    if args.ws_url:
        return args.ws_url, None
    if args.discover:
        instance = await discover_metascalp(timeout_sec=args.open_timeout_sec)
        if instance is None:
            raise SystemExit("MetaScalp discovery failed; use --ws-url or start MetaScalp")
        selected_connection_id = None
        if args.select_demo_mexc:
            client = MetaScalpClient(AioHttpJsonClient(instance.base_url, timeout_sec=args.open_timeout_sec))
            connection = await client.select_connection("mexc", None, require_demo_mode=True)
            if connection is None:
                raise SystemExit("No connected MEXC DemoMode MetaScalp connection found")
            selected_connection_id = connection.id
        return metascalp_ws_url(instance.base_url, args.ws_path), selected_connection_id
    if args.events > 0:
        raise SystemExit("--ws-url or --discover is required when --events is greater than 0")
    return None, None


def _read_orders(path: str | None) -> list[OrderState]:
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    items = payload.get("orders", payload) if isinstance(payload, dict) else payload
    return [_order_from_dict(item) for item in items]


def _order_from_inline(value: str) -> OrderState:
    parts = value.split(":")
    if len(parts) not in {5, 6}:
        raise SystemExit(_ORDER_HELP)
    intent_id, client_id, symbol, qty, connection_id = parts[:5]
    order_id = parts[5] if len(parts) == 6 else None
    return OrderState(
        intent_id=intent_id,
        client_order_id=client_id,
        venue_order_id=order_id,
        symbol=symbol,
        qty=Decimal(qty),
        open=True,
        status=OrderLifecycleStatus.ACCEPTED,
        metadata={"connection_id": int(connection_id)},
    )


def _order_from_dict(item: dict[str, Any]) -> OrderState:
    status = OrderLifecycleStatus(item.get("status", OrderLifecycleStatus.ACCEPTED.value))
    return OrderState(
        intent_id=str(item["intent_id"]),
        client_order_id=str(item["client_order_id"]),
        venue_order_id=str(item["venue_order_id"]) if item.get("venue_order_id") is not None else None,
        symbol=str(item["symbol"]),
        qty=Decimal(str(item["qty"])),
        filled_qty=Decimal(str(item.get("filled_qty", "0"))),
        avg_fill_price=Decimal(str(item["avg_fill_price"])) if item.get("avg_fill_price") is not None else None,
        open=bool(item.get("open", True)),
        status=status,
        accepted_ts_ms=item.get("accepted_ts_ms"),
        expires_ts_ms=item.get("expires_ts_ms"),
        last_update_ts_ms=item.get("last_update_ts_ms"),
        unknown_status=bool(item.get("unknown_status", False)),
        metadata=dict(item.get("metadata", {})),
    )


_ORDER_HELP = "Inline order as intent_id:client_id:symbol:qty:connection_id[:order_id]."


if __name__ == "__main__":
    main()
