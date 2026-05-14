"""Rebuild local health and dashboard artifacts without order actions."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    args = build_parser().parse_args()
    payload = refresh_dashboard(args)
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh local read-only health and dashboard reports."
    )
    parser.add_argument(
        "--runner-summary",
        default="reports/metascalp_demo_runner_live_dry_both_streams.json",
        help="Existing runner summary JSON used for feed health.",
    )
    parser.add_argument("--health-out", default="reports/health_check_metascalp_smoke.json")
    parser.add_argument("--dashboard-out", default="reports/dashboard.html")
    parser.add_argument("--memory", default="memory/memory.json")
    parser.add_argument("--db", default="reports/health_check_smoke.duckdb")
    parser.add_argument("--discover-metascalp", action="store_true")
    parser.add_argument("--select-demo-mexc", action="store_true")
    parser.add_argument("--open-timeout-sec", type=float, default=2.0)
    parser.add_argument(
        "--report-link",
        action="append",
        default=[],
        help="Additional dashboard report link as Label=path. Can be repeated.",
    )
    parser.add_argument(
        "--history-report",
        action="append",
        default=[],
        help="Historical dashboard report as Label=path. Can be repeated.",
    )
    return parser


def refresh_dashboard(args: argparse.Namespace) -> dict[str, object]:
    commands = refresh_commands(args)
    for command in commands:
        subprocess.run(command, check=True)
    return {
        "health_out": args.health_out,
        "dashboard_out": args.dashboard_out,
        "read_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "secrets_read": False,
        "live_trading_enabled": False,
    }


def refresh_commands(args: argparse.Namespace) -> list[list[str]]:
    python = sys.executable
    app_root = Path(__file__).resolve().parent
    health_cmd = [
        python,
        str(app_root / "health_check.py"),
        "--runner-summary",
        args.runner_summary,
        "--db",
        args.db,
        "--open-timeout-sec",
        str(args.open_timeout_sec),
        "--out",
        args.health_out,
    ]
    if args.discover_metascalp:
        health_cmd.append("--discover-metascalp")
    if args.select_demo_mexc:
        health_cmd.append("--select-demo-mexc")

    dashboard_cmd = [
        python,
        str(app_root / "build_dashboard.py"),
        "--health",
        args.health_out,
        "--runner-summary",
        args.runner_summary,
        "--memory",
        args.memory,
        "--out",
        args.dashboard_out,
    ]
    for report_link in args.report_link:
        dashboard_cmd.extend(["--report-link", report_link])
    for history_report in args.history_report:
        dashboard_cmd.extend(["--history-report", history_report])

    return [health_cmd, dashboard_cmd]


if __name__ == "__main__":
    main()
