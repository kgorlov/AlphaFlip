"""Safe local paper runner over replay JSONL market data."""

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.binance_ws import combined_book_ticker_url, parse_book_ticker_message
from llbot.adapters.mexc_contract_ws import (
    MEXC_CONTRACT_WS_URL,
    parse_message as parse_mexc_message,
    subscribe_ticker,
)
from llbot.domain.enums import MarketProfileName, MarketType
from llbot.domain.market_data import BookTicker
from llbot.domain.models import Quote
from llbot.execution.paper_fill import FillModel
from llbot.service.clock_sync import receive_timestamp
from llbot.service.paper_runner import (
    PaperRunResult,
    PaperRunnerConfig,
    run_quote_paper_result,
    run_replay_paper_result,
)
from llbot.service.replay_report import replay_paper_summary_to_dict
from llbot.signals.feature_store import quote_from_book_ticker
from llbot.storage.audit_jsonl import (
    JsonlAuditWriter,
    audit_record_to_dict,
    write_audit_records,
    write_json,
)
from llbot.storage.replay_jsonl import read_replay_events


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run internal paper trading. Replay mode stays local; "
            "--live-ws contacts public market-data WebSockets only and never routes orders."
        )
    )
    parser.add_argument("--input", action="append", help="Replay JSONL file path.")
    parser.add_argument(
        "--live-ws",
        action="store_true",
        help="Consume bounded public Binance/MEXC WebSocket quotes in paper mode only.",
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Canonical strategy symbol.")
    parser.add_argument("--leader-symbol", default="BTCUSDT", help="Binance reference symbol.")
    parser.add_argument("--lagger-symbol", default="BTC_USDT", help="MEXC execution symbol.")
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in MarketProfileName],
        default=MarketProfileName.PERP_TO_PERP.value,
    )
    parser.add_argument("--model", choices=["residual", "impulse", "both"], default="both")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--z-entry", default="2.2")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--min-impulse-bps", default="2")
    parser.add_argument("--safety-bps", default="2")
    parser.add_argument("--ttl-ms", type=int, default=3000)
    parser.add_argument("--cooldown-ms", type=int, default=1000)
    parser.add_argument("--fee-bps", default="0")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--take-profit-bps")
    parser.add_argument(
        "--starting-balance-usd",
        default="0",
        help="Optional paper cycle starting balance for PnL percent reporting only.",
    )
    parser.add_argument("--stale-feed-ms", type=int)
    parser.add_argument(
        "--events",
        type=int,
        default=100,
        help="Safety cap: maximum live WebSocket quotes to process in --live-ws mode.",
    )
    parser.add_argument(
        "--target-closed-trades",
        type=int,
        help="Stop --live-ws paper mode after this many closed paper trades.",
    )
    parser.add_argument("--open-timeout-sec", type=float, default=20.0)
    parser.add_argument("--ws-reconnect-delay-sec", type=float, default=2.0)
    parser.add_argument("--ws-max-reconnects", type=int, default=50)
    parser.add_argument(
        "--summary-update-interval",
        type=int,
        default=100,
        help="Refresh --summary-out during live paper every N quotes, plus on trade events.",
    )
    parser.add_argument(
        "--fill-model",
        choices=[model.value for model in FillModel],
        default=FillModel.TOUCH.value,
    )
    parser.add_argument("--audit-out", help="Write paper audit JSONL to this path.")
    parser.add_argument("--summary-out", help="Write paper summary JSON to this path.")
    parser.add_argument("--health-out", help="Write paper feed-health summary JSON to this path.")
    parser.add_argument("--print-audit", action="store_true", help="Print audit records to stdout.")
    args = parser.parse_args()

    audit_streamed = False
    if args.live_ws:
        if args.input:
            parser.error("--input cannot be combined with --live-ws")
        if args.profile != MarketProfileName.PERP_TO_PERP.value:
            parser.error("--live-ws currently supports only perp_to_perp")
        result = asyncio.run(_run_live_ws(args))
        audit_streamed = bool(args.audit_out)
    else:
        if not args.input:
            parser.error("--input is required unless --live-ws is set")
        events = []
        for input_path in args.input:
            events.extend(read_replay_events(input_path))
        result = run_replay_paper_result(events, _paper_config(args))

    summary = result.summary
    audit_records = result.audit_records

    if args.audit_out and not audit_streamed:
        write_audit_records(args.audit_out, audit_records)
    if args.print_audit:
        for record in audit_records:
            print(json.dumps(audit_record_to_dict(record), ensure_ascii=True, separators=(",", ":")))

    summary_payload = summary_payload_from_args(summary, args, _stop_reason_from_summary(summary, args))
    if args.summary_out:
        write_json(args.summary_out, summary_payload)
    if args.health_out:
        write_json(args.health_out, result.health_report)

    print(json.dumps(audit_record_to_dict(summary_payload), ensure_ascii=True, separators=(",", ":")))


