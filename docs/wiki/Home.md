# AlphaFlip Wiki

AlphaFlip is a Binance -> MEXC lead-lag trading bot project focused on safe research, replay, paper trading, and guarded MetaScalp demo execution.

## Quick Links

- [Architecture](Architecture.md)
- [Safety](Safety.md)
- [Operations](Operations.md)
- [Development](Development.md)
- [Research and Roadmap](Research-and-Roadmap.md)
- [Repository runbook](https://github.com/kgorlov/AlphaFlip/blob/master/docs/RUNBOOK.md)
- [Canonical architecture spec](https://github.com/kgorlov/AlphaFlip/blob/master/docs/ARCHITECTURE.md)

## Current Scope

The current system is not a live-trading bot. It is a live-ready architecture with safety gates and local tooling for:

- public Binance and MEXC WebSocket market data;
- deterministic replay and paper trading;
- residual z-score and event-driven impulse signals;
- online lag calibration;
- risk gating and feed-health gating;
- MetaScalp demo-mode execution planning and guarded submission;
- private MetaScalp update capture and offline reconciliation;
- DuckDB, Parquet, JSONL, dashboard, health, and daily summary artifacts.

## Golden Rules

- Keep Binance as the reference market and MEXC as the execution venue.
- Keep market profiles explicit.
- Keep live trading disabled by default.
- Keep LLMs out of signal generation and execution routing.
- Do not commit secrets or local account settings.
- Do not use private, reverse-engineered, or undocumented MEXC endpoints.

## First Commands

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```
