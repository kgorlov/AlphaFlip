"""Research-stage gates for ML experiments.

These checks keep experimental classifiers out of the trading path until the
offline dataset and rule-based baseline are good enough to justify them.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchReadiness:
    clean_tick_orderbook_dataset: bool = False
    rule_based_engine_proven: bool = False
    min_dataset_samples_met: bool = False
    explicit_neural_network_approval: bool = False


@dataclass(frozen=True, slots=True)
class ResearchDecision:
    allowed: bool
    reason: str


def evaluate_trade_skip_classifier_readiness(readiness: ResearchReadiness) -> ResearchDecision:
    """Return whether a simple offline trade/skip classifier may be tried."""

    if not readiness.clean_tick_orderbook_dataset:
        return ResearchDecision(False, "clean_tick_orderbook_dataset_required")
    if not readiness.min_dataset_samples_met:
        return ResearchDecision(False, "minimum_dataset_samples_required")
    if not readiness.rule_based_engine_proven:
        return ResearchDecision(False, "rule_based_baseline_required")
    return ResearchDecision(True, "ready_for_simple_trade_skip_classifier")


def evaluate_neural_network_training_readiness(readiness: ResearchReadiness) -> ResearchDecision:
    """Return whether neural-network training is explicitly allowed."""

    classifier = evaluate_trade_skip_classifier_readiness(readiness)
    if not classifier.allowed:
        return ResearchDecision(False, classifier.reason)
    if not readiness.explicit_neural_network_approval:
        return ResearchDecision(False, "explicit_neural_network_approval_required")
    return ResearchDecision(True, "ready_for_neural_network_training")
