from __future__ import annotations

import numpy as np
import unittest

from w0prep.statistics import (
    classify_final_label,
    clustered_bootstrap,
    document_mean_effects,
    holm_adjust,
)


class StatisticsTests(unittest.TestCase):
    def test_document_clusters_receive_equal_weight(self) -> None:
        rows = [
            {"document_id": "a", "effect": 1.0},
            {"document_id": "a", "effect": 3.0},
            {"document_id": "b", "effect": -2.0},
        ]
        np.testing.assert_array_equal(document_mean_effects(rows), np.asarray([2.0, -2.0]))

    def test_bootstrap_is_deterministic_and_positive(self) -> None:
        effects = np.linspace(0.2, 1.0, 64)
        left = clustered_bootstrap(effects, seed=7, replicates=2000, family_size=30)
        right = clustered_bootstrap(effects, seed=7, replicates=2000, family_size=30)
        self.assertEqual(left, right)
        self.assertLess(left.raw_p, 0.05)
        self.assertGreater(left.simultaneous_lcb, 0.0)

    def test_holm_stepdown(self) -> None:
        adjusted = holm_adjust([0.01, 0.04, 0.03])
        np.testing.assert_allclose(adjusted, [0.03, 0.06, 0.06])

    def test_label_precedence(self) -> None:
        self.assertEqual(classify_final_label(closure_ok=False, control_a_pass=True, control_b_pass=True, control_c_pass=True), "FAIL-W0-WORKLOAD-CLOSURE")
        self.assertEqual(classify_final_label(closure_ok=True, control_a_pass=False, control_b_pass=True, control_c_pass=True), "KILL-NO-PAIR-LOCALITY")
        self.assertEqual(classify_final_label(closure_ok=True, control_a_pass=True, control_b_pass=False, control_c_pass=True), "HOLD-GEOMETRIC-REPLACEMENT-ONLY")
        self.assertEqual(classify_final_label(closure_ok=True, control_a_pass=True, control_b_pass=True, control_c_pass=False), "KILL-NO-TEMPORAL-LINEAGE-SIGNAL")
        self.assertEqual(classify_final_label(closure_ok=True, control_a_pass=True, control_b_pass=True, control_c_pass=True), "HOLD-PAIR-LOCALITY-NOVELTY-REVIEW")


if __name__ == "__main__":
    unittest.main()
