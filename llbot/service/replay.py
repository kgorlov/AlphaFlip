"""Replay saved market data through signal models."""

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Iterable

from llbot.domain.enums import IntentType, RuntimeMode, Side, Venue
from llbot.domain.models import Intent, PortfolioState, Quote
from llbot.domain.protocols import SignalModel
from llbot.execution.paper_fill import FillModel, PaperFill, simulate_quote_fill
from llbot.monitoring.health import (
    FeedStreamState,
    evaluate_feed_health,
    feed_health_metadata,
    feed_stream_key,
    update_feed_stream_state,
)
from llbot.risk.limits import BasicRiskEngine
from llbot.signals.feature_store import quote_from_book_ticker
from llbot.storage.replay_jsonl import ReplayEvent, book_ticker_from_replay_event


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    processed_events: int
    quotes: int
    intents: int
    skipped_events: int
    intent_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplayPaperSummary:
    processed_events: int
    quotes: int
    intents: int
    skipped_events: int
    risk_allowed: int
    risk_blocked: int
    fills: int
    not_filled: int
    closed_positions: int
    open_positions: int
    gross_realized_pnl_usd: Decimal
    realized_cost_usd: Decimal
    realized_pnl_usd: Decimal
    gross_unrealized_pnl_usd: Decimal
    unrealized_cost_usd: Decimal
    unrealized_pnl_usd: Decimal
    audit_records: int
    intent_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplayAuditRecord:
    event_type: str
    timestamp_ms: int
    mode: RuntimeMode
    symbol: str
    execution_symbol: str
    intent_id: str
    intent_type: str
    side: str
    model: str
    expected_edge_bps: Decimal
    decision_result: str
    skip_reason: str | None
    risk_allowed: bool
    risk_reason: str
    fill_model: FillModel | None
    fill_filled: bool
    fill_price: Decimal | None
    fill_qty: Decimal
    fill_reason: str | None
    binance_quote: dict[str, object] | None
    mexc_quote: dict[str, object] | None
    order_request: dict[str, object]
    order_response: dict[str, object]
    position_id: str | None = None
    exit_reason: str | None = None
    gross_pnl_usd: Decimal | None = None
    cost_usd: Decimal | None = None
    realized_pnl_usd: Decimal | None = None
    features: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PaperPosition:
    position_id: str
    entry_intent_id: str
    symbol: str
    execution_symbol: str
    side: Side
    qty: Decimal
    entry_price: Decimal
    entry_ts_ms: int
    expires_ts_ms: int
    model: str


def replay_events(
    events: Iterable[ReplayEvent],
    models: Iterable[SignalModel],
) -> tuple[ReplaySummary, list[Intent]]:
    model_list = tuple(models)
    ordered = sorted(events, key=lambda event: _event_sort_key(event))
    intents: list[Intent] = []
    processed = 0
    quote_count = 0
    skipped = 0
    intent_counts: dict[str, int] = {}

    for event in ordered:
        processed += 1
        if event.event_type != "book_ticker":
            skipped += 1
            continue

        quote = quote_from_book_ticker(book_ticker_from_replay_event(event))
        quote_count += 1
        for model in model_list:
            new_intents = model.on_quote(quote)
            intents.extend(new_intents)
            for intent in new_intents:
                model_name = str(intent.features.get("model", "unknown"))
                intent_counts[model_name] = intent_counts.get(model_name, 0) + 1

    return (
        ReplaySummary(
            processed_events=processed,
            quotes=quote_count,
            intents=len(intents),
            skipped_events=skipped,
            intent_counts=intent_counts,
        ),
        intents,
    )


