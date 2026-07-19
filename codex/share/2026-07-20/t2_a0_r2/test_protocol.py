#!/usr/bin/env python3
import copy
import json
import unittest
from pathlib import Path

import experiment as exp


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = HERE.parent / "config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = exp.make_workloads(CONFIG, sanity=True)["instances"][0]

    def test_canonical_determinism(self):
        value = {"b": [2, 1], "a": {"z": 3}}
        self.assertEqual(exp.canonical_bytes(value), exp.canonical_bytes(copy.deepcopy(value)))
        self.assertEqual(exp.digest(value), exp.digest(copy.deepcopy(value)))

    def test_four_task_operators_are_distinct(self):
        operators = [exp.task_operator(family) for family in CONFIG["formal"]["workload_families"]]
        self.assertEqual(len({exp.digest(operator) for operator in operators}), 4)

    def test_resize_preserves_durable_memory(self):
        for policy in exp.POLICIES:
            state = exp.initial_state(self.workload["instance_id"], policy, CONFIG)
            before_live = exp.digest(exp.live_durable_view(state))
            before_audit = exp.digest(state["versions"])
            exp.resize(state, 3)
            self.assertEqual(len(state["active"]), 3)
            exp.resize(state, 12)
            self.assertEqual(len(state["active"]), 12)
            self.assertEqual(before_live, exp.digest(exp.live_durable_view(state)))
            self.assertEqual(before_audit, exp.digest(state["versions"]))

    def test_fork_deep_copy(self):
        state, _ = exp.run_prefix(self.workload, "LRU", CONFIG)
        fork = exp.canonical_bytes(state)
        left = json.loads(fork)
        right = json.loads(fork)
        left["head"]["m00"]["semantic_token"] ^= 1
        self.assertEqual(exp.canonical_bytes(right), fork)

    def test_action_derived_head_changes_future_query(self):
        state, _ = exp.run_prefix(self.workload, "LRU", CONFIG)
        event = self.workload["low"][0]
        before = exp.query_for(state, event, "closed_loop")
        mid = event["logical_memory_id"]
        state["head"][mid]["semantic_token"] = (state["head"][mid]["semantic_token"] + 1) % 257
        after = exp.query_for(state, event, "closed_loop")
        self.assertNotEqual(before["semantic_hash"], after["semantic_hash"])

    def test_write_disabled_removes_only_durable_edge(self):
        state, _ = exp.run_prefix(self.workload, "LRU", CONFIG)
        event = self.workload["low"][0]
        durable_before = exp.digest(exp.live_durable_view(state))
        query_before = exp.query_for(state, event, "write_disabled")
        exp.execute_step(state, event, "write_disabled", "A", "TEST-FORK")
        query_after = exp.query_for(state, event, "write_disabled")
        self.assertEqual(durable_before, exp.digest(exp.live_durable_view(state)))
        self.assertNotEqual(query_before["semantic_hash"], query_after["semantic_hash"])

    def test_live_semantics_excludes_lineage(self):
        state, _ = exp.run_prefix(self.workload, "LRU", CONFIG)
        before = exp.digest(exp.live_durable_view(state))
        current = state["latest"]["m00"]
        state["versions"][current]["created_by_action"] = "AUDIT-ONLY-MUTATION"
        self.assertEqual(before, exp.digest(exp.live_durable_view(state)))

    def test_four_model_sanity_invariants(self):
        triplet = CONFIG["sanity"]["capacity_triplet"]
        evaluation_steps = CONFIG["sanity"]["evaluation_steps"]
        for policy in exp.POLICIES:
            prefix, _ = exp.run_prefix(self.workload, policy, CONFIG)
            model_pairs = {}
            for model in exp.MODELS:
                pair, logs_a, logs_b = exp.run_one_cell(
                    prefix,
                    self.workload,
                    policy,
                    triplet,
                    model,
                    evaluation_steps,
                    check_order=True,
                )
                model_pairs[model] = pair
                self.assertTrue(all(not row["memory_deletes"] for row in logs_a + logs_b))
                self.assertTrue(
                    all(
                        len(row["active_memory_ids"]) == triplet[2]
                        for row in logs_a + logs_b
                        if row["phase"] == "evaluation"
                    )
                )
            self.assertEqual(model_pairs["open_loop_query"]["metrics"]["Q"], 0)
            self.assertEqual(model_pairs["write_disabled"]["metrics"]["M"], 0)
            self.assertEqual(model_pairs["transparent_retrieval"]["metrics"]["D"], 0)
            self.assertIsNotNone(model_pairs["closed_loop"]["witness"])
            self.assertGreaterEqual(len(model_pairs["closed_loop"]["witness"]["lineage_path_a"]), 2)
            self.assertGreaterEqual(len(model_pairs["closed_loop"]["witness"]["lineage_path_b"]), 2)
            self.assertIn(
                "evaluation_cumulative_outcome_delta_abs",
                model_pairs["closed_loop"]["metrics"],
            )


if __name__ == "__main__":
    unittest.main()
