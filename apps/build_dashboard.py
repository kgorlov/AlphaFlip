"""Build a static read-only operations dashboard."""

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.monitoring.dashboard import load_dashboard_artifacts, write_dashboard


DEFAULT_REPORTS = {
    "Replay Research": "reports/replay_research_smoke.json",
    "Demo Fill Compare": "reports/demo_fill_compare_smoke.json",
    "Private Reconciliation": "reports/metascalp_reconcile_smoke.json",
    "Private Capture Summary": "reports/metascalp_private_capture_store_smoke.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static read-only operations dashboard.")
    parser.add_argument("--health", default="reports/health_check_metascalp_smoke.json")
    parser.add_argument("--runner-summary", default="reports/metascalp_demo_runner_live_dry_both_streams.json")
    parser.add_argument("--memory", default="memory/memory.json")
    parser.add_argument(
        "--report-link",
        action="append",
        default=[],
        help="Additional report link as Label=path. Can be repeated.",
    )
    parser.add_argument(
        "--history-report",
        action="append",
        default=[],
        help="Historical local report as Label=path. Can be repeated.",
    )
    parser.add_argument("--out", default="reports/dashboard.html")
    args = parser.parse_args()

    artifacts = load_dashboard_artifacts(
        health_path=args.health,
        runner_summary_path=args.runner_summary,
        memory_path=args.memory,
        report_paths={**DEFAULT_REPORTS, **_parse_report_links(args.report_link)},
        history_paths=_parse_report_links(args.history_report),
    )
    write_dashboard(args.out, artifacts)
    payload = {
        "out": args.out,
        "read_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "live_trading_enabled": False,
    }
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


def _parse_report_links(values: list[str]) -> dict[str, str]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--report-link must use Label=path")
        label, path = value.split("=", 1)
        label = label.strip()
        path = path.strip()
        if not label or not path:
            raise SystemExit("--report-link must use non-empty Label=path")
        parsed[label] = path
    return parsed


if __name__ == "__main__":
    main()
