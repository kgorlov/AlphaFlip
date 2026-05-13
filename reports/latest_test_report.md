# Latest Test Report

## 2026-05-13 README And Wiki Documentation

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 163 tests in 2.303s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Documentation added:

- `README.md` with project purpose, safety defaults, setup, validation, common safe commands, and status.
- Wiki source pages under `docs/wiki/` for Home, Architecture, Safety, Operations, Development, and Research/Roadmap.
- `_Sidebar.md` for GitHub Wiki navigation.

Publication:

- Pushed README and wiki source pages to `origin/master`.
- Attempted to clone `https://github.com/kgorlov/AlphaFlip.wiki.git`; GitHub returned `Repository not found`.
- `gh` is not installed locally, so wiki enablement could not be automated from this environment.

## 2026-05-13 Repository Publication Setup

Tracked secret-file check:

```text
git ls-files | Select-String -Pattern '(^|/)(\.env|.*\.env|.*\.pem|.*\.key|secrets/|local/)'
```

Result: no tracked secret files detected.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 163 tests in 1.312s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Repository setup:

- Added `.gitmodules` entries for all existing reference gitlinks under `references/trading-bot-basis/`.
- Prepared the local repository for `https://github.com/kgorlov/AlphaFlip.git` as the `origin` remote.
- Pushed `master` to `origin/master` with upstream tracking enabled.

## 2026-05-13 Deep Research Milestone

Command:

```text
python -m unittest discover -s tests
```

Result:

```text
Ran 24 tests in 0.052s
OK
```

Additional check:

```text
python -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- project memory load/update/pruning;
- redacted JSONL logging;
- dynamic Binance/MEXC leadership scoring;
- unstable/noisy leader rejection.

## 2026-05-13 WebSocket And Replay Milestone

Command:

```text
python -m unittest discover -s tests
```

Result:

```text
Ran 31 tests in 0.083s
OK
```

Additional check:

```text
python -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- Binance spot/USD-M bookTicker stream URL builder and parser;
- MEXC contract ticker/depth subscription builders and parsers;
- local receive timestamp capture for market data events;
- replay JSONL writer/reader for book ticker and depth events;
- public `apps/collect_market.py` collector path without order execution.

Environment check:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass on Python 3.12 venv.

Smoke capture:

```text
.\.venv\Scripts\python.exe apps\collect_market.py --venue mexc-contract --symbol BTC_USDT --events 2 --out data\replay\smoke_mexc_contract_BTC_USDT.jsonl --mexc-depth
.\.venv\Scripts\python.exe apps\collect_market.py --venue binance-usdm --symbol BTCUSDT --events 2 --out data\replay\smoke_binance_usdm_BTCUSDT.jsonl --open-timeout-sec 30
```

Result: both public WebSocket captures wrote replay JSONL. The first Binance attempt with default Python 3.10 failed because `websockets` was not installed; the Python 3.12 `.venv` path is now the expected runtime.

## 2026-05-13 Replay Signal Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 36 tests in 0.033s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"intent_counts":{}}
```

Coverage added:

- residual z-score long/short entry intent generation;
- impulse transfer long/short entry intent generation;
- replay runner event sorting, quote feeding, depth skipping, and per-model intent counts;
- decision timestamps for generated intents use the latest available leader/lagger receive timestamp.

## 2026-05-13 Replay Paper Audit Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 39 tests in 0.087s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay paper CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"risk_allowed":0,"risk_blocked":0,"fills":0,"not_filled":0,"audit_records":0,"intent_counts":{}}
```

Coverage added:

- replay-paper risk gate evaluation for generated intents;
- quote-based touch fill simulation for replay-generated intents;
- risk block audit records with skip reasons;
- replay audit JSONL persistence for paper signal decisions.

## 2026-05-13 Replay Paper Lifecycle Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 41 tests in 0.057s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay paper CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"risk_allowed":0,"risk_blocked":0,"fills":0,"not_filled":0,"closed_positions":0,"open_positions":0,"realized_pnl_usd":"0","audit_records":0,"intent_counts":{}}
```

Coverage added:

- replay-paper position tracking from filled long/short entries;
- TTL/time-stop close using execution venue quotes;
- realized PnL sign tests for long and short TTL exits;
- exit audit records with `ttl_exit`, reduce-only paper order request, and simulated realized PnL.

## 2026-05-13 Replay Paper PnL Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 44 tests in 0.034s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay paper CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"risk_allowed":0,"risk_blocked":0,"fills":0,"not_filled":0,"closed_positions":0,"open_positions":0,"gross_realized_pnl_usd":"0","realized_cost_usd":"0","realized_pnl_usd":"0","gross_unrealized_pnl_usd":"0","unrealized_cost_usd":"0","unrealized_pnl_usd":"0","audit_records":0,"intent_counts":{}}
```

