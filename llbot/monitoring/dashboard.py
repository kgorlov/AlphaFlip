"""Static read-only operations dashboard rendering."""

import html
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardArtifacts:
    health: dict[str, Any] | None = None
    runner_summary: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    reports: tuple["DashboardReportLink", ...] = ()
    history: tuple["DashboardHistoryPoint", ...] = ()


@dataclass(frozen=True, slots=True)
class DashboardReportLink:
    label: str
    path: str
    exists: bool
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class DashboardHistoryPoint:
    label: str
    path: str
    feed_max_gap_ms: Decimal
    intents: Decimal
    fills: Decimal
    pnl_usd: Decimal
    health_state: Decimal


def load_dashboard_artifacts(
    *,
    health_path: str | Path | None = None,
    runner_summary_path: str | Path | None = None,
    memory_path: str | Path | None = None,
    report_paths: dict[str, str | Path] | None = None,
    history_paths: dict[str, str | Path] | None = None,
) -> DashboardArtifacts:
    return DashboardArtifacts(
        health=_load_json(health_path),
        runner_summary=_load_json(runner_summary_path),
        memory=_load_json(memory_path),
        reports=_report_links(report_paths or {}),
        history=_history_points(history_paths or {}),
    )


def render_dashboard(artifacts: DashboardArtifacts) -> str:
    health = artifacts.health or {}
    runner = artifacts.runner_summary or {}
    memory = artifacts.memory or {}

    system = _dict(health.get("system"))
    components = _list(system.get("components"))
    safety = _dict(health.get("safety"))
    paper_summary = _dict(runner.get("paper_summary"))
    runner_limits = _dict(runner.get("runner_limits"))
    runner_health = _dict(runner.get("health"))
    streams = _dict(runner_health.get("streams"))
    metascalp = _dict(runner.get("metascalp"))
    progress = _dict(memory.get("codex_progress"))

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Lead-Lag Ops Dashboard</title>",
            "<style>",
            _CSS,
            "</style>",
            "</head>",
            "<body>",
            '<main class="shell">',
            _header(system),
            _section("System Health", _components_table(components)),
            _section("Feed Streams", _streams_table(streams, runner_limits)),
            _section("MetaScalp", _key_values(metascalp)),
            _section("Paper Summary", _key_values(paper_summary)),
            _section("Historical Sparklines", _history_sparklines(artifacts.history)),
            _section("Reports", _reports_table(artifacts.reports)),
            _section("Safety", _key_values(safety)),
            _section("Progress", _key_values(progress)),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def write_dashboard(path: str | Path, artifacts: DashboardArtifacts) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_dashboard(artifacts), encoding="utf-8")


def _header(system: dict[str, Any]) -> str:
    status = str(system.get("status", "unknown"))
    return (
        '<header class="topbar">'
        "<div>"
        '<p class="eyebrow">Binance -> MEXC</p>'
        "<h1>Lead-Lag Ops Dashboard</h1>"
        "</div>"
        f'<div class="status status-{_class_name(status)}">{_esc(status.upper())}</div>'
        "</header>"
    )


def _section(title: str, body: str) -> str:
    return f'<section class="band"><h2>{_esc(title)}</h2>{body}</section>'


def _components_table(components: list[Any]) -> str:
    rows = []
    for component in components:
        item = _dict(component)
        status = str(item.get("status", "unknown"))
        rows.append(
            "<tr>"
            f"<td>{_esc(item.get('name', 'unknown'))}</td>"
            f'<td><span class="pill pill-{_class_name(status)}">{_esc(status)}</span></td>'
            f"<td>{_esc(item.get('reason', 'unknown'))}</td>"
            f"<td><code>{_esc(_compact_json(item.get('metadata', {})))}</code></td>"
            "</tr>"
        )
    return _table(("Component", "Status", "Reason", "Metadata"), rows)


