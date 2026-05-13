# Operations

All commands are intended to run from the repository root in PowerShell.

## Validate

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

## Probe MetaScalp

```powershell
.\.venv\Scripts\python.exe apps\probe_metascalp.py
```

MetaScalp discovery scans `127.0.0.1:17845-17855`.

## Capture Public Market Data

Binance USD-M book ticker:

```powershell
.\.venv\Scripts\python.exe apps\collect_market.py --venue binance-usdm --symbol BTCUSDT --events 20 --out data\replay\binance_usdm_BTCUSDT.jsonl --open-timeout-sec 30
```

MEXC contract ticker/depth:

```powershell
.\.venv\Scripts\python.exe apps\collect_market.py --venue mexc-contract --symbol BTC_USDT --events 20 --out data\replay\mexc_contract_BTC_USDT.jsonl --mexc-depth --open-timeout-sec 30
```

These commands only read public market data.

## Replay And Paper

Replay saved JSONL through paper trading:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json
```

Bounded public WebSocket paper pass:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 100 --symbol BTCUSDT --leader-symbol BTCUSDT --lagger-symbol BTC_USDT --min-samples 1 --stale-feed-ms 1500 --summary-out reports\runner_paper_live_ws_summary.json --health-out reports\runner_paper_live_ws_health.json
```

The paper runner does not contact MetaScalp.

## MetaScalp Demo Runner

Dry-run bridge from public signals to MetaScalp demo audit records:

```powershell
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 100 --connection-id 4 --summary-out reports\metascalp_demo_runner_summary.json --paper-audit-out reports\metascalp_demo_runner_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_orders.jsonl
```

Real demo POST requires explicit confirmation:

```powershell
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 500 --connection-id 4 --max-demo-orders 1 --submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER --summary-out reports\metascalp_demo_runner_submit_summary.json --paper-audit-out reports\metascalp_demo_runner_submit_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_submit_orders.jsonl
```

## Health And Dashboard

Build health report:

```powershell
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --discover-metascalp --select-demo-mexc --db reports\health_check_smoke.duckdb --out reports\health_check_metascalp_smoke.json
```

Refresh static dashboard:

```powershell
.\.venv\Scripts\python.exe apps\refresh_dashboard.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health-out reports\health_check_metascalp_smoke.json --dashboard-out reports\dashboard.html
```

Serve static dashboard locally:

```powershell
.\.venv\Scripts\python.exe apps\serve_dashboard.py --dashboard reports\dashboard.html --host 127.0.0.1 --port 8765
```

The dashboard is read-only and has no order controls.

## Reports

Useful local artifacts:

- `reports/latest_test_report.md`
- `reports/current_execplan.md`
- `reports/dashboard.html`
- `reports/daily_summary_smoke.json`
- `reports/replay_research_smoke.json`
- `reports/demo_fill_compare_smoke.json`
- `reports/metascalp_reconcile_smoke.json`
