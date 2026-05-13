"""Online per-symbol lag calibration."""

from dataclasses import dataclass
from decimal import Decimal


DEFAULT_CANDIDATE_LAGS_MS = (25, 50, 100, 200, 500, 1000)


@dataclass(frozen=True, slots=True)
class LagCandidateStats:
    lag_ms: int
    samples: int = 0
    hits: int = 0
    residual_sum_sq: Decimal = Decimal("0")
    paper_pnl_usd: Decimal = Decimal("0")

    @property
    def hit_rate(self) -> Decimal:
        if self.samples == 0:
            return Decimal("0")
        return Decimal(self.hits) / Decimal(self.samples)

    @property
    def residual_variance(self) -> Decimal:
        if self.samples == 0:
            return Decimal("0")
        return self.residual_sum_sq / Decimal(self.samples)


@dataclass(frozen=True, slots=True)
class LagObservation:
    symbol: str
    lag_ms: int
    predicted_move_bps: Decimal
    actual_move_bps: Decimal
    paper_pnl_usd: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class LagSelection:
    symbol: str
    lag_ms: int | None
    reason: str
    stats: LagCandidateStats | None = None
    score: Decimal | None = None


class OnlineLagCalibrator:
    """Track rolling lag quality and select the best candidate lag per symbol."""

    def __init__(
        self,
        candidate_lags_ms: tuple[int, ...] = DEFAULT_CANDIDATE_LAGS_MS,
        min_samples: int = 10,
        pnl_weight: Decimal = Decimal("1"),
        residual_penalty: Decimal = Decimal("1"),
    ) -> None:
        if not candidate_lags_ms:
            raise ValueError("candidate_lags_ms must not be empty")
        self.candidate_lags_ms = tuple(candidate_lags_ms)
        self.min_samples = min_samples
        self.pnl_weight = pnl_weight
        self.residual_penalty = residual_penalty
        self._stats: dict[str, dict[int, LagCandidateStats]] = {}

    def update(self, observation: LagObservation) -> LagCandidateStats:
        if observation.lag_ms not in self.candidate_lags_ms:
            raise ValueError(f"Unsupported lag candidate: {observation.lag_ms}")
        by_lag = self._stats.setdefault(
            observation.symbol,
            {lag_ms: LagCandidateStats(lag_ms=lag_ms) for lag_ms in self.candidate_lags_ms},
        )
        current = by_lag[observation.lag_ms]
        residual = observation.actual_move_bps - observation.predicted_move_bps
        hit = _same_direction(observation.predicted_move_bps, observation.actual_move_bps)
        updated = LagCandidateStats(
            lag_ms=current.lag_ms,
            samples=current.samples + 1,
            hits=current.hits + (1 if hit else 0),
            residual_sum_sq=current.residual_sum_sq + residual * residual,
            paper_pnl_usd=current.paper_pnl_usd + observation.paper_pnl_usd,
        )
        by_lag[observation.lag_ms] = updated
        return updated

    def stats(self, symbol: str) -> dict[int, LagCandidateStats]:
        by_lag = self._stats.get(symbol)
        if by_lag is None:
            return {lag_ms: LagCandidateStats(lag_ms=lag_ms) for lag_ms in self.candidate_lags_ms}
        return dict(by_lag)

    def select(self, symbol: str) -> LagSelection:
        candidates = [
            stats
            for stats in self.stats(symbol).values()
            if stats.samples >= self.min_samples
        ]
        if not candidates:
            return LagSelection(symbol=symbol, lag_ms=None, reason="insufficient_samples")
        best = max(candidates, key=lambda stats: (self._score(stats), -stats.lag_ms))
        return LagSelection(
            symbol=symbol,
            lag_ms=best.lag_ms,
            reason="ok",
            stats=best,
            score=self._score(best),
        )

    def _score(self, stats: LagCandidateStats) -> Decimal:
        return (
            stats.hit_rate * Decimal("100")
            + stats.paper_pnl_usd * self.pnl_weight
            - stats.residual_variance * self.residual_penalty
        )


def _same_direction(predicted: Decimal, actual: Decimal) -> bool:
    if predicted == 0 or actual == 0:
        return False
    return (predicted > 0 and actual > 0) or (predicted < 0 and actual < 0)
