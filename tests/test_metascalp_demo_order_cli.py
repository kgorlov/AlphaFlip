import argparse
from unittest import IsolatedAsyncioTestCase, TestCase

from apps import metascalp_demo_order as cli
from llbot.adapters.metascalp import MetaScalpInstance


class MetaScalpDemoOrderCliTests(IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        cli.discover_metascalp = _ORIGINAL_DISCOVER
        cli.AioHttpJsonClient = _ORIGINAL_HTTP

    async def test_manual_connection_path_is_dry_run_by_default(self) -> None:
        result = await cli.run(_args(connection_id=11))

        self.assertEqual(result["decision_result"], "dry_run_planned")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["submit_requested"])
        self.assertFalse(result["submit_allowed"])
        self.assertEqual(result["metascalp_base_url"], "http://127.0.0.1:17845")
        self.assertEqual(result["metascalp_health"]["connection_id"], 11)
        self.assertTrue(result["metascalp_health"]["demo_mode"])
        self.assertEqual(result["request"]["Price"], "100.1")
        self.assertEqual(result["request"]["ClientId"], "llb-cli-intent")

    async def test_submit_demo_requires_discovery_to_verify_connection(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            await cli.run(
                _args(
                    connection_id=11,
                    submit_demo=True,
                    confirm_demo_submit=cli.CONFIRM_DEMO_SUBMIT,
                )
            )

        self.assertIn("--submit-demo requires --discover", str(raised.exception))

    async def test_discovery_submit_uses_discovered_base_url_and_posts(self) -> None:
        async def fake_discover(host: str, port_min: int, port_max: int) -> MetaScalpInstance:
            return MetaScalpInstance(host=host, port=17850, ping={"ok": True})

        cli.discover_metascalp = fake_discover
        cli.AioHttpJsonClient = _FakeHttp
        _FakeHttp.instances = []

        result = await cli.run(
            _args(
                discover=True,
                connection_id=None,
                submit_demo=True,
                confirm_demo_submit=cli.CONFIRM_DEMO_SUBMIT,
            )
        )

        self.assertEqual(result["decision_result"], "accepted")
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["submit_requested"])
        self.assertTrue(result["submit_allowed"])
        self.assertEqual(result["metascalp_base_url"], "http://127.0.0.1:17850")
        self.assertEqual(result["client_id_returned"], "llb-cli-intent")
        self.assertEqual(result["execution_time_ms"], 9)
        self.assertEqual(_FakeHttp.instances[-1].base_url, "http://127.0.0.1:17850")
        self.assertEqual(_FakeHttp.instances[-1].post_calls[0][0], "/api/connections/11/orders")

    async def test_discovery_rejects_non_demo_connection(self) -> None:
        async def fake_discover(host: str, port_min: int, port_max: int) -> MetaScalpInstance:
            return MetaScalpInstance(host=host, port=17850, ping={"ok": True})

        cli.discover_metascalp = fake_discover
        cli.AioHttpJsonClient = _FakeHttpNonDemo
        _FakeHttpNonDemo.instances = []

        with self.assertRaises(SystemExit) as raised:
            await cli.run(_args(discover=True, connection_id=None))

        self.assertIn("No connected DemoMode", str(raised.exception))


class MetaScalpDemoOrderCliPureTests(TestCase):
    def test_should_allow_submit_requires_exact_confirmation(self) -> None:
        self.assertFalse(cli.should_allow_submit(_args(submit_demo=False, confirm_demo_submit=None)))
        self.assertFalse(cli.should_allow_submit(_args(submit_demo=True, confirm_demo_submit="wrong")))
        self.assertTrue(
            cli.should_allow_submit(
                _args(submit_demo=True, confirm_demo_submit=cli.CONFIRM_DEMO_SUBMIT)
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
        return {"Data": {"ClientId": payload["ClientId"], "ExecutionTimeMs": 9}}


class _FakeHttpNonDemo(_FakeHttp):
    instances = []

    async def get_json(self, path, params=None):
        if path == "/api/connections":
            return {
                "Data": [
                    {
                        "Id": 11,
                        "Name": "MEXC live",
                        "Exchange": "Mexc",
                        "Market": "UsdtFutures",
                        "State": 2,
                        "ViewMode": False,
                        "DemoMode": False,
                    }
                ]
            }
        raise AssertionError(path)


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
        "symbol": "BTCUSDT",
        "execution_symbol": "BTC_USDT",
        "side": "buy",
        "qty": "2",
        "price_cap": "100.1",
        "intent_id": "cli-intent",
        "ttl_ms": 3000,
        "expected_edge_bps": "8",
        "min_qty": "1",
        "qty_step": "1",
        "price_tick": "0.1",
        "min_notional_usd": "200",
        "contract_size": "1",
        "submit_demo": False,
        "confirm_demo_submit": None,
        "out": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


_ORIGINAL_DISCOVER = cli.discover_metascalp
_ORIGINAL_HTTP = cli.AioHttpJsonClient
