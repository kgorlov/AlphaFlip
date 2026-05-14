from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase

from llbot.adapters.metascalp import MetaScalpConnection
from llbot.adapters.metascalp import MetaScalpClient
from llbot.adapters.http_client import HttpRequestError
from llbot.domain.enums import IntentType, MarketProfileName, MarketType, OrderStyle, RuntimeMode, Side, Venue
from llbot.domain.models import Intent, SymbolProfile
from llbot.execution.planner import (
    EntryPlan,
    apply_edge_order_style,
    build_entry_intent,
    select_order_style_for_edge,
)
from llbot.execution.metascalp_executor import (
    GuardedMetaScalpDemoExecutor,
    MetaScalpExecutorConfig,
)
from llbot.execution.order_state import (
    OrderLifecycleStatus,
    OrderReconciliationEvent,
    build_ttl_cancel_plan,
    cancel_plan_audit_record,
    cancel_response_audit_record,
    mark_cancel_planned,
    order_state_from_submit_audit,
    reconcile_order_state,
)
from llbot.execution.metascalp_planner import (
    build_metascalp_dry_run_order_plan,
    dry_run_order_audit_record,
    metascalp_response_audit_record,
    validate_intent_for_symbol,
)


class MetaScalpExecutionPlannerTests(TestCase):
    def test_builds_traceable_dry_run_aggressive_limit_request(self) -> None:
        intent = _intent()

        plan = build_metascalp_dry_run_order_plan(
            intent,
            _connection(),
            execution_symbol="BTC_USDT",
            profile=_profile(),
        )
        audit = dry_run_order_audit_record(plan, intent)

        self.assertTrue(plan.validation.ok)
        self.assertTrue(plan.dry_run)
        self.assertEqual(plan.connection_id, 11)
        self.assertEqual(plan.endpoint, "/api/connections/11/orders")
        self.assertEqual(plan.payload["Symbol"], "BTC_USDT")
        self.assertEqual(plan.payload["Side"], "Buy")
        self.assertEqual(plan.payload["OrderType"], "Limit")
        self.assertEqual(plan.payload["Price"], "100.1")
        self.assertEqual(plan.payload["Volume"], "2")
        self.assertEqual(plan.payload["ClientId"], "llb-intent-test-1")
        self.assertEqual(plan.payload["Comment"], "leadlag:intent-test-1")
        self.assertFalse(plan.payload["ReduceOnly"])

        self.assertEqual(audit.event_type, "metascalp_order_dry_run")
        self.assertEqual(audit.decision_result, "dry_run_planned")
        self.assertIsNone(audit.client_id_returned)
        self.assertIsNone(audit.execution_time_ms)
        self.assertFalse(audit.unknown_status)
        self.assertIsNone(audit.skip_reason)

    def test_exit_intent_sets_reduce_only(self) -> None:
        intent = _intent(
            intent_type=IntentType.EXIT_LONG,
            side=Side.SELL,
        )

        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT")

        self.assertEqual(plan.payload["Side"], "Sell")
        self.assertTrue(plan.payload["ReduceOnly"])

    def test_spot_exit_does_not_set_reduce_only_when_unsupported(self) -> None:
        intent = _intent(intent_type=IntentType.EXIT_LONG, side=Side.SELL)
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTCUSDT", _spot_profile())

        self.assertFalse(plan.payload["ReduceOnly"])

    def test_explicit_reduce_only_support_metadata_overrides_market_type(self) -> None:
        intent = _intent(intent_type=IntentType.EXIT_LONG, side=Side.SELL)
        profile = _spot_profile(metadata={"reduce_only_supported": True})

        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTCUSDT", profile)

        self.assertTrue(plan.payload["ReduceOnly"])

    def test_order_style_selection_requires_edge_thresholds(self) -> None:
        passive = select_order_style_for_edge(
            Decimal("15"),
            taker_min_edge_bps=Decimal("8"),
            maker_min_edge_bps=Decimal("14"),
        )
        aggressive = select_order_style_for_edge(
            Decimal("9"),
            taker_min_edge_bps=Decimal("8"),
            maker_min_edge_bps=Decimal("14"),
        )
        blocked = select_order_style_for_edge(
            Decimal("7"),
            taker_min_edge_bps=Decimal("8"),
            maker_min_edge_bps=Decimal("14"),
        )

        self.assertEqual(passive.order_style, OrderStyle.PASSIVE_LIMIT)
        self.assertEqual(aggressive.order_style, OrderStyle.AGGRESSIVE_LIMIT)
        self.assertFalse(blocked.allowed)

    def test_apply_edge_order_style_builds_passive_intent_only_for_large_edge(self) -> None:
        plan = apply_edge_order_style(
            EntryPlan(
                symbol="BTCUSDT",
                profile=MarketProfileName.PERP_TO_PERP,
                direction=IntentType.ENTER_LONG,
                qty=Decimal("2"),
                price_cap=Decimal("100.1"),
                ttl_ms=3000,
                expected_edge_bps=Decimal("15"),
            ),
            taker_min_edge_bps=Decimal("8"),
            maker_min_edge_bps=Decimal("14"),
        )
        intent = build_entry_intent(plan, created_ts_ms=123)

        self.assertEqual(intent.order_style, OrderStyle.PASSIVE_LIMIT)

    def test_validation_rejects_quantity_price_and_notional(self) -> None:
        self.assertEqual(
            validate_intent_for_symbol(_intent(qty=Decimal("0")), _profile()).reason,
            "qty_must_be_positive",
        )
        self.assertEqual(
            validate_intent_for_symbol(_intent(qty=Decimal("2.5")), _profile()).reason,
            "qty_step_mismatch",
        )
        self.assertEqual(
            validate_intent_for_symbol(_intent(price_cap=Decimal("100.11")), _profile()).reason,
            "price_tick_mismatch",
        )
        self.assertEqual(
            validate_intent_for_symbol(_intent(qty=Decimal("1")), _profile()).reason,
            "notional_below_min",
        )

    def test_failed_validation_is_audited_without_submission(self) -> None:
        intent = _intent(qty=Decimal("2.5"))
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())
        audit = dry_run_order_audit_record(plan, intent)

        self.assertFalse(plan.validation.ok)
        self.assertEqual(audit.decision_result, "validation_failed")
        self.assertEqual(audit.skip_reason, "qty_step_mismatch")
        self.assertTrue(audit.dry_run)
        self.assertEqual(audit.response["ClientId"], None)
        self.assertEqual(audit.response["ExecutionTimeMs"], None)

    def test_future_response_audit_captures_client_id_and_execution_time(self) -> None:
        intent = _intent()
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())

        audit = metascalp_response_audit_record(
            plan,
            intent,
            {"Data": {"ClientId": "llb-intent-test-1", "ExecutionTimeMs": 12}},
            status_code=200,
        )

        self.assertEqual(audit.event_type, "metascalp_order_response")
        self.assertEqual(audit.decision_result, "accepted")
        self.assertEqual(audit.client_id_returned, "llb-intent-test-1")
        self.assertEqual(audit.execution_time_ms, 12)
        self.assertFalse(audit.unknown_status)

    def test_future_5xx_response_is_unknown_status(self) -> None:
        intent = _intent()
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())

        audit = metascalp_response_audit_record(
            plan,
            intent,
            {"Message": "temporary server error"},
            status_code=502,
        )

        self.assertEqual(audit.decision_result, "unknown_status")
        self.assertEqual(audit.skip_reason, "server_error_unknown_order_status")
        self.assertTrue(audit.unknown_status)
        self.assertIsNone(audit.client_id_returned)
        self.assertIsNone(audit.execution_time_ms)


