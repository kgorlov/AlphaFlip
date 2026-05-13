# Safety

Safety is a core design requirement. The project must be useful for research and paper/demo validation without accidentally enabling live execution.

## Defaults

- Live trading is disabled by default.
- The public market-data collector cannot submit or cancel orders.
- The paper runner has no execution path.
- MetaScalp order and cancel CLIs are dry-run by default.
- Demo submissions require explicit confirmation strings.
- LLMs must not participate in live signal generation or execution routing.

## Required Blocks

The risk engine must stop opening new positions when any of these conditions apply:

- max daily loss reached;
- max open position count reached;
- max per-symbol notional reached;
- max total notional reached;
- max active symbols reached;
- duplicate symbol/direction exposure;
- Binance feed stale or missing;
- MEXC feed stale or missing;
- MetaScalp disconnected or connection inactive;
- observed feed latency above threshold;
- reconnect storm or order-book desync;
- repeated order placement/cancel errors;
- abnormal cancel ratio;
- repeated fill slippage above threshold;
- unexpected position or balance mismatch;
- manual kill switch active.

## Secrets

Do not commit:

- `.env` files;
- API keys or secrets;
- cookies;
- PEM or key files;
- MEXC UID values;
- local MetaScalp user settings;
- local account state.

The project stores secret references only as environment-variable names in `memory/memory.json`.

## MetaScalp Demo Confirmation

Real MetaScalp demo order submission requires:

```text
--submit-demo --confirm-demo-submit METASCALP_DEMO_ORDER
```

Real MetaScalp demo cancel requires:

```text
--submit-demo --confirm-demo-cancel METASCALP_DEMO_CANCEL
```

These paths must verify a connected `DemoMode=true` MEXC connection before POST calls.

## Before Any Live Consideration

A strategy must pass:

- shadow/paper validation;
- replay report;
- latency report;
- fee report;
- slippage report;
- fill-model comparison;
- MetaScalp demo reconciliation;
- operator review of audit logs.

Live mode remains out of scope until explicitly designed, configured, and confirmed.
