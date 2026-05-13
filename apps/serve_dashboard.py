"""Serve the static dashboard on a local-only HTTP address."""

import argparse
import functools
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    args = build_parser().parse_args()
    serve_dashboard(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the read-only static dashboard locally.")
    parser.add_argument("--dashboard", default="reports/dashboard.html")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def serve_dashboard(args: argparse.Namespace) -> None:
    validate_local_host(args.host)
    dashboard = Path(args.dashboard).resolve()
    if not dashboard.exists():
        raise SystemExit(f"Dashboard file does not exist: {dashboard}")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(dashboard.parent))
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    payload = {
        "url": f"http://{args.host}:{args.port}/{dashboard.name}",
        "directory": str(dashboard.parent),
        "read_only": True,
        "orders_submitted": False,
        "orders_cancelled": False,
        "live_trading_enabled": False,
    }
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def validate_local_host(host: str) -> None:
    if host not in LOCAL_HOSTS:
        raise SystemExit("--host must be local-only: 127.0.0.1, localhost, or ::1")


if __name__ == "__main__":
    main()
