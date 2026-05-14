"""Compare replay and paper summary PnL artifacts."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.service.paper_pnl_compare import compare_replay_paper_pnl
from llbot.storage.audit_jsonl import audit_record_to_dict, write_json


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
            "Compare local replay and paper summary JSON artifacts. "
            "This is offline-only and never submits or cancels orders."
        )
    )
    parser.add_argument("--replay-summary", required=True, help="Replay summary JSON file.")
    parser.add_argument("--paper-summary", required=True, help="Paper runner summary JSON file.")
    parser.add_argument("--tolerance-usd", default="0", help="Allowed absolute PnL delta.")
    parser.add_argument("--out", help="Write comparison report JSON.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    replay = _read_object(args.replay_summary)
    paper = _read_object(args.paper_summary)
    report = compare_replay_paper_pnl(
        replay,
        paper,
        tolerance_usd=Decimal(str(args.tolerance_usd)),
    )
    return {
        "summary": audit_record_to_dict(report.summary),
        "matched": report.matched,
        "tolerance_usd": report.tolerance_usd,
        "pnl_deltas": audit_record_to_dict(report.pnl_deltas),
        "count_deltas": audit_record_to_dict(report.count_deltas),
        "intent_count_deltas": audit_record_to_dict(report.intent_count_deltas),
        "mismatch_reasons": list(report.mismatch_reasons),
        "replay": audit_record_to_dict(report.replay),
        "paper": audit_record_to_dict(report.paper),
        "offline_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "live_trading_enabled": False,
    }


def _read_object(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise SystemExit("Summary JSON must contain an object")
    return payload


if __name__ == "__main__":
    main()
