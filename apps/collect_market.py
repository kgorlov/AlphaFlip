"""Capture a small public WebSocket market-data sample into replay JSONL."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.binance_ws import combined_book_ticker_url, parse_book_ticker_message
from llbot.adapters.mexc_contract_ws import (
    MEXC_CONTRACT_WS_URL,
    parse_message as parse_mexc_message,
    subscribe_depth,
    subscribe_ticker,
)
from llbot.domain.enums import MarketType
from llbot.domain.market_data import BookTicker, OrderBookDepth
from llbot.service.clock_sync import receive_timestamp
from llbot.storage.replay_jsonl import (
    JsonlReplayWriter,
    replay_event_from_book_ticker,
    replay_event_from_depth,
)


async def _collect_binance_usdm(
    symbol: str,
    events: int,
    out: Path,
    open_timeout_sec: float,
) -> None:
    import websockets

    spec = combined_book_ticker_url([symbol], MarketType.USDT_PERP)
    writer = JsonlReplayWriter(out)
    count = 0
    async with websockets.connect(
        spec.url,
        open_timeout=open_timeout_sec,
        ping_interval=20,
        ping_timeout=60,
    ) as ws:
        async for raw in ws:
            received = receive_timestamp()
            parsed = parse_book_ticker_message(json.loads(raw), MarketType.USDT_PERP, received)
            if parsed is None:
                continue
            writer.append(replay_event_from_book_ticker(parsed))
            count += 1
            print(f"{count}/{events} binance {parsed.symbol} bid={parsed.bid_price} ask={parsed.ask_price}")
            if count >= events:
                return


async def _collect_mexc_contract(
    symbol: str,
    events: int,
    out: Path,
    depth: bool,
    open_timeout_sec: float,
) -> None:
    import websockets

    writer = JsonlReplayWriter(out)
    count = 0
    async with websockets.connect(
        MEXC_CONTRACT_WS_URL,
        open_timeout=open_timeout_sec,
        ping_interval=None,
    ) as ws:
        await ws.send(json.dumps(subscribe_ticker(symbol).message))
        if depth:
            await ws.send(json.dumps(subscribe_depth(symbol).message))
        async for raw in ws:
            received = receive_timestamp()
            parsed = parse_mexc_message(json.loads(raw), received)
            if parsed is None:
                continue
            if isinstance(parsed, BookTicker):
                writer.append(replay_event_from_book_ticker(parsed))
                kind = "ticker"
            elif isinstance(parsed, OrderBookDepth):
                writer.append(replay_event_from_depth(parsed))
                kind = "depth"
            else:
                continue
            count += 1
            print(f"{count}/{events} mexc {kind} {parsed.symbol}")
            if count >= events:
                return


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture public market data to replay JSONL.")
    parser.add_argument("--venue", choices=["binance-usdm", "mexc-contract"], required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--events", type=int, default=10)
    parser.add_argument("--out", default="data/replay/sample.jsonl")
    parser.add_argument("--mexc-depth", action="store_true")
    parser.add_argument("--open-timeout-sec", type=float, default=20.0)
    args = parser.parse_args()

    out = Path(args.out)
    try:
        if args.venue == "binance-usdm":
            asyncio.run(_collect_binance_usdm(args.symbol, args.events, out, args.open_timeout_sec))
        else:
            asyncio.run(
                _collect_mexc_contract(
                    args.symbol,
                    args.events,
                    out,
                    args.mexc_depth,
                    args.open_timeout_sec,
                )
            )
    except (TimeoutError, OSError) as exc:
        raise SystemExit(f"market-data capture failed: {exc}") from exc


if __name__ == "__main__":
    main()