Coverage added:

- take-profit replay-paper exits before TTL;
- mark-to-market unrealized PnL for open replay-paper positions;
- fee/slippage bps cost deduction from realized and unrealized paper PnL;
- exit audit records with gross PnL, cost, and net realized PnL.

## 2026-05-13 Replay Paper Stale/Reversal Summary Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 47 tests in 0.034s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay paper CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\replay_paper_summary_smoke.json
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"risk_allowed":0,"risk_blocked":0,"fills":0,"not_filled":0,"closed_positions":0,"open_positions":0,"gross_realized_pnl_usd":"0","realized_cost_usd":"0","realized_pnl_usd":"0","gross_unrealized_pnl_usd":"0","unrealized_cost_usd":"0","unrealized_pnl_usd":"0","audit_records":0,"intent_counts":{}}
```

Coverage added:

- stale Binance reference data exits for replay-paper positions;
- reversal exits before opening the opposite paper entry;
- stale reference blocks same-tick re-entry after a stale-data stop;
- replay-paper summary JSON persistence through `--summary-out`.

## 2026-05-13 Replay Research Report Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 49 tests in 0.037s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay research CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass, wrote replay research JSON with feed-health and fill-model variant summaries.

Coverage added:

- per-venue/symbol replay feed-health metrics with max quote gaps and stale-gap counts;
- per-symbol/day replay-paper signal/fill/exit/PnL slices;
- same-replay fill model variant summary comparison;
- CLI research report persistence through `--research-report-out`.

## 2026-05-13 Feed Health Gate And Fill Diagnostics Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 52 tests in 0.104s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay research CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass, wrote research report with reusable feed-health decision and fill-model diagnostics section.

Coverage added:

- reusable feed stream state updates and feed-health decisions for live/paper/replay paths;
- replay report feed-health built from the same monitoring gate code;
- missing/stale stream health tests;
- candidate-level fill-model diagnostics keyed by signal intent id.

## 2026-05-13 Feed Health Risk Metadata Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 54 tests in 0.036s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay research CLI smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

Coverage added:

- feed-health decisions map into `PortfolioState.metadata` keys used by `BasicRiskEngine`;
- replay-paper risk-blocks entries when Binance reference data is stale;
- replay-paper risk-blocks entries when MEXC execution feed is missing;
- risk-block audit records now carry `binance_feed_stale` or `mexc_feed_stale` reasons for feed-health failures.

## 2026-05-13 Paper Runner Service Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 57 tests in 0.038s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

New paper runner smoke check:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json
```

Result:

```text
{"processed_events":4,"quotes":2,"intents":0,"skipped_events":2,"risk_allowed":0,"risk_blocked":0,"fills":0,"not_filled":0,"closed_positions":0,"open_positions":0,"gross_realized_pnl_usd":"0","realized_cost_usd":"0","realized_pnl_usd":"0","gross_unrealized_pnl_usd":"0","unrealized_cost_usd":"0","unrealized_pnl_usd":"0","audit_records":0,"intent_counts":{}}
```

Replay backtest compatibility smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass, with zero smoke intents and fill-model variant summaries.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool memory\memory.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_summary_smoke.json
```

Result: pass.

Coverage added:

- shared `llbot.service.paper_runner` model/risk/fill wiring;
- safe replay-backed `apps/runner_paper.py` CLI with summary and audit outputs;
- `apps/replay_backtest.py --paper` now delegates to the shared paper runner service;
- paper runner tests for model selection, TTL close PnL, and stale MEXC feed risk blocking.

## 2026-05-13 Live-Like Paper Quote Loop Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 58 tests in 0.078s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Runner help check:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --help
```

Result: pass, shows `--live-ws`, `--events`, and `--open-timeout-sec`.

Replay paper smoke check:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json
```

Result: pass, zero smoke intents.

Live WebSocket mode dry CLI check:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 0 --min-samples 1 --summary-out reports\runner_paper_live_ws_summary_smoke.json
```

Result: pass. This validates the CLI path without opening network sockets.

