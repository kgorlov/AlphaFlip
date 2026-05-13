"""Compare internal paper fills against reconciled MetaScalp demo fills."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class PaperFillSnapshot:
    client_order_id: str
    intent_id: str
    symbol: str
    qty: Decimal
    price: Decimal
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DemoFillSnapshot:
    client_order_id: str
    symbol: str
    qty: Decimal
    price: Decimal
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FillComparison:
    client_order_id: str
    intent_id: str | None
    symbol: str | None
    paper_qty: Decimal | None
    demo_qty: Decimal | None
    qty_diff: Decimal | None
    paper_price: Decimal | None
    demo_price: Decimal | None
    price_diff: Decimal | None
    status: str


@dataclass(frozen=True, slots=True)
class DemoFillComparisonReport:
    comparisons: list[FillComparison]
    unmatched_paper: list[PaperFillSnapshot]
    unmatched_demo: list[DemoFillSnapshot]

    @property
    def summary(self) -> dict[str, int]:
        matched = len(self.comparisons)
        qty_mismatches = sum(1 for item in self.comparisons if item.qty_diff not in {None, Decimal("0")})
        price_mismatches = sum(1 for item in self.comparisons if item.price_diff not in {None, Decimal("0")})
        return {
            "matched": matched,
            "unmatched_paper": len(self.unmatched_paper),
            "unmatched_demo": len(self.unmatched_demo),
            "qty_mismatches": qty_mismatches,
            "price_mismatches": price_mismatches,
        }


def compare_demo_fills(
    paper_records: Iterable[dict[str, Any]],
    reconciled_orders: Iterable[dict[str, Any]],
) -> DemoFillComparisonReport:
    paper = {fill.client_order_id: fill for fill in _paper_fills(paper_records)}
    demo = {fill.client_order_id: fill for fill in _demo_fills(reconciled_orders)}
    matched_ids = sorted(set(paper) & set(demo))

    comparisons = [
        FillComparison(
            client_order_id=client_id,
            intent_id=paper[client_id].intent_id,
            symbol=paper[client_id].symbol or demo[client_id].symbol,
            paper_qty=paper[client_id].qty,
            demo_qty=demo[client_id].qty,
            qty_diff=demo[client_id].qty - paper[client_id].qty,
            paper_price=paper[client_id].price,
            demo_price=demo[client_id].price,
            price_diff=demo[client_id].price - paper[client_id].price,
            status="matched",
        )
        for client_id in matched_ids
    ]

    unmatched_paper = [paper[key] for key in sorted(set(paper) - set(demo))]
    unmatched_demo = [demo[key] for key in sorted(set(demo) - set(paper))]
    return DemoFillComparisonReport(comparisons, unmatched_paper, unmatched_demo)


def _paper_fills(records: Iterable[dict[str, Any]]) -> list[PaperFillSnapshot]:
    fills: list[PaperFillSnapshot] = []
    for record in records:
        if record.get("event_type") != "replay_signal_decision":
            continue
        if record.get("decision_result") != "filled" or not bool(record.get("fill_filled")):
            continue
        client_id = _client_id(record)
        fill_price = _decimal_or_none(record.get("fill_price"))
        fill_qty = _decimal_or_none(record.get("fill_qty"))
        if client_id is None or fill_price is None or fill_qty is None:
            continue
        fills.append(
            PaperFillSnapshot(
                client_order_id=client_id,
                intent_id=str(record.get("intent_id", "")),
                symbol=str(record.get("execution_symbol") or record.get("symbol") or ""),
                qty=fill_qty,
                price=fill_price,
                raw=record,
            )
        )
    return fills


def _demo_fills(orders: Iterable[dict[str, Any]]) -> list[DemoFillSnapshot]:
    fills: list[DemoFillSnapshot] = []
    for order in orders:
        status = str(order.get("status", ""))
        filled_qty = _decimal_or_none(order.get("filled_qty"))
        avg_fill_price = _decimal_or_none(order.get("avg_fill_price"))
        client_id = order.get("client_order_id")
        if client_id is None or filled_qty is None or filled_qty <= 0 or avg_fill_price is None:
            continue
        fills.append(
            DemoFillSnapshot(
                client_order_id=str(client_id),
                symbol=str(order.get("symbol", "")),
                qty=filled_qty,
                price=avg_fill_price,
                status=status,
                raw=order,
            )
        )
    return fills


def _client_id(record: dict[str, Any]) -> str | None:
    request = record.get("order_request")
    if isinstance(request, dict):
        for key in ("ClientId", "clientId", "client_id"):
            if request.get(key):
                return str(request[key])
    if record.get("client_order_id"):
        return str(record["client_order_id"])
    if record.get("intent_id"):
        return f"llb-{record['intent_id']}"
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
