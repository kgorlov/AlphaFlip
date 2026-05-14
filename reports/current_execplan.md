# Current ExecPlan

## Objective

Finalize explicit `spot_to_spot` and `perp_to_perp` profile support validation.

## Files

- `llbot/universe/rotator.py`
- `llbot/service/research_policy.py`
- `tests/test_universe.py`
- `tests/test_universe_provider.py`
- `tests/test_research_policy.py`
- `TASKS.md`
- `memory/memory.json`
- `memory/notes.md`
- `reports/current_execplan.md`
- `reports/latest_test_report.md`

## Acceptance Checks

- `spot_to_spot` builds ranked Binance spot -> MEXC spot profiles from direct exchange snapshots.
- `perp_to_perp` remains covered for Binance USD-M -> MEXC contract profiles.
- Live universe rotation emits correct Binance bookTicker stream names and MEXC direct WebSocket subscriptions for both profiles.
- MetaScalp execution remains guarded by existing planner tests; no submit/cancel/live path is enabled.
- Trade/skip classifier and neural-network research are guarded until clean data and baseline proof exist.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.

## Status

Completed on 2026-05-14.

## Validation

- `.\.venv\Scripts\python.exe -m unittest tests.test_universe tests.test_universe_provider tests.test_metascalp_execution`: passed, 30 tests.
- `.\.venv\Scripts\python.exe -m unittest tests.test_research_policy`: passed, 4 tests.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 202 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.

## Non-Goals

- No live trading enablement.
- No MetaScalp order submission or cancellation.
- No private MEXC execution path.
- No ML trade/skip classifier before clean tick/orderbook data exists.
