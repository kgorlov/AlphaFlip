"""Build a local daily summary JSON from existing reports."""

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.service.daily_summary import build_daily_summary, load_json_object, write_daily_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local daily summary from report artifacts.")
    parser.add_argument("--runner-summary", default="reports/metascalp_demo_runner_live_dry_both_streams.json")
    parser.add_argument("--health", default="reports/health_check_metascalp_smoke.json")
    parser.add_argument("--research", default="reports/replay_research_smoke.json")
    parser.add_argument("--fill-compare", default="reports/demo_fill_compare_smoke.json")
    parser.add_argument("--reconciliation", default="reports/metascalp_reconcile_smoke.json")
    parser.add_argument("--out", default="reports/daily_summary_smoke.json")
    args = parser.parse_args()

    summary = build_daily_summary(
        runner_summary=load_json_object(args.runner_summary),
        health_report=load_json_object(args.health),
        research_report=load_json_object(args.research),
        fill_compare=load_json_object(args.fill_compare),
        reconciliation=load_json_object(args.reconciliation),
    )
    write_daily_summary(args.out, summary)
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
