"""Replay one saved trading day from Parquet and/or DuckDB artifacts."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.domain.enums import MarketProfileName
from llbot.execution.paper_fill import FillModel
from llbot.service.day_replay import day_replay_result_to_dict, run_day_replay
from llbot.service.paper_runner import PaperRunnerConfig
from llbot.storage.audit_jsonl import audit_record_to_dict, write_audit_records, write_json


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)
    if args.out:
        write_json(args.out, result)
    print(json.dumps(audit_record_to_dict(result), ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay one saved trading day from local Parquet/DuckDB artifacts. "
            "This is offline-only and never submits or cancels orders."
        )
    )
    parser.add_argument("--day", required=True, help="Trading day prefix, e.g. 2026-05-13.")
    parser.add_argument("--parquet", action="append", default=[], help="Replay Parquet input file.")
    parser.add_argument("--duckdb", help="DuckDB file containing market_quotes/market_trades.")
    parser.add_argument("--duckdb-source", help="Optional DuckDB source filter.")
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
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--min-impulse-bps", default="2")
    parser.add_argument("--safety-bps", default="2")
    parser.add_argument("--ttl-ms", type=int, default=3000)
    parser.add_argument("--cooldown-ms", type=int, default=1000)
    parser.add_argument("--fee-bps", default="0")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--take-profit-bps")
    parser.add_argument("--stale-feed-ms", type=int)
    parser.add_argument(
        "--fill-model",
        choices=[model.value for model in FillModel],
        default=FillModel.TOUCH.value,
    )
    parser.add_argument("--audit-out", help="Write replay paper audit JSONL.")
    parser.add_argument("--research-out", help="Write replay research JSON.")
    parser.add_argument("--out", default="reports/replay_day_smoke.json")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.parquet and not args.duckdb:
        raise SystemExit("Provide at least one --parquet file or --duckdb file")
    result = run_day_replay(
        day=args.day,
        config=_config(args),
        parquet_paths=args.parquet,
        duckdb_path=args.duckdb,
        duckdb_source=args.duckdb_source,
    )
    if args.audit_out:
        write_audit_records(args.audit_out, result.paper.audit_records)
    if args.research_out:
        write_json(args.research_out, result.research_report)
    return day_replay_result_to_dict(result)


def _config(args: argparse.Namespace) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        canonical_symbol=args.symbol,
        leader_symbol=args.leader_symbol,
        lagger_symbol=args.lagger_symbol,
        profile=MarketProfileName(args.profile),
        model=args.model,
        qty=Decimal(str(args.qty)),
        min_samples=args.min_samples,
        min_impulse_bps=Decimal(str(args.min_impulse_bps)),
        safety_bps=Decimal(str(args.safety_bps)),
        ttl_ms=args.ttl_ms,
        cooldown_ms=args.cooldown_ms,
        fee_bps=Decimal(str(args.fee_bps)),
        slippage_bps=Decimal(str(args.slippage_bps)),
        take_profit_bps=(
            Decimal(str(args.take_profit_bps)) if args.take_profit_bps is not None else None
        ),
        stale_feed_ms=args.stale_feed_ms,
        fill_model=FillModel(args.fill_model),
    )


if __name__ == "__main__":
    main()
