from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from w0prep.controls import (
    MISSING_NO_CANDIDATE,
    SelectedRealPair,
    UniverseItem,
    generate_control_b,
)


def _unit(x: float, y: float) -> np.ndarray:
    value = np.asarray([x, y], dtype=np.float32)
    return value / np.linalg.norm(value)


class ControlBTests(unittest.TestCase):
    def _base(self):
        items = [
            UniverseItem("core-z", "source-a", "other/z", "payload-z"),
            UniverseItem("core-a", "source-a", "other/a", "payload-a"),
            UniverseItem("core-same-doc", "source-a", "doc/real", "payload-same"),
            UniverseItem("reserve-first", "source-a", "reserve/first", "payload-r1"),
            UniverseItem("reserve-second", "source-a", "reserve/second", "payload-r2"),
        ]
        embeddings = np.stack(
            [
                _unit(0.8, 0.6),
                _unit(0.8, 0.6),
                _unit(0.8, 0.6),
                _unit(0.0, 1.0),
                _unit(-1.0, 0.0),
            ]
        )
        core = {"source-a": ["core-z", "core-a", "core-same-doc"]}
        reserve = {"source-a": ["reserve-first", "reserve-second"]}
        return items, embeddings, core, reserve

    def test_distance_match_tie_uses_id_and_records_first_reserve(self) -> None:
        items, embeddings, core, reserve = self._base()
        pair = SelectedRealPair("pair-1", "source-a", "doc/real")
        result = generate_control_b(
            model="minilm",
            selected_pairs=[pair],
            old_embeddings=np.stack([_unit(0.8, 0.6)]),
            new_embeddings=np.stack([_unit(1.0, 0.0)]),
            universe_items=items,
            universe_embeddings=embeddings,
            core_ids_by_source=core,
            reserve_ids_by_source=reserve,
            expected_dimension=2,
            expected_universe_size=5,
            expected_core_size=3,
            expected_reserve_size=2,
        )
        self.assertEqual(result.complete_count, 1)
        self.assertEqual(result.missing_count, 0)
        self.assertEqual(
            result.counts_by_source,
            {"source-a": {"complete": 1, "missing": 0, "total": 1}},
        )
        row = result.rows[0]
        self.assertEqual(row["candidate_id"], "core-a")
        self.assertEqual(row["candidate_document_path"], "other/a")
        self.assertEqual(row["first_reserve_replacement_id"], "reserve-first")
        self.assertEqual(row["absolute_distance_error"], 0.0)

    def test_model_specific_embeddings_can_select_different_candidates(self) -> None:
        items, _embeddings, core, reserve = self._base()
        pair = SelectedRealPair("pair-1", "source-a", "doc/real")
        old = np.stack([_unit(0.8, 0.6)])
        new = np.stack([_unit(1.0, 0.0)])
        minilm_universe = np.stack(
            [_unit(0.8, 0.6), _unit(0.1, 0.995), _unit(0.8, 0.6), _unit(0, 1), _unit(-1, 0)]
        )
        nomic_universe = np.stack(
            [_unit(0.1, 0.995), _unit(0.8, 0.6), _unit(0.8, 0.6), _unit(0, 1), _unit(-1, 0)]
        )

        def run(model: str, universe: np.ndarray):
            return generate_control_b(
                model=model,
                selected_pairs=[pair],
                old_embeddings=old,
                new_embeddings=new,
                universe_items=items,
                universe_embeddings=universe,
                core_ids_by_source=core,
                reserve_ids_by_source=reserve,
                expected_dimension=2,
                expected_universe_size=5,
                expected_core_size=3,
                expected_reserve_size=2,
            )

        self.assertEqual(run("minilm", minilm_universe).rows[0]["candidate_id"], "core-z")
        self.assertEqual(run("nomic", nomic_universe).rows[0]["candidate_id"], "core-a")

    def test_payload_multiplicity_is_over_full_universe_not_only_core(self) -> None:
        items, embeddings, core, reserve = self._base()
        items[3] = UniverseItem("reserve-first", "source-a", "reserve/first", "payload-a")
        # core-a is the exact geometric match but is ineligible because the same
        # payload occurs in reserve; core-z must be chosen without a fallback rule.
        result = generate_control_b(
            model="minilm",
            selected_pairs=[SelectedRealPair("pair-1", "source-a", "doc/real")],
            old_embeddings=np.stack([_unit(0.8, 0.6)]),
            new_embeddings=np.stack([_unit(1.0, 0.0)]),
            universe_items=items,
            universe_embeddings=embeddings,
            core_ids_by_source=core,
            reserve_ids_by_source=reserve,
            expected_dimension=2,
            expected_universe_size=5,
            expected_core_size=3,
            expected_reserve_size=2,
        )
        self.assertEqual(result.rows[0]["candidate_id"], "core-z")

    def test_empty_eligible_pool_emits_missing_without_metric_fallback(self) -> None:
        items, embeddings, core, reserve = self._base()
        items[0] = UniverseItem("core-z", "source-a", "doc/real", "payload-z")
        items[1] = UniverseItem("core-a", "source-a", "doc/real", "payload-a")
        result = generate_control_b(
            model="nomic",
            selected_pairs=[SelectedRealPair("pair-missing", "source-a", "doc/real")],
            old_embeddings=np.stack([_unit(0.8, 0.6)]),
            new_embeddings=np.stack([_unit(1.0, 0.0)]),
            universe_items=items,
            universe_embeddings=embeddings,
            core_ids_by_source=core,
            reserve_ids_by_source=reserve,
            expected_dimension=2,
            expected_universe_size=5,
            expected_core_size=3,
            expected_reserve_size=2,
        )
        self.assertEqual(result.complete_count, 0)
        self.assertEqual(result.missing_count, 1)
        self.assertEqual(result.rows[0]["status"], "MISSING")
        self.assertEqual(result.rows[0]["missing_reason"], MISSING_NO_CANDIDATE)
        self.assertIsNone(result.rows[0]["candidate_id"])

    def test_canonical_jsonl_is_pair_order_independent_and_writable(self) -> None:
        items, embeddings, core, reserve = self._base()
        pairs = [
            SelectedRealPair("pair-z", "source-a", "doc/real"),
            SelectedRealPair("pair-a", "source-a", "doc/another"),
        ]
        old = np.stack([_unit(0.8, 0.6), _unit(0.8, 0.6)])
        new = np.stack([_unit(1.0, 0.0), _unit(1.0, 0.0)])

        def run(pair_rows, old_rows, new_rows):
            return generate_control_b(
                model="minilm",
                selected_pairs=pair_rows,
                old_embeddings=old_rows,
                new_embeddings=new_rows,
                universe_items=items,
                universe_embeddings=embeddings,
                core_ids_by_source=core,
                reserve_ids_by_source=reserve,
                expected_dimension=2,
                expected_universe_size=5,
                expected_core_size=3,
                expected_reserve_size=2,
            )

        forward = run(pairs, old, new)
        reverse = run(list(reversed(pairs)), old[::-1].copy(), new[::-1].copy())
        self.assertEqual(forward.jsonl_bytes, reverse.jsonl_bytes)
        self.assertEqual(forward.jsonl_sha256, reverse.jsonl_sha256)
        decoded = [json.loads(line) for line in forward.jsonl_bytes.splitlines()]
        self.assertEqual([row["pair_id"] for row in decoded], ["pair-a", "pair-z"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "control_b.jsonl"
            forward.write_jsonl(output)
            self.assertEqual(output.read_bytes(), forward.jsonl_bytes)


if __name__ == "__main__":
    unittest.main()
