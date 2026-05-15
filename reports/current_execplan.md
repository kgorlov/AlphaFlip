# Current ExecPlan

## Objective

Update operator Live Paper PnL summary dynamically while a run is still active.

## Files

- `apps/runner_paper.py`
- `llbot/service/paper_runner.py`
- `tests/test_paper_runner.py`
- `memory/memory.json`
- `memory/notes.md`
- `reports/current_execplan.md`
- `reports/latest_test_report.md`

## Acceptance Checks

- Live Paper summary file is refreshed during a running quote stream.
- Dynamic summary includes current realized, unrealized, and total PnL.
- Dynamic summary marks `stop_reason=running` until the final stop reason is known.
- Summary writes remain bounded by an update interval and trade events.
- No order submission, live trading, secret input, or direct private MEXC path is exposed.
- `python -m unittest tests.test_paper_runner` passes.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.

## Status

Completed on 2026-05-15.

## Validation

- `.\.venv\Scripts\python.exe -m unittest tests.test_paper_runner`: passed, 11 tests.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 220 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.

## Non-Goals

- No live trading enablement.
- No browser-hosted secret/API-key input.
- No direct MEXC private execution.
- No change to signal, risk, fill, or PnL calculation logic.
