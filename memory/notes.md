# Project Notes

## Current Direction

- Treat the repository as the source of truth for Codex work.
- Keep live trading disabled by default.
- Use deterministic code for market data, signals, risk, execution, paper, and replay.
- Never put an LLM in the live signal or execution path.
- Validate Binance leadership dynamically per symbol/window instead of assuming it globally.

## 2026-05-13 README And Wiki Documentation

- Added root `README.md` as the repository entry point with safety defaults, setup, validation, common commands, and status.
- Added wiki source pages under `docs/wiki/` for Home, Architecture, Safety, Operations, Development, and Research/Roadmap.
- Added `docs/wiki/_Sidebar.md` so the same pages can be copied into GitHub Wiki with navigation.
- Decision: keep wiki source tracked in the main repository even when GitHub Wiki is published separately.
- Pushed README and wiki source to `origin/master`.
- GitHub Wiki publication is blocked until the separate wiki repository exists; `https://github.com/kgorlov/AlphaFlip.wiki.git` returned `Repository not found`, and `gh` is not installed locally to enable wiki settings.
- Installed GitHub CLI `gh` 2.92.0 in the user profile and authenticated as `kgorlov`.
- Configured repository settings through `gh`: description, homepage URL, Issues enabled, Projects enabled, Wiki enabled, and topics (`trading-bot`, `lead-lag`, `binance`, `mexc`, `metascalp`, `paper-trading`, `python`).
- Ran `gh auth setup-git`; main repo HTTPS git access works.
- Retried `AlphaFlip.wiki.git` after confirming `hasWikiEnabled=true`; GitHub still returns `Repository not found`, so a first wiki page likely needs to be created through the GitHub web UI before the wiki git repository exists.
- After the first wiki page was created through the web UI, `AlphaFlip.wiki.git` became cloneable.
- Synced all tracked `docs/wiki/*.md` pages to GitHub Wiki and pushed wiki commit `6dcd9ef Sync AlphaFlip wiki pages`.

## 2026-05-13 Repository Publication Setup

- Configured the local repository for publication to `https://github.com/kgorlov/AlphaFlip.git`.
- Added `.gitmodules` for the existing reference gitlinks under `references/trading-bot-basis/`, matching their current remotes.
- Decision: keep reference repositories as submodules/research material instead of vendoring their source into production code.
- Validation before push: tracked secret-file scan found no `.env`, `*.pem`, `*.key`, `secrets/`, or `local/` paths; full unittest and compileall passed.
- Pushed local `master` to `https://github.com/kgorlov/AlphaFlip.git` and set upstream tracking to `origin/master`.

## Deep Research Report Decisions

- Add repo-state files: `.agent/PLANS.md`, `memory/memory.json`, `memory/notes.md`, and `reports/*`.
- Add redacted JSONL logging before storing any operational events.
- Add dynamic lead-lag scoring as a gate before signal execution.
- Prefer internal replay/paper validation because MEXC has no reliable public test environment.

## 2026-05-13 Milestone

- Implemented `llbot.signals.leadlag` to estimate empirical leadership from event-time midpoint paths.
- Added tests that reject unstable/noisy leadership instead of assuming Binance always leads.
- Added `llbot.state.memory_utils` and `llbot.common.logger` with secret-key redaction.
- Current validation: `python -m unittest discover -s tests` passes 24 tests.

## 2026-05-13 WebSocket And Replay Milestone

- Added official-stream parsers for Binance spot/USD-M `bookTicker` and MEXC contract ticker/depth.
- Added local receive timestamps with both wall-clock milliseconds and monotonic nanoseconds.
- Added replay JSONL event capture/readback for book ticker and depth events.
- Added `apps/collect_market.py` for public data capture only. It does not submit, cancel, or route orders.
- Added Python 3.12 `.venv` setup and `docs/RUNBOOK.md`.
- Public smoke captures wrote `data/replay/smoke_mexc_contract_BTC_USDT.jsonl` and `data/replay/smoke_binance_usdm_BTCUSDT.jsonl`.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 31 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Signal Milestone

