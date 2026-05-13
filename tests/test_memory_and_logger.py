import json
import logging
import tempfile
from pathlib import Path
from unittest import TestCase

from llbot.common.logger import build_logger, close_logger, log_event, redact
from llbot.state.memory_utils import load_memory, update_memory
from llbot.storage.audit_jsonl import write_json


class MemoryAndLoggerTests(TestCase):
    def test_memory_pruning_caps_recent_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "updated_at_utc": "2026-05-13T00:00:00Z",
                        "recent_errors": [{"idx": idx} for idx in range(5)],
                        "symbol_state": {},
                        "retention": {
                            "max_recent_errors": 2,
                            "max_symbol_entries": 500,
                        },
                    }
                ),
                encoding="utf-8",
            )

            updated = update_memory(path, lambda data: data)

            self.assertEqual([item["idx"] for item in updated["recent_errors"]], [3, 4])
            self.assertEqual(load_memory(path)["schema_version"], "1.0.0")

    def test_logger_redacts_secret_like_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.jsonl"
            logger = build_logger("test-redaction", path)

            try:
                log_event(
                    logger,
                    logging.INFO,
                    "request",
                    api_key="abc",
                    nested={"secret": "def", "safe": "ok"},
                )

                line = path.read_text(encoding="utf-8").strip()
                payload = json.loads(line)

                self.assertEqual(payload["event"]["api_key"], "***REDACTED***")
                self.assertEqual(payload["event"]["nested"]["secret"], "***REDACTED***")
                self.assertEqual(payload["event"]["nested"]["safe"], "ok")
            finally:
                close_logger(logger)

    def test_redact_does_not_mutate_safe_values(self) -> None:
        self.assertEqual(redact({"symbol": "BTCUSDT"}), {"symbol": "BTCUSDT"})

    def test_write_json_persists_summary_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"

            write_json(path, {"realized_pnl_usd": "1.23", "safe": True})

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"realized_pnl_usd": "1.23", "safe": True},
            )