Replay backtest compatibility smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass, replay paper remains compatible after the incremental engine extraction.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_summary_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_live_ws_summary_smoke.json
```

Result: pass.

Coverage added:

- incremental `PaperTradingEngine` shared by replay and live-like quote streams;
- async `run_quote_paper` path for `Quote` streams;
- deterministic async quote-stream test without network I/O;
- bounded `apps/runner_paper.py --live-ws` mode for Binance USD-M and MEXC contract public ticker feeds.

## 2026-05-13 Live-Paper Observability Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 61 tests in 0.047s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Replay paper smoke with audit and health outputs:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json --audit-out reports\runner_paper_audit_smoke.jsonl --health-out reports\runner_paper_health_smoke.json
```

Result: pass, zero smoke intents, wrote summary/audit/health outputs.

Live WebSocket mode dry observability check:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 0 --min-samples 1 --summary-out reports\runner_paper_live_ws_summary_smoke.json --audit-out reports\runner_paper_live_ws_audit_smoke.jsonl --health-out reports\runner_paper_live_ws_health_smoke.json
```

Result: pass, created an empty streamed audit file and health JSON without opening network sockets.

Replay backtest compatibility smoke check:

```text
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

JSON/file validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_health_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_live_ws_health_smoke.json
(Get-Item reports\runner_paper_audit_smoke.jsonl).Length; (Get-Item reports\runner_paper_live_ws_audit_smoke.jsonl).Length
```

Result: pass; both smoke audit files are empty because no smoke intents were generated.

Coverage added:

- `PaperRunResult` with summary, audit records, and feed-health report;
- feed-health report for required Binance/MEXC streams and per-stream event/gap counts;
- streaming `JsonlAuditWriter` for decision-by-decision audit JSONL writes;
- CLI `--health-out` and live-paper audit streaming through `--audit-out`.

## 2026-05-13 MetaScalp Dry-Run Planner Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 67 tests in 0.053s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

MetaScalp dry-run smoke:

```text
.\.venv\Scripts\python.exe apps\plan_metascalp_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_order_dry_run_smoke.json
```

Result: pass, wrote an audit-shaped dry-run order request with no network calls and no order submission.

Compatibility smoke checks:

```text
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json --audit-out reports\runner_paper_audit_smoke.jsonl --health-out reports\runner_paper_health_smoke.json
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 0 --min-samples 1 --summary-out reports\runner_paper_live_ws_summary_smoke.json --audit-out reports\runner_paper_live_ws_audit_smoke.jsonl --health-out reports\runner_paper_live_ws_health_smoke.json
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_health_smoke.json
```

Result: pass.

Coverage added:

- MetaScalp dry-run order request planner with `connectionId`, endpoint, payload, and traceable `ClientId`;
- pre-execution validation for positive quantity/price, quantity step, price tick, min quantity, min notional, and symbol profile mismatch;
- dry-run audit record with `ClientId`/`ExecutionTimeMs` placeholders;
- future response audit normalization that treats 5xx as unknown order status;
- no-network CLI smoke tool `apps\plan_metascalp_order.py`.

## 2026-05-13 Guarded MetaScalp Demo Executor Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 72 tests in 0.075s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Compatibility and smoke checks:

```text
.\.venv\Scripts\python.exe apps\plan_metascalp_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json --audit-out reports\runner_paper_audit_smoke.jsonl --health-out reports\runner_paper_health_smoke.json
.\.venv\Scripts\python.exe apps\runner_paper.py --live-ws --events 0 --min-samples 1 --summary-out reports\runner_paper_live_ws_summary_smoke.json --audit-out reports\runner_paper_live_ws_audit_smoke.jsonl --health-out reports\runner_paper_live_ws_health_smoke.json
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_health_smoke.json
```

Result: pass.

Coverage added:

- `post_json` support in the HTTP abstraction and `MetaScalpClient.place_order`;
- `GuardedMetaScalpDemoExecutor` with dry-run default;
- guard blocks for live mode, non-demo connections, inactive connections, and non-demo runtime submissions;
- explicit demo POST path tested only with a fake HTTP client;
- 5xx POST errors normalized as unknown order status.

## 2026-05-13 Order Lifecycle And TTL Cancel Planning Milestone

Command:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 76 tests in 0.067s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Smoke checks:

```text
.\.venv\Scripts\python.exe apps\plan_metascalp_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json --audit-out reports\runner_paper_audit_smoke.jsonl --health-out reports\runner_paper_health_smoke.json
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\runner_paper_health_smoke.json
```

Result: pass.

Coverage added:

- order lifecycle statuses for planned, accepted, unknown, partial fill, fill, cancel planned, cancelled, and rejected;
- state initialization from MetaScalp submit audit records;
- unknown submit status remains open and reconcilable;
- deterministic reconciliation for accepted, fill, cancelled, and rejected events;
- dry-run TTL cancel plan and cancel audit record.

## 2026-05-13 MetaScalp Demo Order CLI Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_demo_order_cli tests.test_metascalp_execution
```

