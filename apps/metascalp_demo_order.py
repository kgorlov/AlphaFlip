"""Guarded MetaScalp demo order CLI.

Dry-run is the default. A real demo POST requires both --submit-demo and the
exact --confirm-demo-submit text. Live mode is intentionally not supported.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.metascalp import MetaScalpClient, MetaScalpConnection, discover_metascalp
from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, RuntimeMode, Side, Venue
from llbot.domain.models import Intent, SymbolProfile
from llbot.execution.metascalp_executor import GuardedMetaScalpDemoExecutor, MetaScalpExecutorConfig
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json

CONFIRM_DEMO_SUBMIT = "METASCALP_DEMO_ORDER"


@dataclass(frozen=True)
class ResolvedMetaScalpTarget:
    base_url: str
    connection: MetaScalpConnection


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run(args))
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or submit a guarded MetaScalp demo order. Dry-run by default."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port-min", type=int, default=17845)
    parser.add_argument("--port-max", type=int, default=17855)
    parser.add_argument("--base-url", help="MetaScalp base URL. If omitted with --discover, probe ports.")
    parser.add_argument("--discover", action="store_true", help="Discover MetaScalp and select DemoMode connection.")
    parser.add_argument("--connection-id", type=int, help="Use this connection ID without discovery.")
    parser.add_argument("--exchange", default="mexc")
    parser.add_argument("--market-contains", default="futures")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--execution-symbol", default="BTC_USDT")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--price-cap", required=True)
    parser.add_argument("--intent-id", default="manual-demo-order")
    parser.add_argument("--ttl-ms", type=int, default=3000)
    parser.add_argument("--expected-edge-bps", default="1")
    parser.add_argument("--min-qty")
    parser.add_argument("--qty-step")
    parser.add_argument("--price-tick")
    parser.add_argument("--min-notional-usd")
    parser.add_argument("--contract-size")
    parser.add_argument("--submit-demo", action="store_true", help="Allow real POST to DemoMode connection.")
    parser.add_argument("--confirm-demo-submit", help=f"Must equal {CONFIRM_DEMO_SUBMIT} for real demo POST.")
    parser.add_argument("--out", help="Write audit JSON to this path.")
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    intent = intent_from_args(args)
    profile = profile_from_args(args)
    allow_submit = should_allow_submit(args)
    if allow_submit and not args.discover:
        raise SystemExit("--submit-demo requires --discover so DemoMode and active state are verified")

    target = await resolve_connection(args)
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
    audit = await executor.submit(intent, target.connection, args.execution_symbol, profile)
    payload = audit_record_to_dict(audit)
    payload["metascalp_base_url"] = target.base_url
    payload["metascalp_health"] = connection_health(target.connection)
    payload["submit_requested"] = bool(args.submit_demo)
    payload["submit_allowed"] = allow_submit
    return payload


async def resolve_connection(args: argparse.Namespace) -> ResolvedMetaScalpTarget:
    if args.discover:
        instance = await discover_metascalp(args.host, args.port_min, args.port_max)
        if instance is None:
            raise SystemExit(f"MetaScalp not found on {args.host}:{args.port_min}-{args.port_max}")
        base_url = args.base_url or instance.base_url
        client = MetaScalpClient(AioHttpJsonClient(base_url))
        connection = await client.select_connection(
            args.exchange,
            args.market_contains,
            require_demo_mode=True,
            require_connected=True,
        )
        if connection is None:
            raise SystemExit("No connected DemoMode MetaScalp connection matched the filters")
        return ResolvedMetaScalpTarget(base_url=base_url, connection=connection)

    if args.connection_id is None:
        raise SystemExit("--connection-id is required unless --discover is set")
    base_url = args.base_url or f"http://{args.host}:{args.port_min}"
    connection = MetaScalpConnection(
        id=args.connection_id,
        name="manual",
        exchange=args.exchange,
        exchange_id=None,
        market=args.market_contains,
        market_type=None,
        state=2,
        view_mode=False,
        demo_mode=True,
    )
    return ResolvedMetaScalpTarget(base_url=base_url, connection=connection)


def should_allow_submit(args: argparse.Namespace) -> bool:
    return bool(args.submit_demo and args.confirm_demo_submit == CONFIRM_DEMO_SUBMIT)


def connection_health(connection: MetaScalpConnection) -> dict[str, object]:
    return {
        "connection_id": connection.id,
        "exchange": connection.exchange,
        "market": connection.market,
        "connected": connection.connected,
        "demo_mode": connection.demo_mode,
        "view_mode": connection.view_mode,
    }


def intent_from_args(args: argparse.Namespace) -> Intent:
    side = Side.BUY if args.side == "buy" else Side.SELL
    intent_type = IntentType.ENTER_LONG if side == Side.BUY else IntentType.ENTER_SHORT
    return Intent(
        intent_id=args.intent_id,
        symbol=args.symbol,
        profile=MarketProfileName.PERP_TO_PERP,
        intent_type=intent_type,
        side=side,
        qty=Decimal(str(args.qty)),
        price_cap=Decimal(str(args.price_cap)),
        ttl_ms=args.ttl_ms,
        order_style=OrderStyle.AGGRESSIVE_LIMIT,
        confidence=Decimal("1"),
        expected_edge_bps=Decimal(str(args.expected_edge_bps)),
        created_ts_ms=0,
    )


def profile_from_args(args: argparse.Namespace) -> SymbolProfile:
    return SymbolProfile(
        canonical_symbol=args.symbol,
        leader_symbol=args.symbol,
        lagger_symbol=args.execution_symbol,
        profile=MarketProfileName.PERP_TO_PERP,
        leader_venue=Venue.BINANCE,
        lagger_venue=Venue.MEXC,
        leader_market=MarketType.USDT_PERP,
        lagger_market=MarketType.USDT_PERP,
        min_qty=optional_decimal(args.min_qty),
        qty_step=optional_decimal(args.qty_step),
        price_tick=optional_decimal(args.price_tick),
        min_notional_usd=optional_decimal(args.min_notional_usd),
        contract_size=optional_decimal(args.contract_size),
    )


def optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


if __name__ == "__main__":
    main()
