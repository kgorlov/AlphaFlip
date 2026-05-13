"""Guarded MetaScalp demo cancel CLI.

Dry-run is the default. A real demo cancel requires discovery plus an exact
confirmation phrase. Live mode is intentionally not supported.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.metascalp_demo_order import connection_health, resolve_connection
from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.metascalp import MetaScalpClient
from llbot.domain.enums import RuntimeMode
from llbot.execution.metascalp_executor import GuardedMetaScalpDemoExecutor, MetaScalpExecutorConfig
from llbot.execution.order_state import CancelPlan
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json

CONFIRM_DEMO_CANCEL = "METASCALP_DEMO_CANCEL"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run(args))
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or submit a guarded MetaScalp demo cancel. Dry-run by default."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port-min", type=int, default=17845)
    parser.add_argument("--port-max", type=int, default=17855)
    parser.add_argument("--base-url", help="MetaScalp base URL. If omitted with --discover, probe ports.")
    parser.add_argument("--discover", action="store_true", help="Discover MetaScalp and select DemoMode connection.")
    parser.add_argument("--connection-id", type=int, help="Use this connection ID without discovery.")
    parser.add_argument("--exchange", default="mexc")
    parser.add_argument("--market-contains", default="futures")
    parser.add_argument("--intent-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--order-id")
    parser.add_argument("--symbol", default="BTC_USDT")
    parser.add_argument("--reason", default="ttl_expired")
    parser.add_argument("--due-ts-ms", type=int, default=0)
    parser.add_argument("--submit-demo", action="store_true", help="Allow real cancel POST to DemoMode connection.")
    parser.add_argument("--confirm-demo-cancel", help=f"Must equal {CONFIRM_DEMO_CANCEL} for real demo cancel.")
    parser.add_argument("--out", help="Write audit JSON to this path.")
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    allow_submit = should_allow_cancel(args)
    if allow_submit and not args.discover:
        raise SystemExit("--submit-demo requires --discover so DemoMode and active state are verified")

    target = await resolve_connection(args)
    plan = cancel_plan_from_args(args, target.connection.id)
    client = MetaScalpClient(AioHttpJsonClient(target.base_url))
    executor = GuardedMetaScalpDemoExecutor(
        client,
        MetaScalpExecutorConfig(
            allow_submit=allow_submit,
            runtime_mode=RuntimeMode.METASCALP_DEMO if allow_submit else RuntimeMode.PAPER,
            require_demo_mode=True,
            require_connected=True,
        ),
    )
    audit = await executor.cancel(plan, target.connection)
    payload = audit_record_to_dict(audit)
    payload["metascalp_base_url"] = target.base_url
    payload["metascalp_health"] = connection_health(target.connection)
    payload["submit_requested"] = bool(args.submit_demo)
    payload["submit_allowed"] = allow_submit
    return payload


def should_allow_cancel(args: argparse.Namespace) -> bool:
    return bool(args.submit_demo and args.confirm_demo_cancel == CONFIRM_DEMO_CANCEL)


def cancel_plan_from_args(args: argparse.Namespace, connection_id: int) -> CancelPlan:
    request = {
        "ClientId": args.client_id,
        "OrderId": args.order_id,
        "Symbol": args.symbol,
        "Reason": args.reason,
    }
    return CancelPlan(
        intent_id=args.intent_id,
        client_order_id=args.client_id,
        connection_id=connection_id,
        endpoint=f"/api/connections/{connection_id}/orders/cancel",
        request=request,
        reason=args.reason,
        due_ts_ms=args.due_ts_ms,
    )


if __name__ == "__main__":
    main()
