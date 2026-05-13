"""Replay MetaScalp private updates into local order reconciliation state."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.execution.metascalp_reconcile import reconcile_metascalp_updates
from llbot.execution.order_state import OrderLifecycleStatus, OrderState
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize and replay MetaScalp private order/position/balance JSONL updates."
    )
    parser.add_argument("--orders", help="JSON file with open order states to reconcile.")
    parser.add_argument(
        "--order",
        action="append",
        default=[],
        help="Inline order as intent_id:client_id:symbol:qty:connection_id[:order_id].",
    )
    parser.add_argument("--updates", help="JSONL file with MetaScalp private updates. Defaults to stdin.")
    parser.add_argument("--out", help="Write reconciliation JSON report.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    orders = _read_orders(args.orders) + [_order_from_inline(value) for value in args.order]
    updates = _read_updates(args.updates)
    result = reconcile_metascalp_updates(orders, updates)
    return {
        "orders": [audit_record_to_dict(order) for order in result.orders],
        "audit_records": [audit_record_to_dict(record) for record in result.audit_records],
        "positions": [audit_record_to_dict(position) for position in result.positions],
        "balances": [audit_record_to_dict(balance) for balance in result.balances],
        "summary": {
            "orders": len(result.orders),
            "updates": len(updates),
            "audit_records": len(result.audit_records),
            "positions": len(result.positions),
            "balances": len(result.balances),
            "unmatched_updates": result.unmatched_updates,
            "unknown_updates": result.unknown_updates,
        },
    }


def _read_orders(path: str | None) -> list[OrderState]:
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    items = payload.get("orders", payload) if isinstance(payload, dict) else payload
    return [_order_from_dict(item) for item in items]


def _read_updates(path: str | None) -> list[dict[str, Any]]:
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines() if path else sys.stdin.read().splitlines()
    updates: list[dict[str, Any]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise SystemExit("MetaScalp update JSONL rows must be JSON objects")
        updates.append(payload)
    return updates


def _order_from_inline(value: str) -> OrderState:
    parts = value.split(":")
    if len(parts) not in {5, 6}:
        raise SystemExit("--order must be intent_id:client_id:symbol:qty:connection_id[:order_id]")
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


if __name__ == "__main__":
    main()