- Added deterministic replay of saved JSONL book ticker events through the same `SignalModel` protocol used by live/paper runners.
- Added residual z-score and impulse transfer long/short tests using synthetic Binance/MEXC quote paths.
- Replay currently emits signal intents only; risk gating, fill simulation, PnL, and exit handling remain the next paper-evaluation step.
- Decision timestamp for generated intents is now the latest available leader/lagger receive timestamp, so Binance-triggered decisions do not inherit stale MEXC timestamps.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 36 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Paper Audit Milestone

- Added replay-paper evaluation that feeds generated intents through `BasicRiskEngine` and quote-based paper fill simulation.
- Added per-signal `ReplayAuditRecord` output with signal, quote snapshot, risk decision, skip reason, paper order request/response, and fill data.
- Added `llbot.storage.audit_jsonl` for deterministic audit JSONL persistence without secrets.
- `apps/replay_backtest.py --paper` stays local and safe: it reads saved public market data only and does not contact MetaScalp or exchanges.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 39 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Paper Lifecycle Milestone

- Filled replay-paper entries now open in-memory paper positions and update `PortfolioState` so later risk checks see open position/notional usage.
- MEXC execution quotes close expired paper positions on TTL/time-stop, using bid for long exits and ask for short exits.
- Replay summaries now include `closed_positions`, `open_positions`, and `realized_pnl_usd`.
- Exit audit records use `event_type=replay_position_exit`, `exit_reason=ttl_exit`, a reduce-only paper order request, and simulated realized PnL.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 41 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Paper PnL Milestone

- Added take-profit exits for replay-paper positions before TTL when gross PnL bps reaches the configured threshold.
- Added mark-to-market open-position PnL at replay end using the latest MEXC execution quote.
- Added fee/slippage bps cost accounting to realized and unrealized paper PnL summaries.
- Exit audit records now include gross PnL, cost, and net realized PnL alongside the exit reason.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 44 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Paper Stale/Reversal Summary Milestone

- Added stale-data exits for replay-paper positions when the Binance reference quote is stale relative to the MEXC execution quote.
- Stale reference data now also blocks same-tick re-entry after a stale-data stop.
- Added reversal exits that close existing paper positions before an opposite entry signal is filled.
- Added `--summary-out` to `apps/replay_backtest.py` and a smoke summary at `reports/replay_paper_summary_smoke.json`.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 47 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Replay Research Report Milestone

- Added `llbot.service.replay_report` for replay feed-health metrics, per-symbol/day paper slices, and research report payloads.
- Added `--research-report-out` to `apps/replay_backtest.py` for persisted replay research JSON.
- Added `--compare-fill-models`; the CLI reruns each fill-model variant with fresh signal model instances to avoid rolling-state contamination.
- Wrote smoke report `reports/replay_research_smoke.json`.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 49 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Feed Health Gate And Fill Diagnostics Milestone

- Added reusable `llbot.monitoring.health` feed stream state, stale/missing stream decisions, and JSON-friendly state conversion.
- Replay research feed-health now uses the same monitoring gate code intended for paper/live-like runners.
- Added candidate-level fill-model diagnostics keyed by `intent_id`, showing per-model fill decision, fill price, fill reason, and skip reason.
- `--compare-fill-models` now passes variant audit records into the research report so differences can be inspected, not only summarized.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 52 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Feed Health Risk Metadata Milestone

- Added `feed_health_metadata` to map feed-health decisions into `binance_feed_stale` and `mexc_feed_stale` risk metadata.
- Replay-paper now updates feed stream state from each quote and evaluates required Binance/MEXC streams before risk checks.
- Missing MEXC execution feed and stale Binance reference feed now produce `risk_blocked` audit records instead of silent skips or no-execution-quote decisions when `stale_feed_ms` is configured.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 54 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Paper Runner Service Milestone

- Added `llbot.service.paper_runner` as the shared local paper runner wiring for signal models, risk gates, feed-health metadata, and quote-fill simulation.
- Implemented `apps/runner_paper.py` as a safe replay-backed paper CLI with summary/audit outputs and no MetaScalp or exchange I/O.
- Updated `apps/replay_backtest.py --paper` to use the same paper runner service instead of its own paper wiring.
- Decision: the first `runner_paper.py` milestone remains replay-backed/local only; a live WebSocket paper loop is still a later step after the shared service is validated.

