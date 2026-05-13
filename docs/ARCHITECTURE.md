# Binance -> MEXC Lead-Lag Architecture

This document is the implementation target for the first real version of the bot.

## Recommendation

Use a hybrid architecture:

- public market data comes directly from official Binance and MEXC APIs;
- execution in v1 goes through MetaScalp local API;
- MetaScalp is not the primary low-latency signal data path;
- `connectionId` is the routing key for MetaScalp execution;
- MEXC `uid` is account metadata and strategy/account isolation metadata, not the main architecture axis.

The first executable build should use Python 3.12 and `asyncio`.

## Runtime Modes

- `shadow`: collect market data and emit intents, no order simulation and no exchange orders.
- `paper`: internal paper fill models only.
- `metascalp-demo`: send orders only to a MetaScalp connection where `DemoMode=true`.
- `live`: disabled by default and requires explicit config plus runtime confirmation.

## Market Profiles

The code must keep market profiles explicit.

- `spot_to_spot`
  - leader: Binance spot
  - lagger: MEXC spot
  - execution: MetaScalp
- `perp_to_perp`
  - leader: Binance USDT perpetual
  - lagger: MEXC USDT perpetual
  - execution: MetaScalp

Do not mix spot and perpetual prices with raw spread logic. Cross-type trading needs a separate basis layer.

## Component Layout

```text
apps/
  runner_live.py
  runner_paper.py
  replay_backtest.py
  hydrate_universe.py
conf/
  config.example.yaml
llbot/
  adapters/
    binance_spot.py
    binance_usdm.py
    mexc_spot.py
    mexc_contract.py
    metascalp.py
  domain/
    models.py
    events.py
    enums.py
    protocols.py
  universe/
    symbol_mapper.py
    filters.py
    scorer.py
    rotator.py
  signals/
    residual_zscore.py
    impulse_transfer.py
    lag_calibrator.py
    feature_store.py
  execution/
    planner.py
    router.py
    paper_fill.py
    order_state.py
  risk/
    limits.py
    kill_switch.py
    exposure.py
  storage/
    duckdb_store.py
    parquet_sink.py
  monitoring/
    metrics.py
    health.py
    alerts.py
  service/
    app.py
    scheduler.py
    clock_sync.py
```

## Universe Manager

The universe manager builds and refreshes the tradable symbol set.

Inputs:

- Binance exchange info, 24h ticker, book ticker, and depth/liquidity snapshots;
- MEXC spot exchange info, 24h ticker, book ticker, and depth/liquidity snapshots;
- MEXC contract detail for futures mode;
- MetaScalp connections for executable venue availability.

Hard filters:

- symbol exists on both venues for the same market profile;
- trading is enabled;
- API trading is allowed when exposed by venue metadata;
- 24h quote volume is above threshold;
- spread is below threshold;
- top-5 depth is above threshold;
- lagging venue tick size is not too coarse;
- MEXC contract state and min/max volume are valid for futures mode.

Scoring:

```text
score =
  + 0.30 * norm(min(quote_volume_binance_24h, quote_volume_mexc_24h))
  + 0.20 * norm(min(top5_depth_usd_binance, top5_depth_usd_mexc))
  - 0.15 * norm(max(spread_bps_binance, spread_bps_mexc))
  - 0.10 * norm(tick_size_bps_mexc)
  - 0.10 * norm(fee_budget_bps)
  - 0.10 * norm(volatility_noise_bps)
  - 0.05 * norm(subscription_cost)
```

Use REST/all-symbol snapshots for broad scanning and WebSocket subscriptions only for top-N candidates.

## Signal Algorithms

Use a hierarchy of algorithms: coarse candidate selection, signal generation, execution gate.

### Algorithm A: Residual Z-Score

This is the MVP signal.

```text
mid_binance = (bid_b + ask_b) / 2
mid_mexc    = (bid_m + ask_m) / 2

basis_t = log(mid_mexc) - beta_t * log(mid_binance)
mu_t    = EMA(basis_t, 2-5 min)
sigma_t = EWMSTD(basis_t, 2-5 min)
z_t     = (basis_t - mu_t) / sigma_t
```

