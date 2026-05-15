import tempfile
import json
from pathlib import Path
from unittest import TestCase

from apps.operator_console import (
    CONFIRM_DEMO_SUBMIT,
    OperatorState,
    action_specs,
    build_action_command,
    build_state_payload,
    latest_audit_rows,
    paper_summary,
    universe_candidates,
)


class OperatorConsoleTests(TestCase):
    def test_actions_expose_safe_groups_and_demo_confirmation_flag(self) -> None:
        specs = action_specs()

        self.assertIn("probe_metascalp", specs)
        self.assertIn("demo_runner_dry", specs)
        self.assertIn("refresh_universe", specs)
        self.assertIn("live_paper_30000", specs)
        self.assertIn("demo_submit_tiny", specs)
        self.assertFalse(specs["demo_runner_dry"].needs_confirmation)
        self.assertTrue(specs["demo_submit_tiny"].needs_confirmation)

    def test_state_payload_reports_live_disabled_and_no_secret_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            payload = build_state_payload(state)

        self.assertTrue(payload["safety"]["local_only"])
        self.assertFalse(payload["safety"]["live_trading_enabled"])
        self.assertFalse(payload["safety"]["secrets_input_enabled"])
        self.assertTrue(payload["safety"]["demo_submit_requires_confirmation"])

    def test_safe_actions_do_not_enable_submit_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            command = build_action_command(state, "demo_runner_dry", {})

        self.assertIn("apps/runner_metascalp_demo.py", command)
        self.assertNotIn("--submit-demo", command)
        self.assertNotIn("--confirm-demo-submit", command)

    def test_live_paper_action_targets_closed_trades_with_event_safety_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            command = build_action_command(
                state,
                "live_paper_30000",
                {
                    "target_closed_trades": "12",
                    "qty": "0.002",
                    "stale_feed_ms": "4000",
                    "z_entry": "1.2",
                    "min_impulse_bps": "0.8",
                    "starting_balance_usd": "2500",
                    "symbol": "SOLUSDT",
                    "leader_symbol": "SOLUSDT",
                    "lagger_symbol": "SOL_USDT",
                },
            )

        self.assertIn("apps/runner_paper.py", command)
        self.assertIn("--live-ws", command)
        events_index = command.index("--events")
        target_index = command.index("--target-closed-trades")
        qty_index = command.index("--qty")
        stale_index = command.index("--stale-feed-ms")
        z_index = command.index("--z-entry")
        impulse_index = command.index("--min-impulse-bps")
        balance_index = command.index("--starting-balance-usd")
        symbol_index = command.index("--symbol")
        leader_index = command.index("--leader-symbol")
        lagger_index = command.index("--lagger-symbol")
        self.assertEqual(command[events_index + 1], "120000")
        self.assertEqual(command[target_index + 1], "12")
        self.assertEqual(command[symbol_index + 1], "SOLUSDT")
        self.assertEqual(command[leader_index + 1], "SOLUSDT")
        self.assertEqual(command[lagger_index + 1], "SOL_USDT")
        self.assertEqual(command[qty_index + 1], "0.002")
        self.assertEqual(command[stale_index + 1], "4000")
        self.assertEqual(command[z_index + 1], "1.2")
        self.assertEqual(command[impulse_index + 1], "0.8")
        self.assertEqual(command[balance_index + 1], "2500")

    def test_live_paper_action_defaults_to_100_closed_trades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            command = build_action_command(state, "live_paper_30000", {})

        events_index = command.index("--events")
        target_index = command.index("--target-closed-trades")
        self.assertEqual(command[events_index + 1], "1000000")
        self.assertEqual(command[target_index + 1], "100")

    def test_refresh_universe_writes_operator_candidate_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            command = build_action_command(state, "refresh_universe", {})

        self.assertIn("apps/hydrate_universe.py", command)
        self.assertIn("--out", command)
        self.assertIn("reports/operator_universe_candidates.json", command)

    def test_demo_submit_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            with self.assertRaises(ValueError):
                state.start_job("demo_submit_tiny", {"confirm": "wrong"})

    def test_demo_submit_command_is_demo_only_and_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OperatorState(Path(tmp))

            command = build_action_command(
                state,
                "demo_submit_tiny",
                {"confirm": CONFIRM_DEMO_SUBMIT, "qty": "0.001", "price": "100", "side": "buy"},
            )

        self.assertIn("apps/metascalp_demo_order.py", command)
        self.assertIn("--submit-demo", command)
        self.assertIn("--confirm-demo-submit", command)
        self.assertIn(CONFIRM_DEMO_SUBMIT, command)
        self.assertNotIn("--live", command)

    def test_latest_audit_prefers_operator_live_paper_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports"
            reports.mkdir()
            (reports / "operator_live_paper_audit.jsonl").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "model": "residual_zscore",
                        "decision_result": "risk_blocked",
                        "skip_reason": "mexc_feed_stale",
                        "expected_edge_bps": "1",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (reports / "metascalp_demo_runner_manual_submit_paper.jsonl").write_text(
                json.dumps({"symbol": "OLD", "decision_result": "risk_blocked"}) + "\n",
                encoding="utf-8",
            )

            rows = latest_audit_rows(root)

        self.assertEqual(rows[0]["source"], "operator_live_paper_audit.jsonl")
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")

    def test_latest_audit_marks_closed_profit_and_fill_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports"
            reports.mkdir()
            (reports / "operator_live_paper_audit.jsonl").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "side": "sell",
                        "model": "residual_zscore",
                        "decision_result": "closed",
                        "realized_pnl_usd": "0.0245",
                        "fill_price": "81205.1",
                        "fill_qty": "0.001",
                        "exit_reason": "zscore_mean_reversion",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rows = latest_audit_rows(root)

        self.assertEqual(rows[0]["result"], "profit")
        self.assertEqual(rows[0]["success"], "yes")
        self.assertEqual(rows[0]["pnl_usd"], "0.0245")
        self.assertEqual(rows[0]["fill_price"], "81205.1")
        self.assertEqual(rows[0]["fill_qty"], "0.001")
        self.assertEqual(rows[0]["exit_reason"], "zscore_mean_reversion")

    def test_paper_summary_reads_profit_kpis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports"
            reports.mkdir()
            (reports / "operator_live_paper_summary.json").write_text(
                json.dumps(
                    {
                        "intents": 5,
                        "fills": 2,
                        "closed_positions": 2,
                        "open_positions": 1,
                        "target_closed_trades": 100,
                        "stop_reason": "target_closed_trades_reached",
                        "realized_pnl_usd": "0.12",
                        "unrealized_pnl_usd": "-0.01",
                        "starting_balance_usd": "100",
                    }
                ),
                encoding="utf-8",
            )
            (reports / "operator_live_paper_audit.jsonl").write_text(
                json.dumps({"decision_result": "closed", "realized_pnl_usd": "0.14"})
                + "\n"
                + json.dumps({"decision_result": "closed", "realized_pnl_usd": "-0.02"})
                + "\n",
                encoding="utf-8",
            )

            summary = paper_summary(root)

        self.assertEqual(summary["total_pnl_usd"], "0.11")
        self.assertEqual(summary["starting_balance_usd"], "100")
        self.assertEqual(summary["pnl_pct_of_balance"], "0.1100")
        self.assertEqual(summary["realized_pnl_usd"], "0.12")
        self.assertEqual(summary["unrealized_pnl_usd"], "-0.01")
        self.assertEqual(summary["winning_trades"], 1)
        self.assertEqual(summary["win_rate_pct"], "50.0")
        self.assertEqual(summary["fills"], 2)
        self.assertEqual(summary["target_closed_trades"], 100)
        self.assertEqual(summary["stop_reason"], "target_closed_trades_reached")

    def test_universe_candidates_reads_ranked_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports"
            reports.mkdir()
            (reports / "operator_universe_candidates.json").write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "rank": 1,
                                "canonical_symbol": "SOLUSDT",
                                "leader_symbol": "SOLUSDT",
                                "lagger_symbol": "SOL_USDT",
                                "metadata": {
                                    "universe_score": "0.42",
                                    "spread_bps_mexc": "2.5",
                                    "top5_depth_usd_mexc": "50000",
                                    "quote_volume_binance_24h": "1000000",
                                    "quote_volume_mexc_24h": "900000",
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rows = universe_candidates(root)

        self.assertEqual(rows[0]["canonical_symbol"], "SOLUSDT")
        self.assertEqual(rows[0]["lagger_symbol"], "SOL_USDT")
        self.assertEqual(rows[0]["score"], "0.42")

    def test_latest_audit_marks_loss_as_unsuccessful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports"
            reports.mkdir()
            (reports / "operator_live_paper_audit.jsonl").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "model": "residual_zscore",
                        "decision_result": "closed",
                        "realized_pnl_usd": "-0.02",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rows = latest_audit_rows(root)

        self.assertEqual(rows[0]["result"], "loss")
        self.assertEqual(rows[0]["success"], "no")