## 2026-05-13 Live-Like Paper Quote Loop Milestone

- Extracted `PaperTradingEngine` so replay and live-like quote streams share the same signal, risk, feed-health, position, exit, and paper-fill logic.
- Added `run_quote_paper` for async `Quote` streams and tested it with deterministic in-memory quote generators.
- Added `apps/runner_paper.py --live-ws` for bounded public Binance USD-M and MEXC contract ticker paper runs.
- Decision: `--live-ws` is market-data only; it does not contact MetaScalp and has no order submission, cancel, private API, or live execution path.

## 2026-05-13 Live-Paper Observability Milestone

- Added `PaperRunResult` with summary, audit records, and a JSON-friendly feed-health report for replay and live-like paper runs.
- Added streaming `JsonlAuditWriter` so bounded live-paper audit records can be flushed as decisions/exits are produced.
- Added `apps/runner_paper.py --health-out` for required stream health, missing/stale decisions, and per-stream event/gap counts.
- Decision: observability remains paper-only and market-data-only; no MetaScalp submit/cancel path was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 61 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 MetaScalp Dry-Run Planner Milestone

- Added local MetaScalp dry-run order planner with quantity, price tick, and min-notional validation before any execution attempt.
- Added traceable `ClientId` generation from `intent_id` and a planned `POST /api/connections/{id}/orders` endpoint/payload without performing the POST.
- Added audit records for dry-run plans and future MetaScalp responses, including `ClientId`, `ExecutionTimeMs`, and `unknown_status` for 5xx handling.
- Added `apps/plan_metascalp_order.py` as a no-network smoke tool for generating a dry-run request/audit JSON.
- Decision: this milestone still does not submit orders, cancel orders, subscribe to MetaScalp WebSocket, or enable live/demo execution.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 67 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Guarded MetaScalp Demo Executor Milestone

- Added HTTP `post_json` support and `MetaScalpClient.place_order`, used only behind guarded executor tests.
- Added `GuardedMetaScalpDemoExecutor` with dry-run default, explicit `allow_submit`, `RuntimeMode.METASCALP_DEMO` requirement, connected connection requirement, and `DemoMode=true` requirement.
- Added response audit normalization for accepted demo responses and 5xx unknown-status handling.
- Decision: live mode is rejected by code and submission remains disabled by default; no cancel path or MetaScalp WebSocket subscription was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 72 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Order Lifecycle And TTL Cancel Planning Milestone

- Added order lifecycle statuses and state initialization from MetaScalp submit audit records.
- Unknown submit status now remains open/reconcilable instead of being assumed rejected.
- Added deterministic reconciliation transitions for accepted, fill, cancelled, and rejected events.
- Added dry-run TTL cancel plans and cancel audit records with endpoint, client/order identifiers, reason, and due timestamp.
- Decision: this remains planning/reconciliation only; no operational cancel endpoint call or MetaScalp WebSocket subscription was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 76 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 MetaScalp Demo Order CLI Milestone

- Added `apps/metascalp_demo_order.py` as the first executable MetaScalp demo-order path.
- Default CLI behavior is dry-run only and writes the same normalized audit shape as executor responses.
- Real demo submission requires `--discover --submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER`, so DemoMode and active connection state are verified before `POST /api/connections/{id}/orders`.
- Discovery now reuses the discovered MetaScalp base URL for the POST client.
- Decision: live mode remains unavailable, manual `connection-id` is allowed for dry-run only, and operational cancel/WebSocket reconciliation remain next work.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 81 tests, `.venv\Scripts\python.exe -m compileall llbot apps tests` passes, and the dry-run CLI smoke writes `reports\metascalp_demo_order_dry_run_smoke.json`.

## 2026-05-13 MetaScalp Demo Cancel CLI Milestone

