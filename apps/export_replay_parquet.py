"""Export replay JSONL market data to Parquet."""

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.storage.parquet_sink import write_replay_events_parquet
from llbot.storage.replay_jsonl import read_replay_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Export replay JSONL events to Parquet.")
    parser.add_argument("--input", action="append", required=True, help="Replay JSONL input path.")
    parser.add_argument("--out", required=True, help="Parquet output path.")
    args = parser.parse_args()

    events = []
    for path in args.input:
        events.extend(read_replay_events(path))
    summary = write_replay_events_parquet(events, args.out)
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
