from decimal import Decimal
from unittest import TestCase

from llbot.domain.enums import Venue
from llbot.signals.leadlag import MidpointSample, estimate_leadership


class LeadLagTests(TestCase):
    def test_leader_score_detects_stable_binance_lead(self) -> None:
        binance = _samples(
            0,
            [100, 101, 100.5, 102, 101.5, 103, 102.75, 104],
        )
        mexc = _samples(
            100,
            [100, 101, 100.5, 102, 101.5, 103, 102.75, 104],
        )

        result = estimate_leadership(
            binance,
            mexc,
            candidate_lags_ms=(50, 100, 200),
            min_pairs=5,
            min_score=Decimal("0.8"),
        )

        self.assertEqual(result.leader, Venue.BINANCE)
        self.assertEqual(result.lagger, Venue.MEXC)
        self.assertEqual(result.lag_ms, 100)
        self.assertGreaterEqual(result.leader_score, Decimal("0.8"))

    def test_leader_score_requires_stable_positive_lag(self) -> None:
        binance = _samples(0, [100, 101, 100, 101, 100, 101, 100, 101])
        mexc = _samples(100, [100, 99, 100, 99, 100, 99, 100, 99])

        result = estimate_leadership(
            binance,
            mexc,
            candidate_lags_ms=(100,),
            min_pairs=5,
            min_score=Decimal("0.55"),
        )

        self.assertIsNone(result.leader)
        self.assertEqual(result.reason, "unstable")

    def test_insufficient_samples_are_rejected(self) -> None:
        result = estimate_leadership(
            [MidpointSample(0, Decimal("100"))],
            [MidpointSample(0, Decimal("100"))],
        )

        self.assertIsNone(result.leader)
        self.assertEqual(result.reason, "insufficient_samples")


def _samples(start_ts_ms: int, mids: list[float]) -> list[MidpointSample]:
    return [
        MidpointSample(start_ts_ms + idx * 100, Decimal(str(mid)))
        for idx, mid in enumerate(mids)
    ]