def _streams_table(streams: dict[str, Any], runner_limits: dict[str, Any]) -> str:
    counts = _dict(runner_limits.get("stream_event_counts"))
    keys = sorted(set(streams) | set(counts))
    rows = []
    for key in keys:
        stream = _dict(streams.get(key))
        rows.append(
            "<tr>"
            f"<td>{_esc(key)}</td>"
            f"<td>{_esc(stream.get('book_ticker_events', counts.get(key, 0)))}</td>"
            f"<td>{_esc(stream.get('max_gap_ms', ''))}</td>"
            f"<td>{_esc(stream.get('stale_gap_count', ''))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="4" class="muted">No feed stream data</td></tr>')
    return _table(("Stream", "Quotes", "Max Gap Ms", "Stale Gaps"), rows)


def _reports_table(reports: tuple[DashboardReportLink, ...]) -> str:
    rows = []
    for report in reports:
        status = "exists" if report.exists else "missing"
        link = (
            f'<a href="{_esc(_href(report.path))}">{_esc(report.path)}</a>'
            if report.exists
            else _esc(report.path)
        )
        size = "" if report.size_bytes is None else str(report.size_bytes)
        rows.append(
            "<tr>"
            f"<td>{_esc(report.label)}</td>"
            f'<td><span class="pill pill-{_class_name(status)}">{_esc(status)}</span></td>'
            f"<td>{link}</td>"
            f"<td>{_esc(size)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="4" class="muted">No report links configured</td></tr>')
    return _table(("Report", "Status", "Path", "Bytes"), rows)


def _history_sparklines(history: tuple[DashboardHistoryPoint, ...]) -> str:
    if not history:
        return '<p class="muted">No historical report data</p>'
    rows = [
        _sparkline_row("Feed Max Gap Ms", [point.feed_max_gap_ms for point in history]),
        _sparkline_row("Intents", [point.intents for point in history]),
        _sparkline_row("Fills", [point.fills for point in history]),
        _sparkline_row("PnL USD", [point.pnl_usd for point in history]),
        _sparkline_row("Health State", [point.health_state for point in history]),
    ]
    return (
        '<div class="history-grid">'
        + "".join(rows)
        + "</div>"
        + _table(
            ("Label", "Feed Gap", "Intents", "Fills", "PnL", "Health", "Path"),
            [
                "<tr>"
                f"<td>{_esc(point.label)}</td>"
                f"<td>{_esc(point.feed_max_gap_ms)}</td>"
                f"<td>{_esc(point.intents)}</td>"
                f"<td>{_esc(point.fills)}</td>"
                f"<td>{_esc(point.pnl_usd)}</td>"
                f"<td>{_esc(point.health_state)}</td>"
                f"<td>{_esc(point.path)}</td>"
                "</tr>"
                for point in history
            ],
        )
    )


def _sparkline_row(label: str, values: list[Decimal]) -> str:
    return (
        '<div class="spark-item">'
        f"<div><strong>{_esc(label)}</strong><span>{_esc(_value_range(values))}</span></div>"
        f'{_sparkline_svg(values)}'
        "</div>"
    )


def _sparkline_svg(values: list[Decimal]) -> str:
    width = Decimal("160")
    height = Decimal("42")
    if len(values) == 1:
        y = height / Decimal("2")
        points = f"0,{y} {width},{y}"
    else:
        min_value = min(values)
        max_value = max(values)
        span = max_value - min_value
        step = width / Decimal(len(values) - 1)
        coords = []
        for idx, value in enumerate(values):
            x = step * Decimal(idx)
            if span == 0:
                y = height / Decimal("2")
            else:
                y = height - ((value - min_value) / span * height)
            coords.append(f"{_svg_num(x)},{_svg_num(y)}")
        points = " ".join(coords)
    return (
        '<svg class="spark" viewBox="0 0 160 42" role="img" aria-label="sparkline">'
        f'<polyline points="{_esc(points)}"></polyline>'
        "</svg>"
    )


def _key_values(payload: dict[str, Any]) -> str:
    if not payload:
        return '<p class="muted">No data</p>'
    rows = [
        f"<tr><td>{_esc(key)}</td><td><code>{_esc(_value(value))}</code></td></tr>"
        for key, value in sorted(payload.items())
    ]
    return _table(("Key", "Value"), rows)


def _table(headers: tuple[str, ...], rows: list[str]) -> str:
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "".join(rows)
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _load_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _history_points(history_paths: dict[str, str | Path]) -> tuple[DashboardHistoryPoint, ...]:
    points: list[DashboardHistoryPoint] = []
    for label, raw_path in history_paths.items():
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        payload = _load_json(path)
        if payload is None:
            continue
        points.append(_history_point(str(label), path.as_posix(), payload))
    return tuple(points)


def _history_point(label: str, path: str, payload: dict[str, Any]) -> DashboardHistoryPoint:
    summary = _dict(payload.get("summary")) or _dict(payload.get("paper_summary")) or payload
    return DashboardHistoryPoint(
        label=label,
        path=path,
        feed_max_gap_ms=_max_feed_gap(payload),
        intents=_decimal(summary.get("intents")),
        fills=_decimal(summary.get("fills")),
        pnl_usd=_decimal(summary.get("realized_pnl_usd")) + _decimal(summary.get("unrealized_pnl_usd")),
        health_state=_health_state(payload),
    )


def _report_links(report_paths: dict[str, str | Path]) -> tuple[DashboardReportLink, ...]:
    links = []
    for label, raw_path in report_paths.items():
        path = Path(raw_path)
        exists = path.exists() and path.is_file()
        links.append(
            DashboardReportLink(
                label=str(label),
                path=path.as_posix(),
                exists=exists,
                size_bytes=path.stat().st_size if exists else None,
            )
        )
    return tuple(links)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _value(value: Any) -> str:
    if isinstance(value, dict | list):
        return _compact_json(value)
    return str(value)


def _max_feed_gap(payload: dict[str, Any]) -> Decimal:
    streams = _dict(_dict(payload.get("feed_health")).get("streams"))
    values = [_decimal(_dict(stream).get("max_gap_ms")) for stream in streams.values()]
    if values:
        return max(values)
    health = _dict(payload.get("health"))
    streams = _dict(health.get("streams"))
    values = [_decimal(_dict(stream).get("max_gap_ms")) for stream in streams.values()]
    return max(values) if values else Decimal("0")


def _health_state(payload: dict[str, Any]) -> Decimal:
    status = str(_dict(payload.get("system")).get("status", "")).lower()
    if not status:
        status = str(_dict(_dict(payload.get("feed_health")).get("decision")).get("reason", "")).lower()
    if status in {"ok", "healthy"}:
        return Decimal("1")
    if status in {"warn", "warning", "stale_stream", "missing_stream"}:
        return Decimal("0.5")
    if status in {"critical", "error"}:
        return Decimal("0")
    return Decimal("1") if not status else Decimal("0.5")


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _value_range(values: list[Decimal]) -> str:
    if not values:
        return ""
    return f"{min(values)} -> {max(values)}"


def _svg_num(value: Decimal) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _href(path: str) -> str:
    return path.replace("\\", "/")


def _class_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-") or "unknown"


_CSS = """
:root {
  color-scheme: light;
  --bg: #f5f7f9;
  --ink: #172026;
  --muted: #62717c;
  --line: #d8e0e6;
  --panel: #ffffff;
  --ok: #157f5b;
  --warn: #a15c00;
  --critical: #b3261e;
  --unknown: #59636c;
  --accent: #0f6b8f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 14px;
}
.shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 24px 0 36px;
}
.topbar {
  min-height: 96px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--line);
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0;
}
h2 {
  margin: 0 0 12px;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0;
}
.band {
  padding: 22px 0;
  border-bottom: 1px solid var(--line);
}
.status,
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border: 1px solid currentColor;
  font-weight: 700;
  line-height: 1;
}
.status-ok,
.pill-ok { color: var(--ok); }
.status-warn,
.pill-warn { color: var(--warn); }
.status-critical,
.pill-critical { color: var(--critical); }
.status-unknown,
.pill-unknown { color: var(--unknown); }
.table-wrap {
  overflow-x: auto;
  background: var(--panel);
  border: 1px solid var(--line);
}
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}
tbody tr:last-child td { border-bottom: 0; }
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  color: #24323b;
}
.muted { color: var(--muted); }
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.spark-item {
  min-height: 82px;
  padding: 10px 12px;
  background: var(--panel);
  border: 1px solid var(--line);
}
.spark-item div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.spark-item span {
  color: var(--muted);
  font-size: 12px;
}
.spark {
  display: block;
  width: 100%;
  height: 42px;
}
.spark polyline {
  fill: none;
  stroke: var(--accent);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}
@media (max-width: 680px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
    padding-bottom: 18px;
  }
  h1 { font-size: 23px; }
  th,
  td { padding: 9px 10px; }
}
"""
