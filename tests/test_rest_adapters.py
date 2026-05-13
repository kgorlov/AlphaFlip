from unittest import IsolatedAsyncioTestCase

from llbot.adapters.binance_usdm import BinanceUsdmRestClient
from llbot.adapters.metascalp import MetaScalpClient
from llbot.adapters.mexc_contract import MexcContractRestClient


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get_json(self, path, params=None):
        self.calls.append((path, params))
        return self.routes[path]

    async def post_json(self, path, payload=None):
        self.calls.append((path, payload))
        return self.routes[path]


class RestAdapterTests(IsolatedAsyncioTestCase):
    async def test_binance_usdm_parses_public_snapshots(self) -> None:
        http = FakeHttp(
            {
                "/fapi/v1/exchangeInfo": {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "TRADING",
                            "contractType": "PERPETUAL",
                            "baseAsset": "BTC",
                            "quoteAsset": "USDT",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                },
                "/fapi/v1/ticker/24hr": [
                    {"symbol": "BTCUSDT", "quoteVolume": "1000000", "volume": "10"}
                ],
                "/fapi/v1/ticker/bookTicker": [
                    {
                        "symbol": "BTCUSDT",
                        "bidPrice": "100",
                        "bidQty": "10",
                        "askPrice": "101",
                        "askQty": "9",
                        "time": 123,
                    }
                ],
            }
        )
        client = BinanceUsdmRestClient(http)

        symbols = await client.exchange_info()
        stats = await client.ticker_24hr()
        books = await client.book_ticker()

        self.assertTrue(symbols[0].trading_enabled)
        self.assertEqual(str(symbols[0].price_tick), "0.10")
        self.assertEqual(str(stats["BTCUSDT"].quote_volume), "1000000")
        self.assertEqual(str(books["BTCUSDT"].spread_bps), "99.50248756218905472636815920")

    async def test_mexc_contract_parses_detail_ticker_and_depth(self) -> None:
        http = FakeHttp(
            {
                "/api/v1/contract/detail": {
                    "success": True,
                    "data": [
                        {
                            "symbol": "BTC_USDT",
                            "baseCoin": "BTC",
                            "quoteCoin": "USDT",
                            "state": 0,
                            "apiAllowed": True,
                            "contractSize": "0.001",
                            "priceUnit": "0.1",
                            "volUnit": "1",
                            "minVol": "1",
                            "maxVol": "1000",
                            "makerFeeRate": "0.0002",
                            "takerFeeRate": "0.0006",
                        }
                    ],
                },
                "/api/v1/contract/ticker": {
                    "success": True,
                    "data": [
                        {
                            "symbol": "BTC_USDT",
                            "bid1": "100",
                            "ask1": "101",
                            "amount24": "2000000",
                            "volume24": "100",
                            "timestamp": 123,
                        }
                    ],
                },
                "/api/v1/contract/depth/BTC_USDT": {
                    "bids": [[100, 1000]],
                    "asks": [[101, 1000]],
                    "timestamp": 123,
                },
            }
        )
        client = MexcContractRestClient(http)

        details = await client.contract_detail()
        stats, books = await client.ticker()
        depth = await client.depth("BTC_USDT")

        self.assertTrue(details[0].trading_enabled)
        self.assertTrue(details[0].api_allowed)
        self.assertEqual(str(stats["BTC_USDT"].quote_volume), "2000000")
        self.assertEqual(str(books["BTC_USDT"].ask_price), "101")
        self.assertEqual(str(depth.top_depth_usd(contract_size=details[0].contract_size)), "100.000")

    async def test_metascalp_selects_demo_connection(self) -> None:
        http = FakeHttp(
            {
                "/api/connections": [
                    {
                        "Id": 11,
                        "Name": "MEXC demo",
                        "Exchange": "Mexc",
                        "ExchangeId": 1,
                        "Market": "UsdtFutures",
                        "MarketType": 1,
                        "State": 2,
                        "ViewMode": False,
                        "DemoMode": True,
                    }
                ]
            }
        )
        client = MetaScalpClient(http)

        connection = await client.select_connection("mexc", "futures", require_demo_mode=True)

        self.assertIsNotNone(connection)
        self.assertEqual(connection.id, 11)
        self.assertTrue(connection.connected)

    async def test_metascalp_parses_connections_wrapper(self) -> None:
        http = FakeHttp(
            {
                "/api/connections": {
                    "connections": [
                        {
                            "Id": 4,
                            "Name": "MEXC: Futures",
                            "Exchange": "MEXC",
                            "ExchangeId": 8,
                            "Market": "Futures",
                            "MarketType": 1,
                            "State": 2,
                            "ViewMode": False,
                            "DemoMode": True,
                        }
                    ]
                }
            }
        )
        client = MetaScalpClient(http)

        connection = await client.select_connection("mexc", None, require_demo_mode=True)

        self.assertIsNotNone(connection)
        self.assertEqual(connection.id, 4)
        self.assertEqual(connection.market, "Futures")

    async def test_metascalp_place_order_posts_payload(self) -> None:
        http = FakeHttp(
            {
                "/api/connections/11/orders": {
                    "Data": {"ClientId": "llb-test", "ExecutionTimeMs": 5}
                }
            }
        )
        client = MetaScalpClient(http)

        response = await client.place_order(11, {"ClientId": "llb-test"})

        self.assertEqual(http.calls, [("/api/connections/11/orders", {"ClientId": "llb-test"})])
        self.assertEqual(response["Data"]["ExecutionTimeMs"], 5)

    async def test_metascalp_cancel_order_posts_payload(self) -> None:
        http = FakeHttp(
            {
                "/api/connections/11/orders/cancel": {
                    "Data": {"ClientId": "llb-test", "Cancelled": True}
                }
            }
        )
        client = MetaScalpClient(http)

        response = await client.cancel_order(11, {"ClientId": "llb-test"})

        self.assertEqual(http.calls, [("/api/connections/11/orders/cancel", {"ClientId": "llb-test"})])
        self.assertTrue(response["Data"]["Cancelled"])
