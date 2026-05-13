"""Dynamic lead-lag scoring for same-symbol cross-exchange midpoint paths."""

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

from llbot.domain.enums import Venue


@dataclass(frozen=True, slots=True)
class MidpointSample:
    ts_ms: int
    mid: Decimal


@dataclass(frozen=True, slots=True)
class LagScore:
    lag_ms: int
    pairs: int
    correlation: Decimal
    sign_agreement: Decimal
    score: Decimal


@dataclass(frozen=True, slots=True)
class LeadershipResult:
    leader: Venue | None
    lagger: Venue | None
    leader_score: Decimal
    lag_ms: int | None
    lag_scores: tuple[LagScore, ...]
    reason: str = "ok"

    @property
    def stable(self) -> bool:
        return self.leader is not None and self.leader_score > 0


def estimate_leadership(
    binance: list[MidpointSample],
    mexc: list[MidpointSample],
    candidate_lags_ms: tuple[int, ...] = (25, 50, 100, 200, 500, 1000),
    min_pairs: int = 5,
    min_score: Decimal = Decimal("0.55"),
) -> LeadershipResult:
    """Estimate whether Binance or MEXC empirically leads in an event-time window."""

    binance = _clean_samples(binance)
    mexc = _clean_samples(mexc)
    if len(binance) < 2 or len(mexc) < 2:
        return LeadershipResult(None, None, Decimal("0"), None, (), "insufficient_samples")

    binance_scores = _direction_scores(binance, mexc, candidate_lags_ms, min_pairs)
    mexc_scores = _direction_scores(mexc, binance, candidate_lags_ms, min_pairs)
    all_scores = tuple(binance_scores + mexc_scores)
    best_binance = _best_score(binance_scores)
    best_mexc = _best_score(mexc_scores)

    if best_binance is None and best_mexc is None:
        return LeadershipResult(None, None, Decimal("0"), None, all_scores, "insufficient_pairs")

    if best_binance is not None and (best_mexc is None or best_binance.score > best_mexc.score):
        if best_binance.score < min_score:
            return LeadershipResult(None, None, best_binance.score, best_binance.lag_ms, all_scores, "unstable")
        return LeadershipResult(Venue.BINANCE, Venue.MEXC, best_binance.score, best_binance.lag_ms, all_scores)

    assert best_mexc is not None
    if best_mexc.score < min_score:
        return LeadershipResult(None, None, best_mexc.score, best_mexc.lag_ms, all_scores, "unstable")
    return LeadershipResult(Venue.MEXC, Venue.BINANCE, best_mexc.score, best_mexc.lag_ms, all_scores)


def _direction_scores(
    leader: list[MidpointSample],
    lagger: list[MidpointSample],
    candidate_lags_ms: tuple[int, ...],
    min_pairs: int,
) -> list[LagScore]:
    scores: list[LagScore] = []
    leader_returns = _returns(leader, lag_ms=0)
    for lag_ms in candidate_lags_ms:
        lagger_shifted = _returns(lagger, lag_ms=-lag_ms)
        aligned = _align_returns(leader_returns, lagger_shifted)
        if len(aligned) < min_pairs:
            continue
        xs = [item[0] for item in aligned]
        ys = [item[1] for item in aligned]
        corr = _correlation(xs, ys)
        sign = _sign_agreement(xs, ys)
        score = max(Decimal("0"), corr) * Decimal("0.7") + sign * Decimal("0.3")
        scores.append(
            LagScore(
                lag_ms=lag_ms,
                pairs=len(aligned),
                correlation=corr,
                sign_agreement=sign,
                score=score,
            )
        )
    return scores


def _returns(samples: list[MidpointSample], lag_ms: int) -> list[tuple[int, Decimal]]:
    out: list[tuple[int, Decimal]] = []
    for prev, current in zip(samples, samples[1:]):
        if prev.mid <= 0:
            continue
        ret = Decimal("10000") * (current.mid - prev.mid) / prev.mid
        out.append((current.ts_ms + lag_ms, ret))
    return out


def _align_returns(
    left: list[tuple[int, Decimal]],
    right: list[tuple[int, Decimal]],
    tolerance_ms: int = 5,
) -> list[tuple[Decimal, Decimal]]:
    aligned: list[tuple[Decimal, Decimal]] = []
    j = 0
    for ts_left, value_left in left:
        while j < len(right) and right[j][0] < ts_left - tolerance_ms:
            j += 1
        if j >= len(right):
            break
        ts_right, value_right = right[j]
        if abs(ts_right - ts_left) <= tolerance_ms:
            aligned.append((value_left, value_right))
    return aligned


def _correlation(xs: list[Decimal], ys: list[Decimal]) -> Decimal:
    if len(xs) != len(ys) or len(xs) < 2:
        return Decimal("0")
    x_float = [float(x) for x in xs]
    y_float = [float(y) for y in ys]
    x_mean = sum(x_float) / len(x_float)
    y_mean = sum(y_float) / len(y_float)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_float, y_float))
    x_var = sum((x - x_mean) ** 2 for x in x_float)
    y_var = sum((y - y_mean) ** 2 for y in y_float)
    denom = sqrt(x_var * y_var)
    if denom == 0:
        return Decimal("0")
    return Decimal(str(numerator / denom))


def _sign_agreement(xs: list[Decimal], ys: list[Decimal]) -> Decimal:
    usable = [(x, y) for x, y in zip(xs, ys) if x != 0 and y != 0]
    if not usable:
        return Decimal("0")
    same = sum(1 for x, y in usable if (x > 0) == (y > 0))
    return Decimal(same) / Decimal(len(usable))


def _best_score(scores: list[LagScore]) -> LagScore | None:
    if not scores:
        return None
    return max(scores, key=lambda item: (item.score, item.pairs))


def _clean_samples(samples: list[MidpointSample]) -> list[MidpointSample]:
    return sorted((sample for sample in samples if sample.mid > 0), key=lambda item: item.ts_ms)

