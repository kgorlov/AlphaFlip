"""Policy gates for any future direct MEXC private execution adapter."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DirectMexcPolicy:
    enabled_in_v1: bool = False
    require_idempotency_key: bool = True
    require_signed_request: bool = True
    require_ip_whitelist: bool = True
    require_scoped_key: bool = True
    require_official_endpoint: bool = True


@dataclass(frozen=True, slots=True)
class DirectMexcPolicyDecision:
    allowed: bool
    reason: str


def validate_direct_mexc_execution_request(
    request: dict[str, Any],
    policy: DirectMexcPolicy | None = None,
) -> DirectMexcPolicyDecision:
    """Validate a future direct MEXC private request before any adapter can send it."""

    policy = policy or DirectMexcPolicy()
    if not policy.enabled_in_v1:
        return DirectMexcPolicyDecision(False, "direct_mexc_execution_disabled_in_v1")

    if policy.require_idempotency_key and not _has_idempotency_key(request):
        return DirectMexcPolicyDecision(False, "missing_idempotency_key")
    if policy.require_signed_request and not bool(request.get("signed_request")):
        return DirectMexcPolicyDecision(False, "missing_signed_request")
    if policy.require_ip_whitelist and not bool(request.get("ip_whitelist_enabled")):
        return DirectMexcPolicyDecision(False, "ip_whitelist_required")
    if policy.require_scoped_key and not bool(request.get("scoped_api_key")):
        return DirectMexcPolicyDecision(False, "scoped_api_key_required")
    if policy.require_official_endpoint and not bool(request.get("official_endpoint")):
        return DirectMexcPolicyDecision(False, "official_endpoint_required")
    if bool(request.get("reverse_engineered_endpoint")):
        return DirectMexcPolicyDecision(False, "private_undocumented_endpoint_forbidden")

    return DirectMexcPolicyDecision(True, "ok")


def direct_mexc_v1_status() -> dict[str, object]:
    return {
        "execution_path": "metascalp_v1_only",
        "direct_mexc_execution_enabled": False,
        "future_adapter_stage": "later_adapter_only",
        "required_idempotency_fields": ["newClientOrderId", "externalOid"],
        "requires_signed_rest": True,
        "requires_ip_whitelist": True,
        "requires_scoped_keys": True,
        "official_endpoints_only": True,
    }


def _has_idempotency_key(request: dict[str, Any]) -> bool:
    return bool(request.get("newClientOrderId") or request.get("externalOid"))
