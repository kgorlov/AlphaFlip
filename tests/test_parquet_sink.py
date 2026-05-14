import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from llbot.domain.enums import MarketType, Venue
from llbot.domain.market_data import BookTicker
from llbot.storage.parquet_sink import (
    read_replay_events_parquet,
    read_replay_events_parquet_events,
    write_replay_events_parquet,
)
from llbot.storage.replay_jsonl import replay_event_from_book_ticker


class ParquetSinkTests(TestCase):
    def test_writes_and_reads_replay_events_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "replay.parquet"
            summary = write_replay_events_parquet([_event()], out)
            rows = read_replay_events_parquet(out)

        self.assertEqual(summary["rows"], 1)
        self.assertEqual(rows[0]["event_type"], "book_ticker")
        self.assertEqual(rows[0]["venue"], "binance")
        self.assertEqual(rows[0]["bid_price"], "100")

    def test_reads_parquet_rows_back_as_replay_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "replay.parquet"
            write_replay_events_parquet([_event()], out)
            events = read_replay_events_parquet_events(out)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "book_ticker")
        self.assertEqual(events[0].venue, "binance")
        self.assertEqual(events[0].payload["ask_price"], "101")


def _event():
    return replay_event_from_book_ticker(
        BookTicker(
            venue=Venue.BINANCE,
            market=MarketType.USDT_PERP,
            symbol="BTCUSDT",
            bid_price=Decimal("100"),
            bid_qty=Decimal("1"),
            ask_price=Decimal("101"),
            ask_qty=Decimal("2"),
            timestamp_ms=10,
            local_ts_ms=11,
            receive_monotonic_ns=12,
            raw={"s": "BTCUSDT"},
        )
    )