Result:

```text
Ran 19 tests in 0.032s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 81 tests in 0.099s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall apps\metascalp_demo_order.py tests\test_metascalp_demo_order_cli.py
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

MetaScalp demo order CLI dry-run smoke:

```text
.\.venv\Scripts\python.exe apps\metascalp_demo_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --intent-id smoke-demo-order --ttl-ms 3000 --expected-edge-bps 8 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --contract-size 1 --out reports\metascalp_demo_order_dry_run_smoke.json
```

Result: pass, wrote a dry-run audit JSON with `submit_allowed=false` and no network POST.

Compatibility smoke checks:

```text
.\.venv\Scripts\python.exe apps\plan_metascalp_order.py --connection-id 11 --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 2 --price-cap 100.1 --min-qty 1 --qty-step 1 --price-tick 0.1 --min-notional-usd 200 --out reports\metascalp_order_dry_run_smoke.json
.\.venv\Scripts\python.exe apps\runner_paper.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --summary-out reports\runner_paper_summary_smoke.json --audit-out reports\runner_paper_audit_smoke.jsonl --health-out reports\runner_paper_health_smoke.json
.\.venv\Scripts\python.exe apps\replay_backtest.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --min-samples 1 --paper --fee-bps 5 --slippage-bps 5 --take-profit-bps 10 --stale-feed-ms 1500 --compare-fill-models --research-report-out reports\replay_research_smoke.json
```

Result: pass.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_order_dry_run_smoke.json
```

Result: pass.

Coverage added:

- `apps\metascalp_demo_order.py` guarded executable CLI;
- dry-run default using manual `connection-id`;
- real demo submit requires exact confirmation text and `--discover`;
- discovered MetaScalp base URL is reused for the POST client;
- discovery rejects non-DemoMode connections.

## 2026-05-13 MetaScalp Demo Cancel CLI Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_execution tests.test_metascalp_demo_cancel_cli tests.test_rest_adapters
```

Result:

```text
Ran 27 tests in 0.060s
OK
```

Additional targeted check:

```text
.\.venv\Scripts\python.exe -m compileall llbot\adapters\metascalp.py llbot\execution\metascalp_executor.py llbot\execution\order_state.py apps\metascalp_demo_cancel.py tests\test_metascalp_demo_cancel_cli.py
```

Result: pass.

MetaScalp demo cancel CLI dry-run smoke:

```text
.\.venv\Scripts\python.exe apps\metascalp_demo_cancel.py --connection-id 11 --intent-id smoke-demo-order --client-id llb-smoke-demo-order --order-id ord-1 --symbol BTC_USDT --reason ttl_expired --due-ts-ms 4000 --out reports\metascalp_demo_cancel_dry_run_smoke.json
```

Result: pass, wrote a dry-run cancel audit JSON with `submit_allowed=false` and no network POST.

JSON validation:

```text
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_cancel_dry_run_smoke.json
```

Result: pass.

Coverage added:

- `MetaScalpClient.cancel_order` for `POST /api/connections/{id}/orders/cancel`;
- guarded executor cancel path with dry-run default;
- cancel 5xx handling as unknown cancel status;
- `apps\metascalp_demo_cancel.py` guarded executable CLI;
- real demo cancel requires exact confirmation text and `--discover`.

Full suite after order and cancel CLI milestones:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 90 tests in 0.128s
OK
```

Full compile and JSON validation:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool memory\memory.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_order_dry_run_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_cancel_dry_run_smoke.json
```

Result: pass.

## 2026-05-13 MetaScalp Reconciliation Replay Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_reconcile tests.test_reconcile_metascalp_updates_cli
```

Result:

```text
Ran 4 tests in 0.003s
OK
```

Offline reconciliation smoke:

```text
.\.venv\Scripts\python.exe apps\reconcile_metascalp_updates.py --order smoke-demo-order:llb-smoke-demo-order:BTC_USDT:2:11:ord-1 --updates reports\metascalp_updates_smoke.jsonl --out reports\metascalp_reconcile_smoke.json
```

