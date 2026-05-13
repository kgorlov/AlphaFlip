# Development

AlphaFlip is a Python 3.12 project with typed modules, CLI entry points, and unit tests.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

## Test Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall llbot apps tests
```

## Project Rules

- Read `AGENTS.md` before non-trivial work.
- Keep `reports/current_execplan.md` current for milestone work.
- Update `reports/latest_test_report.md` after validation.
- Update `memory/memory.json` and `memory/notes.md` when progress or assumptions change.
- Keep exchange adapters, signal logic, execution logic, risk logic, storage, and monitoring separated.
- Prefer deterministic tests and offline smoke paths.
- Do not import production code from `references/` unless that dependency is explicitly approved.

## Coding Guidelines

- Use direct official WebSocket market data for latency-sensitive paths.
- Use REST snapshots only for metadata, universe discovery, ranking, and recovery.
- Keep market profiles explicit on data and symbols.
- Treat MetaScalp `connectionId` as the execution routing key.
- Treat MEXC `uid` only as metadata.
- Keep live order placement disabled unless a future live design explicitly enables it.

## Adding A Feature

1. Update `reports/current_execplan.md`.
2. Implement the smallest useful change in the relevant module.
3. Add or update tests.
4. Run targeted tests.
5. Run the full test suite and compile check.
6. Update `reports/latest_test_report.md`.
7. Update project memory files.
8. Commit with a focused message.

## CI

The GitHub Actions workflow in `.github/workflows/ci.yml` installs the package, runs unit tests, and runs `compileall`.
