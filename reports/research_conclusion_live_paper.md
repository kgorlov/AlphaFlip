# Live Paper Research Conclusion

Generated: 2026-05-15

## Dataset

- Source: `reports/operator_live_paper_audit.jsonl`
- Records: 160
- Filled entries: 64
- Closed trades: 63
- Risk-blocked decisions: 33
- Symbols represented in closed trades: BTCUSDT only
- Session window: 2026-05-15T13:47:38.907Z to 2026-05-15T14:02:14.190Z

## Raw Paper Results

- Gross realized PnL: 0.4266 USD
- Winning trades: 37
- Losing trades: 25
- Flat trades: 1
- Win rate: 58.73%
- Average gross PnL per closed trade: 0.006771 USD
- Best trade: 0.0774 USD
- Worst trade: -0.0928 USD

## By Model

- `impulse_transfer`: 46 closed, 65.22% win rate, 0.3929 USD gross PnL.
- `residual_zscore`: 17 closed, 41.18% win rate, 0.0337 USD gross PnL.

## Cost Sensitivity

The run used `fee_bps=0` and `slippage_bps=0`, so current PnL is gross paper PnL.

- Approximate round-trip notional: 9939.1626 USD
- Break-even round-trip cost: 0.4292 bps
- Net PnL at 1 bps round-trip cost: -0.56731626 USD
- Net PnL at 2 bps round-trip cost: -1.56123252 USD
- Net PnL at 4 bps round-trip cost: -3.54906504 USD
- Net PnL at 8 bps round-trip cost: -7.52473008 USD
- Net PnL at 12 bps round-trip cost: -11.50039512 USD

## Conclusion

This sample is enough to reject the current BTCUSDT paper setup as economically tradable. The raw signal is slightly positive before costs, but the edge is too small: any realistic round-trip fee, spread, latency, or slippage assumption turns it negative.

This sample is not enough to approve the strategy generally, because all closed trades are BTCUSDT. The next research pass should test ranked non-BTC candidates such as SOLUSDT, XRPUSDT, DOGEUSDT, SUIUSDT, AVAXUSDT, and ADAUSDT with non-zero fee and slippage assumptions.

Recommended direction:

- Do not consider live trading from this sample.
- Prefer `impulse_transfer` over `residual_zscore` for the next paper pass.
- Run non-BTC candidates with realistic `fee_bps` and `slippage_bps`.
- Treat `operator_live_paper_summary.json` from this run as stale; use the audit file for this conclusion.