Result: pass, wrote a reconciliation report with one filled order, one position snapshot, and one balance snapshot.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 94 tests in 0.123s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_reconcile_smoke.json
```

Result: pass.

Coverage added:

- MetaScalp private update normalization for order, position, and balance payloads;
- order update reconciliation into existing `OrderState`;
- visible audit records for unmatched and unknown updates;
- offline JSONL reconciliation CLI for captured MetaScalp updates;
- Windows BOM-tolerant JSON/JSONL input reading.

## 2026-05-13 Demo Fill Comparison Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_demo_fill_compare tests.test_compare_demo_fills_cli
```

Result:

```text
Ran 3 tests in 0.004s
OK
```

Offline comparison smoke:

```text
.\.venv\Scripts\python.exe apps\compare_demo_fills.py --paper-audit reports\paper_fill_smoke.jsonl --reconciled reports\metascalp_reconcile_smoke.json --out reports\demo_fill_compare_smoke.json
```

Result: pass, wrote one matched fill with a `0.1` demo-vs-paper price difference.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 97 tests in 0.111s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\demo_fill_compare_smoke.json
```

Result: pass.

Coverage added:

- paper audit fill snapshots keyed by traceable `ClientId`;
- reconciled MetaScalp demo fill snapshots keyed by `client_order_id`;
- quantity and average price difference reporting;
- unmatched paper and unmatched demo fill reporting;
- offline comparison CLI.

## 2026-05-13 DuckDB Private Execution Storage Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_duckdb_store tests.test_store_metascalp_reconcile_cli
```

Result:

```text
Ran 3 tests in 0.545s
OK
```

Offline storage smoke:

```text
.\.venv\Scripts\python.exe apps\store_metascalp_reconcile.py --reconciled reports\metascalp_reconcile_smoke.json --db reports\metascalp_private_smoke.duckdb --summary-out reports\metascalp_private_store_smoke.json
```

Result: pass, wrote one order, one fill, one position, one balance, and three reconciliation audit records.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 100 tests in 0.426s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_store_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_reconcile_smoke.json
.\.venv\Scripts\python.exe -m json.tool memory\memory.json
```

Result: pass.

Coverage added:

- DuckDB schema for reconciled MetaScalp private orders, fills, positions, balances, and audit records;
- idempotent per-source report ingestion for smoke runs;
- offline storage CLI with explicit no-submit/no-cancel/no-WebSocket/no-secrets safety summary;
- smoke artifact at `reports\metascalp_private_store_smoke.json`.

## 2026-05-13 MetaScalp Private Capture Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_private_ws tests.test_capture_metascalp_private_cli
```

Result:

```text
Ran 7 tests in 0.136s
OK
```

Dry capture smoke:

```text
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --events 0 --out reports\metascalp_private_capture_smoke.jsonl --summary-out reports\metascalp_private_capture_smoke.json
```

Result: pass, wrote an empty capture JSONL and summary without opening a WebSocket.

Read-existing reconciliation and storage smoke:

```text
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --read-existing --events 0 --out reports\metascalp_updates_smoke.jsonl --order smoke-demo-order:llb-smoke-demo-order:BTC_USDT:2:11:ord-1 --reconcile-out reports\metascalp_private_capture_reconcile_smoke.json --db reports\metascalp_private_capture_smoke.duckdb --source metascalp-private-capture-smoke --summary-out reports\metascalp_private_capture_store_smoke.json
```

Result: pass, read three updates, reconciled one filled order, and stored one fill plus position/balance/audit rows in DuckDB.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 107 tests in 0.514s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_capture_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_capture_store_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_capture_reconcile_smoke.json
.\.venv\Scripts\python.exe -m json.tool memory\memory.json
```

Result: pass.

Coverage added:

- MetaScalp private WebSocket URL builder and subscription JSON parser;
- raw private WebSocket update capture into JSONL with receive timestamps;
- capture CLI dry smoke path that opens no socket;
- read-existing path from captured/private JSONL into reconciliation and DuckDB storage;
- explicit safety summary showing no order submit, no cancel submit, and no secret reads.

## 2026-05-13 Safety Batch Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_config tests.test_risk_and_paper tests.test_health
```

Result:

```text
Ran 18 tests in 0.001s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 114 tests in 0.524s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- max-active-symbols risk gate;
- duplicate symbol-direction risk gate;
- paper fill/exit metadata for `open_position_direction_counts` and active symbols;
- feed latency alert evaluation and risk metadata mapping.

## 2026-05-13 Real MetaScalp WS Alignment Milestone

Local MetaScalp probe:

```text
.\.venv\Scripts\python.exe apps\probe_metascalp.py
```

Result:

```text
MetaScalp not found on 127.0.0.1:17845-17855
```

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_private_ws tests.test_metascalp_reconcile tests.test_capture_metascalp_private_cli
```