def paper_summary_payload(summary: object, starting_balance_usd: object = "0") -> dict[str, object]:
    payload = replay_paper_summary_to_dict(summary)
    total_pnl = _decimal(payload.get("realized_pnl_usd")) + _decimal(payload.get("unrealized_pnl_usd"))
    starting_balance = _decimal(starting_balance_usd)
    payload["total_pnl_usd"] = total_pnl
    payload["starting_balance_usd"] = starting_balance
    payload["pnl_pct_of_balance"] = (
        (total_pnl / starting_balance) * Decimal("100")
        if starting_balance > 0
        else Decimal("0")
    )
    return payload


def summary_payload_from_args(
    summary: object,
    args: argparse.Namespace,
    stop_reason: str,
) -> dict[str, object]:
    payload = paper_summary_payload(summary, args.starting_balance_usd)
    payload["canonical_symbol"] = args.symbol
    payload["leader_symbol"] = args.leader_symbol
    payload["lagger_symbol"] = args.lagger_symbol
    if args.target_closed_trades is not None:
        payload["target_closed_trades"] = args.target_closed_trades
    payload["stop_reason"] = stop_reason
    return payload


def _summary_writer(args: argparse.Namespace):
    def write(summary: object) -> None:
        write_json(args.summary_out, summary_payload_from_args(summary, args, "running"))

    return write


def _paper_config(args: argparse.Namespace) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        canonical_symbol=args.symbol,
        leader_symbol=args.leader_symbol,
        lagger_symbol=args.lagger_symbol,
        profile=MarketProfileName(args.profile),
        model=args.model,
        qty=Decimal(str(args.qty)),
        z_entry=Decimal(str(args.z_entry)),
        min_samples=args.min_samples,
        min_impulse_bps=Decimal(str(args.min_impulse_bps)),
        safety_bps=Decimal(str(args.safety_bps)),
        ttl_ms=args.ttl_ms,
        cooldown_ms=args.cooldown_ms,
        fee_bps=Decimal(str(args.fee_bps)),
        slippage_bps=Decimal(str(args.slippage_bps)),
        take_profit_bps=(
            Decimal(str(args.take_profit_bps)) if args.take_profit_bps is not None else None
        ),
        stale_feed_ms=args.stale_feed_ms,
        fill_model=FillModel(args.fill_model),
    )


async def _run_live_ws(args: argparse.Namespace) -> PaperRunResult:
    summary_sink = _summary_writer(args) if args.summary_out else None
    if args.audit_out:
        with JsonlAuditWriter(args.audit_out) as writer:
            return await run_quote_paper_result(
                _live_ws_quotes(args),
                _paper_config(args),
                max_quotes=args.events,
                max_closed_positions=args.target_closed_trades,
                audit_sink=writer.append,
                summary_sink=summary_sink,
                summary_interval_quotes=args.summary_update_interval,
            )
    return await run_quote_paper_result(
        _live_ws_quotes(args),
        _paper_config(args),
        max_quotes=args.events,
        max_closed_positions=args.target_closed_trades,
        summary_sink=summary_sink,
        summary_interval_quotes=args.summary_update_interval,
    )


