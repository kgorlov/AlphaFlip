# Runbook

All commands are intended to be run from the project root in PowerShell.

## Environment

Create or refresh the local Python 3.12 environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Run validation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

## Safe Local Checks

Probe MetaScalp local API:

```powershell
.\.venv\Scripts\python.exe apps\probe_metascalp.py
```

Build a dry-run MetaScalp order request without submitting it:

```powershell
.\.venv\Scripts\python.exe apps\plan_metascalp_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_order_dry_run_smoke.json
```

This command performs local validation and writes an audit-shaped JSON payload with `ClientId` and `ExecutionTimeMs` placeholders. It does not discover MetaScalp, does not call `POST /api/connections/{id}/orders`, and does not submit or cancel orders.

Build the same guarded MetaScalp demo order through the executable CLI in dry-run mode:

```powershell
.\.venv\Scripts\python.exe apps\metascalp_demo_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_demo_order_dry_run_smoke.json
```

The demo order CLI remains dry-run by default. A real demo submit is only available with `--discover --submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER`, which forces local MetaScalp discovery and selection of a connected `DemoMode=true` MEXC connection before calling `POST /api/connections/{id}/orders`. Live mode is not exposed by this CLI and is rejected by the executor.
Order lifecycle code can now track accepted/unknown/rejected states, reconcile fill/cancel/reject events, and build TTL cancel plans.

Build a guarded MetaScalp demo cancel through the executable CLI in dry-run mode:

```powershell
.\.venv\Scripts\python.exe apps\metascalp_demo_cancel.py --connection-id 11 --intent-id smoke-demo-order --client-id llb-smoke-demo-order --order-id ord-1 --symbol BTC_USDT --reason ttl_expired --due-ts-ms 4000 --out reports\metascalp_demo_cancel_dry_run_smoke.json
```

The demo cancel CLI remains dry-run by default. A real demo cancel is only available with `--discover --submit-demo --confirm-demo-cancel METASCALP_DEMO_CANCEL`, which verifies a connected `DemoMode=true` MEXC connection before calling `POST /api/connections/{id}/orders/cancel`. The project still has no MetaScalp WebSocket order/position/balance subscription.

Replay captured MetaScalp private updates into local reconciliation state:

```powershell
.\.venv\Scripts\python.exe apps\reconcile_metascalp_updates.py --order smoke-demo-order:llb-smoke-demo-order:BTC_USDT:2:11:ord-1 --updates reports\metascalp_updates_smoke.jsonl --out reports\metascalp_reconcile_smoke.json
```

The reconciliation CLI is offline-only: it reads JSONL updates from a file or stdin, normalizes order/position/balance payloads, applies order events to local open-order state, and writes an audit report. It does not open WebSocket connections, submit orders, cancel orders, or read secrets.

Compare internal paper fills with reconciled MetaScalp demo fills:

```powershell
.\.venv\Scripts\python.exe apps\compare_demo_fills.py --paper-audit reports\paper_fill_smoke.jsonl --reconciled reports\metascalp_reconcile_smoke.json --out reports\demo_fill_compare_smoke.json
```

The comparison report is offline-only. It matches fills by traceable client order ID, reports paper/demo quantity and average price differences, and lists unmatched paper or demo fills.

Store reconciled MetaScalp private state in local DuckDB:

```powershell
.\.venv\Scripts\python.exe apps\store_metascalp_reconcile.py --reconciled reports\metascalp_reconcile_smoke.json --db reports\metascalp_private_smoke.duckdb --summary-out reports\metascalp_private_store_smoke.json
```

The storage CLI is offline-only. It loads a reconciliation report into queryable `metascalp_orders`, `metascalp_fills`, `metascalp_positions`, `metascalp_balances`, and `metascalp_reconciliation_audit` tables. It does not open WebSocket connections, submit orders, cancel orders, or read secrets.
The DuckDB schema also includes broad local research tables for market quotes, trades, signal intents, order facts, fill facts, and PnL facts.

Export replay JSONL market data to Parquet:

```powershell
.\.venv\Scripts\python.exe apps\export_replay_parquet.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --out reports\replay_smoke.parquet
```

This is an offline conversion from local public replay files. It does not contact exchanges or MetaScalp.

Replay one saved trading day from Parquet or DuckDB:

```powershell
.\.venv\Scripts\python.exe apps\replay_day.py --day 2026-05-13 --parquet reports\replay_smoke.parquet --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --out reports\replay_day_smoke.json --audit-out reports\replay_day_audit_smoke.jsonl --research-out reports\replay_day_research_smoke.json
```

The day replay command is offline-only. It reads local Parquet and/or DuckDB market tables, filters events by `captured_at_utc` day, runs the shared paper engine, and writes summary/audit/research artifacts. It does not contact exchanges or MetaScalp, submit/cancel orders, read secrets, or enable live trading.

Build a daily summary report from existing local artifacts:

```powershell
.\.venv\Scripts\python.exe apps\daily_summary.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health reports\health_check_metascalp_smoke.json --research reports\replay_research_smoke.json --fill-compare reports\demo_fill_compare_smoke.json --reconciliation reports\metascalp_reconcile_smoke.json --out reports\daily_summary_smoke.json
```

The daily summary is read-only and reports paper counts, health alert counts, research/fill-comparison counts, reconciliation counts, and safety flags.

Build a safe local health report from the latest runner summary and execution storage:

```powershell
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --db reports\health_check_smoke.duckdb --out reports\health_check_smoke.json
```

Include local MetaScalp discovery and connected MEXC DemoMode selection:

```powershell
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --discover-metascalp --select-demo-mexc --db reports\health_check_smoke.duckdb --out reports\health_check_metascalp_smoke.json
```

The health check CLI reports data-feed, MetaScalp, storage, and risk-state components. It does not submit orders, cancel orders, read secrets, or enable live trading.
Health reports also include deterministic alert records for missing/stale feeds, MetaScalp disconnects, and active risk stops. A healthy smoke should show `"alerts":[]`.

Build the read-only local operations dashboard:

```powershell
.\.venv\Scripts\python.exe apps\build_dashboard.py --health reports\health_check_metascalp_smoke.json --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --memory memory\memory.json --out reports\dashboard.html
```

The dashboard includes links to replay research, demo fill comparison, private reconciliation, and private capture summary reports when those local artifacts exist. You can add more links with repeated `--report-link "Label=path"` arguments.

Open `reports\dashboard.html` in a browser. The dashboard is a static artifact generated from local JSON files; it does not run a server, submit orders, cancel orders, request secrets, or enable live trading.

Refresh health and dashboard artifacts with one read-only command:

```powershell
.\.venv\Scripts\python.exe apps\refresh_dashboard.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health-out reports\health_check_metascalp_smoke.json --dashboard-out reports\dashboard.html
```

The refresh workflow runs the local health report builder and static dashboard builder. It does not submit orders, cancel orders, read secrets, or enable live trading.

Serve the static dashboard on a local-only HTTP address:

```powershell
.\.venv\Scripts\python.exe apps\serve_dashboard.py --dashboard reports\dashboard.html --host 127.0.0.1 --port 8765
```

The server only serves static files from the dashboard directory and rejects non-local bind hosts.

Capture MetaScalp private WebSocket updates to JSONL:

```powershell
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --discover --select-demo-mexc --events 20 --out reports\metascalp_private_capture.jsonl --summary-out reports\metascalp_private_capture.json
```

The private capture CLI only reads WebSocket messages. It does not submit orders, cancel orders, read secrets, or enable live trading. The documented MetaScalp local WebSocket endpoint is `ws://127.0.0.1:{port}/`, using the same port discovered by `GET /ping`. `--select-demo-mexc` lists connections and subscribes the first connected `DemoMode=true` MEXC connection with `{"Type":"subscribe","Data":{"ConnectionId":...}}`.

You can also pass an explicit connection:

```powershell
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --ws-url ws://127.0.0.1:17845/ --connection-id 11 --events 20 --out reports\metascalp_private_capture.jsonl
```

For a bounded smoke that exits if no private updates arrive after the subscribe acknowledgement:

```powershell
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --discover --select-demo-mexc --events 10 --idle-timeout-sec 5 --out reports\metascalp_private_real_bounded.jsonl --summary-out reports\metascalp_private_real_bounded.json
```

Dry smoke without opening a WebSocket:

```powershell
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --events 0 --out reports\metascalp_private_capture_smoke.jsonl --summary-out reports\metascalp_private_capture_smoke.json
```

Replay an existing captured/private JSONL file through reconciliation and DuckDB storage:

```powershell
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --read-existing --events 0 --out reports\metascalp_updates_smoke.jsonl --order smoke-demo-order:llb-smoke-demo-order:BTC_USDT:2:11:ord-1 --reconcile-out reports\metascalp_private_capture_reconcile_smoke.json --db reports\metascalp_private_capture_smoke.duckdb --source metascalp-private-capture-smoke --summary-out reports\metascalp_private_capture_store_smoke.json
```

Hydrate the Binance/MEXC universe through public REST:

```powershell
.\.venv\Scripts\python.exe apps\hydrate_universe.py --depth-limit 1
```

## Public Market Data Capture

These commands only read public WebSocket market data and write replay JSONL. They do not submit, cancel, or route orders.

Scanner-mode WebSocket planning is implemented in `llbot.service.ws_runtime`. Use `WebSocketRuntimeConfig` to keep stream shards bounded, schedule reconnects before the 24h WebSocket limit, and pass explicit `ping_interval`/`ping_timeout` settings into websocket clients. The helper layer is deterministic and offline: it builds stream specs only and does not open sockets.

Capture Binance USD-M bookTicker:

```powershell
.\.venv\Scripts\python.exe apps\collect_market.py --venue binance-usdm --symbol BTCUSDT --events 20 --out data\replay\binance_usdm_BTCUSDT.jsonl --open-timeout-sec 30
```

Capture Binance USD-M aggregate trades or partial depth:

```powershell
.\.venv\Scripts\python.exe apps\collect_market.py --venue binance-usdm --symbol BTCUSDT --events 20 --binance-trade --out data\replay\binance_usdm_trades_BTCUSDT.jsonl --open-timeout-sec 30
.\.venv\Scripts\python.exe apps\collect_market.py --venue binance-usdm --symbol BTCUSDT --events 20 --binance-depth --out data\replay\binance_usdm_depth_BTCUSDT.jsonl --open-timeout-sec 30
```

Impulse-transfer signals can optionally require recent Binance trade aggression and/or order-book imbalance. These confirmations are local signal gates only; they do not submit or cancel orders.

Capture MEXC contract depth/ticker:

```powershell
.\.venv\Scripts\python.exe apps\collect_market.py --venue mexc-contract --symbol BTC_USDT --events 20 --out data\replay\mexc_contract_BTC_USDT.jsonl --mexc-depth --open-timeout-sec 30
```

## Replay Signal Check

Replay saved market data through the deterministic signal engines:

```powershell
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl
```

This command reads replay JSONL, emits signal intents only when requested with `--print-intents`, and does not submit, cancel, or route orders.

Run the same replay through paper risk gates and quote fill simulation:

```powershell
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --paper --fill-model touch --audit-out reports\replay_paper_audit.jsonl
```

The paper path writes replay audit JSONL for generated signal decisions. It remains local and does not contact MetaScalp or any exchange.
Paper replay summaries include risk/fill counts, open/closed paper position counts, and realized TTL-exit PnL.
Use `--take-profit-bps`, `--fee-bps`, and `--slippage-bps` to include take-profit exits and cost-adjusted PnL summaries.
Use `--stale-feed-ms` to stop paper positions when the Binance reference quote is stale, and `--summary-out reports\replay_paper_summary.json` to persist the summary JSON.
Use `--research-report-out reports\replay_research.json --compare-fill-models` to persist feed-health metrics, per-symbol/day slices, and fill-model variant summaries.
Research reports include reusable feed-health gate decisions and candidate-level fill-model diagnostics keyed by signal intent ID.
When `--stale-feed-ms` is set, replay-paper also maps feed-health decisions into risk metadata so entries are risk-blocked with `binance_feed_stale` or `mexc_feed_stale`.

Run the safe paper runner over saved replay JSONL:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json
```

`apps\runner_paper.py` uses the shared paper runner service, risk gates, feed-health metadata, and paper fill models. Replay mode remains local and does not contact MetaScalp or any exchange.
Signal research utilities now include an offline online-lag calibrator with default candidate lags `[25, 50, 100, 200, 500, 1000]` ms and a typed feature store for residual, impulse, imbalance, spread, volatility, and latency features. These utilities are deterministic and do not route orders.

Run a bounded live-like paper pass over direct public WebSocket quotes:

```powershell
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 100 --symbol BTCUSDT --leader-symbol BTCUSDT --lagger-symbol BTC_USDT --min-samples 1 --stale-feed-ms 1500 --summary-out reports\runner_paper_live_ws_summary.json
```

`--live-ws` currently supports `perp_to_perp`: Binance USD-M `bookTicker` as the reference feed and MEXC contract ticker as the paper execution feed. It contacts public market-data WebSockets only; it does not contact MetaScalp and has no order submission or cancel path.
Add `--audit-out reports\runner_paper_live_ws_audit.jsonl` to stream paper signal/exit audit records as they are created. Add `--health-out reports\runner_paper_live_ws_health.json` to persist required stream status, stale/missing decisions, and per-stream event/gap counts.

## MetaScalp Demo Runner

Run live public Binance/MEXC paper signals and bridge filled paper entries to MetaScalp demo audit records. Dry-run is the default and does not submit orders:

```powershell
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 100 --connection-id 4 --summary-out reports\metascalp_demo_runner_summary.json --paper-audit-out reports\metascalp_demo_runner_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_orders.jsonl
```

Use `--min-events-per-stream 1 --max-events 50000` when a bounded validation must wait for both required public streams. This prevents a high-frequency Binance stream from ending the run before a slower MEXC ticker is processed:

```powershell
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 5000 --min-events-per-stream 1 --max-events 50000 --connection-id 4 --summary-out reports\metascalp_demo_runner_live_dry_both_streams.json --paper-audit-out reports\metascalp_demo_runner_live_both_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_live_both_orders.jsonl
```

Real demo POST requires explicit confirmation:

```powershell
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 500 --connection-id 4 --max-demo-orders 1 --submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER --summary-out reports\metascalp_demo_runner_submit_summary.json --paper-audit-out reports\metascalp_demo_runner_submit_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_submit_orders.jsonl
```

This runner uses public Binance/MEXC WebSockets for signals and MetaScalp REST only for guarded `metascalp-demo` order submission. It does not enable live trading.

## Safety

- Live trading is disabled by default.
- The collector has no order execution path.
- The local paper runner has no order execution path.
- Do not put `.env`, API keys, PEM files, or local MetaScalp settings into the repository.
