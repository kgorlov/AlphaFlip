import argparse
from unittest import IsolatedAsyncioTestCase, TestCase

from apps import metascalp_demo_cancel as cli
from llbot.adapters.metascalp import MetaScalpInstance


class MetaScalpDemoCancelCliTests(IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        cli.resolve_connection.__globals__["discover_metascalp"] = _ORIGINAL_DISCOVER
        cli.resolve_connection.__globals__["AioHttpJsonClient"] = _ORIGINAL_RESOLVE_HTTP
        cli.AioHttpJsonClient = _ORIGINAL_HTTP

    async def test_manual_connection_path_is_dry_run_by_default(self) -> None:
        result = await cli.run(_args(connection_id=11))

        self.assertEqual(result["decision_result"], "cancel_dry_run_planned")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["submit_allowed"])
        self.assertEqual(result["endpoint"], "/api/connections/11/orders/cancel")
        self.assertEqual(result["request"]["ClientId"], "llb-cli-intent")
        self.assertEqual(result["metascalp_health"]["connection_id"], 11)

    async def test_submit_demo_cancel_requires_discovery(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            await cli.run(
                _args(
                    connection_id=11,
                    submit_demo=True,
                    confirm_demo_cancel=cli.CONFIRM_DEMO_CANCEL,
                )
            )

        self.assertIn("--submit-demo requires --discover", str(raised.exception))

    async def test_discovery_cancel_uses_discovered_base_url_and_posts(self) -> None:
        async def fake_discover(host: str, port_min: int, port_max: int) -> MetaScalpInstance:
            return MetaScalpInstance(host=host, port=17850, ping={"ok": True})

        cli.resolve_connection.__globals__["discover_metascalp"] = fake_discover
        cli.resolve_connection.__globals__["AioHttpJsonClient"] = _FakeHttp
        cli.AioHttpJsonClient = _FakeHttp
        _FakeHttp.instances = []

        result = await cli.run(
            _args(
                discover=True,
                connection_id=None,
                submit_demo=True,
                confirm_demo_cancel=cli.CONFIRM_DEMO_CANCEL,
            )
        )

        self.assertEqual(result["decision_result"], "cancel_accepted")
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["submit_allowed"])
        self.assertEqual(result["metascalp_base_url"], "http://127.0.0.1:17850")
        self.assertEqual(_FakeHttp.instances[-1].post_calls[0][0], "/api/connections/11/orders/cancel")


class MetaScalpDemoCancelCliPureTests(TestCase):
    def test_should_allow_cancel_requires_exact_confirmation(self) -> None:
        self.assertFalse(cli.should_allow_cancel(_args(submit_demo=False, confirm_demo_cancel=None)))
        self.assertFalse(cli.should_allow_cancel(_args(submit_demo=True, confirm_demo_cancel="wrong")))
        self.assertTrue(
            cli.should_allow_cancel(
                _args(submit_demo=True, confirm_demo_cancel=cli.CONFIRM_DEMO_CANCEL)
            )
        )


class _FakeHttp:
    instances = []

    def __init__(self, base_url, timeout_sec=1.0):
        self.base_url = base_url
        self.timeout_sec = timeout_sec
        self.post_calls = []
        self.__class__.instances.append(self)

    async def get_json(self, path, params=None):
        if path == "/api/connections":
            return {
                "Data": [
                    {
                        "Id": 11,
                        "Name": "MEXC demo",
                        "Exchange": "Mexc",
                        "Market": "UsdtFutures",
                        "State": 2,
                        "ViewMode": False,
                        "DemoMode": True,
                    }
                ]
            }
        raise AssertionError(path)

    async def post_json(self, path, payload=None):
        self.post_calls.append((path, payload))
        return {"Data": {"ClientId": payload["ClientId"], "Cancelled": True}}


def _args(**overrides) -> argparse.Namespace:
    values = {
        "host": "127.0.0.1",
        "port_min": 17845,
        "port_max": 17855,
        "base_url": None,
        "discover": False,
        "connection_id": 11,
        "exchange": "mexc",
        "market_contains": "futures",
        "intent_id": "cli-intent",
        "client_id": "llb-cli-intent",
        "order_id": "ord-1",
        "symbol": "BTC_USDT",
        "reason": "ttl_expired",
        "due_ts_ms": 4000,
        "submit_demo": False,
        "confirm_demo_cancel": None,
        "out": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


_ORIGINAL_DISCOVER = cli.resolve_connection.__globals__["discover_metascalp"]
_ORIGINAL_RESOLVE_HTTP = cli.resolve_connection.__globals__["AioHttpJsonClient"]
_ORIGINAL_HTTP = cli.AioHttpJsonClient