class MetaScalpDemoExecutorTests(IsolatedAsyncioTestCase):
    async def test_executor_defaults_to_dry_run_without_post(self) -> None:
        http = _FakePostHttp({"/api/connections/11/orders": {"Data": {"ClientId": "x"}}})
        executor = GuardedMetaScalpDemoExecutor(MetaScalpClient(http))

        audit = await executor.submit(_intent(), _connection(), "BTC_USDT", _profile())

        self.assertEqual(audit.decision_result, "dry_run_planned")
        self.assertTrue(audit.dry_run)
        self.assertEqual(http.post_calls, [])

    async def test_executor_rejects_live_mode_and_non_demo_connection(self) -> None:
        live_executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(_FakePostHttp({})),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.LIVE),
        )
        live_audit = await live_executor.submit(_intent(), _connection(), "BTC_USDT", _profile())

        non_demo_executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(_FakePostHttp({})),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.METASCALP_DEMO),
        )
        non_demo_audit = await non_demo_executor.submit(
            _intent(),
            _connection(demo_mode=False),
            "BTC_USDT",
            _profile(),
        )

        self.assertEqual(live_audit.decision_result, "guard_blocked")
        self.assertEqual(live_audit.skip_reason, "live_mode_not_supported")
        self.assertEqual(non_demo_audit.decision_result, "guard_blocked")
        self.assertEqual(non_demo_audit.skip_reason, "connection_not_demo")

    async def test_executor_posts_only_when_explicitly_allowed_for_demo_mode(self) -> None:
        http = _FakePostHttp(
            {"/api/connections/11/orders": {"Data": {"ClientId": "llb-intent-test-1", "ExecutionTimeMs": 7}}}
        )
        executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(http),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.METASCALP_DEMO),
        )

        audit = await executor.submit(_intent(), _connection(), "BTC_USDT", _profile())

        self.assertEqual(http.post_calls[0][0], "/api/connections/11/orders")
        self.assertEqual(http.post_calls[0][1]["ClientId"], "llb-intent-test-1")
        self.assertEqual(audit.decision_result, "accepted")
        self.assertFalse(audit.dry_run)
        self.assertEqual(audit.client_id_returned, "llb-intent-test-1")
        self.assertEqual(audit.execution_time_ms, 7)

    async def test_executor_marks_post_5xx_as_unknown_status(self) -> None:
        http = _FakePostHttp({}, error=HttpRequestError("POST http://x failed: 502 bad gateway"))
        executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(http),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.METASCALP_DEMO),
        )

        audit = await executor.submit(_intent(), _connection(), "BTC_USDT", _profile())

        self.assertEqual(audit.decision_result, "unknown_status")
        self.assertTrue(audit.unknown_status)
        self.assertEqual(audit.skip_reason, "server_error_unknown_order_status")

    async def test_cancel_defaults_to_dry_run_without_post(self) -> None:
        http = _FakePostHttp({"/api/connections/11/orders/cancel": {"Data": {"Cancelled": True}}})
        executor = GuardedMetaScalpDemoExecutor(MetaScalpClient(http))

        audit = await executor.cancel(_cancel_plan(), _connection())

        self.assertEqual(audit.decision_result, "cancel_dry_run_planned")
        self.assertTrue(audit.dry_run)
        self.assertEqual(http.post_calls, [])

    async def test_cancel_posts_only_when_explicitly_allowed_for_demo_mode(self) -> None:
        http = _FakePostHttp({"/api/connections/11/orders/cancel": {"Data": {"Cancelled": True}}})
        executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(http),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.METASCALP_DEMO),
        )

        audit = await executor.cancel(_cancel_plan(), _connection())

        self.assertEqual(http.post_calls[0][0], "/api/connections/11/orders/cancel")
        self.assertEqual(http.post_calls[0][1]["ClientId"], "llb-intent-test-1")
        self.assertEqual(audit.decision_result, "cancel_accepted")
        self.assertFalse(audit.dry_run)

    async def test_cancel_5xx_is_unknown_cancel_status(self) -> None:
        http = _FakePostHttp({}, error=HttpRequestError("POST http://x failed: 503 unavailable"))
        executor = GuardedMetaScalpDemoExecutor(
            MetaScalpClient(http),
            MetaScalpExecutorConfig(allow_submit=True, runtime_mode=RuntimeMode.METASCALP_DEMO),
        )

        audit = await executor.cancel(_cancel_plan(), _connection())

        self.assertEqual(audit.decision_result, "cancel_unknown_status")
        self.assertEqual(audit.skip_reason, "server_error_unknown_cancel_status")


