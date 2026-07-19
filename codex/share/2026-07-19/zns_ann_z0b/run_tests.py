#!/usr/bin/env python3
"""Cycle-positive differential tests for the bounded Z0B simulator pair."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from bounded_reference import BoundedReference
from bounded_sim import BoundedSimulator


HERE = Path(__file__).resolve().parent


def page(key: str, role: str = "graph") -> dict[str, str]:
    return {"key": key, "role": role}


def write(seq: int, key: str, *, page_index: int = 0, role: str = "graph") -> dict[str, Any]:
    return {
        "op": "write",
        "global_seq": seq,
        "page_index_within_request": page_index,
        "key": key,
        "role": role,
        "page_bytes": 4096,
        "update_or_replacement_id": seq,
        "batch_id": (seq - 1) // 2 + 1,
    }


def truncate(seq: int, keys: list[str]) -> dict[str, Any]:
    return {
        "op": "truncate",
        "global_seq": seq,
        "page_index_within_request": -1,
        "invalidated_keys": keys,
        "update_or_replacement_id": seq,
        "batch_id": (seq - 1) // 2 + 1,
    }


def one_full_zone(capacity: int, spares: int) -> dict[str, Any]:
    keys = [chr(ord("a") + index) for index in range(capacity)]
    return {
        "config": {
            "logical_block_size_bytes": 4096,
            "zone_capacity_blocks": capacity,
            "number_of_zones": 1 + spares,
            "host_spare_zones": spares,
        },
        "initial_zones": [
            {"zone_id": 0, "state": "FULL", "pages": [page(key) for key in keys]}
        ],
    }


def run_lockstep(spec: dict[str, Any], events: list[dict[str, Any]], policy: str):
    primary = BoundedSimulator(spec, policy)
    reference = BoundedReference(spec, policy)
    if primary.state_view() != reference.state_view():
        raise AssertionError("initial primary/reference mismatch")
    for ordinal, event in enumerate(events, 1):
        primary.apply(event)
        reference.apply(event)
        if primary.state_view() != reference.state_view():
            raise AssertionError(f"primary/reference mismatch after event {ordinal}")
    return primary, reference


class BoundedZ0BTests(unittest.TestCase):
    def test_preregistration_is_frozen_and_matrix_is_288(self) -> None:
        prereg = json.loads((HERE / "preregistration.json").read_text())
        self.assertEqual(prereg["matrix"]["total_configurations"], 288)
        self.assertEqual(prereg["placement"]["random_packing"]["seeds"], [2026071901, 2026071902, 2026071903])
        self.assertEqual(prereg["placement"]["offline_hot_cold_oracle"]["sort"], "descending rewrite_count")
        self.assertEqual(prereg["trend"]["sample"], "last ceil(C/2) complete cycles")
        self.assertEqual(prereg["trend"]["bootstrap"]["resamples"], 100000)
        self.assertIsNone(
            prereg["cross_realization"]["relocated_page_distribution_distance"]["threshold"]
        )

    def test_initial_free_pool_spare_two_vs_eight_changes_gc_onset(self) -> None:
        onset = {}
        for spares, expected in ((2, 3), (8, 15)):
            spec = one_full_zone(2, spares)
            events = [write(1, "a")]
            events.extend(write(seq, f"new-{seq}") for seq in range(2, expected + 1))
            primary, _ = run_lockstep(spec, events, "GreedyValidFraction")
            self.assertEqual(primary.reset_count, 1)
            self.assertEqual(primary.cycles[0]["gc_trigger"]["event_ordinal"], expected)
            onset[spares] = primary.cycles[0]["gc_trigger"]["event_ordinal"]
        self.assertEqual(onset, {2: 3, 8: 15})

    def test_role_separated_partial_closed_zone_is_not_reused_as_head(self) -> None:
        spec = {
            "config": {
                "logical_block_size_bytes": 4096,
                "zone_capacity_blocks": 4,
                "number_of_zones": 4,
                "host_spare_zones": 2,
            },
            "initial_zones": [
                {"zone_id": 0, "state": "CLOSED", "pages": [page("role-a", "A")]},
                {
                    "zone_id": 1,
                    "state": "CLOSED",
                    "append_head": True,
                    "pages": [page("role-b", "B")],
                },
            ],
        }
        primary, _ = run_lockstep(spec, [write(1, "b-new", role="B")], "GreedyValidFraction")
        self.assertEqual(primary.zones[0].state, "CLOSED")
        self.assertEqual(primary.zones[0].wp, 1)
        self.assertEqual(primary.zones[1].state, "OPEN")
        self.assertEqual(primary.zones[1].wp, 2)
        self.assertEqual(primary.mapping["b-new"][1], 1)

    def test_two_pages_can_share_global_seq_with_page_order(self) -> None:
        spec = one_full_zone(4, 2)
        events = [
            write(7, "page-x", page_index=0),
            write(7, "page-y", page_index=1),
        ]
        primary, _ = run_lockstep(spec, events, "GreedyValidFraction")
        self.assertEqual(primary.last_coord, (7, 1))
        self.assertEqual(primary.new_blocks, 2)
        self.assertIn("page-x", primary.mapping)
        self.assertIn("page-y", primary.mapping)

    def test_reference_stays_exact_through_gc_then_truncate_relocated_page(self) -> None:
        spec = one_full_zone(2, 2)
        events = [
            write(1, "a"),
            write(2, "new-2"),
            write(3, "new-3"),
            truncate(4, ["b"]),
        ]
        primary, reference = run_lockstep(spec, events, "GreedyValidFraction")
        self.assertEqual(primary.reset_count, 1)
        self.assertEqual(reference.resets, 1)
        self.assertNotIn("b", primary.mapping)
        self.assertNotIn("b", reference.locations())
        relocated_b = [
            slot
            for zone in primary.zones
            for slot in zone.slots
            if slot.key == "b" and slot.kind == "RELOC"
        ]
        self.assertEqual(len(relocated_b), 1)
        self.assertFalse(relocated_b[0].valid)

    def test_tail_after_last_reset_is_not_a_complete_cycle(self) -> None:
        spec = one_full_zone(2, 2)
        events = [write(1, "a"), write(2, "new-2"), write(3, "new-3")]
        primary, _ = run_lockstep(spec, events, "GreedyValidFraction")
        self.assertEqual(len(primary.cycles), 1)
        self.assertEqual(primary.cycles[0]["allocated_new_blocks"], 2)
        self.assertEqual(primary.tail()["allocated_new_blocks"], 1)
        self.assertFalse(primary.tail()["complete_cycle"])

    def test_two_cleaners_have_identical_victim_and_cycle_sequence(self) -> None:
        spec = one_full_zone(3, 2)
        events = [
            write(1, "a"),
            write(2, "b"),
            write(3, "c"),
            write(4, "a"),
            write(5, "b"),
            write(6, "c"),
            write(7, "a"),
        ]
        greedy, _ = run_lockstep(spec, events, "GreedyValidFraction")
        oracle, _ = run_lockstep(spec, events, "OracleMinCopy")
        self.assertEqual(greedy.victim_sequence, [0, 1])
        self.assertEqual(greedy.victim_sequence, oracle.victim_sequence)
        self.assertEqual(greedy.cycles, oracle.cycles)
        self.assertEqual(greedy.state_view(), oracle.state_view())


if __name__ == "__main__":
    unittest.main(verbosity=2)