async def _live_ws_quotes(args: argparse.Namespace) -> AsyncIterator[Quote]:
    queue: asyncio.Queue[Quote | Exception] = asyncio.Queue()
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(
            _pump_binance_usdm(
                args.leader_symbol,
                args.open_timeout_sec,
                queue,
                stop,
                args.ws_reconnect_delay_sec,
                args.ws_max_reconnects,
            )
        ),
        asyncio.create_task(
            _pump_mexc_contract(
                args.lagger_symbol,
                args.open_timeout_sec,
                queue,
                stop,
                args.ws_reconnect_delay_sec,
                args.ws_max_reconnects,
            )
        ),
    ]

    try:
        while True:
            _consume_finished_task_errors(tasks)
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                if all(task.done() for task in tasks):
                    return
                continue

            if isinstance(item, Exception):
                print(
                    json.dumps(
                        {
                            "warning": "live_paper_websocket_reconnect",
                            "error": str(item),
                            "paper_mode_only": True,
                        },
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    file=sys.stderr,
                )
                if all(task.done() for task in tasks) and queue.empty():
                    return
                continue
            yield item
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _pump_binance_usdm(
    symbol: str,
    open_timeout_sec: float,
    queue: asyncio.Queue[Quote | Exception],
    stop: asyncio.Event,
    reconnect_delay_sec: float = 2.0,
    max_reconnects: int = 50,
) -> None:
    import websockets

    reconnects = 0
    while not stop.is_set():
        spec = combined_book_ticker_url([symbol], MarketType.USDT_PERP)
        try:
            async with websockets.connect(
                spec.url,
                open_timeout=open_timeout_sec,
                ping_interval=20,
                ping_timeout=60,
            ) as ws:
                reconnects = 0
                async for raw in ws:
                    if stop.is_set():
                        return
                    parsed = parse_book_ticker_message(
                        json.loads(raw),
                        MarketType.USDT_PERP,
                        receive_timestamp(),
                    )
                    if parsed is not None:
                        await queue.put(quote_from_book_ticker(parsed))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reconnects += 1
            if not stop.is_set():
                await queue.put(exc)
            if reconnects > max_reconnects:
                return
            await _reconnect_sleep(stop, reconnect_delay_sec)


async def _pump_mexc_contract(
    symbol: str,
    open_timeout_sec: float,
    queue: asyncio.Queue[Quote | Exception],
    stop: asyncio.Event,
    reconnect_delay_sec: float = 2.0,
    max_reconnects: int = 50,
) -> None:
    import websockets

    reconnects = 0
    while not stop.is_set():
        try:
            async with websockets.connect(
                MEXC_CONTRACT_WS_URL,
                open_timeout=open_timeout_sec,
                ping_interval=None,
            ) as ws:
                reconnects = 0
                await ws.send(json.dumps(subscribe_ticker(symbol).message))
                async for raw in ws:
                    if stop.is_set():
                        return
                    parsed = parse_mexc_message(json.loads(raw), receive_timestamp())
                    if isinstance(parsed, BookTicker):
                        await queue.put(quote_from_book_ticker(parsed))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reconnects += 1
            if not stop.is_set():
                await queue.put(exc)
            if reconnects > max_reconnects:
                return
            await _reconnect_sleep(stop, reconnect_delay_sec)


def _consume_finished_task_errors(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if task.done() and not task.cancelled():
            task.exception()


async def _reconnect_sleep(stop: asyncio.Event, delay_sec: float) -> None:
    if delay_sec <= 0:
        return
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay_sec)
    except TimeoutError:
        return


def _decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _stop_reason(summary_payload: dict[str, object], args: argparse.Namespace) -> str:
    closed = int(summary_payload.get("closed_positions", 0) or 0)
    target = args.target_closed_trades
    if target is not None and closed >= target:
        return "target_closed_trades_reached"
    quotes = int(summary_payload.get("quotes", 0) or 0)
    if args.live_ws and quotes >= int(args.events):
        return "max_events_reached"
    return "stream_ended"


def _stop_reason_from_summary(summary: object, args: argparse.Namespace) -> str:
    return _stop_reason(replay_paper_summary_to_dict(summary), args)


if __name__ == "__main__":
    main()
