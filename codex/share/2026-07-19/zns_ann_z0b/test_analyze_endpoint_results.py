#!/usr/bin/env python3
"""Synthetic boundary tests for the frozen 288-config post-processor."""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import analyze_endpoint_results as analysis


HERE = Path(__file__).resolve().parent


def record(system: str, realization: int, capacity: int, spares: int,
           placement: str, cleaner: str, cycles: int = 0,
           host_wa: Fraction = Fraction(1), rising: bool = False) -> analysis.RunRecord:
    trace = ("dgai-50k" if system == "DGAI" else "odinann-400k") + f"-r{realization}"
    placement_id = {
        "Canonical": "canonical", "RoleSeparated": "role",
        "RandomPacking-2026071901": "random-2026071901",
        "RandomPacking-2026071902": "random-2026071902",
        "RandomPacking-2026071903": "random-2026071903",
        "OfflineHotColdOracle": "oracle",
    }[placement]
    cleaner_id = "greedy" if cleaner == "GreedyValidFraction" else "oracle"
    moved = tuple(index + 1 if rising else 2 for index in range(cycles))
    victim = tuple(Fraction(value, capacity) for value in moved)
    cycle_wa = tuple(Fraction(index + 2, 1) if rising else Fraction(3, 2)
                     for index in range(cycles))
    return analysis.RunRecord(
        trace, system, realization, capacity, spares, placement, cleaner,
        f"z{capacity}-h{spares}-{placement_id}-{cleaner_id}", host_wa, cycles,
        moved, victim, cycle_wa, tuple(range(1, cycles + 1)),
    )


def synthetic_matrix() -> list[analysis.RunRecord]:
    records = []
    placements = [row[3] for row in analysis.PLACEMENTS]
    cleaners = [row[2] for row in analysis.CLEANERS]
    for system in ("DGAI", "OdinANN"):
        for realization in (1, 2, 3):
            for capacity in (65536, 262144):
                for spares in (2, 8):
                    for placement in placements:
                        for cleaner in cleaners:
                            cycles = 0
                            host_wa = Fraction(1)
                            rising = False
                            # Stable high-pressure Canonical group.
                            if (system, capacity, spares, placement, cleaner) == (
                                    "OdinANN", 65536, 2, "Canonical", "GreedyValidFraction"):
                                cycles = 8
                                host_wa = (Fraction(3, 2) if realization != 2 else Fraction(5, 4))
                            # Eligible RoleSeparated group with exact nonzero trend; together
                            # with Canonical this produces a realization direction flip.
                            if (system, capacity, spares, placement, cleaner) == (
                                    "OdinANN", 65536, 2, "RoleSeparated", "GreedyValidFraction"):
                                cycles = 8
                                host_wa = Fraction(4, 3)
                                rising = True
                            # Exactly one realization owns this reclaim signal.
                            if (system, capacity, spares, placement, cleaner) == (
                                    "OdinANN", 262144, 8, "RandomPacking-2026071901", "OracleMinCopy"):
                                cycles = 8 if realization == 1 else 2
                            # One DGAI realization jumps from ZERO to >=8 cycle regime.
                            if (system, capacity, spares, placement, cleaner) == (
                                    "DGAI", 65536, 8, "Canonical", "GreedyValidFraction"):
                                cycles = 8 if realization == 3 else 0
                            records.append(record(system, realization, capacity, spares,
                                                  placement, cleaner, cycles, host_wa, rising))
    return records


class AnalyzeEndpointResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = json.loads((HERE / "preregistration.json").read_text())

    def test_exact_w1_and_normalization(self) -> None:
        self.assertEqual(analysis.exact_w1([0, 2], [1]), Fraction(1))
        self.assertEqual(analysis.normalized_w1([0, 2], [1]), Fraction(1))
        self.assertIsNone(analysis.exact_w1([], [1]))
        self.assertEqual(analysis.normalized_w1([0], [0]), Fraction(0))

    def test_no_trend_and_nonstationary_exact_lines(self) -> None:
        bootstrap = self.prereg["trend"]["bootstrap"]
        no_trend = analysis.trend_result(
            [Fraction(3, 2)] * 4, [5, 6, 7, 8], "cfg", "trace", "HostWA_cycle", bootstrap)
        nonstationary = analysis.trend_result(
            [Fraction(1), Fraction(2), Fraction(3), Fraction(4)], [5, 6, 7, 8],
            "cfg", "trace", "relocated_pages_cycle", bootstrap)
        self.assertEqual(no_trend["trend_label"], "NO-DETECTED-SEQUENCE-TREND")
        self.assertEqual(no_trend["theil_sen_slope"], "0/1")
        self.assertEqual(nonstationary["trend_label"], "NONSTATIONARY")
        self.assertEqual(nonstationary["theil_sen_slope"], "1/1")
        self.assertEqual(no_trend["resamples"], 100000)

    def test_general_moving_block_bootstrap_path(self) -> None:
        x = [1, 2, 3, 4, 5, 6]
        y = [Fraction(1), Fraction(3), Fraction(2), Fraction(5), Fraction(4), Fraction(8)]
        slope, intercept = analysis.exact_theil_sen(x, y)
        low, high, block, method = analysis.bootstrap_ci(x, y, slope, intercept, 719, 257)
        self.assertLessEqual(low, high)
        self.assertEqual(block, 2)
        self.assertEqual(method, "float64-all-pair-type7-percentile")

    def test_matrix_facts_cover_flip_single_signal_and_dgai_regime(self) -> None:
        records = synthetic_matrix()
        self.assertEqual(len(records), 288)
        groups = analysis.cross_realization(records)
        directions = analysis.placement_directions(records)
        trend_rows = analysis.trends(records, self.prereg)
        facts = analysis.decision_facts(records, groups, directions, trend_rows)
        self.assertIn(
            "OdinANN:z65536:h2:GreedyValidFraction",
            facts["HOLD-PLACEMENT-DOMINATED"]["canonical_role_opposite_direction_flip_ids"],
        )
        self.assertIn(
            "OdinANN:z262144:h8:RandomPacking-2026071901:OracleMinCopy",
            facts["PASS-RECLAIM-SIGNAL"]["single_odin_trace_signal_groups"],
        )
        self.assertIn(
            "DGAI:z65536:h8:Canonical:GreedyValidFraction",
            facts["HOLD-PLACEMENT-DOMINATED"]["dgai_multi_realization_regime_inconsistency_ids"],
        )
        self.assertTrue(facts["PASS-RECLAIM-SIGNAL"][
            "canonical_or_role_any_run_ge_8_and_all_three_metrics_no_trend"])
        labels = {metric["trend_label"] for row in trend_rows for metric in row["metrics"]}
        self.assertEqual(labels, {"NO-DETECTED-SEQUENCE-TREND", "NONSTATIONARY"})
        self.assertIsNone(facts["automatic_final_verdict"])

    def test_strict_six_by_48_reader_and_no_timestamp_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="z0b-analysis-selftest-") as temporary:
            campaign = Path(temporary)
            schedule = {"schema": "zns-ann-z0b-endpoint-schedule-v1", "runs": []}
            for system, stem in (("DGAI", "dgai-50k"), ("OdinANN", "odinann-400k")):
                for realization in (1, 2, 3):
                    trace = f"{stem}-r{realization}"
                    schedule["runs"].append({"label": trace, "system": system,
                                             "realization": realization})
                    result = campaign / "results" / trace
                    for directory in ("replay", "reference", "comparison"):
                        (result / directory).mkdir(parents=True, exist_ok=True)
                    (result / "final_status.json").write_text(json.dumps(
                        {"status": "pass", "configuration_count": 48}))
                    (result / "closure.json").write_text(json.dumps(
                        {"status": "pass", "temporal_fields_consumed": False,
                         "checks": {"synthetic": True}}))
                    (result / "matrix_crosscheck.json").write_text(json.dumps(
                        {"status": "pass", "configuration_count": 48,
                         "exact_replay_reference_match": True, "temporal_fields_used": False}))
                    for blocks in (65536, 262144):
                        for spares in (2, 8):
                            for placement_id, native_placement, seed, _placement in analysis.PLACEMENTS:
                                for cleaner_id, native_cleaner, _cleaner in analysis.CLEANERS:
                                    name = f"z{blocks}-h{spares}-{placement_id}-{cleaner_id}.json"
                                    common = {
                                        "status": "pass", "sequence_only": True,
                                        "temporal_fields_used": False, "placement": native_placement,
                                        "random_seed": seed, "cleaner": native_cleaner,
                                        "initial_image": {"logical_bytes": 4096, "allocated_bytes": 4096,
                                                          "page_count": 1},
                                        "bytes": {"application_returned_bytes": 4096,
                                                  "normalized_fragment_bytes": 4096,
                                                  "allocated_append_bytes": 4096,
                                                  "replacement_rmw_read_bytes": 0,
                                                  "new_page_zero_fill_bytes": 0,
                                                  "relocation_allocated_bytes": 0},
                                        "host_wa_fraction": "1/1", "reset_count": 0,
                                        "complete_cycle_count": 0,
                                        "tail": {"complete_cycle": False, "allocated_new_blocks": 1,
                                                 "allocated_append_bytes": 4096,
                                                 "application_returned_bytes": 4096},
                                        "victim_sequence": [], "cycles": [],
                                        "final_state_sha256": "00" * 32,
                                        "transition_rolling_sha256": "11" * 32,
                                    }
                                    main = {"schema": "zns-ann-z0b-native-replay-v1",
                                            "engine": "main", **common,
                                            "comparable_result": common}
                                    reference = {"schema": "zns-ann-z0b-native-reference-v1",
                                                 "engine": "reference", **common,
                                                 "comparable_result": common}
                                    main_path = result / "replay" / name
                                    reference_path = result / "reference" / name
                                    main_path.write_text(json.dumps(main, sort_keys=True))
                                    reference_path.write_text(json.dumps(reference, sort_keys=True))
                                    comparison = {
                                        "schema": "zns-ann-z0b-native-exact-comparison-v1",
                                        "status": "pass", "primary_equals_reference": True,
                                        "main_sha256": analysis.sha256_path(main_path),
                                        "reference_sha256": analysis.sha256_path(reference_path),
                                    }
                                    (result / "comparison" / name).write_text(json.dumps(comparison))
            (campaign / "schedule.json").write_text(json.dumps(schedule, sort_keys=True))
            output = campaign / "analysis.json"
            answer = analysis.analyze(argparse.Namespace(
                campaign_root=campaign, preregistration=HERE / "preregistration.json", output=output))
            second_output = campaign / "analysis-second.json"
            analysis.analyze(argparse.Namespace(
                campaign_root=campaign, preregistration=HERE / "preregistration.json",
                output=second_output))
            document = json.loads(output.read_text())
            self.assertEqual(output.read_bytes(), second_output.read_bytes())
            self.assertEqual(answer["configurations"], 288)
            self.assertEqual(document["main_reference_exact_pass_count"], 288)
            self.assertFalse(document["timestamps_emitted"])
            serialized = output.read_text().lower()
            self.assertNotIn("timestamp_ns", serialized)
            self.assertNotIn('"timestamps":', serialized)
            self.assertNotIn('"utc":', serialized)
            self.assertTrue(document["decision_facts"]["KILL-NO-RECLAIM-SIGNAL"][
                "odin_all_nonoracle_runs_below_8_cycles"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
