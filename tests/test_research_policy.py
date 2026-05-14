from unittest import TestCase

from llbot.service.research_policy import (
    ResearchReadiness,
    evaluate_neural_network_training_readiness,
    evaluate_trade_skip_classifier_readiness,
)


class ResearchPolicyTests(TestCase):
    def test_trade_skip_classifier_waits_for_clean_dataset(self) -> None:
        decision = evaluate_trade_skip_classifier_readiness(ResearchReadiness())

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "clean_tick_orderbook_dataset_required")

    def test_trade_skip_classifier_requires_baseline_and_sample_floor(self) -> None:
        missing_samples = evaluate_trade_skip_classifier_readiness(
            ResearchReadiness(clean_tick_orderbook_dataset=True)
        )
        missing_baseline = evaluate_trade_skip_classifier_readiness(
            ResearchReadiness(
                clean_tick_orderbook_dataset=True,
                min_dataset_samples_met=True,
            )
        )

        self.assertFalse(missing_samples.allowed)
        self.assertEqual(missing_samples.reason, "minimum_dataset_samples_required")
        self.assertFalse(missing_baseline.allowed)
        self.assertEqual(missing_baseline.reason, "rule_based_baseline_required")

    def test_trade_skip_classifier_can_be_enabled_for_offline_research(self) -> None:
        decision = evaluate_trade_skip_classifier_readiness(
            ResearchReadiness(
                clean_tick_orderbook_dataset=True,
                min_dataset_samples_met=True,
                rule_based_engine_proven=True,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "ready_for_simple_trade_skip_classifier")

    def test_neural_network_training_requires_extra_explicit_approval(self) -> None:
        blocked = evaluate_neural_network_training_readiness(
            ResearchReadiness(
                clean_tick_orderbook_dataset=True,
                min_dataset_samples_met=True,
                rule_based_engine_proven=True,
            )
        )
        allowed = evaluate_neural_network_training_readiness(
            ResearchReadiness(
                clean_tick_orderbook_dataset=True,
                min_dataset_samples_met=True,
                rule_based_engine_proven=True,
                explicit_neural_network_approval=True,
            )
        )

        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.reason, "explicit_neural_network_approval_required")
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.reason, "ready_for_neural_network_training")
