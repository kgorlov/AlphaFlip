# Current ExecPlan

## Objective

Run a bounded MetaScalp DemoMode trading smoke and align the order payload with the observed local API.

## Files

- `llbot/universe/rotator.py`
- `llbot/service/research_policy.py`
- `llbot/execution/metascalp_planner.py`
- `tests/test_universe.py`
- `tests/test_universe_provider.py`
- `tests/test_research_policy.py`
- `tests/test_metascalp_execution.py`
- `tests/test_metascalp_demo_order_cli.py`
- `tests/test_metascalp_demo_runner.py`
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
- MetaScalp demo submit uses the local API's accepted payload schema.
- One explicitly confirmed DemoMode manual submit is accepted.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.

## Status

Completed on 2026-05-14.

## Validation

- `.\.venv\Scripts\python.exe -m unittest tests.test_universe tests.test_universe_provider tests.test_metascalp_execution`: passed, 30 tests.
- `.\.venv\Scripts\python.exe -m unittest tests.test_research_policy`: passed, 4 tests.
- `.\.venv\Scripts\python.exe apps\metascalp_demo_order.py --discover --submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER --symbol BTCUSDT --execution-symbol BTC_USDT --side buy --qty 0.001 --price-cap 81280 --min-qty 0.001 --qty-step 0.001 --price-tick 0.1 --min-notional-usd 5 --contract-size 1 --expected-edge-bps 1 --intent-id manual-demo-view-003 --out reports\metascalp_demo_order_manual_submit_tiny.json`: accepted by MetaScalp DemoMode.
- `.\.venv\Scripts\python.exe -m unittest tests.test_metascalp_execution tests.test_metascalp_demo_order_cli tests.test_metascalp_demo_runner`: passed, 33 tests.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 202 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.

## Non-Goals

- No live trading enablement.
- No MetaScalp order submission or cancellation.
- No private MEXC execution path.
- No ML trade/skip classifier before clean tick/orderbook data exists.