class OrderLifecycleTests(TestCase):
    def test_accepted_submit_audit_initializes_open_order_state(self) -> None:
        intent = _intent()
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())
        audit = metascalp_response_audit_record(
            plan,
            intent,
            {"Data": {"ClientId": "llb-intent-test-1", "ExecutionTimeMs": 7, "OrderId": "ord-1"}},
            status_code=200,
        )

        state = order_state_from_submit_audit(audit, qty=intent.qty, now_ts_ms=1000, ttl_ms=3000)

        self.assertEqual(state.status, OrderLifecycleStatus.ACCEPTED)
        self.assertTrue(state.open)
        self.assertEqual(state.client_order_id, "llb-intent-test-1")
        self.assertEqual(state.venue_order_id, "ord-1")
        self.assertEqual(state.expires_ts_ms, 4000)
        self.assertEqual(state.metadata["execution_time_ms"], 7)

    def test_unknown_submit_audit_remains_open_for_reconciliation(self) -> None:
        intent = _intent()
        plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())
        audit = metascalp_response_audit_record(plan, intent, {"Message": "bad gateway"}, status_code=502)

        state = order_state_from_submit_audit(audit, qty=intent.qty, now_ts_ms=1000, ttl_ms=3000)

        self.assertEqual(state.status, OrderLifecycleStatus.UNKNOWN)
        self.assertTrue(state.open)
        self.assertTrue(state.unknown_status)

    def test_reconcile_fill_cancel_and_reject_events(self) -> None:
        state = _accepted_order_state()

        partial = reconcile_order_state(
            state,
            OrderReconciliationEvent(
                event_type="fill",
                client_order_id=state.client_order_id,
                ts_ms=1100,
                filled_qty=Decimal("1"),
                avg_fill_price=Decimal("100.1"),
            ),
        )
        filled = reconcile_order_state(
            partial,
            OrderReconciliationEvent(
                event_type="fill",
                client_order_id=state.client_order_id,
                ts_ms=1200,
                filled_qty=Decimal("2"),
                avg_fill_price=Decimal("100.1"),
            ),
        )
        cancelled = reconcile_order_state(
            state,
            OrderReconciliationEvent(
                event_type="cancelled",
                client_order_id=state.client_order_id,
                ts_ms=1300,
            ),
        )
        rejected = reconcile_order_state(
            state,
            OrderReconciliationEvent(
                event_type="rejected",
                client_order_id=state.client_order_id,
                ts_ms=1400,
                reason="exchange_rejected",
            ),
        )

        self.assertEqual(partial.status, OrderLifecycleStatus.PARTIALLY_FILLED)
        self.assertTrue(partial.open)
        self.assertEqual(filled.status, OrderLifecycleStatus.FILLED)
        self.assertFalse(filled.open)
        self.assertEqual(cancelled.status, OrderLifecycleStatus.CANCELLED)
        self.assertFalse(cancelled.open)
        self.assertEqual(rejected.status, OrderLifecycleStatus.REJECTED)
        self.assertEqual(rejected.metadata["reject_reason"], "exchange_rejected")

    def test_ttl_cancel_plan_and_audit_are_dry_run(self) -> None:
        state = _accepted_order_state()

        before = build_ttl_cancel_plan(state, connection_id=11, now_ts_ms=3999)
        plan = build_ttl_cancel_plan(state, connection_id=11, now_ts_ms=4000)
        assert plan is not None
        audit = cancel_plan_audit_record(plan)
        planned_state = mark_cancel_planned(state, plan)

        self.assertIsNone(before)
        self.assertEqual(plan.endpoint, "/api/connections/11/orders/cancel")
        self.assertEqual(plan.request["ClientId"], "llb-intent-test-1")
        self.assertEqual(plan.request["OrderId"], "ord-1")
        self.assertTrue(plan.dry_run)
        self.assertEqual(audit.event_type, "metascalp_cancel_dry_run")
        self.assertEqual(audit.decision_result, "cancel_dry_run_planned")
        self.assertEqual(planned_state.status, OrderLifecycleStatus.CANCEL_PLANNED)
        self.assertTrue(planned_state.open)

    def test_cancel_response_audit_marks_5xx_unknown(self) -> None:
        audit = cancel_response_audit_record(_cancel_plan(), {"Message": "bad gateway"}, status_code=502)

        self.assertEqual(audit.event_type, "metascalp_cancel_response")
        self.assertEqual(audit.decision_result, "cancel_unknown_status")
        self.assertEqual(audit.skip_reason, "server_error_unknown_cancel_status")
        self.assertTrue(audit.metadata["unknown_status"])