- Added `MetaScalpClient.cancel_order` for `POST /api/connections/{id}/orders/cancel`.
- Added guarded executor cancel handling with dry-run default and 5xx unknown cancel status normalization.
- Added `apps/metascalp_demo_cancel.py` as the executable MetaScalp demo cancel path.
- Real demo cancel requires `--discover --submit-demo --confirm-demo-cancel METASCALP_DEMO_CANCEL`.
- Decision: MetaScalp WebSocket/private update subscription is still not implemented; reconciliation after real demo orders remains the next blocker before demo-fill comparison.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 90 tests, `.venv\Scripts\python.exe -m compileall llbot apps tests` passes, and the dry-run cancel CLI smoke writes `reports\metascalp_demo_cancel_dry_run_smoke.json`.

## 2026-05-13 MetaScalp Reconciliation Replay Milestone

- Added normalization for MetaScalp private order, position, and balance update payloads.
- Added offline reconciliation that applies order accepted/fill/cancel/reject events to local `OrderState`.
- Unmatched and unknown updates are emitted as explicit audit records instead of being silently discarded.
- Added `apps/reconcile_metascalp_updates.py` to replay captured JSONL updates from file/stdin into a reconciliation report.
- Decision: this is an offline replay/reconciliation layer only; it does not open a private MetaScalp WebSocket or use secrets.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 94 tests, `.venv\Scripts\python.exe -m compileall llbot apps tests` passes, and the offline reconciliation smoke writes `reports\metascalp_reconcile_smoke.json`.

## 2026-05-13 Demo Fill Comparison Milestone

- Added offline paper-vs-MetaScalp demo fill comparison keyed by traceable client order ID.
- Added quantity and average fill price deltas, plus unmatched paper and unmatched demo fill lists.
- Added `apps/compare_demo_fills.py` to compare paper audit JSONL against reconciled MetaScalp order state JSON.
- Decision: this is an offline report only; real MetaScalp private WebSocket capture is still not implemented.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 97 tests, `.venv\Scripts\python.exe -m compileall llbot apps tests` passes, and the smoke report writes `reports\demo_fill_compare_smoke.json`.

## 2026-05-13 DuckDB Private Execution Storage Milestone

- Added `llbot.storage.duckdb_store` with queryable tables for reconciled MetaScalp orders, fills, positions, balances, and reconciliation audit records.
- Added `apps/store_metascalp_reconcile.py` to load an offline reconciliation report into local DuckDB and emit an ingestion summary.
- Smoke storage now writes `reports\metascalp_private_smoke.duckdb` and `reports\metascalp_private_store_smoke.json` from `reports\metascalp_reconcile_smoke.json`.
- Decision: storage is implemented before live private WebSocket capture so captured updates have a stable persistence target.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 100 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 MetaScalp Private Capture Milestone

- Added `llbot.adapters.metascalp_ws` for guarded MetaScalp private WebSocket capture into raw JSONL records with local receive timestamps.
- Added `apps/capture_metascalp_private.py` with explicit `--ws-url` or `--discover --ws-path`, repeated `--subscription-json`, `--read-existing`, optional reconciliation, and optional DuckDB storage.
- Smoke capture now writes `reports\metascalp_private_capture_smoke.json` without opening a WebSocket, and read-existing smoke writes `reports\metascalp_private_capture_store_smoke.json`.
- Decision: MetaScalp WebSocket URL/path and subscription messages stay explicit because the project does not assume undocumented local MetaScalp private WebSocket paths.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 107 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Safety Batch Milestone

- Added `RiskConfig.max_active_symbols` and a `BasicRiskEngine` block for opening a new symbol after the configured active-symbol cap is reached.
- Added duplicate symbol-direction blocking with `open_position_direction_counts` metadata, so one long and one short can be distinguished explicitly.
- Paper fill/exit state now maintains `open_position_direction_counts` and `active_symbols` metadata for later risk checks.
- Added feed-latency alert evaluation for `local_ts_ms - exchange_ts_ms` and mapped high latency to `feed_latency_high` risk metadata.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 114 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Real MetaScalp WS Alignment Milestone