class PaperTradingEngine:
    """Incremental quote-driven paper engine shared by replay and live-paper loops."""

    def __init__(
        self,
        models: Iterable[SignalModel],
        risk_engine: BasicRiskEngine,
        portfolio_state: PortfolioState,
        execution_symbol: str,
        fill_model: FillModel = FillModel.TOUCH,
        execution_venue: Venue = Venue.MEXC,
        mode: RuntimeMode = RuntimeMode.PAPER,
        take_profit_bps: Decimal | None = None,
        fee_bps: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
        stale_feed_ms: int | None = None,
    ) -> None:
        self.model_list = tuple(models)
        self.risk_engine = risk_engine
        self.state = portfolio_state
        self.execution_symbol = execution_symbol
        self.fill_model = fill_model
        self.execution_venue = execution_venue
        self.mode = mode
        self.take_profit_bps = take_profit_bps
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.stale_feed_ms = stale_feed_ms
        self.latest_quotes: dict[tuple[Venue, str], Quote] = {}
        self.audit_records: list[ReplayAuditRecord] = []
        self.feed_streams: dict[str, FeedStreamState] = {}
        self.processed = 0
        self.quote_count = 0
        self.skipped = 0
        self.intent_count = 0
        self.risk_allowed = 0
        self.risk_blocked = 0
        self.fills = 0
        self.not_filled = 0
        self.closed_positions = 0
        self.gross_realized_pnl_usd = Decimal("0")
        self.realized_cost_usd = Decimal("0")
        self.realized_pnl_usd = Decimal("0")
        self.intent_counts: dict[str, int] = {}
        self.open_positions: list[PaperPosition] = []

    def record_skipped_event(self) -> None:
        self.processed += 1
        self.skipped += 1

    def on_quote(self, quote: Quote) -> list[ReplayAuditRecord]:
        """Process a single public quote and return audit records created by it."""

        start = len(self.audit_records)
        self.processed += 1
        self.latest_quotes[(quote.venue, quote.symbol)] = quote
        stream_key = feed_stream_key(quote.venue.value, quote.symbol)
        self.feed_streams[stream_key] = update_feed_stream_state(
            self.feed_streams.get(stream_key),
            quote.venue.value,
            quote.symbol,
            quote.local_ts_ms,
            self.stale_feed_ms,
        )
        self.quote_count += 1

        if quote.venue == self.execution_venue and quote.symbol == self.execution_symbol:
            self._record_exits(
                *_close_stale_positions(
                    self.open_positions,
                    quote,
                    self.mode,
                    self.fill_model,
                    self.latest_quotes,
                    self.state,
                    self.stale_feed_ms,
                    self.fee_bps,
                    self.slippage_bps,
                )
            )
            self._record_exits(
                *_close_positions(
                    self.open_positions,
                    quote,
                    self.mode,
                    self.fill_model,
                    self.latest_quotes,
                    self.state,
                    self.take_profit_bps,
                    self.fee_bps,
                    self.slippage_bps,
                )
            )

        for model in self.model_list:
            for intent in model.on_quote(quote):
                self._process_intent(intent)

        return self.audit_records[start:]

    def summary(self) -> ReplayPaperSummary:
        gross_unrealized_pnl_usd, unrealized_cost_usd, unrealized_pnl_usd = _mark_to_market(
            self.open_positions,
            self.latest_quotes,
            self.execution_venue,
            self.execution_symbol,
            self.fee_bps,
            self.slippage_bps,
        )
        return ReplayPaperSummary(
            processed_events=self.processed,
            quotes=self.quote_count,
            intents=self.intent_count,
            skipped_events=self.skipped,
            risk_allowed=self.risk_allowed,
            risk_blocked=self.risk_blocked,
            fills=self.fills,
            not_filled=self.not_filled,
            closed_positions=self.closed_positions,
            open_positions=len(self.open_positions),
            gross_realized_pnl_usd=self.gross_realized_pnl_usd,
            realized_cost_usd=self.realized_cost_usd,
            realized_pnl_usd=self.realized_pnl_usd,
            gross_unrealized_pnl_usd=gross_unrealized_pnl_usd,
            unrealized_cost_usd=unrealized_cost_usd,
            unrealized_pnl_usd=unrealized_pnl_usd,
            audit_records=len(self.audit_records),
            intent_counts=dict(self.intent_counts),
        )

    def audit_records_snapshot(self) -> list[ReplayAuditRecord]:
        return list(self.audit_records)

    def feed_streams_snapshot(self) -> dict[str, FeedStreamState]:
        return dict(self.feed_streams)

    def _record_exits(
        self,
        exits: list[ReplayAuditRecord],
        open_positions: list[PaperPosition],
        state: PortfolioState,
    ) -> None:
        self.open_positions = open_positions
        self.state = state
        self.closed_positions += len(exits)
        self.gross_realized_pnl_usd += _sum_exit_field(exits, "gross_pnl_usd")
        self.realized_cost_usd += _sum_exit_field(exits, "cost_usd")
        self.realized_pnl_usd += _sum_exit_field(exits, "realized_pnl_usd")
        self.audit_records.extend(exits)

    def _process_intent(self, intent: Intent) -> None:
        self.intent_count += 1
        model_name = str(intent.features.get("model", "unknown"))
        self.intent_counts[model_name] = self.intent_counts.get(model_name, 0) + 1

        execution_quote = self.latest_quotes.get((self.execution_venue, self.execution_symbol))
        if execution_quote is not None:
            self._record_exits(
                *_close_reversal_positions(
                    self.open_positions,
                    intent,
                    execution_quote,
                    self.mode,
                    self.fill_model,
                    self.latest_quotes,
                    self.state,
                    self.fee_bps,
                    self.slippage_bps,
                )
            )

        state_for_risk = _state_with_feed_health_metadata(
            self.state,
            self.feed_streams,
            intent,
            self.execution_venue,
            self.execution_symbol,
            self.stale_feed_ms,
        )
        allowed, risk_reason = self.risk_engine.allow(intent, state_for_risk)
        if not allowed:
            self.risk_blocked += 1
            self.audit_records.append(
                _audit_record(
                    intent=intent,
                    execution_symbol=self.execution_symbol,
                    mode=self.mode,
                    decision_result="risk_blocked",
                    skip_reason=risk_reason,
                    risk_allowed=False,
                    risk_reason=risk_reason,
                    fill_model=self.fill_model,
                    fill=None,
                    latest_quotes=self.latest_quotes,
                    position_id=None,
                )
            )
            return

        self.risk_allowed += 1
        if execution_quote is None:
            self.not_filled += 1
            self.audit_records.append(
                _audit_record(
                    intent=intent,
                    execution_symbol=self.execution_symbol,
                    mode=self.mode,
                    decision_result="no_execution_quote",
                    skip_reason="no_execution_quote",
                    risk_allowed=True,
                    risk_reason=risk_reason,
                    fill_model=self.fill_model,
                    fill=None,
                    latest_quotes=self.latest_quotes,
                    position_id=None,
                )
            )
            return

        fill_intent = replace(intent, symbol=self.execution_symbol)
        fill = simulate_quote_fill(fill_intent, execution_quote, self.fill_model)
        if fill.filled:
            self.fills += 1
            position = _position_from_fill(intent, self.execution_symbol, fill)
            self.open_positions.append(position)
            self.state = _state_after_fill(self.state, intent, fill)
            decision_result = "filled"
            skip_reason = None
            position_id = position.position_id
        else:
            self.not_filled += 1
            decision_result = "not_filled"
            skip_reason = fill.reason
            position_id = None

        self.audit_records.append(
            _audit_record(
                intent=intent,
                execution_symbol=self.execution_symbol,
                mode=self.mode,
                decision_result=decision_result,
                skip_reason=skip_reason,
                risk_allowed=True,
                risk_reason=risk_reason,
                fill_model=self.fill_model,
                fill=fill,
                latest_quotes=self.latest_quotes,
                position_id=position_id,
            )
        )


