# ExecPlan Protocol

Use this file as the reusable template for non-trivial project work.

## Required Read Order

1. `AGENTS.md`
2. `.agent/PLANS.md`
3. `memory/memory.json`
4. `reports/current_execplan.md` if it exists
5. The target module and its tests

## Milestone Contract

Each milestone must have:

- one concrete objective;
- files expected to change;
- acceptance checks;
- tests to add or update;
- explicit non-goals.

## Work Loop

1. Read the required context.
2. Update `reports/current_execplan.md`.
3. Implement the smallest useful change.
4. Add or update tests.
5. Run relevant checks.
6. Update `reports/latest_test_report.md`.
7. Update `memory/memory.json` and `memory/notes.md`.
8. Do a short self-review for correctness, regressions, security, and missing tests.

## Hard Rules

- Do not store secrets in repo files.
- Do not read `.env`, `*.pem`, or `*.key` files.
- Do not create duplicate alternate implementations.
- Do not put LLMs in live signal or execution paths.
- Treat live trading as disabled unless both config and runtime confirmation explicitly enable it.

