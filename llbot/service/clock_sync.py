"""Clock helpers for local receive timestamps."""

import time

from llbot.domain.market_data import ReceiveTimestamp


def receive_timestamp() -> ReceiveTimestamp:
    return ReceiveTimestamp(local_ts_ms=time.time_ns() // 1_000_000, monotonic_ns=time.monotonic_ns())

