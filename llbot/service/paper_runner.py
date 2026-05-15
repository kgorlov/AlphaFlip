"""Shared local paper runner wiring for replay-backed validation."""

from dataclasses import dataclass
from decimal import Decimal
from typing import AsyncIterable, Callable, Iterable

from llbot.config import RiskConfig
from llbot.domain.enums import MarketProfileName, RuntimeMode, Venue
from llbot.domain.models import PortfolioState, Quote
from llbot.domain.protocols import SignalModel
from llbot.execution.paper_fill import FillModel
from llbot.monitoring.health import (
    evaluate_feed_health,
    feed_stream_key,
    feed_stream_state_to_dict,
)
from llbot.risk.limits import BasicRiskEngine
from llbot.service.replay import (
    PaperTradingEngine,
    ReplayAuditRecord,
    ReplayPaperSummary,
    replay_paper_engine,
    replay_paper_events,
)
from llbot.signals.impulse_transfer import ImpulseTransferConfig, ImpulseTransferSignal
from llbot.signals.residual_zscore import ResidualZScoreConfig, ResidualZScoreSignal
from llbot.storage.replay_jsonl import ReplayEvent


@dataclass(frozen=True, slots=True)
class PaperRunnerConfig:
    """Configuration for local paper runs that never route real orders."""

    canonical_symbol: str = "BTCUSDT"
    leader_symbol: str = "BTCUSDT"
    lagger_symbol: str = "BTC_USDT"
    profile: MarketProfileName = MarketProfileName.PERP_TO_PERP
    model: str = "both"
    qty: Decimal = Decimal("1")
    z_entry: Decimal = Decimal("2.2")
    min_samples: int = 10
    min_impulse_bps: Decimal = Decimal("2")
    safety_bps: Decimal = Decimal("2")
    ttl_ms: int = 3000
    cooldown_ms: int = 1000
    impulse_windows_ms: tuple[int, ...] = (50, 100, 200, 500)
    fee_bps: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    take_profit_bps: Decimal | None = None
    stale_feed_ms: int | None = None
    fill_model: FillModel = FillModel.TOUCH


@dataclass(frozen=True, slots=True)
class PaperRunResult:
    summary: ReplayPaperSummary
    audit_records: list[ReplayAuditRecord]
    health_report: dict[str, object]


def build_signal_models(config: PaperRunnerConfig) -> list[SignalModel]:
    """Build deterministic signal models for replay/live-like paper validation."""

    models: list[SignalModel] = []
    common = {
        "canonical_symbol": config.canonical_symbol,
        "leader_symbol": config.leader_symbol,
        "lagger_symbol": config.lagger_symbol,
        "profile": config.profile,
        "qty": config.qty,
        "safety_bps": config.safety_bps,
        "ttl_ms": config.ttl_ms,
        "cooldown_ms": config.cooldown_ms,
    }
    if config.model in {"residual", "both"}:
        models.append(
            ResidualZScoreSignal(
                ResidualZScoreConfig(
                    **common,
                    z_entry=config.z_entry,
                    min_samples=config.min_samples,
                )
            )
        )
    if config.model in {"impulse", "both"}:
        models.append(
            ImpulseTransferSignal(
                ImpulseTransferConfig(
                    **common,
                    windows_ms=config.impulse_windows_ms,
                    min_impulse_bps=config.min_impulse_bps,
                )
            )
        )
    if not models:
        raise ValueError(f"Unsupported paper runner model: {config.model}")
    return models


def initial_paper_portfolio_state(
    metadata: dict[str, object] | None = None,
) -> PortfolioState:
    """Return a risk state suitable for local paper runs."""

    state_metadata = {"metascalp_connected": True}
    if metadata:
        state_metadata.update(metadata)
    return PortfolioState(
        open_positions=0,
        total_notional_usd=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        metadata=state_metadata,
    )


def build_paper_trading_engine(
    config: PaperRunnerConfig,
    risk_config: RiskConfig | None = None,
    portfolio_state: PortfolioState | None = None,
) -> PaperTradingEngine:
    """Create the incremental quote-driven engine used by replay and live-paper paths."""

    return PaperTradingEngine(
        build_signal_models(config),
        risk_engine=BasicRiskEngine(risk_config or RiskConfig()),
        portfolio_state=portfolio_state or initial_paper_portfolio_state(),
        execution_symbol=config.lagger_symbol,
        fill_model=config.fill_model,
        mode=RuntimeMode.PAPER,
        take_profit_bps=config.take_profit_bps,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
        stale_feed_ms=config.stale_feed_ms,
    )


def run_replay_paper(
    events: Iterable[ReplayEvent],
    config: PaperRunnerConfig,
    risk_config: RiskConfig | None = None,
    portfolio_state: PortfolioState | None = None,
) -> tuple[ReplayPaperSummary, list[ReplayAuditRecord]]:
    """Run a local replay-backed paper pass through signals, risk, and quote fills."""

    return replay_paper_events(
        events,
        build_signal_models(config),
        risk_engine=BasicRiskEngine(risk_config or RiskConfig()),
        portfolio_state=portfolio_state or initial_paper_portfolio_state(),
        execution_symbol=config.lagger_symbol,
        fill_model=config.fill_model,
        mode=RuntimeMode.PAPER,
        take_profit_bps=config.take_profit_bps,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
        stale_feed_ms=config.stale_feed_ms,
    )