class _FakePostHttp:
    def __init__(self, routes, error=None):
        self.routes = routes
        self.error = error
        self.post_calls = []

    async def get_json(self, path, params=None):
        return self.routes[path]

    async def post_json(self, path, payload=None):
        self.post_calls.append((path, payload))
        if self.error is not None:
            raise self.error
        return self.routes[path]


def _intent(
    qty: Decimal = Decimal("2"),
    price_cap: Decimal = Decimal("100.1"),
    intent_type: IntentType = IntentType.ENTER_LONG,
    side: Side = Side.BUY,
) -> Intent:
    return Intent(
        intent_id="intent-test-1",
        symbol="BTCUSDT",
        profile=MarketProfileName.PERP_TO_PERP,
        intent_type=intent_type,
        side=side,
        qty=qty,
        price_cap=price_cap,
        ttl_ms=3000,
        order_style=OrderStyle.AGGRESSIVE_LIMIT,
        confidence=Decimal("1"),
        expected_edge_bps=Decimal("8"),
        created_ts_ms=123,
    )


def _connection(demo_mode: bool = True, state: int = 2) -> MetaScalpConnection:
    return MetaScalpConnection(
        id=11,
        name="MEXC demo",
        exchange="Mexc",
        exchange_id=1,
        market="UsdtFutures",
        market_type=1,
        state=state,
        view_mode=False,
        demo_mode=demo_mode,
    )