Result:

```text
Ran 13 tests in 0.130s
OK
```

Dry capture smoke:

```text
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --events 0 --out reports\metascalp_private_capture_smoke.jsonl --summary-out reports\metascalp_private_capture_smoke.json
```

Result: pass, wrote an empty capture JSONL and summary without opening a WebSocket.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 117 tests in 0.525s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_capture_smoke.json
```

Result: pass.

Coverage added:

- documented MetaScalp WebSocket endpoint generation for `ws://127.0.0.1:{port}/`;
- documented `Type=subscribe` connection subscription message;
- CLI `--discover --select-demo-mexc` path for connected MEXC DemoMode connection selection;
- documented `order_update`, `position_update`, and `balance_update` normalization;
- list payload expansion for balances, positions, and orders.

## 2026-05-13 Real MetaScalp Launch And Capture Milestone

Launch and probe:

```text
Start-Process C:\Users\user\AppData\Local\MetaScalp-Beta\current\MetaScalp.exe
.\.venv\Scripts\python.exe apps\probe_metascalp.py
```

Result:

```text
MetaScalp found at http://127.0.0.1:17845: {'app': 'MetaScalp', 'version': '1.0.671'}
```

Raw connection check:

```text
GET http://127.0.0.1:17845/api/connections
```

Result: found MEXC Futures `Id=4`, `State=2`, `DemoMode=true`, and Binance USDT Futures view connection `Id=6`.

Real private WebSocket bounded capture:

```text
.\.venv\Scripts\python.exe apps\capture_metascalp_private.py --discover --select-demo-mexc --events 10 --open-timeout-sec 5 --idle-timeout-sec 5 --out reports\metascalp_private_real_bounded.jsonl --summary-out reports\metascalp_private_real_bounded.json
```

Result: pass, opened `ws://127.0.0.1:17845/`, sent one subscription, captured one `subscribed` acknowledgement for `ConnectionId=4`, then exited on idle timeout.

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_private_ws tests.test_rest_adapters tests.test_capture_metascalp_private_cli
```

Result:

```text
Ran 15 tests in 0.333s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 119 tests in 1.112s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_private_real_bounded.json
```

Result: pass.

Coverage added:

- MetaScalp `connections` wrapper parsing;
- bounded private WebSocket capture with idle timeout;
- real local MetaScalp launch/probe/capture smoke artifacts.

## 2026-05-13 MetaScalp Demo Runner Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_demo_runner tests.test_metascalp_execution tests.test_rest_adapters
```

Result:

```text
Ran 27 tests in 0.055s
OK
```

Dry runner smoke:

```text
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 0 --connection-id 4 --summary-out reports\metascalp_demo_runner_dry_smoke.json --paper-audit-out reports\metascalp_demo_runner_paper_smoke.jsonl --metascalp-audit-out reports\metascalp_demo_runner_order_smoke.jsonl
```

Result: pass, selected real MetaScalp MEXC demo connection `4`, wrote summary, opened no market-data sockets, and made no POST.

Live dry runner smoke:

```text
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 10 --connection-id 4 --min-samples 1 --model impulse --min-impulse-bps 1000 --summary-out reports\metascalp_demo_runner_live_dry_smoke.json --paper-audit-out reports\metascalp_demo_runner_live_paper_smoke.jsonl --metascalp-audit-out reports\metascalp_demo_runner_live_order_smoke.jsonl
```

Result: pass, processed 10 public Binance quote events, emitted no intents, and made no POST. Health reported missing MEXC stream within the short 10-event window.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 122 tests in 0.547s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_runner_dry_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_runner_live_dry_smoke.json
```

Result: pass.

Coverage added:

- paper audit to MetaScalp demo `Intent` reconstruction;
- candidate filtering for filled entry records only;
- bounded demo bridge runner with dry-run default and explicit submit confirmation;
- real MetaScalp connection `4` dry-run smoke summary.

## 2026-05-13 MetaScalp Demo Runner Stream Guard Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_demo_runner tests.test_metascalp_execution tests.test_rest_adapters
```

Result:

```text
Ran 30 tests in 0.057s
OK
```

Real public dry-run with both required streams:

```text
.\.venv\Scripts\python.exe apps\runner_metascalp_demo.py --events 5000 --min-events-per-stream 1 --max-events 50000 --connection-id 4 --min-samples 1 --model impulse --min-impulse-bps 1000 --summary-out reports\metascalp_demo_runner_live_dry_both_streams.json --paper-audit-out reports\metascalp_demo_runner_live_both_paper.jsonl --metascalp-audit-out reports\metascalp_demo_runner_live_both_orders.jsonl
```