def replay_paper_events(
    events: Iterable[ReplayEvent],
    models: Iterable[SignalModel],
    risk_engine: BasicRiskEngine,
    portfolio_state: PortfolioState,
    execution_symbol: str,
    fill_model: FillModel = FillModel.TOUCH,
    execution_venue: Venue = Venue.MEXC,
    mode: RuntimeMode = RuntimeMode.PAPER,
    take_profit_bps: Decimal | None = None,
    fee_bps: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
    stale_feed_ms: int | None = None,
) -> tuple[ReplayPaperSummary, list[ReplayAuditRecord]]:
    engine = replay_paper_engine(
        events,
        models,
        risk_engine,
        portfolio_state,
        execution_symbol,
        fill_model,
        execution_venue,
        mode,
        take_profit_bps,
        fee_bps,
        slippage_bps,
        stale_feed_ms,
    )
    return engine.summary(), engine.audit_records_snapshot()


def replay_paper_engine(
    events: Iterable[ReplayEvent],
    models: Iterable[SignalModel],
    risk_engine: BasicRiskEngine,
    portfolio_state: PortfolioState,
    execution_symbol: str,
    fill_model: FillModel = FillModel.TOUCH,
    execution_venue: Venue = Venue.MEXC,
    mode: RuntimeMode = RuntimeMode.PAPER,
    take_profit_bps: Decimal | None = None,
    fee_bps: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
    stale_feed_ms: int | None = None,
) -> PaperTradingEngine:
    engine = PaperTradingEngine(
        models,
        risk_engine,
        portfolio_state,
        execution_symbol,
        fill_model,
        execution_venue,
        mode,
        take_profit_bps,
        fee_bps,
        slippage_bps,
        stale_feed_ms,
    )
    for event in sorted(events, key=lambda event: _event_sort_key(event)):
        if event.event_type != "book_ticker":
            engine.record_skipped_event()
            continue
        engine.on_quote(quote_from_book_ticker(book_ticker_from_replay_event(event)))
    return engine


