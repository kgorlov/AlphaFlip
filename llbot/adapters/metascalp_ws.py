"""MetaScalp private WebSocket capture helpers."""

import json
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llbot.service.clock_sync import receive_timestamp
from llbot.storage.audit_jsonl import audit_record_to_dict


WebSocketConnector = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MetaScalpPrivateWsMessage:
    raw: dict[str, Any]
    local_ts_ms: int
    receive_monotonic_ns: int

    def to_json_record(self) -> dict[str, Any]:
        return {
            "event_type": "metascalp_private_ws_update",
            "local_ts_ms": self.local_ts_ms,
            "receive_monotonic_ns": self.receive_monotonic_ns,
            "raw": audit_record_to_dict(self.raw),
        }


@dataclass(frozen=True, slots=True)
class MetaScalpPrivateCaptureResult:
    ws_url: str | None
    out: str
    captured: int
    subscriptions_sent: int
    opened_websocket: bool
    safety: dict[str, bool] = field(
        default_factory=lambda: {
            "submits_orders": False,
            "cancels_orders": False,
            "reads_secrets": False,
        }
    )


def metascalp_ws_url(base_url: str, ws_path: str = "/") -> str:
    if not ws_path.startswith("/"):
        ws_path = f"/{ws_path}"
    if base_url.startswith("https://"):
        prefix = "wss://"
        host = base_url.removeprefix("https://").rstrip("/")
    elif base_url.startswith("http://"):
        prefix = "ws://"
        host = base_url.removeprefix("http://").rstrip("/")
    elif base_url.startswith(("ws://", "wss://")):
        prefix = ""
        host = base_url.rstrip("/")
    else:
        prefix = "ws://"
        host = base_url.rstrip("/")
    return f"{prefix}{host}{ws_path}"


def subscribe_connection_message(connection_id: int) -> dict[str, Any]:
    return {"Type": "subscribe", "Data": {"ConnectionId": connection_id}}


def unsubscribe_connection_message(connection_id: int) -> dict[str, Any]:
    return {"Type": "unsubscribe", "Data": {"ConnectionId": connection_id}}


def parse_subscription_json(values: list[str]) -> list[dict[str, Any]]:
    subscriptions: list[dict[str, Any]] = []
    for value in values:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("Subscription JSON must decode to an object")
        subscriptions.append(payload)
    return subscriptions


async def capture_metascalp_private_updates(
    ws_url: str,
    *,
    events: int,
    out: str | Path,
    subscriptions: list[dict[str, Any]] | None = None,
    open_timeout_sec: float = 20.0,
    idle_timeout_sec: float | None = None,
    connector: WebSocketConnector | None = None,
) -> MetaScalpPrivateCaptureResult:
    """Capture MetaScalp private WebSocket updates into JSONL.

    When events is zero, the output file is created and no WebSocket connection is opened.
    This is used for deterministic smoke checks.
    """

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if events <= 0:
        out_path.write_text("", encoding="utf-8")
        return MetaScalpPrivateCaptureResult(
            ws_url=ws_url,
            out=str(out_path),
            captured=0,
            subscriptions_sent=0,
            opened_websocket=False,
        )

    if connector is None:
        import websockets

        connector = websockets.connect

    captured = 0
    subscriptions_sent = 0
    with out_path.open("w", encoding="utf-8") as writer:
        async with connector(ws_url, open_timeout=open_timeout_sec, ping_interval=20, ping_timeout=60) as ws:
            for subscription in subscriptions or []:
                await ws.send(json.dumps(subscription, ensure_ascii=True, separators=(",", ":")))
                subscriptions_sent += 1
            iterator = ws.__aiter__()
            while captured < events:
                try:
                    if idle_timeout_sec is None:
                        raw_message = await iterator.__anext__()
                    else:
                        raw_message = await asyncio.wait_for(
                            iterator.__anext__(),
                            timeout=idle_timeout_sec,
                        )
                except (StopAsyncIteration, asyncio.TimeoutError):
                    break
                message = decode_ws_json(raw_message)
                if message is None:
                    continue
                received = receive_timestamp()
                record = MetaScalpPrivateWsMessage(
                    raw=message,
                    local_ts_ms=received.local_ts_ms,
                    receive_monotonic_ns=received.monotonic_ns,
                )
                writer.write(json.dumps(record.to_json_record(), ensure_ascii=True, separators=(",", ":")))
                writer.write("\n")
                writer.flush()
                captured += 1

    return MetaScalpPrivateCaptureResult(
        ws_url=ws_url,
        out=str(out_path),
        captured=captured,
        subscriptions_sent=subscriptions_sent,
        opened_websocket=True,
    )


def decode_ws_json(raw_message: Any) -> dict[str, Any] | None:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    if isinstance(raw_message, str):
        payload = json.loads(raw_message)
    elif isinstance(raw_message, dict):
        payload = raw_message
    else:
        return None
    return payload if isinstance(payload, dict) else None


def read_captured_raw(path: str | Path) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            continue
        raw = payload.get("raw")
        if isinstance(raw, dict):
            updates.append(raw)
        else:
            updates.append(payload)
    return updates
