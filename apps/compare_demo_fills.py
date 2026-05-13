"""Compare paper fills against reconciled MetaScalp demo fills."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.service.demo_fill_compare import compare_demo_fills
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
        description="Compare internal paper fill audit JSONL against reconciled MetaScalp demo fills."
    )
    parser.add_argument("--paper-audit", required=True, help="Paper audit JSONL file.")
    parser.add_argument("--reconciled", required=True, help="Reconciled MetaScalp report JSON.")
    parser.add_argument("--out", help="Write comparison report JSON.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    paper_records = _read_jsonl(args.paper_audit)
    reconciled = json.loads(Path(args.reconciled).read_text(encoding="utf-8-sig"))
    orders = reconciled.get("orders", []) if isinstance(reconciled, dict) else []
    report = compare_demo_fills(paper_records, orders)
    return {
        "summary": report.summary,
        "comparisons": [audit_record_to_dict(item) for item in report.comparisons],
        "unmatched_paper": [audit_record_to_dict(item) for item in report.unmatched_paper],
        "unmatched_demo": [audit_record_to_dict(item) for item in report.unmatched_demo],
    }


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise SystemExit("Paper audit JSONL rows must be JSON objects")
        records.append(payload)
    return records


if __name__ == "__main__":
    main()
