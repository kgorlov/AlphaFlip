# Research And Roadmap

This project is driven by empirical validation. A signal should move from idea to replay, paper, demo, and only much later to any live-ready review.

## Implemented

- Base Python project and typed domain modules.
- Binance USD-M and MEXC contract public WebSocket paths.
- Replay JSONL read/write.
- Parquet export for replay market data.
- Residual z-score signal.
- Event-driven impulse transfer signal.
- Trade aggression and order-book imbalance confirmations.
- Online lag calibration.
- Rolling feature store.
- Risk gates and feed-health metadata.
- Paper fill models: touch, trade-through, queue-aware.
- Replay-paper position lifecycle, costs, PnL, stale exits, reversal exits, and take-profit exits.
- MetaScalp discovery, guarded demo order/cancel CLIs, private update capture, and offline reconciliation.
- DuckDB execution/research storage.
- Health reports, alerts, daily summary, and read-only dashboard.

## High-Priority Remaining Work

- MEXC spot WebSocket protobuf parser.
- Top-N live universe rotation without exceeding exchange limits.
- More complete z-score exit handling for mean reversion and adverse moves.
- Reduce-only futures exits where supported through the execution path.
- Full saved-day replay from Parquet and DuckDB.
- Compare replay PnL with paper PnL over a meaningful sample.
- Historical dashboard charts for feed gaps, intents, fills, PnL, and health state.

## Research Questions

- Which symbols have stable Binance leadership across rolling windows?
- What is the catch-up time distribution for each candidate symbol?
- How often do impulse signals become false positives?
- How much slippage appears by time of day and volatility regime?
- Which fill model best matches MetaScalp demo fills?
- How much expected edge remains after fees, spread, slippage, and latency?

## Promotion Path

1. Collect public market data.
2. Replay the same market day deterministically.
3. Run signal and risk logic in paper mode.
4. Compare paper fill models.
5. Run bounded public WebSocket paper.
6. Run MetaScalp demo dry-run.
7. Submit at most explicitly confirmed MetaScalp demo orders.
8. Reconcile private updates.
9. Review latency, fee, slippage, fill, and PnL reports.

Live trading is not on this path until a separate live-mode design is written and approved.
