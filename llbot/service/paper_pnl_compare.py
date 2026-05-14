"""Compare replay-paper and paper-run PnL summary artifacts."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


_PNL_FIELDS = (
    "gross_realized_pnl_usd",
    "realized_cost_usd",
    "realized_pnl_usd",
    "gross_unrealized_pnl_usd",
    "unrealized_cost_usd",
    "unrealized_pnl_usd",
)

_COUNT_FIELDS = (
    "processed_events",
    "quotes",
    "intents",
    "skipped_events",
    "risk_allowed",
    "risk_blocked",
    "fills",
    "not_filled",
    "closed_positions",
    "open_positions",
    "audit_records",
)


@dataclass(frozen=True, slots=True)
class SummarySnapshot:
    label: str
    pnl: dict[str, Decimal]
    counts: dict[str, int]
    intent_counts: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_net_pnl_usd(self) -> Decimal:
        return self.pnl["realized_pnl_usd"] + self.pnl["unrealized_pnl_usd"]


@dataclass(frozen=True, slots=True)
class PnlComparisonReport:
    matched: bool
    tolerance_usd: Decimal
    replay: SummarySnapshot
    paper: SummarySnapshot
    pnl_deltas: dict[str, Decimal]
    count_deltas: dict[str, int]
    intent_count_deltas: dict[str, int]
    mismatch_reasons: list[str]

    @property
    def summary(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "tolerance_usd": self.tolerance_usd,
            "mismatch_count": len(self.mismatch_reasons),
            "total_net_pnl_delta_usd": self.pnl_deltas["total_net_pnl_usd"],
            "fill_delta": self.count_deltas["fills"],
            "closed_position_delta": self.count_deltas["closed_positions"],
        }


def compare_replay_paper_pnl(
    replay_summary: dict[str, Any],
    paper_summary: dict[str, Any],
    *,
    tolerance_usd: Decimal = Decimal("0"),
) -> PnlComparisonReport:
    replay = summary_snapshot("replay", replay_summary)
    paper = summary_snapshot("paper", paper_summary)
    pnl_deltas = {
        field: paper.pnl[field] - replay.pnl[field]
        for field in _PNL_FIELDS
    }
    pnl_deltas["total_net_pnl_usd"] = paper.total_net_pnl_usd - replay.total_net_pnl_usd

    count_deltas = {
        field: paper.counts[field] - replay.counts[field]
        for field in _COUNT_FIELDS
    }
    intent_keys = sorted(set(replay.intent_counts) | set(paper.intent_counts))
    intent_count_deltas = {
        key: paper.intent_counts.get(key, 0) - replay.intent_counts.get(key, 0)
        for key in intent_keys
    }

    mismatch_reasons = _mismatch_reasons(
        pnl_deltas,
        count_deltas,
        intent_count_deltas,
        tolerance_usd,
    )
    return PnlComparisonReport(
        matched=not mismatch_reasons,
        tolerance_usd=tolerance_usd,
        replay=replay,
        paper=paper,
        pnl_deltas=pnl_deltas,
        count_deltas=count_deltas,
        intent_count_deltas=intent_count_deltas,
        mismatch_reasons=mismatch_reasons,
    )


def summary_snapshot(label: str, payload: dict[str, Any]) -> SummarySnapshot:
    return SummarySnapshot(
        label=label,
        pnl={field: _decimal(payload.get(field, "0")) for field in _PNL_FIELDS},
        counts={field: _int(payload.get(field, 0)) for field in _COUNT_FIELDS},
        intent_counts=_intent_counts(payload.get("intent_counts", {})),
        raw=payload,
    )


def _mismatch_reasons(
    pnl_deltas: dict[str, Decimal],
    count_deltas: dict[str, int],
    intent_count_deltas: dict[str, int],
    tolerance_usd: Decimal,
) -> list[str]:
    reasons: list[str] = []
    for field, delta in pnl_deltas.items():
        if abs(delta) > tolerance_usd:
            reasons.append(f"{field}_delta")
    for field, delta in count_deltas.items():
        if delta != 0:
            reasons.append(f"{field}_delta")
    for key, delta in intent_count_deltas.items():
        if delta != 0:
            reasons.append(f"intent_count_delta:{key}")
    return reasons


def _intent_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(count) for key, count in value.items()}


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)
