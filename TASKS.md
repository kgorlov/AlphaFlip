# Lead-Lag Bot Tasks

Working checklist for the Binance -> MEXC lead-lag bot. Update checkboxes as work is completed and keep the task context intact.

## 1. Project Setup

- [x] Create `references/trading-bot-basis/`.
- [x] Download `lead-lag` for non-synchronous lead-lag estimation.
- [x] Download `lead_lag_pilot` for lead-lag research examples.
- [x] Download `hftbacktest` for latency-aware replay and backtesting.
- [x] Download `blackbird` for cross-exchange arbitrage lifecycle ideas.
- [x] Download sparse Hummingbot strategy references: `cross_exchange_market_making` and `hedge`.
- [x] Create `AGENTS.md` with project rules.
- [x] Add Codex-ready architecture notes.
- [x] Add `.agent/PLANS.md` ExecPlan protocol.
- [x] Add `memory/memory.json` and `memory/notes.md`.
- [x] Add `reports/current_execplan.md` and `reports/latest_test_report.md`.
- [x] Create the base Python project structure.
- [x] Add initial domain models and interfaces.
- [x] Add config example.
- [x] Configure Python 3.12 environment for Windows.
- [x] Add dependency management file.
- [x] Add test runner and baseline CI/check commands.
- [x] Add a local runbook for tests, probes, and safe public market-data capture.

## 2. Market Profiles And Universe

- [ ] Support `spot_to_spot`: Binance spot leader, MEXC spot lagger, MetaScalp execution.
- [ ] Support `perp_to_perp`: Binance USDT perpetual leader, MEXC USDT perpetual lagger, MetaScalp execution.
- [x] Keep market profiles explicit so spot and perpetual prices are never mixed without a basis layer.
- [x] Implement `UniverseProvider`.
- [x] Load Binance `exchangeInfo`, 24h ticker, book ticker, and liquidity snapshots.
- [x] Load MEXC spot exchange info, 24h ticker, book ticker, and liquidity snapshots.
- [x] Load MEXC contract detail for futures path.
- [x] Filter symbols by trading status, API availability, min size, tick size, spread, and depth.
- [x] Rank tradable symbols with a score using volume, top-5 depth, spread, tick size, fee budget, noise, and subscription cost.
- [ ] Keep live WebSocket subscriptions only for top-N symbols.
- [ ] Rotate live universe without exceeding exchange limits.

## 3. Symbol Mapping

- [x] Implement `BTCUSDT` <-> `BTCUSDT` mapping for spot-to-spot.
- [x] Implement `BTCUSDT` <-> `BTC_USDT` mapping for perpetual contracts.
- [x] Store market type profile on every symbol.
- [x] Store MEXC contract fields: `contractSize`, `priceUnit`, `volUnit`, `minVol`, `maxVol`, fee rates, and state.
- [x] Validate order quantities and prices before execution.

## 4. Market Data

- [x] Implement Binance spot WebSocket adapter.
- [x] Implement Binance USD-M futures WebSocket adapter.
- [x] Use Binance individual `<symbol>@bookTicker` for low-latency signal paths.
- [x] Implement Binance trade/depth streams for advanced features.
- [ ] Implement MEXC spot WebSocket adapter with protobuf parser.
- [x] Implement MEXC contract WebSocket adapter.
- [x] Add direct REST snapshot hydration for order book recovery.
- [x] Add WebSocket sharding for full scanner mode.
- [x] Add reconnect-after-24h handling.
- [x] Add ping/pong keepalive handling.
- [ ] Add stale-data detection per symbol and venue.
- [x] Add bounded direct WebSocket paper quote loop for Binance USD-M and MEXC contract ticker.
- [x] Log exchange timestamps and local receive timestamps.
- [x] Add replay JSONL capture for book ticker and depth events.
- [x] Add a public market-data collector CLI for Binance USD-M and MEXC contract streams.

## 5. Signal Algorithms

- [x] Implement Algorithm A: residual z-score on normalized basis.
- [x] Calculate `basis_t = log(mid_mexc) - beta_t * log(mid_binance)`.
- [x] Maintain EMA mean and EWMSTD over a 2-5 minute window.
- [x] Enter long when Binance moved up, MEXC residual is too low, and net edge is positive.
- [x] Enter short when Binance moved down, MEXC residual is too high, and net edge is positive.
- [ ] Exit on z-score mean reversion, hard TTL, stale data, or adverse move.
- [x] Implement Algorithm B: event-driven impulse transfer.
- [x] Calculate Binance impulse over windows `[50, 100, 200, 500] ms`.
- [x] Confirm impulse with trade aggression and/or order-book imbalance.
- [x] Calculate transferred move, MEXC lag, and net edge in bps.
- [x] Implement Algorithm C: online lag calibration.
- [x] Track candidate lags `[25, 50, 100, 200, 500, 1000] ms`.
- [x] Select per-symbol lag horizon by rolling hit rate, residual variance, and paper PnL.
- [x] Add feature store for residual, impulse, imbalance, spread, volatility, and latency features.
- [x] Add dynamic empirical leadership scorer for Binance/MEXC midpoint paths.
- [x] Reject unstable/noisy leader scoring before signal execution.

