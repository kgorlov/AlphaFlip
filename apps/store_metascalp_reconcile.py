"""Store reconciled MetaScalp execution state in local DuckDB."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.storage.audit_jsonl import write_json
from llbot.storage.duckdb_store import DuckDbExecutionStore, load_reconciliation_report


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)
    if args.summary_out:
        write_json(args.summary_out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load an offline MetaScalp reconciliation report into local DuckDB storage."
    )
    parser.add_argument("--reconciled", required=True, help="Reconciled MetaScalp report JSON.")
    parser.add_argument("--db", required=True, help="DuckDB file to create or update.")
    parser.add_argument("--source", help="Logical source label. Defaults to the reconciled report path.")
    parser.add_argument("--summary-out", help="Write ingestion summary JSON.")
    parser.add_argument(
        "--append-source",
        action="store_true",
        help="Append rows for the same source instead of replacing prior rows for that source.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = load_reconciliation_report(args.reconciled)
    source = args.source or str(Path(args.reconciled))
    with DuckDbExecutionStore(args.db) as store:
        inserted = store.ingest_reconciliation_report(
            report,
            source=source,
            replace_source=not args.append_source,
        )
        table_counts = store.table_counts()
    return {
        "db": str(Path(args.db)),
        "source": source,
        "inserted": inserted,
        "table_counts": table_counts,
        "safety": {
            "offline_only": True,
            "submits_orders": False,
            "cancels_orders": False,
            "opens_websocket": False,
            "reads_secrets": False,
        },
    }


if __name__ == "__main__":
    main()
