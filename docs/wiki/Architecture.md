# Architecture

AlphaFlip uses a hybrid architecture:

- Binance provides the leading/reference public market-data signal.
- MEXC is the lagging venue and intended execution venue.
- MetaScalp local API is the v1 execution bridge.
- Replay and paper trading are first-class validation paths.

## Runtime Modes

- `shadow`: collect data and emit signals only.
- `paper`: simulate fills and PnL locally.
- `metascalp-demo`: allow explicitly confirmed MetaScalp demo-mode order submission.
- `live`: disabled by default and not exposed by current demo CLIs.

## Market Profiles

`spot_to_spot`:

- Binance spot reference feed.
- MEXC spot lagging feed.
- MetaScalp execution bridge.

`perp_to_perp`:

- Binance USD-M perpetual reference feed.
- MEXC USDT perpetual lagging feed.
- MetaScalp execution bridge.

Spot and perpetual prices must not be mixed without a dedicated basis layer.

## Main Modules

```text
llbot/adapters/    Exchange and MetaScalp adapters
llbot/domain/      Typed domain models and protocols
llbot/universe/    Symbol mapping, filtering, scoring, and rotation helpers
llbot/signals/     Residual z-score, impulse transfer, lag calibration, features
llbot/execution/   MetaScalp planning, guarded demo execution, reconciliation
llbot/risk/        Risk limits, kill switch, exposure controls
llbot/storage/     Audit JSONL, DuckDB, Parquet, replay JSONL
llbot/monitoring/  Health, alerts, metrics, static dashboard
llbot/service/     Paper runner, replay, reports, dashboard operations
apps/              CLI entry points
```

## Data Flow

1. Universe and metadata are hydrated through official public REST snapshots.
2. Low-latency signals use official public WebSocket streams.
3. Signal models create typed intents.
4. Risk gates block unsafe intents before execution.
5. Paper fill models simulate fills for replay and paper.
6. MetaScalp demo execution is available only through guarded, explicit CLIs.
7. Orders, fills, positions, health, and PnL are written to local artifacts.

## Signal Models

Residual z-score:

- tracks Binance/MEXC log-basis;
- uses a time-aware EWM mean and standard deviation;
- emits long/short intents when the lagging market residual is extreme and expected edge is positive.

Impulse transfer:

- detects short-window Binance moves;
- optionally confirms with trade aggression and book imbalance;
- estimates whether MEXC has not caught up after costs and safety budget.

Online lag calibration:

- evaluates candidate lag horizons `[25, 50, 100, 200, 500, 1000]` ms;
- selects per-symbol lag by hit rate, residual variance, and paper PnL.

## Execution Bridge

MetaScalp v1 flow:

1. Discover local ports `17845-17855` with `GET /ping`.
2. Read connections with `GET /api/connections`.
3. Select a connected MEXC `DemoMode=true` connection for demo execution.
4. Plan aggressive limit orders with strict price caps.
5. Submit only when the CLI receives explicit confirmation.
6. Capture private updates and reconcile state offline.

Exchange `5xx` during submission is treated as unknown status and must be reconciled, not assumed rejected.
