"""Daily summary report built from local smoke/runtime artifacts."""

import json
from pathlib import Path
from typing import Any


def build_daily_summary(
    *,
    runner_summary: dict[str, Any] | None = None,
    health_report: dict[str, Any] | None = None,
    research_report: dict[str, Any] | None = None,
    fill_compare: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paper = _dict((runner_summary or {}).get("paper_summary"))
    health = _dict((health_report or {}).get("system"))
    alerts = _list((health_report or {}).get("alerts"))
    research = research_report or {}
    fills = fill_compare or {}
    reconcile = reconciliation or {}

    return {
        "schema_version": "1.0.0",
        "paper": {
            "quotes": _int(paper.get("quotes")),
            "intents": _int(paper.get("intents")),
            "fills": _int(paper.get("fills")),
            "closed_positions": _int(paper.get("closed_positions")),
            "open_positions": _int(paper.get("open_positions")),
            "realized_pnl_usd": str(paper.get("realized_pnl_usd", "0")),
            "unrealized_pnl_usd": str(paper.get("unrealized_pnl_usd", "0")),
        },
        "health": {
            "status": str(health.get("status", "unknown")),
            "alert_count": len(alerts),
            "critical_alert_count": sum(1 for alert in alerts if _dict(alert).get("severity") == "critical"),
        },
        "research": {
            "symbol_days": len(_list(research.get("symbol_days"))),
            "fill_model_variants": len(_list(research.get("fill_model_variants"))),
        },
        "demo_fill_compare": {
            "matched_fills": _int(fills.get("matched_fills")),
            "unmatched_paper": len(_list(fills.get("unmatched_paper"))),
            "unmatched_demo": len(_list(fills.get("unmatched_demo"))),
        },
        "reconciliation": {
            "orders": len(_list(reconcile.get("orders"))),
            "positions": len(_list(reconcile.get("positions"))),
            "balances": len(_list(reconcile.get("balances"))),
            "audit_records": len(_list(reconcile.get("audit_records"))),
        },
        "safety": {
            "orders_submitted_by_report": False,
            "orders_cancelled_by_report": False,
            "live_trading_enabled": False,
        },
    }


def load_json_object(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def write_daily_summary(path: str | Path, summary: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)
