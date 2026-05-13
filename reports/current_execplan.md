# Current ExecPlan

## Objective

Add user-facing repository documentation: root README and GitHub Wiki pages.

## Files

- `README.md`
- `docs/wiki/Home.md`
- `docs/wiki/Architecture.md`
- `docs/wiki/Safety.md`
- `docs/wiki/Operations.md`
- `docs/wiki/Development.md`
- `docs/wiki/Research-and-Roadmap.md`
- `memory/memory.json`
- `memory/notes.md`
- `reports/current_execplan.md`
- `reports/latest_test_report.md`

## Acceptance Checks

- README explains purpose, safety defaults, setup, validation, core commands, and project layout.
- Wiki pages cover architecture, safety, operations, development, and research roadmap.
- Documentation does not include secrets, live-trading enablement, or unsupported private endpoint guidance.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.
- Documentation changes are pushed to GitHub.
- Wiki pages are pushed to GitHub Wiki when the wiki repository is available.

## Status

In progress on 2026-05-13.

## Validation

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 163 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.
- GitHub repository push: pending.
- GitHub Wiki push: pending.

## Non-Goals

- No trading logic changes.
- No MetaScalp submit/cancel changes.
- No live trading changes.
