from decimal import Decimal
from unittest import IsolatedAsyncioTestCase

from llbot.config import UniverseConfig
from llbot.domain.enums import MarketProfileName, MarketType, Venue
from llbot.domain.market_data import BookTicker, DepthLevel, ExchangeSymbolInfo, OrderBookDepth, Stats24h
from llbot.universe.provider import HybridUniverseProvider


class UniverseProviderTests(IsolatedAsyncioTestCase):
    async def test_refresh_perp_to_perp_builds_ranked_profiles(self) -> None:
        provider = HybridUniverseProvider(
            config=UniverseConfig(
                active_profile=MarketProfileName.PERP_TO_PERP,
                top_n_live=1,
                min_quote_volume_usd_24h=Decimal("1000"),
                min_top5_depth_usd=Decimal("100"),
                max_tick_bps=Decimal("20"),
            ),
            binance_usdm=_BinanceUsdmFake(),
            mexc_contract=_MexcContractFake(),
            depth_hydration_limit=2,
            depth_spacing_sec=0,
        )

        profiles = await provider.refresh()

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].canonical_symbol, "BTCUSDT")
        self.assertEqual(profiles[0].lagger_symbol, "BTC_USDT")
        self.assertEqual(profiles[0].contract_size, Decimal("0.001"))
        self.assertIn("universe_score", profiles[0].metadata)


class _BinanceUsdmFake:
    async def exchange_info(self):
        return [
            ExchangeSymbolInfo(
                venue=Venue.BINANCE,
                market=MarketType.USDT_PERP,
                symbol="BTCUSDT",
                status="TRADING",
                base_asset="BTC",
                quote_asset="USDT",
                trading_enabled=True,
                price_tick=Decimal("0.1"),
            )
        ]

    async def ticker_24hr(self):
        return {
            "BTCUSDT": Stats24h(
                Venue.BINANCE,
                MarketType.USDT_PERP,
                "BTCUSDT",
                quote_volume=Decimal("10000000"),
            )
        }

    async def book_ticker(self):
        return {
            "BTCUSDT": BookTicker(
                Venue.BINANCE,
                MarketType.USDT_PERP,
                "BTCUSDT",
                bid_price=Decimal("100"),
                bid_qty=Decimal("100"),
                ask_price=Decimal("100.05"),
                ask_qty=Decimal("100"),
            )
        }

    async def depth(self, symbol, limit=5):
        return OrderBookDepth(
            Venue.BINANCE,
            MarketType.USDT_PERP,
            symbol,
            bids=(DepthLevel(Decimal("100"), Decimal("100")),),
            asks=(DepthLevel(Decimal("100.05"), Decimal("100")),),
        )


class _MexcContractFake:
    async def contract_detail(self):
        return [
            ExchangeSymbolInfo(
                venue=Venue.MEXC,
                market=MarketType.USDT_PERP,
                symbol="BTC_USDT",
                status="0",
                base_asset="BTC",
                quote_asset="USDT",
                trading_enabled=True,
                api_allowed=True,
                price_tick=Decimal("0.1"),
                qty_step=Decimal("1"),
                min_qty=Decimal("1"),
                max_qty=Decimal("1000000"),
                contract_size=Decimal("0.001"),
                maker_fee_rate=Decimal("0.0002"),
                taker_fee_rate=Decimal("0.0006"),
            )
        ]

    async def ticker(self):
        stats = {
            "BTC_USDT": Stats24h(
                Venue.MEXC,
                MarketType.USDT_PERP,
                "BTC_USDT",
                quote_volume=Decimal("9000000"),
            )
        }
        books = {
            "BTC_USDT": BookTicker(
                Venue.MEXC,
                MarketType.USDT_PERP,
                "BTC_USDT",
                bid_price=Decimal("99.95"),
                bid_qty=None,
                ask_price=Decimal("100.00"),
                ask_qty=None,
            )
        }
        return stats, books

    async def depth(self, symbol, limit=5):
        return OrderBookDepth(
            Venue.MEXC,
            MarketType.USDT_PERP,
            symbol,
            bids=(DepthLevel(Decimal("99.95"), Decimal("2000")),),
            asks=(DepthLevel(Decimal("100.00"), Decimal("2000")),),
        )