- Updated MetaScalp private capture to use the documented local WebSocket root endpoint `ws://127.0.0.1:{port}/`.
- Added documented connection subscription helper: `{"Type":"subscribe","Data":{"ConnectionId":...}}`.
- `apps/capture_metascalp_private.py` can now `--discover --select-demo-mexc` to find the first connected MEXC `DemoMode=true` connection and subscribe to order/position/balance/finres updates.
- Reconciliation now expands documented list payloads such as `Balances`, `Positions`, and `Orders`, and recognizes documented update type names like `order_update`, `position_update`, and `balance_update`.
- Local probe result: MetaScalp was not running on `127.0.0.1:17845-17855`, so real capture could not be executed in this turn.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 117 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Real MetaScalp Launch And Capture Milestone

- Launched `C:\Users\user\AppData\Local\MetaScalp-Beta\current\MetaScalp.exe` from the desktop shortcut target.
- MetaScalp API discovered at `http://127.0.0.1:17845` with version `1.0.671`.
- `/api/connections` returned MEXC Futures connection `Id=4`, `State=2`, `DemoMode=true`, and Binance USDT Futures view connection `Id=6`.
- Fixed MetaScalp connection parsing to handle the documented `{"connections":[...]}` wrapper.
- Added `--idle-timeout-sec` to private capture so bounded real captures do not hang when only the subscribe acknowledgement arrives.
- Real private capture opened `ws://127.0.0.1:17845/`, subscribed connection `4`, captured one `{"Type":"subscribed","Data":{"ConnectionId":4}}` ack, and exited on idle timeout.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 119 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 MetaScalp Demo Runner Milestone

- Added `llbot.service.metascalp_demo_runner` to turn filled paper signal audit records back into traceable `Intent` objects for guarded demo submission.
- Added `apps/runner_metascalp_demo.py`, a bounded live public quote runner that uses the paper engine and can submit at most `--max-demo-orders` to MetaScalp demo.
- Demo runner defaults to dry-run; real POST requires `--submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER`.
- Smoke dry-run with `--events 0` selected real MetaScalp MEXC demo connection `4` and wrote summary/audit files without market-data sockets or POST.
- Live dry-run smoke processed 10 public Binance quote events against connection `4`; no intents were emitted and no POST was made.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 122 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 MetaScalp Demo Runner Stream Guard Milestone

- Added `--min-events-per-stream` and `--max-events` to `apps/runner_metascalp_demo.py` so bounded dry-runs can wait for both required public streams instead of ending on high-frequency Binance events only.
- Runner summaries now include target event count, hard max event count, per-stream minimum, and observed per-stream quote counts.
- Real public dry-run with MetaScalp connection `4` processed `binance:BTCUSDT=6059` and `mexc:BTC_USDT=1`, reported feed health `ok`, emitted no intents, and made no POST.
- Decision: real demo order submission remains blocked until the user explicitly confirms parameters and the exact `METASCALP_DEMO_ORDER` phrase.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 125 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Health Check Milestone

- Added component health checks for data feeds, MetaScalp, DuckDB storage, and risk-state metadata in `llbot.monitoring.health`.
- Added `apps/health_check.py` to build a safe local health report from runner summary JSON, optional MetaScalp discovery, optional DuckDB table counts, and optional risk metadata flags.
- Smoke health report with MetaScalp discovery found `http://127.0.0.1:17845` and connected MEXC DemoMode connection `4`; data feeds, storage, and risk were also `ok`.
- Decision: health checks are read-only and explicitly report `orders_submitted=false`, `orders_cancelled=false`, `secrets_read=false`, and `live_trading_enabled=false`.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 129 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Read-Only Dashboard UI Milestone

- Added an explicit `Operator UI` section to `TASKS.md`; UI was missing because the original plan was focused on trading runtime, replay, risk, storage, and MetaScalp integration.
- Added `llbot.monitoring.dashboard` and `apps/build_dashboard.py` to generate `reports/dashboard.html` from health, runner, and memory JSON artifacts.
- Dashboard shows system health, feed streams, MetaScalp demo status, paper summary, safety flags, and progress without a server.
- Decision: v1 UI is static and read-only; it has no submit order, cancel order, secret input, or live trading controls.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 132 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Dashboard Report Links Milestone