Result: pass, dry-run only, `submit_allowed=false`, recorded `binance:BTCUSDT=6059` and `mexc:BTC_USDT=1`, feed health `ok`, no intents, no POST.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 125 tests in 1.000s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\metascalp_demo_runner_live_dry_both_streams.json
```

Result: pass.

Coverage added:

- `runner_metascalp_demo.py --min-events-per-stream` waits for each required public stream before completing the bounded run.
- `--max-events` provides a hard cap so stream-wait dry-runs remain bounded.
- Runner summary now records target/max event limits and per-stream quote counts.

## 2026-05-13 Health Check Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_health
```

Result:

```text
Ran 9 tests in 0.084s
OK
```

Safe health CLI smoke:

```text
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --db reports\health_check_smoke.duckdb --out reports\health_check_smoke.json
```

Result: pass, data feeds, storage, and risk status `ok`, no order submit/cancel, no secrets, live trading disabled.

MetaScalp health CLI smoke:

```text
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --discover-metascalp --select-demo-mexc --open-timeout-sec 2 --db reports\health_check_smoke.duckdb --out reports\health_check_metascalp_smoke.json
```

Result: pass, MetaScalp `http://127.0.0.1:17845` connection `4` status `ok`, no order submit/cancel.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 129 tests in 0.659s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\health_check_smoke.json
.\.venv\Scripts\python.exe -m json.tool reports\health_check_metascalp_smoke.json
```

Result: pass.

Coverage added:

- component health checks for data feeds, MetaScalp, DuckDB storage, and risk state;
- aggregate system health status with JSON serialization;
- safe `apps\health_check.py` CLI that reports explicit no-submit/no-cancel/no-secrets/no-live safety flags.

## 2026-05-13 Read-Only Dashboard UI Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_dashboard
```

Result:

```text
Ran 3 tests in 0.006s
OK
```

Dashboard build smoke:

```text
.\.venv\Scripts\python.exe apps\build_dashboard.py --health reports\health_check_metascalp_smoke.json --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --memory memory\memory.json --out reports\dashboard.html
```

Result:

```text
{"out":"reports\\dashboard.html","read_only":true,"orders_submitted":false,"orders_cancelled":false,"live_trading_enabled":false}
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 132 tests in 0.642s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
Select-String -Path reports\dashboard.html -Pattern "Lead-Lag Ops Dashboard|data_feeds|metascalp|orders_submitted|submit-demo|<button"
```

Result: pass. Expected dashboard sections were present; no `<button` or `submit-demo` control surface was present.

Coverage added:

- `llbot.monitoring.dashboard` static HTML rendering from health, runner, and memory artifacts;
- `apps\build_dashboard.py` read-only dashboard builder;
- explicit `TASKS.md` operator UI track with read-only safety constraints.

## 2026-05-13 Dashboard Report Links Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_dashboard
```

Result:

```text
Ran 4 tests in 0.006s
OK
```

Dashboard build smoke:

```text
.\.venv\Scripts\python.exe apps\build_dashboard.py --health reports\health_check_metascalp_smoke.json --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --memory memory\memory.json --out reports\dashboard.html
```

Result: pass, dashboard includes existing local links to replay research, demo fill comparison, private reconciliation, and private capture summary reports.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 133 tests in 0.624s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
Select-String -Path reports\dashboard.html -Pattern "Reports|Replay Research|Demo Fill Compare|Private Reconciliation|Private Capture Summary|<button|submit-demo"
```

Result: pass. Expected report links were present; no `<button` or `submit-demo` control surface was present.

Coverage added:

- dashboard report-link model with exists/missing status and size metadata;
- default dashboard links for replay research, demo fill comparison, MetaScalp reconciliation, and private capture summary;
- repeated `--report-link "Label=path"` CLI extension for local read-only report links.

## 2026-05-13 Monitoring Alerts Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_health
```

Result:

```text
Ran 12 tests in 0.087s
OK
```

Health check smoke:

```text
.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --discover-metascalp --select-demo-mexc --open-timeout-sec 2 --db reports\health_check_smoke.duckdb --out reports\health_check_metascalp_smoke.json
```

Result: pass, system `ok`, `alerts=[]`, no order submit/cancel, no secrets, live trading disabled.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 136 tests in 0.588s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\health_check_metascalp_smoke.json
```

Result: pass.

Coverage added:

