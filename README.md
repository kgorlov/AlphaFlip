# AlphaFlip

AlphaFlip is a Python 3.12 research and execution-control project for a Binance -> MEXC lead-lag trading bot.

The current implementation is built around safe paper trading, replay, observability, and guarded MetaScalp demo execution. Live trading is disabled by default and is not part of the current operational path.

## What It Does

- Uses Binance as the leading/reference market-data venue.
- Uses MEXC as the lagging/execution venue.
- Supports explicit market profiles:
  - `spot_to_spot`: Binance spot -> MEXC spot.
  - `perp_to_perp`: Binance USD-M perpetual -> MEXC USDT perpetual.
- Reads low-latency public market data directly from official exchange WebSocket APIs.
- Uses MetaScalp local API as the v1 MEXC execution bridge.
- Runs deterministic replay and paper trading before any demo execution.
- Records audit, health, replay, fill comparison, dashboard, and daily summary artifacts under `reports/`.

## Safety Defaults

AlphaFlip is intentionally conservative:

- live trading is disabled by default;
- LLMs are not in the live signal or execution path;
- public market-data collectors have no order route;
- paper runners do not contact MetaScalp;
- MetaScalp demo order and cancel CLIs are dry-run by default;
- real MetaScalp demo POST calls require explicit confirmation strings;
- secrets, `.env`, PEM/key files, and local MetaScalp user settings must not be committed.

This repository is engineering/research software, not financial advice.

## Repository Layout

```text
apps/       CLI entry points for replay, paper, MetaScalp demo, health, dashboard, and reports
conf/       Example configuration
docs/       Architecture, runbook, and wiki source pages
llbot/      Typed implementation modules
memory/     Compact project state for agent-assisted development
reports/    Local validation, smoke, health, dashboard, and research artifacts
tests/      Unit tests and safe CLI smoke tests
references/ Research-only upstream repositories as submodules
```

## Requirements

- Windows PowerShell commands in the runbook assume Windows.
- Python 3.12.
- Optional: local MetaScalp running on `127.0.0.1:17845-17855` for MetaScalp discovery and demo-mode checks.

Install:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Clone with reference repositories:

```powershell
git clone --recurse-submodules https://github.com/kgorlov/AlphaFlip.git
```

If already cloned:

```powershell
git submodule update --init --recursive
```

## Validate

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Current baseline at publication: 163 unit tests pass.

## Common Safe Commands

Probe local MetaScalp:

```powershell
.\.venv\Scripts\python.exe apps\probe_metascalp.py
```

Run replay-backed paper trading from local JSONL:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json
```

Run a bounded public WebSocket paper pass:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 100 --symbol BTCUSDT --leader-symbol BTCUSDT --lagger-symbol BTC_USDT --min-samples 1 --stale-feed-ms 1500 --summary-out reports\runner_paper_live_ws_summary.json
```

Build a read-only operations dashboard:

```powershell
.\.venv\Scripts\python.exe apps\refresh_dashboard.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health-out reports\health_check_metascalp_smoke.json --dashboard-out reports\dashboard.html
```

Serve the dashboard locally:

```powershell
.\.venv\Scripts\python.exe apps\serve_dashboard.py --dashboard reports\dashboard.html --host 127.0.0.1 --port 8765
```

Plan a MetaScalp demo order without submitting:

```powershell
.\.venv\Scripts\python.exe apps\metascalp_demo_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_demo_order_dry_run_smoke.json
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Runbook](docs/RUNBOOK.md)
- [Wiki source](docs/wiki/Home.md)
- [Task checklist](TASKS.md)

The GitHub Wiki mirrors the files in `docs/wiki/` when wiki publishing is available.

## Status

Implemented areas include:

- Binance and MEXC public market-data adapters for the active futures path.
- Replay JSONL and Parquet conversion.
- Residual z-score and impulse-transfer signal models.
- Online lag calibration and feature store utilities.
- Risk gates, paper fill models, paper position lifecycle, and PnL summaries.
- MetaScalp discovery, guarded demo order/cancel paths, private update capture, and offline reconciliation.
- DuckDB storage, health checks, alert records, daily summaries, and static dashboard generation.

Notable remaining work is tracked in [TASKS.md](TASKS.md), including MEXC spot protobuf parsing, top-N live universe rotation, additional exit logic, and broader day-level replay comparisons.
