from decimal import Decimal
from unittest import TestCase

from apps.hydrate_universe import profiles_payload
from llbot.domain.enums import MarketProfileName, MarketType, Venue
from llbot.domain.models import SymbolProfile


class HydrateUniverseTests(TestCase):
    def test_profiles_payload_serializes_ranked_candidates_safely(self) -> None:
        payload = profiles_payload(
            [
                SymbolProfile(
                    canonical_symbol="SOLUSDT",
                    leader_symbol="SOLUSDT",
                    lagger_symbol="SOL_USDT",
                    profile=MarketProfileName.PERP_TO_PERP,
                    leader_venue=Venue.BINANCE,
                    lagger_venue=Venue.MEXC,
                    leader_market=MarketType.USDT_PERP,
                    lagger_market=MarketType.USDT_PERP,
                    min_qty=Decimal("1"),
                    qty_step=Decimal("1"),
                    price_tick=Decimal("0.001"),
                    contract_size=Decimal("1"),
                    metadata={"universe_score": Decimal("0.42")},
                )
            ]
        )

        self.assertFalse(payload["safety"]["orders_submitted"])
        self.assertFalse(payload["safety"]["live_trading_enabled"])
        self.assertEqual(payload["candidates"][0]["rank"], 1)
        self.assertEqual(payload["candidates"][0]["canonical_symbol"], "SOLUSDT")
        self.assertEqual(payload["candidates"][0]["lagger_symbol"], "SOL_USDT")
        self.assertEqual(payload["candidates"][0]["metadata"]["universe_score"], "0.42")