## 6. Execution Through MetaScalp

- [x] Implement MetaScalp adapter and router.
- [x] Discover MetaScalp ports `17845-17855` with `GET /ping`.
- [x] List connections with `GET /api/connections`.
- [x] Treat `connectionId` as the internal routing ID.
- [x] Treat `uid` as account metadata and account-isolation metadata, not the core routing key.
- [x] Select MEXC connection by exchange, market type, active state, and `DemoMode`.
- [x] Add dry-run MetaScalp demo order request planner without POST submission.
- [x] Add audit schema placeholders for MetaScalp `ClientId`, `ExecutionTimeMs`, and unknown status.
- [x] Add guarded MetaScalp demo executor interface with dry-run default.
- [x] Use MetaScalp DemoMode for first executable version.
- [x] Submit orders with `POST /api/connections/{id}/orders`.
- [x] Add bounded live-public-signal to guarded MetaScalp demo runner.
- [x] Store returned `ClientId` and `ExecutionTimeMs` in normalized audit records.
- [x] Add guarded MetaScalp private WebSocket capture path for order, position, and balance updates.
- [x] Normalize MetaScalp order, position, and balance update payloads for reconciliation.
- [x] Implement aggressive limit entry with price cap.
- [x] Plan aggressive limit MetaScalp entry request with strict price cap in dry-run mode.
- [ ] Implement maker/passive mode only when estimated edge is large enough.
- [x] Plan order TTL cancel path with dry-run cancel audit records.
- [x] Add guarded MetaScalp demo cancel CLI with dry-run default and explicit submit confirmation.
- [x] Add per-stream minimum guard for bounded MetaScalp demo dry-runs.
- [ ] Implement reduce-only exits when supported.

## 7. Direct MEXC Future Option

- [ ] Keep direct MEXC execution out of v1 production path.
- [ ] Design direct MEXC spot/private execution only as a later adapter.
- [ ] Require `newClientOrderId` or `externalOid` for direct execution idempotency.
- [ ] Require signed REST, IP whitelist, scoped keys, and pre-trade validation.
- [ ] Do not use private, reverse-engineered, or undocumented endpoints.

## 8. Paper Trading And Fill Models

- [x] Implement `shadow` mode: signals only, no orders.
- [x] Implement internal paper fill model.
- [x] Track replay paper positions from filled entries.
- [x] Add safe local `runner_paper.py` CLI backed by the shared paper runner service.
- [x] Reuse the same incremental paper engine for replay and live-like quote streams.
- [x] Close replay paper positions on TTL/time-stop.
- [x] Close replay paper positions on take-profit.
- [x] Close replay paper positions on stale reference data.
- [x] Close replay paper positions on reversal signals.
- [x] Compute replay-paper realized PnL for TTL exits.
- [x] Mark open replay paper positions to market at replay end.
- [x] Apply configured fee/slippage bps to replay-paper PnL summaries.
- [x] Implement touch-fill simulation.
- [x] Implement conservative trade-through simulation.
- [x] Implement queue-aware simulation.
- [x] Compare replay fill model variants on the same replay summary.
- [x] Compare internal paper fills with MetaScalp demo fills.
- [x] Add offline MetaScalp update reconciliation replay for demo fill/cancel events.
- [x] Store differences between fill models for every candidate trade.

## 9. Risk And Kill Switch

- [x] Add manual kill-switch file or command.
- [x] Add max daily loss.
- [x] Add max open positions.
- [x] Add max one position per symbol per direction.
- [x] Add max notional per symbol.
- [x] Add max total notional.
- [x] Add max active symbols.
- [x] Block entries when `net_edge_bps <= 0`.
- [x] Block entries when Binance feed is stale.
- [x] Block entries when MEXC feed is stale.
- [x] Populate replay-paper risk metadata from feed-health decisions.
- [x] Block entries on MetaScalp disconnect.
- [x] Block entries on reconnect storm.
- [x] Block entries on order-book desync or repeated book resets.
- [x] Block entries on repeated order errors.
- [x] Block entries on abnormal cancel ratio.
- [x] Block entries on high slippage.
- [x] Alert when `local_receive_ts - exchange_send_ts` exceeds threshold.
- [x] Detect unexpected position or balance mismatch.

## 10. Storage, Audit, And Monitoring

