from decimal import Decimal
from unittest import TestCase

from llbot.execution.metascalp_reconcile import (
    expand_metascalp_update,
    normalize_metascalp_update,
    reconcile_metascalp_updates,
)
from llbot.execution.order_state import OrderLifecycleStatus, OrderState


class MetaScalpReconcileTests(TestCase):
    def test_normalizes_order_fill_from_data_wrapper(self) -> None:
        update = normalize_metascalp_update(
            {
                "Type": "OrderUpdate",
                "Data": {
                    "ClientId": "llb-1",
                    "OrderId": "ord-1",
                    "Status": "Filled",
                    "FilledQty": "2",
                    "AvgFillPrice": "100.5",
                    "Timestamp": 1234,
                },
            }
        )

        assert update.order_event is not None
        self.assertEqual(update.update_type, "order")
        self.assertEqual(update.order_event.event_type, "fill")
        self.assertEqual(update.order_event.client_order_id, "llb-1")
        self.assertEqual(update.order_event.filled_qty, Decimal("2"))
        self.assertEqual(update.order_event.avg_fill_price, Decimal("100.5"))

    def test_reconciles_order_events_and_keeps_unmatched_visible(self) -> None:
        result = reconcile_metascalp_updates(
            [_order()],
            [
                {"Type": "OrderUpdate", "Data": {"ClientId": "llb-1", "Status": "Accepted", "Timestamp": 100}},
                {
                    "Type": "OrderUpdate",
                    "Data": {
                        "ClientId": "llb-1",
                        "OrderId": "ord-1",
                        "Status": "Partially_Filled",
                        "FilledQty": "1",
                        "AvgFillPrice": "100",
                        "Timestamp": 200,
                    },
                },
                {
                    "Type": "OrderUpdate",
                    "Data": {
                        "ClientId": "llb-1",
                        "OrderId": "ord-1",
                        "Status": "Filled",
                        "FilledQty": "2",
                        "AvgFillPrice": "100.1",
                        "Timestamp": 300,
                    },
                },
                {"Type": "OrderUpdate", "Data": {"ClientId": "missing", "Status": "Cancelled"}},
            ],
        )

        self.assertEqual(result.orders[0].status, OrderLifecycleStatus.FILLED)
        self.assertFalse(result.orders[0].open)
        self.assertEqual(result.orders[0].filled_qty, Decimal("2"))
        self.assertEqual(result.unmatched_updates, 1)
        self.assertEqual(result.audit_records[-1].decision_result, "unmatched_order_update")

    def test_reconciles_cancel_reject_position_balance_and_unknown(self) -> None:
        result = reconcile_metascalp_updates(
            [_order()],
            [
                {"Type": "PositionUpdate", "Data": {"ConnectionId": 11, "Symbol": "BTC_USDT", "Qty": "2"}},
                {"Type": "BalanceUpdate", "Data": {"Asset": "USDT", "Available": "10", "Total": "12"}},
                {"Type": "OrderUpdate", "Data": {"ClientId": "llb-1", "Status": "Cancelled", "Timestamp": 100}},
                {"Type": "OrderUpdate", "Data": {"ClientId": "llb-2", "Status": "Rejected", "Reason": "bad"}},
                {"Type": "Heartbeat", "Data": {"ok": True}},
            ],
        )

        self.assertEqual(result.orders[0].status, OrderLifecycleStatus.CANCELLED)
        self.assertEqual(result.positions[0].symbol, "BTC_USDT")
        self.assertEqual(result.positions[0].qty, Decimal("2"))
        self.assertEqual(result.balances[0].asset, "USDT")
        self.assertEqual(result.balances[0].available, Decimal("10"))
        self.assertEqual(result.unmatched_updates, 1)
        self.assertEqual(result.unknown_updates, 1)

    def test_expands_documented_metascalp_list_payloads(self) -> None:
        expanded = expand_metascalp_update(
            {
                "Type": "balance_update",
                "Data": {
                    "ConnectionId": 11,
                    "Balances": [
                        {"Asset": "USDT", "Available": "10", "Total": "12"},
                        {"Asset": "BTC", "Available": "1", "Total": "1"},
                    ],
                },
            }
        )

        self.assertEqual(len(expanded), 2)
        self.assertEqual(expanded[0]["Data"]["ConnectionId"], 11)
        self.assertEqual(expanded[1]["Data"]["Asset"], "BTC")

    def test_reconciles_documented_update_names_and_numeric_order_status(self) -> None:
        result = reconcile_metascalp_updates(
            [_order()],
            [
                {
                    "Type": "order_update",
                    "Data": {
                        "ClientId": "llb-1",
                        "Id": 123,
                        "Status": 2,
                        "FilledSize": "2",
                        "FilledPrice": "100.2",
                        "Timestamp": 100,
                    },
                },
                {
                    "Type": "position_update",
                    "Data": {"ConnectionId": 11, "Ticker": "BTC_USDT", "Size": "2", "Price": "100"},
                },
                {
                    "Type": "balance_update",
                    "Data": {
                        "ConnectionId": 11,
                        "Balances": [{"Asset": "USDT", "Available": "9", "Balance": "10"}],
                    },
                },
            ],
        )

        self.assertEqual(result.orders[0].status, OrderLifecycleStatus.FILLED)
        self.assertEqual(result.orders[0].venue_order_id, "123")
        self.assertEqual(result.orders[0].avg_fill_price, Decimal("100.2"))
        self.assertEqual(result.positions[0].symbol, "BTC_USDT")
        self.assertEqual(result.positions[0].avg_price, Decimal("100"))
        self.assertEqual(result.balances[0].total, Decimal("10"))


def _order() -> OrderState:
    return OrderState(
        intent_id="intent-1",
        client_order_id="llb-1",
        venue_order_id=None,
        symbol="BTC_USDT",
        qty=Decimal("2"),
        open=True,
        status=OrderLifecycleStatus.ACCEPTED,
        metadata={"connection_id": 11},
    )
