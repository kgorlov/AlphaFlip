"""Replay saved market-data JSONL through deterministic signal models."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.domain.enums import MarketProfileName
from llbot.execution.paper_fill import FillModel
from llbot.service.paper_runner import PaperRunnerConfig, build_signal_models, run_replay_paper
from llbot.service.replay import replay_events
from llbot.service.replay_report import (
    build_replay_research_report,
    replay_paper_summary_to_dict,
)
from llbot.storage.audit_jsonl import audit_record_to_dict, write_audit_records, write_json
from llbot.storage.replay_jsonl import read_replay_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay JSONL market data through signal models.")
    parser.add_argument("--input", action="append", required=True, help="Replay JSONL file path.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Canonical intent symbol.")
    parser.add_argument("--leader-symbol", default="BTCUSDT")
    parser.add_argument("--lagger-symbol", default="BTC_USDT")
    parser.add_argument("--model", choices=["residual", "impulse", "both"], default="both")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--z-entry", default="2.2")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--min-impulse-bps", default="2")
    parser.add_argument("--safety-bps", default="2")
    parser.add_argument("--fee-bps", default="0")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--take-profit-bps")
    parser.add_argument("--stale-feed-ms", type=int)
    parser.add_argument("--print-intents", action="store_true")
    parser.add_argument("--paper", action="store_true", help="Run risk gates and quote paper fills.")
    parser.add_argument(
        "--fill-model",
        choices=[model.value for model in FillModel],
        default=FillModel.TOUCH.value,
    )
    parser.add_argument("--audit-out", help="Write replay paper audit JSONL to this path.")
    parser.add_argument("--summary-out", help="Write replay paper summary JSON to this path.")
    parser.add_argument("--research-report-out", help="Write replay research report JSON to this path.")
    parser.add_argument(
        "--compare-fill-models",
        action="store_true",
        help="Run touch, queue-aware, and trade-through variants on the same replay.",
    )
    args = parser.parse_args()

    events = []
    for input_path in args.input:
        events.extend(read_replay_events(input_path))

    models = _build_models(args)

    if args.paper:
        summary, audit_records = _run_paper(events, args, FillModel(args.fill_model))
        fill_model_variants = []
        fill_model_variant_records = {}
        if args.compare_fill_models:
            for variant in FillModel:
                variant_summary, variant_records = _run_paper(events, args, variant)
                variant_payload = replay_paper_summary_to_dict(variant_summary)
                variant_payload["fill_model"] = variant.value
                fill_model_variants.append(variant_payload)
                fill_model_variant_records[variant.value] = variant_records
        if args.audit_out:
            write_audit_records(args.audit_out, audit_records)
        if args.print_intents:
            for record in audit_records:
                print(json.dumps(audit_record_to_dict(record), ensure_ascii=True, separators=(",", ":")))
        summary_payload = replay_paper_summary_to_dict(summary)
        if fill_model_variants:
            summary_payload["fill_model_variants"] = fill_model_variants
        if args.summary_out:
            write_json(args.summary_out, summary_payload)
        if args.research_report_out:
            write_json(
                args.research_report_out,
                build_replay_research_report(
                    events,
                    summary,
                    audit_records,
                    stale_gap_ms=args.stale_feed_ms,
                    fill_model_variants=fill_model_variants,
                    fill_model_variant_records=fill_model_variant_records,
                ),
            )
        print(json.dumps(audit_record_to_dict(summary_payload), ensure_ascii=True, separators=(",", ":")))
        return

    summary, intents = replay_events(events, models)
    if args.print_intents:
        for intent in intents:
            print(
                json.dumps(
                    {
                        "intent_id": intent.intent_id,
                        "symbol": intent.symbol,
                        "intent_type": intent.intent_type.value,
                        "side": intent.side.value,
                        "price_cap": str(intent.price_cap),
                        "expected_edge_bps": str(intent.expected_edge_bps),
                        "created_ts_ms": intent.created_ts_ms,
                        "features": intent.features,
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
            )

    print(
        json.dumps(
            {
                "processed_events": summary.processed_events,
                "quotes": summary.quotes,
                "intents": summary.intents,
                "skipped_events": summary.skipped_events,
                "intent_counts": summary.intent_counts,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


def _build_models(args: argparse.Namespace) -> list:
    return build_signal_models(_paper_config(args, FillModel(args.fill_model)))


def _run_paper(events: list, args: argparse.Namespace, fill_model: FillModel):
    return run_replay_paper(events, _paper_config(args, fill_model))


def _paper_config(args: argparse.Namespace, fill_model: FillModel) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        canonical_symbol=args.symbol,
        leader_symbol=args.leader_symbol,
        lagger_symbol=args.lagger_symbol,
        profile=MarketProfileName.PERP_TO_PERP,
        model=args.model,
        qty=Decimal(str(args.qty)),
        z_entry=Decimal(str(args.z_entry)),
        min_samples=args.min_samples,
        min_impulse_bps=Decimal(str(args.min_impulse_bps)),
        safety_bps=Decimal(str(args.safety_bps)),
        fee_bps=Decimal(str(args.fee_bps)),
        slippage_bps=Decimal(str(args.slippage_bps)),
        take_profit_bps=(
            Decimal(str(args.take_profit_bps)) if args.take_profit_bps is not None else None
        ),
        stale_feed_ms=args.stale_feed_ms,
        fill_model=fill_model,
    )


if __name__ == "__main__":
    main()