- Extended the static dashboard with report links for replay research, demo fill comparison, MetaScalp private reconciliation, and private capture summary artifacts.
- Added exists/missing status and file size metadata for each configured report link.
- Added repeated `--report-link "Label=path"` support to `apps/build_dashboard.py` for extra local read-only reports.
- Decision: report links remain local/static only and do not mutate reports, submit orders, cancel orders, read secrets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 133 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Monitoring Alerts Milestone

- Added deterministic alert evaluation for missing required feeds, stale required feeds, MetaScalp critical health, and active risk stops.
- `alerts_to_risk_metadata` now maps feed missing/stale, MetaScalp disconnect, and risk-stop alerts into metadata that can block new entries.
- `apps/health_check.py` now includes normalized `alerts` in its JSON output; healthy smoke reports `alerts=[]`.
- Decision: alerts are local/read-only records only for now; no external notification delivery or order actions were added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 136 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Storage And Daily Summary Batch

- Extended `DuckDbExecutionStore` with broad local research tables for market quotes, trades, signal intents, order facts, fill facts, and PnL facts.
- Added `llbot.storage.parquet_sink` and `apps/export_replay_parquet.py` to convert replay JSONL public market data into Parquet; smoke export wrote 4 rows to `reports/replay_smoke.parquet`.
- Added `llbot.service.daily_summary` and `apps/daily_summary.py` to summarize runner, health, research, fill comparison, and reconciliation reports into `reports/daily_summary_smoke.json`.
- Decision: these storage/reporting tools are offline-only and do not contact exchanges, submit/cancel orders, read secrets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 140 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Lag Calibration And Feature Store Milestone

- Implemented `OnlineLagCalibrator` with default candidate lags `[25, 50, 100, 200, 500, 1000]` ms.
- Lag selection is per-symbol and deterministic, using hit rate, residual variance, and paper PnL after a minimum sample threshold.
- Added typed `FeatureSnapshot` and `RollingFeatureStore` for residual, impulse, imbalance, spread, volatility, and latency features.
- Decision: lag calibration and feature store are research/signal utilities only; they do not route orders or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 144 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Binance Trade/Depth And Impulse Confirmation Milestone

- Added Binance aggregate trade and partial depth stream builders/parsers for USD-M/spot stream specs.
- Added replay JSONL support for normalized trade events.
- `apps/collect_market.py` now supports `--binance-trade` and `--binance-depth` for public market-data capture.
- `ImpulseTransferSignal` can optionally require recent Binance trade aggression and/or order-book imbalance before emitting an intent; defaults preserve existing behavior.
- Decision: this is signal confirmation only and does not route, submit, or cancel orders.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 150 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 WebSocket Runtime Helpers Milestone

- Added `llbot.service.ws_runtime` for deterministic stream sharding, planned reconnect checks, and ping/pong keepalive kwargs.
- Binance stream specs can now be built per shard with a configurable reconnect threshold before the 24h connection limit.
- Decision: this milestone is connection planning only; it does not add a network runner, submit/cancel orders, touch UI, or enable live trading.

## 2026-05-13 Residual EWM Baseline Milestone

- Added time-aware `EwmBasisStats` for residual basis mean and exponentially weighted standard deviation.
- `ResidualZScoreSignal` now uses the EWM baseline for z-score entry decisions and records EWM mean/std/window fields in intent features.
- Default EWM horizon is `180000` ms, inside the required 2-5 minute signal window.
- Decision: this is signal-only and does not add MEXC protobuf parsing, MetaScalp submit/cancel behavior, UI changes, or live trading enablement.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 158 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Read-Only Ops Wrap-Up Batch

- Added GitHub Actions CI at `.github/workflows/ci.yml` to install the project, run unit tests, and run `compileall`.
- Added `apps/refresh_dashboard.py` to rebuild health and dashboard artifacts from local files with explicit no-submit/no-cancel/no-secrets/no-live safety flags.
- Added `apps/serve_dashboard.py` to serve the static dashboard only on local hosts: `127.0.0.1`, `localhost`, or `::1`.
- Decision: refresh and serve workflows are read-only operational helpers; they do not submit/cancel orders, read secrets, open market-data sockets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 163 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Residual Paper Exit Milestone

