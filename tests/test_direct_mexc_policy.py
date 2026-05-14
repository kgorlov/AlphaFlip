from unittest import TestCase

from llbot.execution.direct_mexc_policy import (
    DirectMexcPolicy,
    direct_mexc_v1_status,
    validate_direct_mexc_execution_request,
)


class DirectMexcPolicyTests(TestCase):
    def test_direct_mexc_execution_is_disabled_in_v1(self) -> None:
        decision = validate_direct_mexc_execution_request(_valid_future_request())
        status = direct_mexc_v1_status()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "direct_mexc_execution_disabled_in_v1")
        self.assertFalse(status["direct_mexc_execution_enabled"])
        self.assertEqual(status["execution_path"], "metascalp_v1_only")

    def test_future_adapter_requires_idempotency_and_safety_gates(self) -> None:
        policy = DirectMexcPolicy(enabled_in_v1=True)

        self.assertEqual(
            validate_direct_mexc_execution_request({}, policy).reason,
            "missing_idempotency_key",
        )
        self.assertEqual(
            validate_direct_mexc_execution_request({"newClientOrderId": "cid-1"}, policy).reason,
            "missing_signed_request",
        )
        self.assertEqual(
            validate_direct_mexc_execution_request(
                {**_valid_future_request(), "ip_whitelist_enabled": False},
                policy,
            ).reason,
            "ip_whitelist_required",
        )
        self.assertTrue(validate_direct_mexc_execution_request(_valid_future_request(), policy).allowed)

    def test_undocumented_private_endpoint_is_forbidden(self) -> None:
        policy = DirectMexcPolicy(enabled_in_v1=True)
        decision = validate_direct_mexc_execution_request(
            {**_valid_future_request(), "reverse_engineered_endpoint": True},
            policy,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "private_undocumented_endpoint_forbidden")


def _valid_future_request() -> dict[str, object]:
    return {
        "newClientOrderId": "cid-1",
        "signed_request": True,
        "ip_whitelist_enabled": True,
        "scoped_api_key": True,
        "official_endpoint": True,
    }