def run_replay_paper_result(
    events: Iterable[ReplayEvent],
    config: PaperRunnerConfig,
    risk_config: RiskConfig | None = None,
    portfolio_state: PortfolioState | None = None,
) -> PaperRunResult:
    """Run replay-backed paper and return summary, audit, and health."""

    engine = replay_paper_engine(
        events,
        build_signal_models(config),
        risk_engine=BasicRiskEngine(risk_config or RiskConfig()),
        portfolio_state=portfolio_state or initial_paper_portfolio_state(),
        execution_symbol=config.lagger_symbol,
        fill_model=config.fill_model,
        mode=RuntimeMode.PAPER,
        take_profit_bps=config.take_profit_bps,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
        stale_feed_ms=config.stale_feed_ms,
    )
    return PaperRunResult(
        engine.summary(),
        engine.audit_records_snapshot(),
        build_paper_health_report(engine, config),
    )


def build_paper_health_report(
    engine: PaperTradingEngine,
    config: PaperRunnerConfig,
) -> dict[str, object]:
    """Build a JSON-friendly health report from the current paper engine state."""

    streams = engine.feed_streams_snapshot()
    required_streams = (
        feed_stream_key(Venue.BINANCE.value, config.leader_symbol),
        feed_stream_key(Venue.MEXC.value, config.lagger_symbol),
    )
    latest_ts_ms = max((state.last_ts_ms for state in streams.values()), default=0)
    if config.stale_feed_ms is None:
        decision_payload: dict[str, object] = {
            "healthy": None,
            "reason": "stale_feed_ms_not_configured",
            "stale_streams": [],
            "missing_streams": [],
        }
    else:
        decision = evaluate_feed_health(
            streams,
            required_streams,
            latest_ts_ms,
            config.stale_feed_ms,
        )
        decision_payload = {
            "healthy": decision.healthy,
            "reason": decision.reason,
            "stale_streams": list(decision.stale_streams),
            "missing_streams": list(decision.missing_streams),
        }

    return {
        "runtime_mode": RuntimeMode.PAPER.value,
        "canonical_symbol": config.canonical_symbol,
        "leader_symbol": config.leader_symbol,
        "lagger_symbol": config.lagger_symbol,
        "required_streams": list(required_streams),
        "stale_after_ms": config.stale_feed_ms,
        "latest_ts_ms": latest_ts_ms,
        "decision": decision_payload,
        "streams": {
            key: feed_stream_state_to_dict(streams[key])
            for key in sorted(streams)
        },
    }


async def run_quote_paper(
    quotes: AsyncIterable[Quote],
    config: PaperRunnerConfig,
    risk_config: RiskConfig | None = None,
    portfolio_state: PortfolioState | None = None,
    max_quotes: int | None = None,
    max_closed_positions: int | None = None,
    audit_sink: Callable[[ReplayAuditRecord], None] | None = None,
) -> tuple[ReplayPaperSummary, list[ReplayAuditRecord]]:
    """Run internal paper trading over a live-like async quote stream."""

    result = await run_quote_paper_result(
        quotes,
        config,
        risk_config,
        portfolio_state,
        max_quotes,
        max_closed_positions,
        audit_sink,
    )
    return result.summary, result.audit_records


async def run_quote_paper_result(
    quotes: AsyncIterable[Quote],
    config: PaperRunnerConfig,
    risk_config: RiskConfig | None = None,
    portfolio_state: PortfolioState | None = None,
    max_quotes: int | None = None,
    max_closed_positions: int | None = None,
    audit_sink: Callable[[ReplayAuditRecord], None] | None = None,
    summary_sink: Callable[[ReplayPaperSummary], None] | None = None,
    summary_interval_quotes: int = 100,
) -> PaperRunResult:
    """Run paper trading over async quotes and return summary, audit, and health."""

    engine = build_paper_trading_engine(config, risk_config, portfolio_state)
    if (max_quotes is not None and max_quotes <= 0) or (
        max_closed_positions is not None and max_closed_positions <= 0
    ):
        return PaperRunResult(
            engine.summary(),
            engine.audit_records_snapshot(),
            build_paper_health_report(engine, config),
        )

    async for quote in quotes:
        records = engine.on_quote(quote)
        if audit_sink is not None:
            for record in records:
                audit_sink(record)
        if summary_sink is not None and _should_emit_summary(
            engine.quote_count,
            records,
            summary_interval_quotes,
        ):
            summary_sink(engine.summary())
        if max_quotes is not None and engine.quote_count >= max_quotes:
            break
        if max_closed_positions is not None and engine.closed_positions >= max_closed_positions:
            break

    return PaperRunResult(
        engine.summary(),
        engine.audit_records_snapshot(),
        build_paper_health_report(engine, config),
    )


def _should_emit_summary(
    quote_count: int,
    records: list[ReplayAuditRecord],
    interval_quotes: int,
) -> bool:
    if records:
        return True
    if interval_quotes <= 0:
        return False
    return quote_count > 0 and quote_count % interval_quotes == 0
