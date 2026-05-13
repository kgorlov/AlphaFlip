from decimal import Decimal
from unittest import TestCase

from llbot.service.demo_fill_compare import compare_demo_fills


class DemoFillCompareTests(TestCase):
    def test_compares_paper_and_demo_fills_by_client_id(self) -> None:
        report = compare_demo_fills(
            [
                _paper("intent-1", "llb-intent-1", "BTC_USDT", "2", "100"),
                _paper("intent-2", "llb-intent-2", "ETH_USDT", "1", "50"),
            ],
            [
                _demo("llb-intent-1", "BTC_USDT", "2", "100.5"),
                _demo("llb-extra", "SOL_USDT", "3", "20"),
            ],
        )

        self.assertEqual(report.summary["matched"], 1)
        self.assertEqual(report.summary["price_mismatches"], 1)
        self.assertEqual(report.summary["qty_mismatches"], 0)
        self.assertEqual(report.summary["unmatched_paper"], 1)
        self.assertEqual(report.summary["unmatched_demo"], 1)
        self.assertEqual(report.comparisons[0].client_order_id, "llb-intent-1")
        self.assertEqual(report.comparisons[0].price_diff, Decimal("0.5"))
        self.assertEqual(report.unmatched_paper[0].client_order_id, "llb-intent-2")
        self.assertEqual(report.unmatched_demo[0].client_order_id, "llb-extra")

    def test_ignores_unfilled_paper_and_zero_demo_fills(self) -> None:
        report = compare_demo_fills(
            [
                {
                    "event_type": "replay_signal_decision",
                    "decision_result": "not_filled",
                    "fill_filled": False,
                    "intent_id": "intent-1",
                }
            ],
            [_demo("llb-intent-1", "BTC_USDT", "0", "100")],
        )

        self.assertEqual(report.summary["matched"], 0)
        self.assertEqual(report.summary["unmatched_paper"], 0)
        self.assertEqual(report.summary["unmatched_demo"], 0)


def _paper(intent_id: str, client_id: str, symbol: str, qty: str, price: str) -> dict:
    return {
        "event_type": "replay_signal_decision",
        "decision_result": "filled",
        "fill_filled": True,
        "fill_qty": qty,
        "fill_price": price,
        "intent_id": intent_id,
        "execution_symbol": symbol,
        "order_request": {"ClientId": client_id},
    }


def _demo(client_id: str, symbol: str, qty: str, price: str) -> dict:
    return {
        "client_order_id": client_id,
        "symbol": symbol,
        "filled_qty": qty,
        "avg_fill_price": price,
        "status": "filled",
    }
