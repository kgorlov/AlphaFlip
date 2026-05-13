"""Residual z-score signal model for Binance -> MEXC catch-up trades."""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from math import exp, log

from llbot.domain.enums import IntentType, MarketProfileName, OrderStyle, Side, Venue
from llbot.domain.models import Intent, Quote, Trade
from llbot.signals.feature_store import QuoteWindow, bps_move, mean


@dataclass(frozen=True, slots=True)
class ResidualZScoreConfig:
    canonical_symbol: str
    leader_symbol: str
    lagger_symbol: str
    profile: MarketProfileName = MarketProfileName.PERP_TO_PERP
    qty: Decimal = Decimal("1")
    beta: Decimal = Decimal("1")
    z_entry: Decimal = Decimal("2.2")
    min_samples: int = 10
    window_samples: int = 120
    ewm_window_ms: int = 180_000
    min_sigma_bps: Decimal = Decimal("0.5")
    fee_bps: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    safety_bps: Decimal = Decimal("2")
    min_edge_bps: Decimal = Decimal("0")
    ttl_ms: int = 3000
    cooldown_ms: int = 1000

    def __post_init__(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples must be positive")
        if self.window_samples < 1:
            raise ValueError("window_samples must be positive")
        if self.ewm_window_ms <= 0:
            raise ValueError("ewm_window_ms must be positive")


class ResidualZScoreSignal:
    """Generate intents when the lagging MEXC residual is far from its baseline."""

    def __init__(self, config: ResidualZScoreConfig) -> None:
        self.config = config
        self.quotes = QuoteWindow()
        self._basis_bps: deque[Decimal] = deque(maxlen=config.window_samples)
        self._ewm_stats = EwmBasisStats(window_ms=config.ewm_window_ms)
        self._last_intent_ts_ms: int | None = None

    def on_quote(self, q: Quote) -> list[Intent]:
        if not self._is_relevant(q):
            return []

        self.quotes.add(q)
        leader = self.quotes.latest(Venue.BINANCE, self.config.leader_symbol)
        lagger = self.quotes.latest(Venue.MEXC, self.config.lagger_symbol)
        if leader is None or lagger is None:
            return []

        current_basis = self._basis_bps_value(leader, lagger)
        intents = self._maybe_entry(leader, lagger, current_basis)
        self._basis_bps.append(current_basis)
        self._ewm_stats.update(current_basis, max(leader.local_ts_ms, lagger.local_ts_ms))
        return intents

    def on_trade(self, t: Trade) -> list[Intent]:
        return []

    def _maybe_entry(self, leader: Quote, lagger: Quote, current_basis: Decimal) -> list[Intent]:
        decision_ts_ms = max(leader.local_ts_ms, lagger.local_ts_ms)
        if len(self._basis_bps) < self.config.min_samples:
            return []
        if self._last_intent_ts_ms is not None:
            if decision_ts_ms - self._last_intent_ts_ms < self.config.cooldown_ms:
                return []

        basis_mean = self._ewm_stats.mean or mean(self._basis_bps)
        sigma = max(self._ewm_stats.std_bps, self.config.min_sigma_bps)
        z_score = (current_basis - basis_mean) / sigma
        leader_prev = self.quotes.previous(Venue.BINANCE, self.config.leader_symbol)
        if leader_prev is None:
            return []
        leader_move_bps = bps_move(leader.mid, leader_prev.mid)

        cost_bps = self.config.fee_bps + self.config.slippage_bps + self.config.safety_bps
        edge_bps = abs(current_basis - basis_mean) - cost_bps
        if edge_bps <= self.config.min_edge_bps:
            return []

        if leader_move_bps > 0 and z_score <= -self.config.z_entry:
            intent = self._entry_intent(
                intent_type=IntentType.ENTER_LONG,
                side=Side.BUY,
                price_cap=lagger.ask,
                edge_bps=edge_bps,
                created_ts_ms=decision_ts_ms,
                features={
                    "model": "residual_zscore",
                    "z_score": str(z_score),
                    "basis_bps": str(current_basis),
                    "basis_mean_bps": str(basis_mean),
                    "basis_ewm_mean_bps": str(basis_mean),
                    "basis_ewm_std_bps": str(sigma),
                    "basis_ewm_window_ms": str(self.config.ewm_window_ms),
                    "leader_move_bps": str(leader_move_bps),
                    "cost_bps": str(cost_bps),
                },
            )
            return [intent]

        if leader_move_bps < 0 and z_score >= self.config.z_entry:
            intent = self._entry_intent(
                intent_type=IntentType.ENTER_SHORT,
                side=Side.SELL,
                price_cap=lagger.bid,
                edge_bps=edge_bps,
                created_ts_ms=decision_ts_ms,
                features={
                    "model": "residual_zscore",
                    "z_score": str(z_score),
                    "basis_bps": str(current_basis),
                    "basis_mean_bps": str(basis_mean),
                    "basis_ewm_mean_bps": str(basis_mean),
                    "basis_ewm_std_bps": str(sigma),
                    "basis_ewm_window_ms": str(self.config.ewm_window_ms),
                    "leader_move_bps": str(leader_move_bps),
                    "cost_bps": str(cost_bps),
                },
            )
            return [intent]
        return []

    def _entry_intent(
        self,
        intent_type: IntentType,
        side: Side,
        price_cap: Decimal,
        edge_bps: Decimal,
        created_ts_ms: int,
        features: dict[str, str],
    ) -> Intent:
        self._last_intent_ts_ms = created_ts_ms
        return Intent(
            intent_id=f"{features['model']}-{self.config.canonical_symbol}-{created_ts_ms}",
            symbol=self.config.canonical_symbol,
            profile=self.config.profile,
            intent_type=intent_type,
            side=side,
            qty=self.config.qty,
            price_cap=price_cap,
            ttl_ms=self.config.ttl_ms,
            order_style=OrderStyle.AGGRESSIVE_LIMIT,
            confidence=Decimal("1"),
            expected_edge_bps=edge_bps,
            created_ts_ms=created_ts_ms,
            features=features,
        )

    def _basis_bps_value(self, leader: Quote, lagger: Quote) -> Decimal:
        log_lagger = Decimal(str(log(float(lagger.mid))))
        log_leader = Decimal(str(log(float(leader.mid))))
        return Decimal("10000") * (log_lagger - self.config.beta * log_leader)

    def _is_relevant(self, q: Quote) -> bool:
        return (q.venue == Venue.BINANCE and q.symbol == self.config.leader_symbol) or (
            q.venue == Venue.MEXC and q.symbol == self.config.lagger_symbol
        )


class EwmBasisStats:
    """Time-aware exponentially weighted basis mean and variance."""

    def __init__(self, window_ms: int) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.window_ms = window_ms
        self.mean: Decimal | None = None
        self.variance: Decimal = Decimal("0")
        self.samples: int = 0
        self.last_ts_ms: int | None = None

    @property
    def std_bps(self) -> Decimal:
        if self.samples < 2 or self.variance <= 0:
            return Decimal("0")
        return self.variance.sqrt()

    def update(self, value: Decimal, ts_ms: int) -> None:
        if self.mean is None:
            self.mean = value
            self.samples = 1
            self.last_ts_ms = ts_ms
            return

        alpha = self._alpha(ts_ms)
        self.last_ts_ms = ts_ms
        if alpha <= 0:
            return

        previous_mean = self.mean
        delta = value - previous_mean
        self.mean = previous_mean + alpha * delta
        self.variance = (Decimal("1") - alpha) * (self.variance + alpha * delta * delta)
        self.samples += 1

    def _alpha(self, ts_ms: int) -> Decimal:
        if self.last_ts_ms is None:
            return Decimal("1")
        dt_ms = ts_ms - self.last_ts_ms
        if dt_ms <= 0:
            return Decimal("0")
        return Decimal(str(1 - exp(-dt_ms / self.window_ms)))