- missing/stale feed alert evaluation from feed-health decisions;
- MetaScalp disconnect/not-found critical component alerts;
- risk-stop alerts for active safety block reasons;
- `apps\health_check.py` now emits normalized alert records in its JSON report.

## 2026-05-13 Storage And Daily Summary Batch

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_duckdb_store tests.test_parquet_sink tests.test_daily_summary
```

Result:

```text
Ran 6 tests in 0.767s
OK
```

Parquet smoke:

```text
.\.venv\Scripts\python.exe apps\export_replay_parquet.py --input data\replay\smoke_binance_usdm_BTCUSDT.jsonl --input data\replay\smoke_mexc_contract_BTC_USDT.jsonl --out reports\replay_smoke.parquet
```

Result:

```text
{"rows":4,"path":"reports\\replay_smoke.parquet"}
```

Daily summary smoke:

```text
.\.venv\Scripts\python.exe apps\daily_summary.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health reports\health_check_metascalp_smoke.json --research reports\replay_research_smoke.json --fill-compare reports\demo_fill_compare_smoke.json --reconciliation reports\metascalp_reconcile_smoke.json --out reports\daily_summary_smoke.json
```

Result: pass, wrote paper, health, research, fill comparison, reconciliation, and safety summary sections.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 140 tests in 0.855s
OK
```

Additional checks:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
.\.venv\Scripts\python.exe -m json.tool reports\daily_summary_smoke.json
```

Result: pass.

Coverage added:

- broad DuckDB research schema for `market_quotes`, `market_trades`, `signal_intents`, `order_facts`, `fill_facts`, and `pnl_facts`;
- replay JSONL to Parquet sink and CLI;
- daily summary service and CLI built from existing local report artifacts.

## 2026-05-13 Lag Calibration And Feature Store Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_lag_calibrator tests.test_signal_models
```

Result:

```text
Ran 8 tests in 0.001s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 144 tests in 0.870s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- online lag calibrator with default candidate lags `[25, 50, 100, 200, 500, 1000]` ms;
- deterministic per-symbol lag selection by hit rate, residual variance, and paper PnL;
- typed rolling feature store for residual, impulse, imbalance, spread, volatility, and latency features.

## 2026-05-13 Binance Trade/Depth And Impulse Confirmation Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_ws_parsers tests.test_replay_jsonl tests.test_signal_models
```

Result:

```text
Ran 18 tests in 0.009s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 150 tests in 0.966s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- Binance aggregate trade and partial depth stream builders/parsers;
- replay JSONL trade event persistence/readback;
- optional impulse-transfer confirmation by Binance trade aggression and/or order-book imbalance;
- collector CLI flags `--binance-trade` and `--binance-depth`.

## 2026-05-13 WebSocket Runtime Helpers Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_ws_runtime
```

Result:

```text
Ran 6 tests in 0.000s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 156 tests in 0.886s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- deterministic WebSocket stream sharding for scanner mode;
- Binance combined stream spec generation per shard;
- planned reconnect decision helper for reconnect-before-24h policy;
- explicit ping/pong keepalive kwargs for websocket clients.

## 2026-05-13 Residual EWM Baseline Milestone

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_signal_models
```

Result:

```text
Ran 9 tests in 0.002s
OK
```

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 158 tests in 1.109s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- time-aware EWM basis mean and variance tracker for residual z-score signals;
- residual signal intent features for EWM mean, EWM standard deviation, and EWM window;
- invalid EWM horizon validation.

## 2026-05-13 Read-Only Ops Wrap-Up Batch

Targeted command:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_dashboard_ops
```

Result:

```text
Ran 5 tests in 0.003s
OK
```

Manual refresh smoke:

```text
.\.venv\Scripts\python.exe apps\refresh_dashboard.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --health-out reports\health_check_metascalp_smoke.json --dashboard-out reports\dashboard.html --discover-metascalp --select-demo-mexc
```

Result: pass. Rebuilt health and dashboard outputs with MetaScalp demo connection `4`, `orders_submitted=false`, `orders_cancelled=false`, `secrets_read=false`, and `live_trading_enabled=false`.

Local-only server guard smoke:

```text
.\.venv\Scripts\python.exe apps\serve_dashboard.py --host 0.0.0.0 --dashboard reports\dashboard.html
```

Result: rejected non-local host as expected.

Full suite:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 163 tests in 2.388s
OK
```

Additional check:

```text
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

Result: pass.

Coverage added:

- GitHub Actions CI workflow for unit tests and compile check;
- read-only dashboard refresh CLI;
- local-only static dashboard server wrapper and host validation.
