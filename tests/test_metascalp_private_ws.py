import json
import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from llbot.adapters.metascalp_ws import (
    capture_metascalp_private_updates,
    decode_ws_json,
    metascalp_ws_url,
    parse_subscription_json,
    read_captured_raw,
    subscribe_connection_message,
)


class MetaScalpPrivateWsHelperTests(TestCase):
    def test_builds_ws_url_from_http_base(self) -> None:
        self.assertEqual(
            metascalp_ws_url("http://127.0.0.1:17845", "/api/ws"),
            "ws://127.0.0.1:17845/api/ws",
        )
        self.assertEqual(
            metascalp_ws_url("https://example.test", "private"),
            "wss://example.test/private",
        )
        self.assertEqual(
            metascalp_ws_url("http://127.0.0.1:17845"),
            "ws://127.0.0.1:17845/",
        )

    def test_builds_documented_connection_subscribe_message(self) -> None:
        self.assertEqual(
            subscribe_connection_message(11),
            {"Type": "subscribe", "Data": {"ConnectionId": 11}},
        )

    def test_parses_subscription_json_objects(self) -> None:
        self.assertEqual(
            parse_subscription_json(['{"method":"sub.orders"}']),
            [{"method": "sub.orders"}],
        )
        with self.assertRaises(ValueError):
            parse_subscription_json(["[]"])

    def test_decodes_text_bytes_and_ignores_non_objects(self) -> None:
        self.assertEqual(decode_ws_json('{"Type":"OrderUpdate"}'), {"Type": "OrderUpdate"})
        self.assertEqual(decode_ws_json(b'{"Type":"BalanceUpdate"}'), {"Type": "BalanceUpdate"})
        self.assertIsNone(decode_ws_json("[1,2]"))


class MetaScalpPrivateWsCaptureTests(IsolatedAsyncioTestCase):
    async def test_events_zero_creates_empty_file_without_opening_websocket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "updates.jsonl"

            result = await capture_metascalp_private_updates(
                "ws://127.0.0.1:17845/ws",
                events=0,
                out=out,
                connector=_failing_connector,
            )

            self.assertTrue(out.exists())
            self.assertEqual(out.read_text(encoding="utf-8"), "")
            self.assertEqual(result.captured, 0)
            self.assertFalse(result.opened_websocket)

    async def test_captures_messages_and_sends_subscriptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "updates.jsonl"
            fake = FakeConnector(
                [
                    json.dumps({"Type": "OrderUpdate", "Data": {"ClientId": "llb-1"}}),
                    json.dumps({"Type": "BalanceUpdate", "Data": {"Asset": "USDT"}}),
                ]
            )

            result = await capture_metascalp_private_updates(
                "ws://127.0.0.1:17845/ws",
                events=2,
                out=out,
                subscriptions=[{"method": "sub.orders"}],
                connector=fake,
            )

            self.assertEqual(result.captured, 2)
            self.assertTrue(result.opened_websocket)
            self.assertEqual(fake.websocket.sent, ['{"method":"sub.orders"}'])
            rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["event_type"], "metascalp_private_ws_update")
            self.assertEqual(rows[0]["raw"]["Type"], "OrderUpdate")
            self.assertEqual(read_captured_raw(out)[1]["Type"], "BalanceUpdate")

    async def test_idle_timeout_returns_partial_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "updates.jsonl"
            fake = FakeConnector([json.dumps({"Type": "subscribed", "Data": {"ConnectionId": 4}})])

            result = await capture_metascalp_private_updates(
                "ws://127.0.0.1:17845/",
                events=2,
                out=out,
                subscriptions=[{"Type": "subscribe", "Data": {"ConnectionId": 4}}],
                idle_timeout_sec=0.01,
                connector=fake,
            )

            self.assertEqual(result.captured, 1)
            self.assertEqual(len(out.read_text(encoding="utf-8").splitlines()), 1)


def _failing_connector(*args, **kwargs):
    raise AssertionError("connector should not be called")


class FakeConnector:
    def __init__(self, messages):
        self.websocket = FakeWebSocket(messages)

    def __call__(self, *args, **kwargs):
        return self.websocket


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def send(self, payload):
        self.sent.append(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)
