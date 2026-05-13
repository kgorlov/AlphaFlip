from decimal import Decimal
from unittest import TestCase

from llbot.config import parse_config
from llbot.domain.enums import MarketProfileName, RuntimeMode


class ConfigTests(TestCase):
    def test_parse_example_shape(self) -> None:
        config = parse_config(
            {
                "runtime": {"mode": "shadow"},
                "universe": {"active_profile": "perp_to_perp", "top_n_live": 12},
                "signal": {"safety_bps": 3},
                "risk": {"max_daily_loss_usd": 42, "max_active_symbols": 3},
            }
        )

        self.assertEqual(config.runtime_mode, RuntimeMode.SHADOW)
        self.assertEqual(config.universe.active_profile, MarketProfileName.PERP_TO_PERP)
        self.assertEqual(config.universe.top_n_live, 12)
        self.assertEqual(config.signal.safety_bps, Decimal("3"))
        self.assertEqual(config.risk.max_daily_loss_usd, Decimal("42"))
        self.assertEqual(config.risk.max_active_symbols, 3)

    def test_live_mode_requires_runtime_flow(self) -> None:
        with self.assertRaises(ValueError):
            parse_config({"runtime": {"mode": "live", "live_requires_runtime_confirmation": True}})
