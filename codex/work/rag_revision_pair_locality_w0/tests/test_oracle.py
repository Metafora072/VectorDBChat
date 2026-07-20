from __future__ import annotations

import unittest

import numpy as np

from w0prep.oracle import (
    TopKRow,
    TopKTable,
    build_universe_oracle,
    evaluate_pair_neighborhood,
    exact_rank,
    exhaustive_topk_queries,
    filter_fixed_reference,
    stable_candidate_order,
)


def _unit(angle: float) -> np.ndarray:
    return np.asarray([np.cos(angle), np.sin(angle)], dtype=np.float32)


def _full_reference(
    queries: np.ndarray,
    query_ids: list[str],
    corpus: np.ndarray,
    corpus_ids: list[str],
    k: int,
    *,
    exclude_self: bool,
) -> tuple[np.ndarray, np.ndarray]:
    scores = queries @ corpus.T
    output_ids: list[list[str]] = []
    output_scores: list[list[float]] = []
    for query_id, row in zip(query_ids, scores, strict=True):
        eligible = [i for i, item in enumerate(corpus_ids) if not (exclude_self and item == query_id)]
        eligible.sort(key=lambda i: (-float(row[i]), corpus_ids[i].encode("utf-8")))
        chosen = eligible[:k]
        output_ids.append([corpus_ids[i] for i in chosen])
        output_scores.append([float(row[i]) for i in chosen])
    return np.asarray(output_ids), np.asarray(output_scores, dtype=np.float32)


