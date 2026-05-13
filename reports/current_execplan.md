# Current ExecPlan

## Objective

Publish the current workspace to `https://github.com/kgorlov/AlphaFlip.git` and make the repository clone-ready.

## Files

- `.gitmodules`
- `memory/memory.json`
- `memory/notes.md`
- `reports/current_execplan.md`
- `reports/latest_test_report.md`

## Acceptance Checks

- `origin` points to `https://github.com/kgorlov/AlphaFlip.git`.
- Reference repositories under `references/trading-bot-basis/` have `.gitmodules` entries matching their existing remotes.
- No tracked secret files are detected.
- Full `python -m unittest discover -s tests` passes.
- `python -m compileall llbot apps tests` passes.
- Current branch is pushed to GitHub.

## Status

In progress on 2026-05-13.

## Validation

- `git ls-files | Select-String -Pattern '(^|/)(\.env|.*\.env|.*\.pem|.*\.key|secrets/|local/)'`: no tracked secret files detected.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: passed, 163 tests.
- `.\.venv\Scripts\python.exe -m compileall llbot apps tests`: passed.

## Non-Goals

- No trading logic changes for this publication step.
- No MetaScalp submit/cancel changes.
- No live trading changes.
