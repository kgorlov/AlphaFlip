"""Local-only operator console for safe AlphaFlip workflows."""

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.serve_dashboard import validate_local_host

CONFIRM_DEMO_SUBMIT = "METASCALP_DEMO_ORDER"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: str
    label: str
    group: str
    description: str
    needs_confirmation: bool = False


@dataclass(slots=True)
class OperatorJob:
    job_id: str
    action_id: str
    label: str
    command: list[str]
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


class OperatorState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.python = str(root / ".venv" / "Scripts" / "python.exe")
        self.jobs: dict[str, OperatorJob] = {}
        self.lock = threading.Lock()

    def start_job(self, action_id: str, payload: dict[str, Any]) -> OperatorJob:
        spec = action_specs()[action_id]
        if spec.needs_confirmation and payload.get("confirm") != CONFIRM_DEMO_SUBMIT:
            raise ValueError(f"{action_id} requires confirm={CONFIRM_DEMO_SUBMIT}")
        command = build_action_command(self, action_id, payload)
        job = OperatorJob(
            job_id=uuid.uuid4().hex[:12],
            action_id=action_id,
            label=spec.label,
            command=command,
        )
        with self.lock:
            self.jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()
        return job

    def _run_job(self, job: OperatorJob) -> None:
        try:
            completed = subprocess.run(
                job.command,
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
            job.returncode = completed.returncode
            job.stdout = _tail(completed.stdout)
            job.stderr = _tail(completed.stderr)
            job.status = "completed" if completed.returncode == 0 else "failed"
        except Exception as exc:  # pragma: no cover - defensive server path
            job.returncode = -1
            job.stderr = str(exc)
            job.status = "failed"
        finally:
            job.finished_at = time.time()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local AlphaFlip operator console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--root", default=".")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    serve_operator_console(args)


def serve_operator_console(args: argparse.Namespace) -> None:
    validate_local_host(args.host)
    root = Path(args.root).resolve()
    state = OperatorState(root)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        json.dumps(
            {
                "url": f"http://{args.host}:{args.port}/",
                "local_only": True,
                "live_trading_enabled": False,
                "demo_submit_requires_confirmation": True,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def make_handler(state: OperatorState) -> type[BaseHTTPRequestHandler]:
    class OperatorHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(render_operator_html())
                return
            if parsed.path == "/api/state":
                self._send_json(build_state_payload(state))
                return
            if parsed.path == "/api/report":
                query = parse_qs(parsed.query)
                path = query.get("path", [""])[0]
                self._send_json(read_report(state.root, path))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            prefix = "/api/actions/"
            if not parsed.path.startswith(prefix):
                self.send_error(404)
                return
            action_id = parsed.path[len(prefix) :]
            if action_id not in action_specs():
                self.send_error(404)
                return
            try:
                payload = self._read_json()
                job = state.start_job(action_id, payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"job": job_payload(job)})

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            size = int(self.headers.get("Content-Length", "0") or "0")
            if size <= 0:
                return {}
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            return payload if isinstance(payload, dict) else {}

        def _send_html(self, html: str, status: int = 200) -> None:
            data = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return OperatorHandler


def action_specs() -> dict[str, ActionSpec]:
    specs = (
        ActionSpec("probe_metascalp", "Probe MetaScalp", "Connections", "Discover local MetaScalp connections."),
        ActionSpec("health_check", "Health Check", "Monitoring", "Build latest health JSON."),
        ActionSpec("refresh_dashboard", "Refresh Dashboard", "Monitoring", "Rebuild health and static dashboard."),
        ActionSpec("refresh_universe", "Refresh Universe", "Universe", "Rank Binance/MEXC candidates from public snapshots."),
        ActionSpec("paper_replay_smoke", "Replay Paper Smoke", "Paper", "Run safe paper replay on smoke data."),
        ActionSpec("live_paper_30000", "Live Paper", "Paper", "Run configurable public WebSocket paper mode."),
        ActionSpec("demo_runner_dry", "Demo Runner Dry", "MetaScalp", "Run MetaScalp demo bridge without POST."),
        ActionSpec(
            "demo_submit_tiny",
            "Submit Tiny Demo",
            "MetaScalp",
            "Submit one tiny MEXC futures DemoMode order.",
            needs_confirmation=True,
        ),
    )
    return {spec.action_id: spec for spec in specs}


def build_action_command(state: OperatorState, action_id: str, payload: dict[str, Any]) -> list[str]:
    py = state.python
    if action_id == "probe_metascalp":
        return [py, "apps/probe_metascalp.py"]
    if action_id == "health_check":
        return [
            py,
            "apps/health_check.py",
            "--runner-summary",
            "reports/metascalp_demo_runner_manual_submit_summary.json",
            "--discover-metascalp",
            "--select-demo-mexc",
            "--out",
            "reports/operator_health.json",
        ]
    if action_id == "refresh_dashboard":
        return [
            py,
            "apps/refresh_dashboard.py",
            "--runner-summary",
            "reports/metascalp_demo_runner_manual_submit_summary.json",
            "--health-out",
            "reports/operator_health.json",
            "--dashboard-out",
            "reports/dashboard.html",
        ]
    if action_id == "refresh_universe":
        return [
            py,
            "apps/hydrate_universe.py",
            "--config",
            "conf/config.example.yaml",
            "--depth-limit",
            "20",
            "--http-timeout-sec",
            "20",
            "--out",
            "reports/operator_universe_candidates.json",
        ]
    if action_id == "paper_replay_smoke":
        return [
            py,
            "apps/runner_paper.py",
            "--input",
            "data/replay/smoke_binance_usdm_BTCUSDT.jsonl",
            "--input",
            "data/replay/smoke_mexc_contract_BTC_USDT.jsonl",
            "--min-samples",
            "1",
            "--fee-bps",
            "5",
            "--slippage-bps",
            "5",
            "--take-profit-bps",
            "10",
            "--stale-feed-ms",
            "1500",
            "--summary-out",
            "reports/operator_runner_paper_summary.json",
            "--audit-out",
            "reports/operator_runner_paper_audit.jsonl",
            "--health-out",
            "reports/operator_runner_paper_health.json",
        ]
    if action_id == "live_paper_30000":
        target_closed_trades = _payload_value(payload, "target_closed_trades", "100")
        events = str(_max_events_for_target(target_closed_trades))
        qty = _payload_value(payload, "qty", "0.001")
        stale_feed_ms = _payload_value(payload, "stale_feed_ms", "3000")
        z_entry = _payload_value(payload, "z_entry", "1.5")
        min_impulse_bps = _payload_value(payload, "min_impulse_bps", "1")
        starting_balance_usd = _payload_value(payload, "starting_balance_usd", "1000")
        symbol = _payload_value(payload, "symbol", "BTCUSDT").upper()
        leader_symbol = _payload_value(payload, "leader_symbol", symbol).upper()
        lagger_symbol = _payload_value(payload, "lagger_symbol", _default_mexc_lagger(symbol)).upper()
        return [
            py,
            "apps/runner_paper.py",
            "--live-ws",
            "--events",
            events,
            "--target-closed-trades",
            target_closed_trades,
            "--symbol",
            symbol,
            "--leader-symbol",
            leader_symbol,
            "--lagger-symbol",
            lagger_symbol,
            "--model",
            "both",
            "--qty",
            qty,
            "--min-samples",
            "1",
            "--z-entry",
            z_entry,
            "--min-impulse-bps",
            min_impulse_bps,
            "--stale-feed-ms",
            stale_feed_ms,
            "--starting-balance-usd",
            starting_balance_usd,
            "--summary-out",
            "reports/operator_live_paper_summary.json",
            "--audit-out",
            "reports/operator_live_paper_audit.jsonl",
            "--health-out",
            "reports/operator_live_paper_health.json",
        ]
    if action_id == "demo_runner_dry":
        return [
            py,
            "apps/runner_metascalp_demo.py",
            "--events",
            "1000",
            "--min-events-per-stream",
            "1",
            "--max-events",
            "20000",
            "--connection-id",
            "4",
            "--max-demo-orders",
            "1",
            "--min-samples",
            "1",
            "--summary-out",
            "reports/operator_demo_runner_dry_summary.json",
            "--paper-audit-out",
            "reports/operator_demo_runner_dry_paper.jsonl",
            "--metascalp-audit-out",
            "reports/operator_demo_runner_dry_orders.jsonl",
        ]
    if action_id == "demo_submit_tiny":
        return [
            py,
            "apps/metascalp_demo_order.py",
            "--discover",
            "--submit-demo",
            "--confirm-demo-submit",
            CONFIRM_DEMO_SUBMIT,
            "--symbol",
            "BTCUSDT",
            "--execution-symbol",
            "BTC_USDT",
            "--side",
            str(payload.get("side", "buy")),
            "--qty",
            str(payload.get("qty", "0.001")),
            "--price-cap",
            str(payload.get("price", "81280")),
            "--min-qty",
            "0.001",
            "--qty-step",
            "0.001",
            "--price-tick",
            "0.1",
            "--min-notional-usd",
            "5",
            "--contract-size",
            "1",
            "--intent-id",
            f"operator-demo-{int(time.time())}",
            "--out",
            "reports/operator_demo_submit_latest.json",
        ]
    raise ValueError(f"Unknown action: {action_id}")


def build_state_payload(state: OperatorState) -> dict[str, Any]:
    with state.lock:
        jobs = [job_payload(job) for job in sorted(state.jobs.values(), key=lambda item: item.started_at, reverse=True)]
    return {
        "safety": {
            "local_only": True,
            "live_trading_enabled": False,
            "demo_submit_requires_confirmation": True,
            "secrets_input_enabled": False,
        },
        "actions": [asdict(spec) for spec in action_specs().values()],
        "jobs": jobs,
        "reports": report_summaries(state.root),
        "paper_summary": paper_summary(state.root),
        "latest_audit": latest_audit_rows(state.root),
        "universe_candidates": universe_candidates(state.root),
    }


def job_payload(job: OperatorJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "action_id": job.action_id,
        "label": job.label,
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "returncode": job.returncode,
        "command": job.command,
        "stdout": job.stdout,
        "stderr": job.stderr,
    }


def report_summaries(root: Path) -> list[dict[str, Any]]:
    reports = [
        ("Dashboard", "reports/dashboard.html"),
        ("Health", "reports/operator_health.json"),
        ("Demo Submit", "reports/operator_demo_submit_latest.json"),
        ("Manual Demo Submit", "reports/metascalp_demo_order_manual_submit_tiny.json"),
        ("Demo Runner Summary", "reports/operator_demo_runner_dry_summary.json"),
        ("Universe Candidates", "reports/operator_universe_candidates.json"),
        ("Live Paper Summary", "reports/operator_live_paper_summary.json"),
        ("Replay Paper Summary", "reports/operator_runner_paper_summary.json"),
        ("Latest Tests", "reports/latest_test_report.md"),
    ]
    rows = []
    for label, path in reports:
        file_path = root / path
        rows.append(
            {
                "label": label,
                "path": path,
                "exists": file_path.exists(),
                "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            }
        )
    return rows


def paper_summary(root: Path) -> dict[str, Any]:
    path = root / "reports/operator_live_paper_summary.json"
    if not path.exists():
        return {
            "intents": 0,
            "fills": 0,
            "closed_positions": 0,
            "winning_trades": 0,
            "win_rate_pct": "0",
            "open_positions": 0,
            "target_closed_trades": 0,
            "canonical_symbol": "",
            "leader_symbol": "",
            "lagger_symbol": "",
            "total_pnl_usd": "0",
            "starting_balance_usd": "0",
            "pnl_pct_of_balance": "0",
            "realized_pnl_usd": "0",
            "unrealized_pnl_usd": "0",
        }
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return {}
    trade_stats = _closed_trade_stats(root / "reports/operator_live_paper_audit.jsonl")
    audit_closed = trade_stats["closed_trades"]
    closed_positions = audit_closed or int(payload.get("closed_positions", 0) or 0)
    winning_trades = trade_stats["winning_trades"]
    total_pnl_usd = _decimal_sum(
        payload.get("realized_pnl_usd", "0"),
        payload.get("unrealized_pnl_usd", "0"),
    )
    starting_balance_usd = str(payload.get("starting_balance_usd") or "1000")
    return {
        "intents": payload.get("intents", 0),
        "fills": payload.get("fills", 0),
        "closed_positions": closed_positions,
        "winning_trades": winning_trades,
        "win_rate_pct": _percent(winning_trades, closed_positions),
        "open_positions": payload.get("open_positions", 0),
        "target_closed_trades": payload.get("target_closed_trades", 0),
        "stop_reason": payload.get("stop_reason", ""),
        "canonical_symbol": payload.get("canonical_symbol", ""),
        "leader_symbol": payload.get("leader_symbol", ""),
        "lagger_symbol": payload.get("lagger_symbol", ""),
        "total_pnl_usd": str(payload.get("total_pnl_usd", total_pnl_usd)),
        "starting_balance_usd": starting_balance_usd,
        "pnl_pct_of_balance": str(
            payload.get("pnl_pct_of_balance", _decimal_percent(total_pnl_usd, starting_balance_usd))
        ),
        "realized_pnl_usd": str(payload.get("realized_pnl_usd", "0")),
        "unrealized_pnl_usd": str(payload.get("unrealized_pnl_usd", "0")),
    }


def _closed_trade_stats(path: Path) -> dict[str, int]:
    closed_trades = 0
    winning_trades = 0
    if not path.exists() or path.stat().st_size == 0:
        return {"closed_trades": 0, "winning_trades": 0}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("decision_result") != "closed":
            continue
        closed_trades += 1
        pnl = _float(payload.get("realized_pnl_usd"))
        if pnl is not None and pnl > 0:
            winning_trades += 1
    return {"closed_trades": closed_trades, "winning_trades": winning_trades}


def latest_audit_rows(root: Path) -> list[dict[str, Any]]:
    paths = [
        root / "reports/operator_live_paper_audit.jsonl",
        root / "reports/operator_demo_runner_dry_orders.jsonl",
        root / "reports/operator_demo_runner_dry_paper.jsonl",
        root / "reports/metascalp_demo_runner_manual_submit_paper.jsonl",
    ]
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines()[-12:]:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    "source": path.name,
                    "timestamp_ms": payload.get("timestamp_ms"),
                    "symbol": payload.get("symbol"),
                    "side": payload.get("side"),
                    "model": payload.get("model"),
                    "decision": payload.get("decision_result"),
                    "reason": payload.get("skip_reason"),
                    "edge_bps": str(payload.get("expected_edge_bps", "")),
                    "result": _trade_result(payload),
                    "success": _trade_success(payload),
                    "pnl_usd": str(payload.get("realized_pnl_usd") or payload.get("gross_pnl_usd") or ""),
                    "fill_price": str(payload.get("fill_price") or ""),
                    "fill_qty": str(payload.get("fill_qty") or ""),
                    "exit_reason": str(payload.get("exit_reason") or payload.get("fill_reason") or ""),
                }
            )
    return rows[:20]


def universe_candidates(root: Path) -> list[dict[str, Any]]:
    path = root / "reports/operator_universe_candidates.json"
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        return []
    rows = []
    for item in candidates[:20]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        rows.append(
            {
                "rank": item.get("rank"),
                "canonical_symbol": item.get("canonical_symbol"),
                "leader_symbol": item.get("leader_symbol"),
                "lagger_symbol": item.get("lagger_symbol"),
                "score": metadata.get("universe_score", ""),
                "mexc_spread_bps": metadata.get("spread_bps_mexc", ""),
                "mexc_depth_usd": metadata.get("top5_depth_usd_mexc", ""),
                "binance_volume_24h": metadata.get("quote_volume_binance_24h", ""),
                "mexc_volume_24h": metadata.get("quote_volume_mexc_24h", ""),
            }
        )
    return rows


def _trade_result(payload: dict[str, Any]) -> str:
    decision = str(payload.get("decision_result") or "")
    if decision == "closed":
        pnl = _float(payload.get("realized_pnl_usd"))
        if pnl is None:
            return "closed"
        if pnl > 0:
            return "profit"
        if pnl < 0:
            return "loss"
        return "flat"
    if decision == "filled":
        return "open"
    if decision == "risk_blocked":
        return "blocked"
    if decision == "not_filled":
        return "not filled"
    return decision or "unknown"


def _trade_success(payload: dict[str, Any]) -> str:
    decision = str(payload.get("decision_result") or "")
    if decision == "closed":
        pnl = _float(payload.get("realized_pnl_usd"))
        if pnl is None:
            return "unknown"
        return "yes" if pnl > 0 else "no"
    if decision == "filled":
        return "open"
    if decision == "risk_blocked":
        return "blocked"
    if decision == "not_filled":
        return "not filled"
    return "unknown"


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal_sum(*values: Any) -> str:
    total = Decimal("0")
    for value in values:
        try:
            if value is None or value == "":
                continue
            total += Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
    return str(total)


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0"
    return f"{(numerator / denominator) * 100:.1f}"


def _decimal_percent(numerator: object, denominator: object) -> str:
    try:
        bottom = Decimal(str(denominator))
        if bottom <= 0:
            return "0"
        return str((Decimal(str(numerator)) / bottom) * Decimal("100"))
    except (InvalidOperation, ValueError):
        return "0"


def read_report(root: Path, path: str) -> dict[str, Any]:
    allowed = {item["path"] for item in report_summaries(root)}
    if path not in allowed:
        return {"error": "report_not_allowed"}
    file_path = root / path
    if not file_path.exists():
        return {"error": "report_missing"}
    if file_path.suffix.lower() == ".json":
        return {"path": path, "payload": json.loads(file_path.read_text(encoding="utf-8-sig"))}
    return {"path": path, "text": file_path.read_text(encoding="utf-8-sig")[:20000]}


def render_operator_html() -> str:
    return _HTML


def _tail(value: str, limit: int = 8000) -> str:
    return value[-limit:] if len(value) > limit else value


def _payload_value(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    text = str(value).strip()
    return text or default


def _max_events_for_target(target_closed_trades: str) -> int:
    try:
        target = max(1, int(target_closed_trades))
    except ValueError:
        target = 100
    return max(30000, target * 10000)


def _default_mexc_lagger(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}_USDT"
    return symbol


_HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AlphaFlip Operator Console</title>
  <style>
    :root { --bg:#f4f7f9; --panel:#fff; --ink:#172026; --muted:#5f6f7a; --line:#d8e1e7; --ok:#157f5b; --bad:#b3261e; --warn:#9a5b00; --accent:#0f6b8f; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 "Segoe UI", Arial, sans-serif; }
    .shell { width:min(1320px, calc(100vw - 28px)); margin:0 auto; padding:20px 0 36px; }
    header { display:flex; justify-content:space-between; gap:16px; align-items:center; min-height:76px; border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:26px; letter-spacing:0; }
    h2 { margin:0 0 10px; font-size:17px; }
    h3 { margin:0 0 8px; font-size:14px; }
    .grid { display:grid; grid-template-columns: 1.1fr .9fr; gap:16px; align-items:start; margin-top:16px; }
    .band { border-bottom:1px solid var(--line); padding:16px 0; }
    .panel { background:var(--panel); border:1px solid var(--line); padding:12px; }
    .actions { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:10px; }
    button { min-height:36px; border:1px solid var(--accent); background:var(--accent); color:white; font-weight:700; cursor:pointer; }
    button.secondary { background:white; color:var(--accent); }
    button.danger { border-color:var(--warn); background:var(--warn); }
    input, select { width:100%; min-height:34px; border:1px solid var(--line); padding:6px 8px; background:white; }
    label { display:block; color:var(--muted); font-size:12px; margin:8px 0 4px; }
    table { width:100%; border-collapse:collapse; table-layout:fixed; }
    th, td { text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:8px; overflow-wrap:anywhere; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; }
    code, pre { font-family:Consolas, "Courier New", monospace; font-size:12px; }
    pre { white-space:pre-wrap; max-height:360px; overflow:auto; background:#eef3f6; padding:10px; border:1px solid var(--line); }
    .pill { display:inline-flex; align-items:center; min-height:24px; padding:3px 8px; border:1px solid currentColor; font-weight:700; }
    .ok { color:var(--ok); } .failed { color:var(--bad); } .running { color:var(--warn); }
    .muted { color:var(--muted); }
    .kpis { display:grid; grid-template-columns:repeat(4, minmax(120px, 1fr)); gap:10px; }
    .kpi strong { display:block; font-size:18px; }
    @media (max-width: 900px) { .grid { grid-template-columns:1fr; } .kpis { grid-template-columns:repeat(2, 1fr); } header { align-items:flex-start; flex-direction:column; padding-bottom:14px; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <p class="muted">Binance -> MEXC / local-only</p>
        <h1>AlphaFlip Operator Console</h1>
      </div>
      <span class="pill ok">LIVE DISABLED</span>
    </header>

    <section class="band">
      <div class="kpis" id="safety"></div>
    </section>

    <section class="band">
      <h2>Paper profit</h2>
      <div class="kpis" id="paper-summary"></div>
    </section>

    <section class="band">
      <h2>Universe candidates</h2>
      <div id="universe"></div>
    </section>

    <div class="grid">
      <section class="band">
        <h2>Actions</h2>
        <div class="actions" id="actions"></div>
      </section>
      <section class="band">
        <h2>Live Paper</h2>
        <div class="panel">
          <label>Canonical symbol</label><input id="paper-symbol" value="BTCUSDT">
          <label>Binance leader</label><input id="paper-leader" value="BTCUSDT">
          <label>MEXC lagger</label><input id="paper-lagger" value="BTC_USDT">
          <label>Target closed trades</label><input id="paper-target-trades" value="100">
          <label>Qty</label><input id="paper-qty" value="0.001">
          <label>Stale feed ms</label><input id="paper-stale" value="3000">
          <label>Starting balance USD</label><input id="paper-balance" value="1000">
          <label>Z entry</label><input id="paper-z-entry" value="1.5">
          <label>Min impulse bps</label><input id="paper-impulse" value="1">
          <button onclick="submitLivePaper()">Run Live Paper</button>
          <p class="muted">Public WebSocket paper mode only. No MetaScalp submit and no live trading.</p>
        </div>
      </section>
    </div>

    <div class="grid">
      <section class="band">
        <h2>Demo submit</h2>
        <div class="panel">
          <label>Side</label><select id="demo-side"><option>buy</option><option>sell</option></select>
          <label>Qty</label><input id="demo-qty" value="0.001">
          <label>Price cap</label><input id="demo-price" value="81280">
          <label>Confirmation</label><input id="demo-confirm" placeholder="METASCALP_DEMO_ORDER">
          <button class="danger" onclick="submitDemo()">Submit tiny DemoMode order</button>
          <p class="muted">MetaScalp DemoMode only. The request is rejected without the confirmation phrase.</p>
        </div>
      </section>
    </div>

    <section class="band">
      <h2>Jobs</h2>
      <div id="jobs"></div>
    </section>

    <section class="band">
      <h2>Trades and signals</h2>
      <div id="audit"></div>
    </section>

    <section class="band">
      <h2>Reports</h2>
      <div id="reports"></div>
    </section>

    <section class="band">
      <h2>Output</h2>
      <pre id="output">Waiting...</pre>
    </section>
  </main>
<script>
async function api(path, options) {
  const res = await fetch(path, options || {});
  return await res.json();
}
function esc(v) { return String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
function pill(status) { return `<span class="pill ${esc(status)}">${esc(status)}</span>`; }
async function runAction(id, payload) {
  const data = await api('/api/actions/' + id, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload || {})});
  document.getElementById('output').textContent = JSON.stringify(data, null, 2);
  await load();
}
async function submitDemo() {
  await runAction('demo_submit_tiny', {
    side: document.getElementById('demo-side').value,
    qty: document.getElementById('demo-qty').value,
    price: document.getElementById('demo-price').value,
    confirm: document.getElementById('demo-confirm').value
  });
}
async function submitLivePaper() {
  await runAction('live_paper_30000', {
    symbol: document.getElementById('paper-symbol').value,
    leader_symbol: document.getElementById('paper-leader').value,
    lagger_symbol: document.getElementById('paper-lagger').value,
    target_closed_trades: document.getElementById('paper-target-trades').value,
    qty: document.getElementById('paper-qty').value,
    stale_feed_ms: document.getElementById('paper-stale').value,
    starting_balance_usd: document.getElementById('paper-balance').value,
    z_entry: document.getElementById('paper-z-entry').value,
    min_impulse_bps: document.getElementById('paper-impulse').value
  });
}
async function openReport(path) {
  const data = await api('/api/report?path=' + encodeURIComponent(path));
  document.getElementById('output').textContent = JSON.stringify(data, null, 2);
}
function actionsHtml(actions) {
  return actions.filter(a => !a.needs_confirmation && a.action_id !== 'live_paper_30000').map(a => `<div class="panel"><h3>${esc(a.label)}</h3><p class="muted">${esc(a.description)}</p><button class="secondary" onclick="runAction('${esc(a.action_id)}')">Run</button></div>`).join('');
}
function jobsHtml(jobs) {
  if (!jobs.length) return '<p class="muted">No jobs yet</p>';
  return `<table><thead><tr><th>Job</th><th>Status</th><th>Command</th><th>Stdout</th><th>Stderr</th></tr></thead><tbody>${jobs.map(j => `<tr><td>${esc(j.label)}<br><code>${esc(j.job_id)}</code></td><td>${pill(j.status)}<br>${esc(j.returncode ?? '')}</td><td><code>${esc((j.command || []).join(' '))}</code></td><td><pre>${esc(j.stdout)}</pre></td><td><pre>${esc(j.stderr)}</pre></td></tr>`).join('')}</tbody></table>`;
}
function auditHtml(rows) {
  if (!rows.length) return '<p class="muted">No audit rows yet</p>';
  return `<table><thead><tr><th>Source</th><th>Symbol</th><th>Side</th><th>Success</th><th>Result</th><th>PnL USD</th><th>Fill</th><th>Exit</th><th>Decision</th><th>Reason</th><th>Edge</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.source)}</td><td>${esc(r.symbol)}</td><td>${esc(r.side)}</td><td>${esc(r.success)}</td><td>${esc(r.result)}</td><td>${esc(r.pnl_usd)}</td><td>${esc(r.fill_price)}<br><span class="muted">${esc(r.fill_qty)}</span></td><td>${esc(r.exit_reason)}</td><td>${esc(r.decision)}</td><td>${esc(r.reason)}</td><td>${esc(r.edge_bps)}</td></tr>`).join('')}</tbody></table>`;
}
function reportsHtml(rows) {
  return `<table><thead><tr><th>Report</th><th>Status</th><th>Path</th><th>Bytes</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.label)}</td><td>${r.exists ? pill('ok') : pill('missing')}</td><td><button class="secondary" onclick="openReport('${esc(r.path)}')">${esc(r.path)}</button></td><td>${esc(r.size_bytes)}</td></tr>`).join('')}</tbody></table>`;
}
function useCandidate(canonical, leader, lagger) {
  document.getElementById('paper-symbol').value = canonical || '';
  document.getElementById('paper-leader').value = leader || canonical || '';
  document.getElementById('paper-lagger').value = lagger || '';
}
function universeHtml(rows) {
  if (!rows.length) return '<p class="muted">Run Refresh Universe to rank non-BTC candidates from public exchange snapshots.</p>';
  return `<table><thead><tr><th>Rank</th><th>Symbol</th><th>Score</th><th>MEXC spread</th><th>MEXC depth</th><th>24h volume</th><th>Action</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.rank)}</td><td>${esc(r.canonical_symbol)}<br><span class="muted">${esc(r.leader_symbol)} -> ${esc(r.lagger_symbol)}</span></td><td>${esc(r.score)}</td><td>${esc(r.mexc_spread_bps)}</td><td>${esc(r.mexc_depth_usd)}</td><td><span class="muted">B</span> ${esc(r.binance_volume_24h)}<br><span class="muted">M</span> ${esc(r.mexc_volume_24h)}</td><td><button class="secondary" onclick="useCandidate('${esc(r.canonical_symbol)}','${esc(r.leader_symbol)}','${esc(r.lagger_symbol)}')">Use</button></td></tr>`).join('')}</tbody></table>`;
}
function safetyHtml(s) {
  return Object.entries(s).map(([k,v]) => `<div class="panel kpi"><span class="muted">${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
}
function paperSummaryHtml(s) {
  return [
    ['Total PnL', s.total_pnl_usd ?? '0'],
    ['Symbol', s.canonical_symbol ?? ''],
    ['PnL %', `${s.pnl_pct_of_balance ?? '0'}%`],
    ['Balance', s.starting_balance_usd ?? '0'],
    ['Realized PnL', s.realized_pnl_usd ?? '0'],
    ['Unrealized PnL', s.unrealized_pnl_usd ?? '0'],
    ['Win Rate', `${s.win_rate_pct ?? '0'}%`],
    ['Wins', s.winning_trades ?? 0],
    ['Fills', s.fills ?? 0],
    ['Closed', s.closed_positions ?? 0],
    ['Target', s.target_closed_trades ?? 0],
    ['Stop', s.stop_reason ?? ''],
    ['Open', s.open_positions ?? 0],
    ['Signals', s.intents ?? 0]
  ].map(([k,v]) => `<div class="panel kpi"><span class="muted">${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
}
async function load() {
  const state = await api('/api/state');
  document.getElementById('safety').innerHTML = safetyHtml(state.safety);
  document.getElementById('paper-summary').innerHTML = paperSummaryHtml(state.paper_summary || {});
  document.getElementById('universe').innerHTML = universeHtml(state.universe_candidates || []);
  document.getElementById('actions').innerHTML = actionsHtml(state.actions);
  document.getElementById('jobs').innerHTML = jobsHtml(state.jobs);
  document.getElementById('audit').innerHTML = auditHtml(state.latest_audit);
  document.getElementById('reports').innerHTML = reportsHtml(state.reports);
}
load();
setInterval(load, 3000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