- Replay/paper positions now retain entry signal features, allowing residual z-score exits to evaluate against the entry EWM baseline.
- Added residual paper exits for z-score mean reversion before TTL and adverse z-score extension before TTL.
- Exit audit records keep the existing reduce-only paper exit request and include the entry residual features for diagnosis.
- Decision: this is paper/replay-only exit logic and does not change MetaScalp submit/cancel behavior or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 166 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Backend Hardening Batch

- Added deterministic top-N live universe planning in `llbot.universe.rotator`, including selected profiles, Binance stream names, MEXC ticker subscription messages, and rotation deltas.
- Rotation planning enforces `max_active_symbols` and computes keep/subscribe/unsubscribe sets without opening WebSockets.
- Added `required_profile_streams` and `evaluate_profile_feed_health` for per-symbol, per-venue stale/missing feed checks from `SymbolProfile`.
- Paper/replay audit records now expose top-level basis, z-score, impulse, lag, fee, slippage, and safety fields while retaining quote snapshots, fills, exits, and PnL fields.
- Decision: this batch is planning, monitoring, and audit only; it does not add a network runner, submit/cancel orders, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 169 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-13 Execution Safety Batch

- Added edge-gated order style planning: passive/maker limits require the maker edge threshold, aggressive/taker limits require the taker threshold, and lower edge is rejected.
- MetaScalp dry-run plans now set reduce-only only for exit intents on supported execution profiles, defaulting to USDT perpetual or explicit profile metadata.
- Added direct MEXC execution policy gates: v1 remains MetaScalp-only, and any later direct private adapter must require `newClientOrderId`/`externalOid`, signed REST, IP whitelist, scoped keys, pre-trade validation metadata, and official endpoints only.
- Decision: this is planner/policy logic only; no real order submission path or live trading behavior was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 176 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 MEXC Spot Protobuf Parser Milestone

- Added `llbot.adapters.mexc_spot_ws` with documented MEXC spot v3 public WebSocket URL, ping, and subscription builders for aggregated book ticker, aggregated depth, and limit depth.
- Implemented a small isolated protobuf reader for public wrapper/bookTicker/depth frames so production code does not import reference repositories or generated private schemas.
- MEXC spot protobuf frames now normalize into `BookTicker` and `OrderBookDepth` with spot market metadata, send/create timestamps, and local receive timestamps.
- Decision: parser scope is public market data only; private MEXC streams and direct MEXC execution remain out of the v1 production path.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 180 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Replay Vs Paper PnL Comparison Milestone

- Added `llbot.service.paper_pnl_compare` to compare saved replay and paper summary artifacts by PnL, counts, and per-model intent counts.
- Added `apps/compare_replay_paper_pnl.py`, an offline-only CLI that writes a JSON comparison report and includes explicit no-submit/no-cancel/no-live safety flags.
- Smoke comparison of `reports/replay_paper_summary_smoke.json` and `reports/runner_paper_summary_smoke.json` matched with zero PnL/count deltas and wrote `reports/replay_paper_pnl_compare_smoke.json`.
- Decision: replay-vs-paper comparison is artifact-only; it does not capture market data, contact MetaScalp, submit/cancel orders, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 185 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Replay Research Metrics Milestone

- Added `research_metrics` to replay research reports with catch-up duration distribution, false-positive rate, slippage-by-hour, and performance-by-volatility-regime sections.
- Catch-up is counted from profitable `take_profit` or `zscore_mean_reversion` exits with duration measured from entry timestamp to exit timestamp.
- False positives are closed paper trades with non-positive realized PnL.
- Volatility regimes are derived from absolute impulse bps: low `<5`, medium `<20`, high `>=20`, with `unknown` fallback.
- Decision: these are offline research metrics derived from replay audit records only; no market-data capture, MetaScalp call, order action, model training, or live trading change was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 186 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Symbol Lead-Lag Selection Milestone

- Added `symbol_selection` to replay research reports, using existing midpoint leadership scoring to estimate per-symbol leader, lagger, lag milliseconds, and stability reason.
- Candidate ranking now combines lag stability, MEXC bookTicker top-of-book liquidity proxy, MEXC spread proxy, and replay-paper realized PnL.
- Symbols without enough paired quote samples are retained in the report with explicit rejection reasons such as `insufficient_samples`.
- Decision: this is an offline research ranking only; it does not change runtime universe rotation, capture market data, call MetaScalp, submit/cancel orders, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 187 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Dashboard Historical Sparklines Milestone