class OracleTests(unittest.TestCase):
    def test_blockwise_matches_independent_full_stable_sort_with_duplicate_vectors(self) -> None:
        ids = [f"id-{i:03d}" for i in range(12)]
        corpus = np.stack([_unit(0.0), _unit(0.0), *(_unit(i / 10) for i in range(2, 12))])
        queries = np.stack([_unit(0.0), _unit(0.53), _unit(1.1)])
        query_ids = ["query-a", "query-b", "query-c"]

        actual = exhaustive_topk_queries(
            queries,
            query_ids,
            corpus,
            ids,
            k=7,
            query_block_size=2,
            corpus_block_size=3,
        )
        expected_ids, expected_scores = _full_reference(
            queries, query_ids, corpus, ids, 7, exclude_self=False
        )
        np.testing.assert_array_equal(actual.neighbor_ids, expected_ids)
        np.testing.assert_array_equal(actual.scores, expected_scores)

    def test_exact_top321_matches_full_sort(self) -> None:
        ids = [f"candidate-{i:03d}" for i in range(330)]
        corpus = np.stack([_unit((i % 113) / 150.0) for i in range(330)])
        queries = np.stack([_unit(0.17), _unit(0.51)])
        query_ids = ["query-left", "query-right"]
        actual = exhaustive_topk_queries(
            queries,
            query_ids,
            corpus,
            ids,
            k=321,
            query_block_size=1,
            corpus_block_size=127,
        )
        expected_ids, expected_scores = _full_reference(
            queries, query_ids, corpus, ids, 321, exclude_self=False
        )
        np.testing.assert_array_equal(actual.neighbor_ids, expected_ids)
        np.testing.assert_array_equal(actual.scores, expected_scores)

    def test_self_exclusion_and_small_universe_size_contract(self) -> None:
        ids = ["a", "b", "c", "d"]
        embeddings = np.stack([_unit(0.0), _unit(0.2), _unit(0.4), _unit(0.6)])
        actual = build_universe_oracle(
            embeddings,
            ids,
            expected_universe_size=4,
            k=3,
            query_block_size=2,
            corpus_block_size=2,
        )
        self.assertTrue(all(query_id not in actual.row(query_id).neighbor_ids for query_id in ids))
        with self.assertRaisesRegex(ValueError, "exactly 5"):
            build_universe_oracle(embeddings, ids, expected_universe_size=5, k=3)

    def test_tie_exactly_at_rank_64_is_resolved_by_id_not_input_or_block_order(self) -> None:
        query = np.asarray([[1.0, 0.0]], dtype=np.float32)
        # 63 strictly better scores, then four vectors tied at the top-64 boundary.
        better = [_unit(0.001 * (i + 1)) for i in range(63)]
        tied = [_unit(0.2)] * 4
        corpus = np.stack([*better, *tied])
        ids = [f"better-{i:03d}" for i in range(63)] + ["tie-d", "tie-b", "tie-c", "tie-a"]
        actual = exhaustive_topk_queries(
            query,
            ["query"],
            corpus,
            ids,
            k=64,
            corpus_block_size=65,
        )
        self.assertEqual(actual.row("query").neighbor_ids[-1], "tie-a")

    def test_equal_scores_across_corpus_block_boundary_use_utf8_id_order(self) -> None:
        query = np.asarray([[1.0, 0.0]], dtype=np.float32)
        corpus = np.stack([_unit(0.0), _unit(0.4), _unit(0.4), _unit(0.7)])
        ids = ["best", "z-boundary", "a-next-block", "last"]
        actual = exhaustive_topk_queries(
            query, ["q"], corpus, ids, k=3, corpus_block_size=2
        )
        self.assertEqual(actual.row("q").neighbor_ids, ("best", "a-next-block", "z-boundary"))

    def test_pair_specific_fixed_reference_filter_preserves_oracle_order(self) -> None:
        row = TopKRow(
            "q",
            tuple(f"id-{i}" for i in range(20)),
            tuple(float(20 - i) for i in range(20)),
        )
        membership = [f"id-{i}" for i in range(1, 20) if i != 4][:16]
        selected = filter_fixed_reference(
            row,
            membership,
            r=16,
            expected_membership_size=16,
        )
        self.assertEqual(selected.neighbor_ids[:4], ("id-1", "id-2", "id-3", "id-5"))
        self.assertEqual(selected.scores[:4], (19.0, 18.0, 17.0, 15.0))
        with self.assertRaisesRegex(ValueError, "fewer than required"):
            filter_fixed_reference(
                row,
                [*(f"id-{i}" for i in range(15)), "outside"],
                r=16,
                expected_membership_size=16,
            )

    def test_top321_can_skip_257_nonmembers_and_still_return_top64(self) -> None:
        nonmembers = tuple(f"reserve-{i:03d}" for i in range(257))
        members = tuple(f"member-{i:03d}" for i in range(64))
        row = TopKRow(
            "external-query",
            nonmembers + members,
            tuple(float(321 - i) for i in range(321)),
        )
        selected = filter_fixed_reference(
            row,
            members,
            r=64,
            expected_membership_size=64,
        )
        self.assertEqual(selected.neighbor_ids, members)

    def test_stable_candidate_order_is_first_occurrence_deduplicated(self) -> None:
        actual = stable_candidate_order(
            "anchor",
            ["a", "b"],
            {"a": ["b", "c", "anchor"], "b": ["d", "a"]},
        )
        self.assertEqual(actual, ("anchor", "a", "b", "c", "d"))

    def test_pair_metrics_jaccard_coverage_and_lossless_hit_positions(self) -> None:
        # Radius is fixed to 16 by the production contract.  A 20-member synthetic
        # reference keeps the test small while exercising the exact same path.
        members = tuple(f"n-{i:02d}" for i in range(20))
        scores = tuple(float(100 - i) for i in range(20))
        anchor_neighbors = members[:16]
        target_neighbors = members[8:20] + members[:4]
        anchor_row = TopKRow("anchor", anchor_neighbors + members[16:], scores)
        target_row = TopKRow("target", target_neighbors + members[4:8], scores)

        first_hop_rows = []
        for i, _query_id in enumerate(members):
            rotation = members[i + 1 :] + members[: i + 1]
            first_hop_rows.append(rotation)
        table = TopKTable(
            members,
            np.asarray(first_hop_rows),
            np.tile(np.arange(20, 0, -1, dtype=np.float32), (20, 1)),
        )

        metrics = evaluate_pair_neighborhood(
            anchor_row=anchor_row,
            target_row=target_row,
            universe_rows=table,
            fixed_reference_ids=members,
            r=16,
            expected_membership_size=20,
        )
        self.assertEqual(metrics.intersection_count, 12)
        self.assertEqual(metrics.union_count, 20)
        self.assertAlmostEqual(metrics.jaccard, 0.6)
        self.assertAlmostEqual(metrics.coverage1, 0.75)
        self.assertLessEqual(metrics.candidate_length, 1 + 16 + 16 * 16)
        self.assertEqual(tuple(hit.target_id for hit in metrics.target_hits), target_neighbors)
        self.assertAlmostEqual(metrics.coverage2, metrics.recall_at(metrics.candidate_length))
        self.assertEqual(metrics.recall_at(0), 0.0)
        positions = [hit.position for hit in metrics.target_hits if hit.position is not None]
        self.assertEqual(
            positions,
            [
                metrics.candidate_ids.index(hit.target_id) + 1
                for hit in metrics.target_hits
                if hit.position is not None
            ],
        )

    def test_exact_rank_uses_id_tie_break_and_is_one_based(self) -> None:
        query = np.asarray([1.0, 0.0], dtype=np.float32)
        candidates = np.stack([_unit(0.2), _unit(0.2), _unit(0.1)])
        ids = ["tie-z", "tie-a", "best"]
        self.assertEqual(exact_rank(query, candidates, ids, "best", expected_candidate_size=3), 1)
        self.assertEqual(exact_rank(query, candidates, ids, "tie-a", expected_candidate_size=3), 2)
        self.assertEqual(exact_rank(query, candidates, ids, "tie-z", expected_candidate_size=3), 3)


if __name__ == "__main__":
    unittest.main()
