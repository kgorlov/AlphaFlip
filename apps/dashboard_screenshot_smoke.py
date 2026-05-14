"""Capture desktop/mobile screenshots of the static dashboard with a local browser."""

import argparse
import json
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.storage.audit_jsonl import write_json

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

DEFAULT_BROWSER_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


@dataclass(frozen=True, slots=True)
class Viewport:
    name: str
    width: int
    height: int
    out: Path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture read-only dashboard screenshots with local headless Chrome/Edge. "
            "No server, orders, secrets, or live trading are used."
        )
    )
    parser.add_argument("--dashboard", default="reports/dashboard.html")
    parser.add_argument("--browser", help="Path to chrome.exe or msedge.exe.")
    parser.add_argument("--desktop-out", default="reports/dashboard_desktop_smoke.png")
    parser.add_argument("--mobile-out", default="reports/dashboard_mobile_smoke.png")
    parser.add_argument("--desktop-size", default="1440x1100")
    parser.add_argument("--mobile-size", default="390x900")
    parser.add_argument("--out", default="reports/dashboard_screenshot_smoke.json")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    browser = Path(args.browser) if args.browser else discover_browser()
    dashboard = Path(args.dashboard).resolve()
    if not dashboard.exists() or not dashboard.is_file():
        raise SystemExit(f"Dashboard HTML not found: {dashboard}")
    if browser is None:
        raise SystemExit("No local Chrome or Edge executable found for screenshot smoke")

    viewports = (
        _viewport("desktop", args.desktop_size, args.desktop_out),
        _viewport("mobile", args.mobile_size, args.mobile_out),
    )
    with tempfile.TemporaryDirectory(prefix="leadlag-dashboard-smoke-") as user_data_dir:
        for viewport in viewports:
            capture_screenshot(browser, dashboard, viewport, Path(user_data_dir))

    captures = [validate_png(viewport.out) | {"name": viewport.name} for viewport in viewports]
    return {
        "dashboard": str(dashboard),
        "browser": str(browser),
        "captures": captures,
        "read_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "secrets_read": False,
        "live_trading_enabled": False,
    }


def discover_browser() -> Path | None:
    for raw_path in DEFAULT_BROWSER_PATHS:
        path = Path(raw_path)
        if path.exists() and path.is_file():
            return path
    return None


def capture_screenshot(
    browser: Path,
    dashboard: Path,
    viewport: Viewport,
    user_data_dir: Path,
) -> None:
    viewport.out.parent.mkdir(parents=True, exist_ok=True)
    url = dashboard.as_uri()
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-features=VizDisplayCompositor",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={viewport.width},{viewport.height}",
        f"--screenshot={viewport.out.resolve()}",
        url,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0:
        raise SystemExit(
            "Dashboard screenshot failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or str(completed.returncode))
        )


def validate_png(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != PNG_SIGNATURE:
        raise SystemExit(f"Screenshot is not a valid PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise SystemExit(f"Screenshot PNG has invalid dimensions: {path}")
    return {
        "path": str(path),
        "bytes": len(data),
        "width": width,
        "height": height,
        "valid_png": True,
    }


def _viewport(name: str, raw_size: str, out: str) -> Viewport:
    width, height = _parse_size(raw_size)
    return Viewport(name=name, width=width, height=height, out=Path(out))


def _parse_size(value: str) -> tuple[int, int]:
    if "x" not in value:
        raise SystemExit("Viewport size must use WIDTHxHEIGHT")
    raw_width, raw_height = value.lower().split("x", 1)
    width = int(raw_width)
    height = int(raw_height)
    if width <= 0 or height <= 0:
        raise SystemExit("Viewport dimensions must be positive")
    return width, height


if __name__ == "__main__":
    main()
