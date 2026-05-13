# Lead-Lag Trading Bot Agent Guide

This project is for building a Binance-to-MEXC lead-lag trading bot. The canonical architecture spec is `docs/ARCHITECTURE.md`.

Binance is the leading/reference market. MEXC is the lagging/execution venue. MetaScalp is the v1 execution bridge.

## Required Project State

For non-trivial work, read these files first:

1. `AGENTS.md`
2. `.agent/PLANS.md`
3. `memory/memory.json`
4. `reports/current_execplan.md` if it exists

After code changes, update:

- `reports/latest_test_report.md` with validation output;
- `memory/memory.json` with current progress and next required step;
- `memory/notes.md` when an assumption or decision changes.

## Core Goal

- Automate Binance -> MEXC lead-lag paper trading first, with live-ready safety architecture.
- Use Binance only as market-data/reference signal input.
- Support explicit market profiles:
  - `spot_to_spot`: Binance spot -> MEXC spot;
  - `perp_to_perp`: Binance USDT perpetual -> MEXC USDT perpetual.
- Execute MEXC orders through the local MetaScalp API in v1.
- Keep live trading disabled by default.
- Keep LLMs out of the live signal and execution path.

## Reference Code

References are stored under `references/trading-bot-basis/`. Treat them as research/source material, not production dependencies.

- `references/trading-bot-basis/lead-lag/`
  - Source: https://github.com/philipperemy/lead-lag
  - Use for estimating lead-lag delay between non-synchronous time series and for calibration research.
- `references/trading-bot-basis/lead_lag_pilot/`
  - Source: https://github.com/ohenrik/lead_lag_pilot
  - Use for high-frequency lead-lag research structure, notebooks, and simple next-tick strategy ideas.
- `references/trading-bot-basis/hftbacktest/`
  - Source: https://github.com/nkaz001/hftbacktest
  - Use for latency-aware replay/backtesting, queue assumptions, feed latency, and order latency modelling.
- `references/trading-bot-basis/blackbird/`
  - Source: https://github.com/webpolis/blackbird
  - Use for cross-exchange long/short arbitrage lifecycle, spread open/close state machine, logging, and stop-file ideas.
- `references/trading-bot-basis/hummingbot/`
  - Source: https://github.com/hummingbot/hummingbot
  - Sparse checkout includes:
    - `hummingbot/strategy/cross_exchange_market_making`
    - `hummingbot/strategy/hedge`
  - Use XEMM for profitability checks, cancel flow, order refresh, and maker/taker thinking.
  - Use hedge for risk-management and exposure-control ideas.

## Architecture Rules

- Use direct official WebSocket market data from Binance and MEXC.
- Do not use MetaScalp market data as the primary low-latency signal path.
- Do not use REST polling for latency-sensitive market data.
- Use REST/all-symbol snapshots only for universe discovery, ranking, metadata, and recovery snapshots.
- Use MetaScalp local API for v1 execution:
  - discover `127.0.0.1` ports `17845` through `17855` with `GET /ping`;
  - list connections with `GET /api/connections`;
  - place orders with `POST /api/connections/{id}/orders`.
- Treat MetaScalp `connectionId` as the internal execution routing ID.
- Treat MEXC `uid` as account metadata and strategy/account isolation metadata, not the core routing key.
- Keep strategy runtime modes explicit:
  - `shadow`: collect signals only;
  - `paper`: simulate execution/fills;
  - `metascalp-demo`: send only to MetaScalp demo/paper connection;
  - `live`: disabled unless explicitly enabled by config and runtime confirmation.
- Any strategy must pass shadow/paper, replay, latency report, fee report, and slippage report before live trading is considered.

## What Not To Do

- Do not copy a GitHub arbitrage bot directly into live trading.
- Do not use CCXT/REST as the low-latency data path.
- Do not store API keys, secrets, cookies, U_ID values, `.env` files, or MetaScalp user settings in the repo.
- Do not use private, reverse-engineered, or undocumented MEXC endpoints.
- Do not bypass exchange limits, KYC restrictions, rate limits, or terms of service.
- Do not enable live order placement by default.

## Strategy Direction

- Build a universe scanner from the intersection of Binance and MEXC symbols for the active market profile.
- Prefer Binance individual `<symbol>@bookTicker` streams for real-time reference updates.
- Use MEXC direct market data streams for lagging market state.
- Shard WebSocket subscriptions when scanning many symbols.
- Track per-symbol freshness and drop signals when either exchange data is stale.
- Maintain rolling basis between Binance and MEXC before computing signal edge.
- Validate Binance leadership dynamically per symbol/window; do not assume Binance leads every symbol at all times.
- Implement residual z-score as the MVP signal.
- Implement event-driven impulse transfer as the latency-style signal.
- Implement online lag calibration per symbol.
- Enter long on MEXC when Binance impulsively moves up and MEXC has not caught up.
- Enter short on MEXC when Binance impulsively moves down and MEXC has not caught up.
- Compute expected edge after fees, spread, slippage, and measured execution latency.

## Minimum Safety Gates

The bot must stop opening new positions when any of these triggers fire:

- max daily loss reached;
- max open position count reached;
- max per-symbol notional reached;
- max total notional reached;
- max active symbols reached;
- Binance feed stale;
- MEXC feed stale;
- MetaScalp disconnected or connection not active;
- observed WebSocket latency above threshold;
- repeated order placement/cancel errors;
- repeated fill slippage above threshold;
- unexpected position or balance mismatch;
- manual kill-switch activated.

## Execution Rules

- Default entry order type should be aggressive limit with a strict price cap, not blind market order.
- Every entry must have a time-to-live cancel path.
- Prefer protective marketable IOC/FOK-style limits for latency entries where the execution venue supports them.
- Exits must support take-profit on catch-up, time-stop, reversal-stop, stale-data-stop, and manual stop.
- Reduce-only must be used for futures exits when available through the execution path.
- All order IDs/client IDs must be traceable back to the signal that created them.
- Exchange `5xx` during order submit must be treated as unknown status and reconciled, not assumed rejected.

## Required Audit Log

Every signal and trade attempt must be logged with at least:

- timestamp;
- symbol;
- mode;
- signal direction;
- Binance bid/ask/mid;
- MEXC bid/ask/mid;
- rolling basis;
- expected edge;
- fees assumed;
- slippage assumed;
- feed latency;
- decision result;
- order request;
- order response;
- fill data;
- exit reason;
- realized or simulated PnL.

## Development Defaults

- Primary implementation language: Python with `asyncio`.
- Prefer explicit typed modules over one large script.
- Keep exchange adapters separate from signal logic, execution logic, and risk logic.
- Build replay tests before trusting live paper output.
- Keep references isolated under `references/`; do not import from them directly in production code unless a conscious dependency decision is made.
