"""Exact fixed-reference neighborhood oracle for the W0 preparation gate.

The implementation deliberately uses exhaustive matrix multiplication and a
full lexicographic sort at every block merge.  In particular, ``argpartition``
is never used: it cannot select the correct members when a score tie crosses
the truncation boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

import numpy as np


ORACLE_UNIVERSE_SIZE = 8_448
FIXED_REFERENCE_SIZE = 8_192
RANK_CANDIDATE_SIZE = 8_193
ORACLE_TOP_K = 321
QUERY_BLOCK_SIZE = 256
CORPUS_BLOCK_SIZE = 4_096
ALLOWED_RADII = frozenset({16, 32, 64})


def _validated_ids(ids: Sequence[str], *, name: str) -> tuple[str, ...]:
    result = tuple(ids)
    if not result:
        raise ValueError(f"{name} must not be empty")
    if any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must be unique")
    return result


def _validated_embeddings(
    embeddings: np.ndarray,
    ids: Sequence[str],
    *,
    name: str,
    require_normalized: bool,
) -> np.ndarray:
    array = np.asarray(embeddings)
    if array.dtype != np.float32:
        raise TypeError(f"{name} must have dtype float32")
    if array.ndim != 2 or array.shape[0] != len(ids) or array.shape[1] == 0:
        raise ValueError(f"{name} must have shape (len(ids), positive_dimension)")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    if require_normalized:
        norms = np.linalg.norm(array, axis=1)
        if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
            raise ValueError(f"{name} rows must be L2-normalized")
    return np.ascontiguousarray(array)


def _utf8_sort_keys(ids: Sequence[str]) -> np.ndarray:
    encoded = [item.encode("utf-8") for item in ids]
    width = max(len(item) for item in encoded)
    return np.asarray(encoded, dtype=f"S{width}")


@dataclass(frozen=True)
class TopKRow:
    query_id: str
    neighbor_ids: tuple[str, ...]
    scores: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.neighbor_ids) != len(self.scores):
            raise ValueError("neighbor_ids and scores must have equal length")
        if len(set(self.neighbor_ids)) != len(self.neighbor_ids):
            raise ValueError("neighbor_ids must be unique")


@dataclass
class TopKTable:
    query_ids: tuple[str, ...]
    neighbor_ids: np.ndarray
    scores: np.ndarray
    _row_by_id: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.neighbor_ids.ndim != 2 or self.scores.shape != self.neighbor_ids.shape:
            raise ValueError("neighbor_ids and scores must be equal-shape matrices")
        if self.neighbor_ids.shape[0] != len(self.query_ids):
            raise ValueError("one result row is required per query ID")
        if len(set(self.query_ids)) != len(self.query_ids):
            raise ValueError("query_ids must be unique")
        self._row_by_id = {query_id: i for i, query_id in enumerate(self.query_ids)}

    @property
    def k(self) -> int:
        return int(self.neighbor_ids.shape[1])

    def row(self, query_id: str) -> TopKRow:
        try:
            index = self._row_by_id[query_id]
        except KeyError as exc:
            raise KeyError(f"query ID is absent from oracle table: {query_id}") from exc
        return TopKRow(
            query_id=query_id,
            neighbor_ids=tuple(str(item) for item in self.neighbor_ids[index]),
            scores=tuple(float(item) for item in self.scores[index]),
        )


def exhaustive_topk_queries(
    query_embeddings: np.ndarray,
    query_ids: Sequence[str],
    corpus_embeddings: np.ndarray,
    corpus_ids: Sequence[str],
    *,
    k: int = ORACLE_TOP_K,
    query_block_size: int = QUERY_BLOCK_SIZE,
    corpus_block_size: int = CORPUS_BLOCK_SIZE,
    exclude_matching_ids: bool = False,
    require_normalized: bool = True,
) -> TopKTable:
    """Compute exact cosine-score top-k rows using blockwise exhaustive GEMM.

    Each merge sorts the *entire* previous-top-k plus new corpus block by
    ``(score descending, ID UTF-8 bytes ascending)`` before truncation.
    """

    query_ids = _validated_ids(query_ids, name="query_ids")
    corpus_ids = _validated_ids(corpus_ids, name="corpus_ids")
    queries = _validated_embeddings(
        query_embeddings,
        query_ids,
        name="query_embeddings",
        require_normalized=require_normalized,
    )
    corpus = _validated_embeddings(
        corpus_embeddings,
        corpus_ids,
        name="corpus_embeddings",
        require_normalized=require_normalized,
    )
    if queries.shape[1] != corpus.shape[1]:
        raise ValueError("query and corpus dimensions differ")
    if k <= 0 or query_block_size <= 0 or corpus_block_size <= 0:
        raise ValueError("k and block sizes must be positive")

    query_id_set = set(query_ids)
    possible_self_exclusions = sum(item in query_id_set for item in corpus_ids)
    # This global check is only a quick rejection.  The per-row check below is
    # authoritative when only a subset of query IDs occurs in the corpus.
    if k > len(corpus_ids) - (1 if exclude_matching_ids and possible_self_exclusions else 0):
        raise ValueError("k exceeds the number of eligible corpus members")

    corpus_keys = _utf8_sort_keys(corpus_ids)
    # Object slots retain references to the one corpus-ID pool.  A NumPy U64
    # matrix would consume four bytes per code point (~694 MiB for 8448x321),
    # despite every production ID being an existing 64-byte ASCII string.
    result_ids = np.empty((len(query_ids), k), dtype=object)
    result_scores = np.empty((len(query_ids), k), dtype=np.float32)

    for query_start in range(0, len(query_ids), query_block_size):
        query_end = min(query_start + query_block_size, len(query_ids))
        query_block = queries[query_start:query_end]
        block_query_ids = query_ids[query_start:query_end]
        best_ids: list[np.ndarray] = [np.empty(0, dtype=result_ids.dtype) for _ in block_query_ids]
        best_keys: list[np.ndarray] = [np.empty(0, dtype=corpus_keys.dtype) for _ in block_query_ids]
        best_scores: list[np.ndarray] = [np.empty(0, dtype=np.float32) for _ in block_query_ids]

        for corpus_start in range(0, len(corpus_ids), corpus_block_size):
            corpus_end = min(corpus_start + corpus_block_size, len(corpus_ids))
            scores = query_block @ corpus[corpus_start:corpus_end].T
            block_ids = np.asarray(corpus_ids[corpus_start:corpus_end], dtype=object)
            block_keys = corpus_keys[corpus_start:corpus_end]

            for local_query, query_id in enumerate(block_query_ids):
                row_scores = scores[local_query]
                if exclude_matching_ids:
                    keep = block_ids != query_id
                    row_scores = row_scores[keep]
                    row_ids = block_ids[keep]
                    row_keys = block_keys[keep]
                else:
                    row_ids = block_ids
                    row_keys = block_keys

                merged_scores = np.concatenate((best_scores[local_query], row_scores))
                merged_ids = np.concatenate((best_ids[local_query], row_ids))
                merged_keys = np.concatenate((best_keys[local_query], row_keys))
                order = np.lexsort((merged_keys, -merged_scores))
                take = order[: min(k, len(order))]
                best_scores[local_query] = merged_scores[take]
                best_ids[local_query] = merged_ids[take]
                best_keys[local_query] = merged_keys[take]

        for local_query, query_id in enumerate(block_query_ids):
            if len(best_ids[local_query]) != k:
                raise ValueError(f"query {query_id} has fewer than k eligible corpus members")
            output_row = query_start + local_query
            result_ids[output_row] = best_ids[local_query]
            result_scores[output_row] = best_scores[local_query]

    return TopKTable(query_ids, result_ids, result_scores)


def build_universe_oracle(
    embeddings: np.ndarray,
    canonical_chunk_ids: Sequence[str],
    *,
    expected_universe_size: int = ORACLE_UNIVERSE_SIZE,
    k: int = ORACLE_TOP_K,
    query_block_size: int = QUERY_BLOCK_SIZE,
    corpus_block_size: int = CORPUS_BLOCK_SIZE,
) -> TopKTable:
    """Build the self-excluded exact oracle over the ordered universe."""

    if len(canonical_chunk_ids) != expected_universe_size:
        raise ValueError(
            f"oracle universe must contain exactly {expected_universe_size} items; "
            f"got {len(canonical_chunk_ids)}"
        )
    return exhaustive_topk_queries(
        embeddings,
        canonical_chunk_ids,
        embeddings,
        canonical_chunk_ids,
        k=k,
        query_block_size=query_block_size,
        corpus_block_size=corpus_block_size,
        exclude_matching_ids=True,
    )


def filter_fixed_reference(
    row: TopKRow,
    member_ids: Iterable[str],
    *,
    r: int,
    expected_membership_size: int = FIXED_REFERENCE_SIZE,
) -> TopKRow:
    """Filter a top-321 row to one pair-specific fixed reference corpus."""

    if r not in ALLOWED_RADII:
        raise ValueError(f"r must be one of {sorted(ALLOWED_RADII)}")
    membership = frozenset(member_ids)
    if len(membership) != expected_membership_size:
        raise ValueError(
            f"fixed reference membership must contain exactly {expected_membership_size} "
            f"unique IDs; got {len(membership)}"
        )
    selected = [
        (neighbor_id, score)
        for neighbor_id, score in zip(row.neighbor_ids, row.scores, strict=True)
        if neighbor_id in membership
    ][:r]
    if len(selected) != r:
        raise ValueError(
            f"top-{len(row.neighbor_ids)} row leaves only {len(selected)} fixed-reference "
            f"members, fewer than required top-{r}"
        )
    return TopKRow(
        query_id=row.query_id,
        neighbor_ids=tuple(item[0] for item in selected),
        scores=tuple(item[1] for item in selected),
    )


@dataclass(frozen=True)
class TargetHit:
    target_id: str
    position: int | None


@dataclass(frozen=True)
class PairNeighborhoodMetrics:
    radius: int
    anchor_neighbors: tuple[str, ...]
    target_neighbors: tuple[str, ...]
    intersection_count: int
    union_count: int
    jaccard: float
    coverage1: float
    candidate_ids: tuple[str, ...]
    candidate_length: int
    target_hits: tuple[TargetHit, ...]
    coverage2: float

    def recall_at(self, candidate_budget: int) -> float:
        if candidate_budget < 0:
            raise ValueError("candidate_budget must be non-negative")
        hits = sum(
            hit.position is not None and hit.position <= candidate_budget
            for hit in self.target_hits
        )
        return hits / self.radius


def stable_candidate_order(
    anchor_id: str,
    anchor_neighbors: Sequence[str],
    first_hop_neighbors: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    """Construct anchor -> NN_R(anchor) -> each first-hop NN_R in order."""

    ordered: list[str] = []
    seen: set[str] = set()

    def append_once(candidate_id: str) -> None:
        if candidate_id not in seen:
            seen.add(candidate_id)
            ordered.append(candidate_id)

    append_once(anchor_id)
    for candidate_id in anchor_neighbors:
        append_once(candidate_id)
    for first_hop_id in anchor_neighbors:
        try:
            second_hop = first_hop_neighbors[first_hop_id]
        except KeyError as exc:
            raise KeyError(f"missing first-hop oracle row: {first_hop_id}") from exc
        for candidate_id in second_hop:
            append_once(candidate_id)
    return tuple(ordered)


def evaluate_pair_neighborhood(
    *,
    anchor_row: TopKRow,
    target_row: TopKRow,
    universe_rows: TopKTable,
    fixed_reference_ids: Iterable[str],
    r: int,
    expected_membership_size: int = FIXED_REFERENCE_SIZE,
) -> PairNeighborhoodMetrics:
    """Compute Jaccard, one-hop coverage, and ordered two-hop hit positions."""

    membership = tuple(fixed_reference_ids)
    if anchor_row.query_id in membership or target_row.query_id in membership:
        raise ValueError("anchor and target must be absent from the pair-specific fixed reference")
    anchor_top = filter_fixed_reference(
        anchor_row,
        membership,
        r=r,
        expected_membership_size=expected_membership_size,
    )
    target_top = filter_fixed_reference(
        target_row,
        membership,
        r=r,
        expected_membership_size=expected_membership_size,
    )

    first_hop: dict[str, tuple[str, ...]] = {}
    for neighbor_id in anchor_top.neighbor_ids:
        filtered = filter_fixed_reference(
            universe_rows.row(neighbor_id),
            membership,
            r=r,
            expected_membership_size=expected_membership_size,
        )
        first_hop[neighbor_id] = filtered.neighbor_ids

    candidates = stable_candidate_order(anchor_row.query_id, anchor_top.neighbor_ids, first_hop)
    if len(candidates) > 1 + r + r * r:
        raise AssertionError("candidate list exceeds the mathematical maximum")
    positions = {candidate_id: index for index, candidate_id in enumerate(candidates, start=1)}
    target_hits = tuple(TargetHit(item, positions.get(item)) for item in target_top.neighbor_ids)

    anchor_set = set(anchor_top.neighbor_ids)
    target_set = set(target_top.neighbor_ids)
    intersection_count = len(anchor_set & target_set)
    union_count = len(anchor_set | target_set)
    full_hits = sum(hit.position is not None for hit in target_hits)
    return PairNeighborhoodMetrics(
        radius=r,
        anchor_neighbors=anchor_top.neighbor_ids,
        target_neighbors=target_top.neighbor_ids,
        intersection_count=intersection_count,
        union_count=union_count,
        jaccard=intersection_count / union_count,
        coverage1=intersection_count / r,
        candidate_ids=candidates,
        candidate_length=len(candidates),
        target_hits=target_hits,
        coverage2=full_hits / r,
    )


def exact_rank(
    query_embedding: np.ndarray,
    candidate_embeddings: np.ndarray,
    candidate_ids: Sequence[str],
    sought_id: str,
    *,
    expected_candidate_size: int = RANK_CANDIDATE_SIZE,
) -> int:
    """Return the 1-based exact rank under (distance asc, ID UTF-8 asc)."""

    candidate_ids = _validated_ids(candidate_ids, name="candidate_ids")
    if len(candidate_ids) != expected_candidate_size:
        raise ValueError(
            f"rank corpus must contain exactly {expected_candidate_size} candidates; "
            f"got {len(candidate_ids)}"
        )
    candidates = _validated_embeddings(
        candidate_embeddings,
        candidate_ids,
        name="candidate_embeddings",
        require_normalized=True,
    )
    query = np.asarray(query_embedding)
    if query.dtype != np.float32 or query.shape != (candidates.shape[1],):
        raise ValueError("query_embedding must be a float32 vector of candidate dimension")
    if not np.isfinite(query).all() or not math.isclose(
        float(np.linalg.norm(query)), 1.0, rel_tol=1e-5, abs_tol=1e-6
    ):
        raise ValueError("query_embedding must be finite and L2-normalized")
    if sought_id not in set(candidate_ids):
        raise ValueError("sought_id is absent from candidates")
    scores = candidates @ query
    order = np.lexsort((_utf8_sort_keys(candidate_ids), -scores))
    sought_index = candidate_ids.index(sought_id)
    return int(np.flatnonzero(order == sought_index)[0]) + 1