- [x] Design DuckDB schema for quotes, trades, intents, orders, fills, positions, and PnL.
- [x] Add DuckDB storage for reconciled MetaScalp orders, fills, positions, balances, and audit records.
- [x] Add Parquet sink for replayable market data.
- [x] Add redacted structured JSONL logger.
- [ ] Log every signal, including skipped signals.
- [ ] Log Binance bid, ask, mid, and timestamps.
- [ ] Log MEXC bid, ask, mid, and timestamps.
- [ ] Log rolling basis, z-score, impulse, lag, and expected edge.
- [ ] Log assumed fees, spread, slippage, and safety bps.
- [x] Log risk decision and block reason.
- [x] Log order request, response, `ClientId`, and execution latency.
- [ ] Log fill data and exit reason.
- [x] Log normalized MetaScalp fill/cancel reconciliation audit records.
- [ ] Log realized and simulated PnL.
- [x] Log replay-paper fill data, exit reason, gross/cost/net realized PnL, and MTM PnL.
- [x] Stream bounded live-paper audit JSONL records as decisions/exits are created.
- [x] Add daily summary report.
- [x] Persist replay-paper summary JSON for research comparison.
- [x] Add replay research report with per-symbol/day summary slices.
- [x] Add replay feed-health metrics for quote gaps and stale-gap counts.
- [x] Add reusable feed-health gates for live/paper/replay paths.
- [x] Add candidate-level fill-model diagnostics to replay research reports.
- [x] Audit risk-blocked replay entries caused by missing/stale feeds.
- [x] Add health checks for data feeds, MetaScalp, storage, and risk state.
- [x] Add feed-health summary JSON for replay/live-like paper runner outputs.
- [x] Add alerts for stale feeds, disconnects, and risk stops.

## 11. Replay And Testing

- [x] Build replay runner that uses the same signal engine as live/paper.
- [x] Add replay JSONL read/write primitives.
- [x] Feed replay intents through risk gates and quote paper fill simulation.
- [x] Test shared paper runner service and safe local paper CLI smoke path.
- [x] Test async live-like paper quote stream path without network I/O.
- [ ] Replay one saved trading day from Parquet/DuckDB.
- [x] Test symbol mapping.
- [x] Test universe filters and scoring.
- [x] Test residual z-score signal.
- [x] Test impulse transfer signal.
- [x] Test dynamic leadership scoring.
- [x] Test online lag calibration.
- [x] Test long/short symmetry.
- [x] Test stale-data filter.
- [x] Test fee/slippage calculations.
- [x] Test order TTL cancel planning and reconciliation state transitions.
- [x] Test guarded MetaScalp demo order CLI and explicit submit confirmation gates.
- [x] Test guarded MetaScalp demo cancel CLI and explicit cancel confirmation gates.
- [x] Test MetaScalp update normalization and offline reconciliation replay.
- [x] Test replay-paper TTL exits and long/short realized PnL.
- [x] Test replay-paper take-profit exits and MTM open-position PnL.
- [x] Test replay-paper stale-data and reversal exits.
- [x] Test replay feed-health metrics and per-symbol/day report slices.
- [x] Test reusable feed-health gates and fill-model candidate diagnostics.
- [x] Test replay risk blocking from feed-health metadata.
- [x] Test safety gates.
- [ ] Compare replay PnL with paper PnL.

## 12. Research Next Steps

- [ ] Estimate lead-lag per symbol with `lead-lag`.
- [ ] Select top symbols by lag stability, liquidity, spread, and paper PnL.
- [ ] Measure catch-up time distribution.
- [ ] Measure false positives.
- [ ] Measure slippage by time of day.
- [ ] Measure performance by volatility regime.
- [ ] Try a simple `trade/skip` classifier only after clean tick/orderbook data exists.
- [ ] Do not train a neural network until the rule-based engine and dataset are proven useful.

## 13. Deep Research Report Protocol

- [x] Keep LLMs out of live signal/execution paths.
- [x] Record milestone scope in `reports/current_execplan.md`.
- [x] Record validation output in `reports/latest_test_report.md`.
- [x] Maintain compact project memory in `memory/memory.json`.
- [x] Add memory pruning test.
- [x] Add replay smoke report artifact.
- [x] Add CI pipeline for unit tests and fast integration checks.

## 14. Operator UI

- [x] Add a read-only local operations dashboard generated from health, runner, and memory artifacts.
- [x] Show data-feed health, MetaScalp demo connection state, storage table counts, risk state, and paper summary.
- [x] Keep UI read-only: no submit order, cancel order, secret input, or live trading controls.
- [x] Add dashboard links to latest replay research, fill comparison, and private reconciliation reports.
- [ ] Add historical sparklines for feed gaps, intents, fills, PnL, and health state from stored reports.
- [x] Add a manual refresh workflow that rebuilds health checks and the dashboard without executing orders.
- [x] Add an optional local-only web server wrapper after the static dashboard is stable.
- [ ] Add UI smoke screenshot checks across desktop and mobile viewports.
