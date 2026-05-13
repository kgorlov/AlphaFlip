"""Build a dry-run MetaScalp order request without submitting it."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.metascalp import MetaScalpConnection
from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, Side, Venue
from llbot.domain.models import Intent, SymbolProfile
from llbot.execution.metascalp_planner import (
    build_metascalp_dry_run_order_plan,
    dry_run_order_audit_record,
)
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and validate a MetaScalp dry-run order payload. No network calls."
    )
    parser.add_argument("--connection-id", type=int, required=True)
    parser.add_argument("--symbol", default="BTCUSDT", help="Canonical strategy symbol.")
    parser.add_argument("--execution-symbol", default="BTC_USDT", help="MEXC/MetaScalp symbol.")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--price-cap", required=True)
    parser.add_argument("--intent-id", default="manual-dry-run")
    parser.add_argument("--ttl-ms", type=int, default=3000)
    parser.add_argument("--expected-edge-bps", default="1")
    parser.add_argument("--min-qty")
    parser.add_argument("--qty-step")
    parser.add_argument("--price-tick")
    parser.add_argument("--min-notional-usd")
    parser.add_argument("--contract-size")
    parser.add_argument("--out", help="Write audit JSON to this path.")
    args = parser.parse_args()

    intent = _intent_from_args(args)
    plan = build_metascalp_dry_run_order_plan(
        intent,
        _connection(args.connection_id),
        execution_symbol=args.execution_symbol,
        profile=_profile_from_args(args),
    )
    audit = dry_run_order_audit_record(plan, intent)
    payload = audit_record_to_dict(audit)
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


def _intent_from_args(args: argparse.Namespace) -> Intent:
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


def _connection(connection_id: int) -> MetaScalpConnection:
    return MetaScalpConnection(
        id=connection_id,
        name="dry-run",
        exchange="Mexc",
        exchange_id=None,
        market="UsdtFutures",
        market_type=None,
        state=2,
        view_mode=False,
        demo_mode=True,
    )


def _profile_from_args(args: argparse.Namespace) -> SymbolProfile:
    return SymbolProfile(
        canonical_symbol=args.symbol,
        leader_symbol=args.symbol,
        lagger_symbol=args.execution_symbol,
        profile=MarketProfileName.PERP_TO_PERP,
        leader_venue=Venue.BINANCE,
        lagger_venue=Venue.MEXC,
        leader_market=MarketType.USDT_PERP,
        lagger_market=MarketType.USDT_PERP,
        min_qty=_optional_decimal(args.min_qty),
        qty_step=_optional_decimal(args.qty_step),
        price_tick=_optional_decimal(args.price_tick),
        min_notional_usd=_optional_decimal(args.min_notional_usd),
        contract_size=_optional_decimal(args.contract_size),
    )


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


if __name__ == "__main__":
    main()
