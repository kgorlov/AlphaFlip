import tempfile
from pathlib import Path
from unittest import TestCase

from apps.replay_day import build_parser, run
from llbot.service.day_replay import day_replay_result_to_dict, run_day_replay
from llbot.service.paper_runner import PaperRunnerConfig
from llbot.storage.duckdb_store import DuckDbExecutionStore
from llbot.storage.parquet_sink import write_replay_events_parquet

from tests.test_paper_runner import _impulse_events


class DayReplayTests(TestCase):
    def test_runs_one_day_from_parquet(self) -> None:
        events = _impulse_events(exit_mid="102")
        day = events[0].captured_at_utc[:10]
        with tempfile.TemporaryDirectory() as tmp:
            parquet = Path(tmp) / "day.parquet"
            write_replay_events_parquet(events, parquet)

            result = run_day_replay(
                day=day,
                config=PaperRunnerConfig(
                    model="impulse",
                    min_samples=1,
                    min_impulse_bps=2,
                    safety_bps=0,
                    cooldown_ms=0,
                    ttl_ms=100,
                    impulse_windows_ms=(100,),
                ),
                parquet_paths=[parquet],
            )

        payload = day_replay_result_to_dict(result)
        self.assertEqual(payload["day"], day)
        self.assertEqual(payload["source_kind"], "parquet")
        self.assertEqual(payload["input_events"], 5)
        self.assertEqual(payload["replayed_events"], 5)
        self.assertEqual(payload["paper_summary"]["closed_positions"], 1)
        self.assertFalse(payload["orders_submitted"])
        self.assertFalse(payload["live_trading_enabled"])

    def test_runs_one_day_from_duckdb(self) -> None:
        events = _impulse_events(exit_mid="102")
        day = events[0].captured_at_utc[:10]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "day.duckdb"
            with DuckDbExecutionStore(db_path) as store:
                store.ingest_replay_events(events, source="day-smoke")

            result = run_day_replay(
                day=day,
                config=PaperRunnerConfig(
                    model="impulse",
                    min_samples=1,
                    min_impulse_bps=2,
                    safety_bps=0,
                    cooldown_ms=0,
                    ttl_ms=100,
                    impulse_windows_ms=(100,),
                ),
                duckdb_path=db_path,
                duckdb_source="day-smoke",
            )

        self.assertEqual(result.source_kind, "duckdb")
        self.assertEqual(result.replayed_events, 5)
        self.assertEqual(result.paper.summary.closed_positions, 1)

    def test_cli_writes_day_replay_outputs(self) -> None:
        events = _impulse_events(exit_mid="102")
        day = events[0].captured_at_utc[:10]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parquet = root / "day.parquet"
            out = root / "day.json"
            audit = root / "audit.jsonl"
            research = root / "research.json"
            write_replay_events_parquet(events, parquet)
            args = build_parser().parse_args(
                [
                    "--day",
                    day,
                    "--parquet",
                    str(parquet),
                    "--model",
                    "impulse",
                    "--min-samples",
                    "1",
                    "--min-impulse-bps",
                    "2",
                    "--safety-bps",
                    "0",
                    "--cooldown-ms",
                    "0",
                    "--ttl-ms",
                    "100",
                    "--out",
                    str(out),
                    "--audit-out",
                    str(audit),
                    "--research-out",
                    str(research),
                ]
            )

            payload = run(args)

            self.assertEqual(payload["paper_summary"]["closed_positions"], 1)
            self.assertTrue(audit.exists())
            self.assertTrue(research.exists())
