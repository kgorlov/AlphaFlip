from unittest import TestCase

from llbot.domain.enums import MarketProfileName, MarketType
from llbot.universe.symbol_mapper import (
    SymbolMapper,
    binance_usdm_to_mexc_contract,
    mexc_contract_to_binance_usdm,
)


class SymbolMapperTests(TestCase):
    def test_perp_mapping(self) -> None:
        self.assertEqual(binance_usdm_to_mexc_contract("btcusdt"), "BTC_USDT")
        self.assertEqual(mexc_contract_to_binance_usdm("BTC_USDT"), "BTCUSDT")

    def test_build_perp_profile(self) -> None:
        profile = SymbolMapper(MarketProfileName.PERP_TO_PERP).build_profile("ethusdt")

        self.assertEqual(profile.canonical_symbol, "ETHUSDT")
        self.assertEqual(profile.leader_symbol, "ETHUSDT")
        self.assertEqual(profile.lagger_symbol, "ETH_USDT")
        self.assertEqual(profile.leader_market, MarketType.USDT_PERP)
        self.assertEqual(profile.lagger_market, MarketType.USDT_PERP)

    def test_build_spot_profile(self) -> None:
        profile = SymbolMapper(MarketProfileName.SPOT_TO_SPOT).build_profile("SOL/USDT")

        self.assertEqual(profile.canonical_symbol, "SOLUSDT")
        self.assertEqual(profile.lagger_symbol, "SOLUSDT")
        self.assertEqual(profile.leader_market, MarketType.SPOT)
        self.assertEqual(profile.lagger_market, MarketType.SPOT)

