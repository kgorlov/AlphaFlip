from decimal import Decimal
from unittest import TestCase

from llbot.signals.lag_calibrator import (
    DEFAULT_CANDIDATE_LAGS_MS,
    LagObservation,
    OnlineLagCalibrator,
)


class OnlineLagCalibratorTests(TestCase):
    def test_tracks_default_candidate_lags_and_rejects_unknown_lag(self) -> None:
        calibrator = OnlineLagCalibrator(min_samples=1)

        self.assertEqual(DEFAULT_CANDIDATE_LAGS_MS, (25, 50, 100, 200, 500, 1000))
        self.assertEqual(tuple(calibrator.stats("BTCUSDT")), DEFAULT_CANDIDATE_LAGS_MS)

        with self.assertRaises(ValueError):
            calibrator.update(
                LagObservation(
                    symbol="BTCUSDT",
                    lag_ms=75,
                    predicted_move_bps=Decimal("1"),
                    actual_move_bps=Decimal("1"),
                )
            )

    def test_selects_lag_by_hit_rate_residual_variance_and_pnl(self) -> None:
        calibrator = OnlineLagCalibrator(min_samples=3, pnl_weight=Decimal("1"))
        for _ in range(3):
            calibrator.update(
                LagObservation(
                    symbol="BTCUSDT",
                    lag_ms=50,
                    predicted_move_bps=Decimal("5"),
                    actual_move_bps=Decimal("4.8"),
                    paper_pnl_usd=Decimal("0.2"),
                )
            )
            calibrator.update(
                LagObservation(
                    symbol="BTCUSDT",
                    lag_ms=100,
                    predicted_move_bps=Decimal("5"),
                    actual_move_bps=Decimal("-2"),
                    paper_pnl_usd=Decimal("-0.1"),
                )
            )

        selected = calibrator.select("BTCUSDT")

        self.assertEqual(selected.reason, "ok")
        self.assertEqual(selected.lag_ms, 50)
        assert selected.stats is not None
        self.assertEqual(selected.stats.samples, 3)
        self.assertEqual(selected.stats.hit_rate, Decimal("1"))
        self.assertGreater(selected.score, Decimal("0"))

    def test_rejects_selection_until_min_samples_are_available(self) -> None:
        calibrator = OnlineLagCalibrator(min_samples=2)
        calibrator.update(
            LagObservation(
                symbol="BTCUSDT",
                lag_ms=25,
                predicted_move_bps=Decimal("1"),
                actual_move_bps=Decimal("1"),
            )
        )

        selected = calibrator.select("BTCUSDT")

        self.assertIsNone(selected.lag_ms)
        self.assertEqual(selected.reason, "insufficient_samples")