def _event_sort_key(event: ReplayEvent) -> tuple[int, int, str, str]:
    ts = event.local_ts_ms or event.exchange_ts_ms or 0
    exchange_ts = event.exchange_ts_ms or 0
    return (ts, exchange_ts, event.venue, event.symbol)


def _audit_record(
    intent: Intent,
    execution_symbol: str,
    mode: RuntimeMode,
    decision_result: str,
    skip_reason: str | None,
    risk_allowed: bool,
    risk_reason: str,
    fill_model: FillModel,
    fill: PaperFill | None,
    latest_quotes: dict[tuple[Venue, str], Quote],
    position_id: str | None,
) -> ReplayAuditRecord:
    return ReplayAuditRecord(
        event_type="replay_signal_decision",
        timestamp_ms=intent.created_ts_ms,
        mode=mode,
        symbol=intent.symbol,
        execution_symbol=execution_symbol,
        intent_id=intent.intent_id,
        intent_type=intent.intent_type.value,
        side=intent.side.value,
        model=str(intent.features.get("model", "unknown")),
        expected_edge_bps=intent.expected_edge_bps,
        decision_result=decision_result,
        skip_reason=skip_reason,
        risk_allowed=risk_allowed,
        risk_reason=risk_reason,
        fill_model=fill_model,
        fill_filled=bool(fill.filled) if fill is not None else False,
        fill_price=fill.fill_price if fill is not None else None,
        fill_qty=fill.fill_qty if fill is not None else Decimal("0"),
        fill_reason=fill.reason if fill is not None else None,
        position_id=position_id,
        exit_reason=None,
        gross_pnl_usd=None,
        cost_usd=None,
        realized_pnl_usd=None,
        binance_quote=_quote_snapshot(latest_quotes.get((Venue.BINANCE, _leader_symbol(intent)))),
        mexc_quote=_quote_snapshot(latest_quotes.get((Venue.MEXC, execution_symbol))),
        order_request={
            "symbol": execution_symbol,
            "canonical_symbol": intent.symbol,
            "side": intent.side.value,
            "qty": intent.qty,
            "price_cap": intent.price_cap,
            "ttl_ms": intent.ttl_ms,
            "order_style": intent.order_style.value,
        },
        order_response={
            "paper": True,
            "decision_result": decision_result,
            "skip_reason": skip_reason,
        },
        features=dict(intent.features),
    )


def _quote_snapshot(quote: Quote | None) -> dict[str, object] | None:
    if quote is None:
        return None
    return {
        "venue": quote.venue.value,
        "market": quote.market.value,
        "symbol": quote.symbol,
        "bid": quote.bid,
        "ask": quote.ask,
        "mid": quote.mid,
        "bid_size": quote.bid_size,
        "ask_size": quote.ask_size,
        "spread_bps": quote.spread_bps,
        "exchange_ts_ms": quote.exchange_ts_ms,
        "local_ts_ms": quote.local_ts_ms,
    }


def _leader_symbol(intent: Intent) -> str:
    return str(intent.features.get("leader_symbol", intent.symbol))