Entry:

- long MEXC when Binance has moved up, `z_t` is too low, and net edge is positive;
- short MEXC when Binance has moved down, `z_t` is too high, and net edge is positive.

Exit:

- z-score returns near zero;
- hard TTL expires;
- adverse move stop;
- stale data stop;
- risk stop.

### Algorithm B: Event-Driven Impulse Transfer

Use this for latency-style signals.

```text
impulse_bps = 10000 * (mid_binance_now / mid_binance_w_ago - 1)
transfer_bps = beta_h * impulse_bps
lag_bps = transfer_bps - mexc_move_bps
net_edge_bps = lag_bps - spread_bps - fee_bps - slippage_bps - safety_bps
```

Signal passes only if:

- Binance shock exceeds threshold in a short window;
- shock is confirmed by trade aggression and/or order-book imbalance;
- MEXC has not transferred the equivalent move;
- `net_edge_bps > 0`.

### Algorithm C: Online Lag Calibration

Maintain candidate horizons per symbol:

```text
[25, 50, 100, 200, 500, 1000] ms
```

Choose active lag by rolling hit rate, residual variance, and realized paper PnL.

## Execution

Execution engine receives `Intent` objects from the signal engine. The signal engine must not know whether orders are routed through MetaScalp or a later direct exchange adapter.

MetaScalp v1 flow:

1. Discover local MetaScalp instance on ports `17845-17855` with `GET /ping`.
2. Read connections with `GET /api/connections`.
3. Select active MEXC connection by exchange, market type, and `DemoMode`.
4. Submit orders with `POST /api/connections/{connectionId}/orders`.
5. Store `ClientId` and `ExecutionTimeMs`.
6. Subscribe to MetaScalp WebSocket for order, position, and balance updates.

Order style:

- use taker/aggressive limit for strongest impulses;
- use maker/passive only when estimated edge is large enough;
- every entry has a TTL cancel;
- futures exits must use reduce-only if available.

## Paper Fill Models

Use three internal paper models and compare against MetaScalp demo:

- `touch`: fill when price touches the level;
- `trade_through`: fill only when price trades through the level;
- `queue_aware`: account for displayed level size and subsequent prints.

## Risk Rules

Risk engine can block every intent, even if the signal is strong.

Mandatory blocks:

- stale Binance feed;
- stale MEXC feed;
- `net_edge_bps <= 0`;
- max daily loss;
- max open positions;
- max one position per symbol per direction;
- max per-symbol notional;
- max total notional;
- reconnect storm;
- packet loss or order-book desync;
- abnormal cancel ratio;
- repeated order errors;
- high slippage;
- unexpected position or balance mismatch;
- manual kill-switch.

## Storage And Replay

Persist enough data to replay the same trading day with the same signal engine:

- quotes;
- trades;
- order-book snapshots or sufficient L2 deltas;
- features;
- intents;
- risk decisions;
- order requests and responses;
- fills;
- positions;
- PnL.

Preferred storage:

- DuckDB for queryable state and reports;
- Parquet for replayable market-data events.

## Minimal Interfaces

```python
class UniverseProvider(Protocol):
    async def refresh(self) -> list[SymbolProfile]: ...

class SignalModel(Protocol):
    def on_quote(self, q: Quote) -> list[Intent]: ...
    def on_trade(self, t: Trade) -> list[Intent]: ...

class Executor(Protocol):
    async def submit(self, intent: Intent) -> ExecutionAck: ...
    async def cancel(self, order_id: str) -> None: ...

class RiskEngine(Protocol):
    def allow(self, intent: Intent, state: PortfolioState) -> tuple[bool, str]: ...
```

## V1 Acceptance Criteria

- The bot finds the local MetaScalp instance and active connections.
- The bot builds Binance <-> MEXC symbol intersections.
- The bot ranks the universe and subscribes only to top-N live symbols.
- The bot computes residual and impulse signals.
- The bot opens trades only on MEXC paper/demo path.
- The bot records quotes, trades, intents, orders, fills, and PnL.
- The replay runner can replay the same day from stored logs with the same signal engine.