def _profile() -> SymbolProfile:
    return SymbolProfile(
        canonical_symbol="BTCUSDT",
        leader_symbol="BTCUSDT",
        lagger_symbol="BTC_USDT",
        profile=MarketProfileName.PERP_TO_PERP,
        leader_venue=Venue.BINANCE,
        lagger_venue=Venue.MEXC,
        leader_market=MarketType.USDT_PERP,
        lagger_market=MarketType.USDT_PERP,
        min_qty=Decimal("1"),
        qty_step=Decimal("1"),
        price_tick=Decimal("0.1"),
        min_notional_usd=Decimal("200"),
        contract_size=Decimal("1"),
    )


def _spot_profile(metadata: dict[str, object] | None = None) -> SymbolProfile:
    return SymbolProfile(
        canonical_symbol="BTCUSDT",
        leader_symbol="BTCUSDT",
        lagger_symbol="BTCUSDT",
        profile=MarketProfileName.SPOT_TO_SPOT,
        leader_venue=Venue.BINANCE,
        lagger_venue=Venue.MEXC,
        leader_market=MarketType.SPOT,
        lagger_market=MarketType.SPOT,
        min_qty=Decimal("1"),
        qty_step=Decimal("1"),
        price_tick=Decimal("0.1"),
        min_notional_usd=Decimal("200"),
        metadata=metadata or {},
    )


def _accepted_order_state():
    intent = _intent()
    plan = build_metascalp_dry_run_order_plan(intent, _connection(), "BTC_USDT", _profile())
    audit = metascalp_response_audit_record(
        plan,
        intent,
        {"Data": {"ClientId": "llb-intent-test-1", "ExecutionTimeMs": 7, "OrderId": "ord-1"}},
        status_code=200,
    )
    return order_state_from_submit_audit(audit, qty=intent.qty, now_ts_ms=1000, ttl_ms=3000)


def _cancel_plan():
    state = _accepted_order_state()
    plan = build_ttl_cancel_plan(state, connection_id=11, now_ts_ms=4000)
    assert plan is not None
    return plan
