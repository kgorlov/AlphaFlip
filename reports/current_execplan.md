# Current ExecPlan

## Objective

Add safe health checks for public data feeds, MetaScalp demo connectivity, DuckDB execution storage, and risk-state metadata.

## Files

- `llbot/monitoring/health.py`
- `apps/health_check.py`
- `tests/test_health.py`
- `docs/RUNBOOK.md`
- `TASKS.md`
- `memory/memory.json`
- `memory/notes.md`
- `reports/latest_test_report.md`

## Acceptance Checks

- Feed health converts existing runner health decisions into component status.
- MetaScalp health reports critical when no instance/connection exists or when the selected connection is not connected/demo as required.
- Storage health reports table counts and flags storage probe failures.
- Risk health maps active safety metadata flags into a critical component.
- CLI can build a no-order health report from an existing runner summary JSON.
- No order submit, cancel, private secrets, or live trading enablement is added.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.

## Status

Completed on 2026-05-13.

## Validation

- `.\.venv\Scripts\python.exe -m unittest tests.test_health`: passed, 9 tests.
- `.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --db reports\health_check_smoke.duckdb --out reports\health_check_smoke.json`: passed, no order submit/cancel, system status `ok`.
- `.\.venv\Scripts\python.exe apps\health_check.py --runner-summary reports\metascalp_demo_runner_live_dry_both_streams.json --discover-metascalp --select-demo-mexc --open-timeout-sec 2 --db reports\health_check_smoke.duckdb --out reports\health_check_metascalp_smoke.json`: passed, MetaScalp connection `4` status `ok`, no order submit/cancel.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 129 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.
- `.\.venv\Scripts\python.exe -m json.tool reports\health_check_smoke.json`: passed.
- `.\.venv\Scripts\python.exe -m json.tool reports\health_check_metascalp_smoke.json`: passed.

## Non-Goals

- No live/demo order submission.
- No private credentials or local MetaScalp settings stored in repo.
- No alert delivery integration beyond health report generation.