def _state_with_feed_health_metadata(
    state: PortfolioState,
    feed_streams: dict[str, FeedStreamState],
    intent: Intent,
    execution_venue: Venue,
    execution_symbol: str,
    stale_feed_ms: int | None,
) -> PortfolioState:
    if stale_feed_ms is None:
        return state

    leader_key = feed_stream_key(Venue.BINANCE.value, _leader_symbol(intent))
    lagger_key = feed_stream_key(execution_venue.value, execution_symbol)
    decision = evaluate_feed_health(
        feed_streams,
        (leader_key, lagger_key),
        intent.created_ts_ms,
        stale_feed_ms,
    )
    metadata = dict(state.metadata)
    health_metadata = feed_health_metadata(decision)
    for key, value in health_metadata.items():
        if key in {"binance_feed_stale", "mexc_feed_stale"}:
            metadata[key] = bool(metadata.get(key, False)) or bool(value)
        else:
            metadata[key] = value
    return PortfolioState(
        open_positions=state.open_positions,
        total_notional_usd=state.total_notional_usd,
        daily_pnl_usd=state.daily_pnl_usd,
        per_symbol_notional_usd=dict(state.per_symbol_notional_usd),
        metadata=metadata,
    )


def _position_from_fill(intent: Intent, execution_symbol: str, fill: PaperFill) -> PaperPosition:
    entry_price = fill.fill_price or intent.price_cap
    return PaperPosition(
        position_id=f"paper-pos-{intent.intent_id}",
        entry_intent_id=intent.intent_id,
        symbol=intent.symbol,
        execution_symbol=execution_symbol,
        side=intent.side,
        qty=fill.fill_qty,
        entry_price=entry_price,
        entry_ts_ms=intent.created_ts_ms,
        expires_ts_ms=intent.created_ts_ms + intent.ttl_ms,
        model=str(intent.features.get("model", "unknown")),
    )


