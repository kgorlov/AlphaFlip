"""Event-driven impulse transfer signal model."""

from dataclasses import dataclass
from decimal import Decimal

from llbot.domain.enums import IntentType, MarketProfileName, OrderStyle, Side, Venue
from llbot.domain.models import Intent, Quote, Trade
from llbot.signals.feature_store import QuoteWindow, bps_move


@dataclass(frozen=True, slots=True)
class ImpulseTransferConfig:
    canonical_symbol: str
    leader_symbol: str
    lagger_symbol: str
    profile: MarketProfileName = MarketProfileName.PERP_TO_PERP
    qty: Decimal = Decimal("1")
    beta: Decimal = Decimal("1")
    windows_ms: tuple[int, ...] = (50, 100, 200, 500)
    min_impulse_bps: Decimal = Decimal("2")
    fee_bps: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    safety_bps: Decimal = Decimal("2")
    min_edge_bps: Decimal = Decimal("0")
    ttl_ms: int = 3000
    cooldown_ms: int = 1000


class ImpulseTransferSignal:
    """Generate intents when Binance moved and MEXC has not transferred the move yet."""

    def __init__(self, config: ImpulseTransferConfig) -> None:
        self.config = config
        self.quotes = QuoteWindow()
        self._last_intent_ts_ms: int | None = None

    def on_quote(self, q: Quote) -> list[Intent]:
        if not self._is_relevant(q):
            return []

        self.quotes.add(q)
        leader = self.quotes.latest(Venue.BINANCE, self.config.leader_symbol)
        lagger = self.quotes.latest(Venue.MEXC, self.config.lagger_symbol)
        if leader is None or lagger is None:
            return []
        decision_ts_ms = max(leader.local_ts_ms, lagger.local_ts_ms)
        if self._last_intent_ts_ms is not None:
            if decision_ts_ms - self._last_intent_ts_ms < self.config.cooldown_ms:
                return []

        for window_ms in self.config.windows_ms:
            intent = self._maybe_window_intent(leader, lagger, window_ms, decision_ts_ms)
            if intent is not None:
                return [intent]
        return []

    def on_trade(self, t: Trade) -> list[Intent]:
        return []

    def _maybe_window_intent(
        self,
        leader: Quote,
        lagger: Quote,
        window_ms: int,
        decision_ts_ms: int,
    ) -> Intent | None:
        leader_prev = self.quotes.at_or_before(
            Venue.BINANCE,
            self.config.leader_symbol,
            leader.local_ts_ms - window_ms,
        )
        lagger_prev = self.quotes.at_or_before(
            Venue.MEXC,
            self.config.lagger_symbol,
            lagger.local_ts_ms - window_ms,
        )
        if leader_prev is None or lagger_prev is None:
            return None

        leader_impulse_bps = bps_move(leader.mid, leader_prev.mid)
        if abs(leader_impulse_bps) < self.config.min_impulse_bps:
            return None

        lagger_move_bps = bps_move(lagger.mid, lagger_prev.mid)
        transferred_bps = self.config.beta * leader_impulse_bps
        lag_bps = transferred_bps - lagger_move_bps
        cost_bps = self.config.fee_bps + self.config.slippage_bps + self.config.safety_bps
        edge_bps = abs(lag_bps) - cost_bps
        if edge_bps <= self.config.min_edge_bps:
            return None

        if leader_impulse_bps > 0 and lag_bps > 0:
            return self._entry_intent(
                intent_type=IntentType.ENTER_LONG,
                side=Side.BUY,
                price_cap=lagger.ask,
                edge_bps=edge_bps,
                created_ts_ms=decision_ts_ms,
                features={
                    "model": "impulse_transfer",
                    "window_ms": str(window_ms),
                    "leader_impulse_bps": str(leader_impulse_bps),
                    "lagger_move_bps": str(lagger_move_bps),
                    "lag_bps": str(lag_bps),
                    "cost_bps": str(cost_bps),
                },
            )

        if leader_impulse_bps < 0 and lag_bps < 0:
            return self._entry_intent(
                intent_type=IntentType.ENTER_SHORT,
                side=Side.SELL,
                price_cap=lagger.bid,
                edge_bps=edge_bps,
                created_ts_ms=decision_ts_ms,
                features={
                    "model": "impulse_transfer",
                    "window_ms": str(window_ms),
                    "leader_impulse_bps": str(leader_impulse_bps),
                    "lagger_move_bps": str(lagger_move_bps),
                    "lag_bps": str(lag_bps),
                    "cost_bps": str(cost_bps),
                },
            )
        return None

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

    def _is_relevant(self, q: Quote) -> bool:
        return (q.venue == Venue.BINANCE and q.symbol == self.config.leader_symbol) or (
            q.venue == Venue.MEXC and q.symbol == self.config.lagger_symbol
        )