- Added read-only dashboard history loading from repeated local `--history-report Label=path` JSON files.
- Dashboard now renders SVG sparklines for feed max gap, intents, fills, PnL, and health state using stored report artifacts.
- `apps/refresh_dashboard.py` forwards `--history-report` arguments to the dashboard builder.
- Decision: sparklines are local artifact visualization only; no browser automation, market-data capture, MetaScalp call, order action, secret input, or live trading change was added.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 187 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Dashboard Screenshot Smoke Milestone

- Added `apps/dashboard_screenshot_smoke.py` to capture desktop and mobile screenshots of the static dashboard with an installed headless Chrome/Edge executable.
- Screenshot smoke validates PNG signatures and dimensions, then writes `reports/dashboard_screenshot_smoke.json` with read-only no-submit/no-cancel/no-secrets/no-live flags.
- Real local smoke used Chrome and wrote `reports/dashboard_desktop_smoke.png` and `reports/dashboard_mobile_smoke.png`.
- Decision: screenshot smoke opens only the static local dashboard HTML through `file://`; it does not start a server, capture market data, call MetaScalp, submit/cancel orders, read secrets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 191 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Saved Day Replay From Parquet/DuckDB Milestone

- Added Parquet replay row round-trip back to `ReplayEvent` objects.
- Added DuckDB market event loading by source and captured day.
- Added `llbot.service.day_replay` and `apps/replay_day.py` to replay one saved trading day from local Parquet and/or DuckDB artifacts through the shared paper runner.
- Smoke day replay wrote `reports/replay_day_smoke.json`, `reports/replay_day_audit_smoke.jsonl`, and `reports/replay_day_research_smoke.json`.
- Decision: day replay is offline artifact analysis only; it does not capture market data, call MetaScalp, submit/cancel orders, read secrets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 196 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 Market Profile Support Wrap-Up

- Closed explicit `spot_to_spot` and `perp_to_perp` support tasks in `TASKS.md`.
- Added provider coverage for Binance spot -> MEXC spot profile construction, including spot market metadata, tick/min-size fields, and no contract size.
- Kept existing provider coverage for Binance USD-M -> MEXC contract profile construction.
- Updated live universe rotation so MEXC spot subscriptions use the shared public protobuf aggregated bookTicker helper instead of an inline channel string.
- Added a research policy gate: simple `trade/skip` classifiers require clean tick/orderbook data, enough samples, and a proven rule-based baseline; neural-network training also requires explicit approval.
- Decision: profile support is still planning/market-data/execution-planner guarded; research ML remains offline-gated; this does not submit or cancel MetaScalp orders, read secrets, or enable live trading.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 202 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.

## 2026-05-14 MetaScalp Demo Manual Submit Smoke

- `apps\probe_metascalp.py` found MetaScalp at `http://127.0.0.1:17845` with MEXC Futures DemoMode connection id `4`.
- A bounded `runner_metascalp_demo.py` submit-enabled run processed public Binance/MEXC quotes and created signal intents, but submitted no orders because risk gates blocked every candidate (`max_total_notional_reached` or `mexc_feed_stale`).
- First manual guarded demo submit reached MetaScalp but showed the local API requires lowercase order fields: `ticker`, `side`, `price`, and `size`.
- Updated MetaScalp order payload building to use the observed local API schema while retaining `clientId` and `comment` for traceability.
- Manual guarded demo submit with `qty=0.001` was accepted by MetaScalp DemoMode, returning `status=ok`, `clientId=a6757b56-8d73-49dc-824f-d499900b`, and `executionTimeMs=464.6353`.
- Decision: this was DemoMode only, behind explicit submit confirmation and connected demo discovery; live trading remains disabled.
- Current validation: `.venv\Scripts\python.exe -m unittest discover -s tests` passes 202 tests and `.venv\Scripts\python.exe -m compileall llbot apps tests` passes.