def _close_positions(
    positions: list[PaperPosition],
    quote: Quote,
    mode: RuntimeMode,
    fill_model: FillModel,
    latest_quotes: dict[tuple[Venue, str], Quote],
    state: PortfolioState,
    take_profit_bps: Decimal | None,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[list[ReplayAuditRecord], list[PaperPosition], PortfolioState]:
    closed: list[ReplayAuditRecord] = []
    remaining: list[PaperPosition] = []
    next_state = state
    for position in positions:
        exit_reason = _exit_reason(position, quote, take_profit_bps)
        if exit_reason is None:
            remaining.append(position)
            continue
        record = _exit_audit_record(
            position,
            quote,
            mode,
            fill_model,
            latest_quotes,
            exit_reason,
            fee_bps,
            slippage_bps,
        )
        closed.append(record)
        next_state = _state_after_exit(next_state, position, record.realized_pnl_usd or Decimal("0"))
    return closed, remaining, next_state


def _close_stale_positions(
    positions: list[PaperPosition],
    quote: Quote,
    mode: RuntimeMode,
    fill_model: FillModel,
    latest_quotes: dict[tuple[Venue, str], Quote],
    state: PortfolioState,
    stale_feed_ms: int | None,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[list[ReplayAuditRecord], list[PaperPosition], PortfolioState]:
    if stale_feed_ms is None:
        return [], positions, state

    closed: list[ReplayAuditRecord] = []
    remaining: list[PaperPosition] = []
    next_state = state
    for position in positions:
        leader_quote = latest_quotes.get((Venue.BINANCE, position.symbol))
        if leader_quote is not None and quote.local_ts_ms - leader_quote.local_ts_ms <= stale_feed_ms:
            remaining.append(position)
            continue
        record = _exit_audit_record(
            position,
            quote,
            mode,
            fill_model,
            latest_quotes,
            "stale_data_stop",
            fee_bps,
            slippage_bps,
        )
        closed.append(record)
        next_state = _state_after_exit(next_state, position, record.realized_pnl_usd or Decimal("0"))
    return closed, remaining, next_state


def _close_reversal_positions(
    positions: list[PaperPosition],
    intent: Intent,
    quote: Quote,
    mode: RuntimeMode,
    fill_model: FillModel,
    latest_quotes: dict[tuple[Venue, str], Quote],
    state: PortfolioState,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[list[ReplayAuditRecord], list[PaperPosition], PortfolioState]:
    closed: list[ReplayAuditRecord] = []
    remaining: list[PaperPosition] = []
    next_state = state
    for position in positions:
        if not _is_reversal(position, intent):
            remaining.append(position)
            continue
        record = _exit_audit_record(
            position,
            quote,
            mode,
            fill_model,
            latest_quotes,
            "reversal_stop",
            fee_bps,
            slippage_bps,
        )
        closed.append(record)
        next_state = _state_after_exit(next_state, position, record.realized_pnl_usd or Decimal("0"))
    return closed, remaining, next_state


def _exit_audit_record(
    position: PaperPosition,
    quote: Quote,
    mode: RuntimeMode,
    fill_model: FillModel,
    latest_quotes: dict[tuple[Venue, str], Quote],
    exit_reason: str,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> ReplayAuditRecord:
    if position.side == Side.BUY:
        exit_intent_type = IntentType.EXIT_LONG
        exit_side = Side.SELL
        exit_price = quote.bid
    else:
        exit_intent_type = IntentType.EXIT_SHORT
        exit_side = Side.BUY
        exit_price = quote.ask

    gross_pnl, cost, realized_pnl = _pnl_values(
        position,
        exit_price,
        fee_bps,
        slippage_bps,
    )

    return ReplayAuditRecord(
        event_type="replay_position_exit",
        timestamp_ms=quote.local_ts_ms,
        mode=mode,
        symbol=position.symbol,
        execution_symbol=position.execution_symbol,
        intent_id=position.entry_intent_id,
        intent_type=exit_intent_type.value,
        side=exit_side.value,
        model=position.model,
        expected_edge_bps=Decimal("0"),
        decision_result="closed",
        skip_reason=None,
        risk_allowed=True,
        risk_reason="ok",
        fill_model=fill_model,
        fill_filled=True,
        fill_price=exit_price,
        fill_qty=position.qty,
        fill_reason=exit_reason,
        binance_quote=_quote_snapshot(latest_quotes.get((Venue.BINANCE, position.symbol))),
        mexc_quote=_quote_snapshot(quote),
        order_request={
            "symbol": position.execution_symbol,
            "canonical_symbol": position.symbol,
            "side": exit_side.value,
            "qty": position.qty,
            "price_cap": exit_price,
            "ttl_ms": 0,
            "order_style": f"paper_{exit_reason}",
            "reduce_only": True,
        },
        order_response={
            "paper": True,
            "decision_result": "closed",
            "exit_reason": exit_reason,
            "gross_pnl_usd": gross_pnl,
            "cost_usd": cost,
            "realized_pnl_usd": realized_pnl,
        },
        position_id=position.position_id,
        exit_reason=exit_reason,
        gross_pnl_usd=gross_pnl,
        cost_usd=cost,
        realized_pnl_usd=realized_pnl,
        features={
            "entry_price": position.entry_price,
            "entry_ts_ms": position.entry_ts_ms,
            "expires_ts_ms": position.expires_ts_ms,
        },
    )


def _exit_reason(
    position: PaperPosition,
    quote: Quote,
    take_profit_bps: Decimal | None,
) -> str | None:
    if take_profit_bps is not None:
        gross_pnl, _, _ = _pnl_values(
            position,
            _exit_price(position, quote),
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
        if _pnl_bps(position, gross_pnl) >= take_profit_bps:
            return "take_profit"

    if quote.local_ts_ms >= position.expires_ts_ms:
        return "ttl_exit"

    return None


def _is_reversal(position: PaperPosition, intent: Intent) -> bool:
    if position.symbol != intent.symbol:
        return False
    if intent.intent_type == IntentType.ENTER_LONG:
        return position.side == Side.SELL
    if intent.intent_type == IntentType.ENTER_SHORT:
        return position.side == Side.BUY
    return False


def _sum_exit_field(records: list[ReplayAuditRecord], field_name: str) -> Decimal:
    return sum(
        (getattr(record, field_name) or Decimal("0") for record in records),
        Decimal("0"),
    )


def _mark_to_market(
    positions: list[PaperPosition],
    latest_quotes: dict[tuple[Venue, str], Quote],
    execution_venue: Venue,
    execution_symbol: str,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    quote = latest_quotes.get((execution_venue, execution_symbol))
    if quote is None:
        return Decimal("0"), Decimal("0"), Decimal("0")

    gross = Decimal("0")
    cost = Decimal("0")
    net = Decimal("0")
    for position in positions:
        position_gross, position_cost, position_net = _pnl_values(
            position,
            _exit_price(position, quote),
            fee_bps,
            slippage_bps,
        )
        gross += position_gross
        cost += position_cost
        net += position_net
    return gross, cost, net


def _exit_price(position: PaperPosition, quote: Quote) -> Decimal:
    if position.side == Side.BUY:
        return quote.bid
    return quote.ask


def _pnl_values(
    position: PaperPosition,
    exit_price: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    if position.side == Side.BUY:
        gross_pnl = (exit_price - position.entry_price) * position.qty
    else:
        gross_pnl = (position.entry_price - exit_price) * position.qty
    cost = _round_trip_cost(position, exit_price, fee_bps + slippage_bps)
    return gross_pnl, cost, gross_pnl - cost


def _round_trip_cost(position: PaperPosition, exit_price: Decimal, cost_bps: Decimal) -> Decimal:
    if cost_bps <= 0:
        return Decimal("0")
    entry_notional = abs(position.entry_price * position.qty)
    exit_notional = abs(exit_price * position.qty)
    return (entry_notional + exit_notional) * cost_bps / Decimal("10000")


def _pnl_bps(position: PaperPosition, gross_pnl: Decimal) -> Decimal:
    entry_notional = abs(position.entry_price * position.qty)
    if entry_notional <= 0:
        return Decimal("0")
    return Decimal("10000") * gross_pnl / entry_notional


def _state_after_fill(state: PortfolioState, intent: Intent, fill: PaperFill) -> PortfolioState:
    fill_price = fill.fill_price or intent.price_cap
    notional = abs(fill.fill_qty * fill_price)
    per_symbol = dict(state.per_symbol_notional_usd)
    per_symbol[intent.symbol] = per_symbol.get(intent.symbol, Decimal("0")) + notional
    metadata = _metadata_after_position_open(state.metadata, intent)
    return PortfolioState(
        open_positions=state.open_positions + 1,
        total_notional_usd=state.total_notional_usd + notional,
        daily_pnl_usd=state.daily_pnl_usd,
        per_symbol_notional_usd=per_symbol,
        metadata=metadata,
    )


def _state_after_exit(
    state: PortfolioState,
    position: PaperPosition,
    realized_pnl_usd: Decimal,
) -> PortfolioState:
    entry_notional = abs(position.qty * position.entry_price)
    per_symbol = dict(state.per_symbol_notional_usd)
    current_symbol_notional = per_symbol.get(position.symbol, Decimal("0"))
    next_symbol_notional = max(Decimal("0"), current_symbol_notional - entry_notional)
    if next_symbol_notional == 0:
        per_symbol.pop(position.symbol, None)
    else:
        per_symbol[position.symbol] = next_symbol_notional

    metadata = _metadata_after_position_close(state.metadata, position)
    return PortfolioState(
        open_positions=max(0, state.open_positions - 1),
        total_notional_usd=max(Decimal("0"), state.total_notional_usd - entry_notional),
        daily_pnl_usd=state.daily_pnl_usd + realized_pnl_usd,
        per_symbol_notional_usd=per_symbol,
        metadata=metadata,
    )


def _metadata_after_position_open(metadata: dict[str, object], intent: Intent) -> dict[str, object]:
    next_metadata = dict(metadata)
    counts = _direction_counts(metadata)
    direction = "short" if intent.intent_type == IntentType.ENTER_SHORT else "long"
    key = f"{intent.symbol}:{direction}"
    counts[key] = counts.get(key, 0) + 1
    next_metadata["open_position_direction_counts"] = counts
    next_metadata["active_symbols"] = sorted(
        {
            key.split(":", 1)[0]
            for key, count in counts.items()
            if count > 0
        }
    )
    return next_metadata


def _metadata_after_position_close(
    metadata: dict[str, object],
    position: PaperPosition,
) -> dict[str, object]:
    next_metadata = dict(metadata)
    counts = _direction_counts(metadata)
    direction = "long" if position.side == Side.BUY else "short"
    key = f"{position.symbol}:{direction}"
    current = counts.get(key, 0)
    if current <= 1:
        counts.pop(key, None)
    else:
        counts[key] = current - 1
    next_metadata["open_position_direction_counts"] = counts
    next_metadata["active_symbols"] = sorted(
        {
            key.split(":", 1)[0]
            for key, count in counts.items()
            if count > 0
        }
    )
    return next_metadata


def _direction_counts(metadata: dict[str, object]) -> dict[str, int]:
    raw = metadata.get("open_position_direction_counts", {})
    if not isinstance(raw, dict):
        return {}
    return {str(key): int(value) for key, value in raw.items() if int(value) > 0}
