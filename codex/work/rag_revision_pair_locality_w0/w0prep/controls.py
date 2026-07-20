"""Preparation-only deterministic generators for W0 paired controls.

This module selects Control B anchors.  It intentionally contains no
neighborhood, rank, recall, or classifier code and therefore cannot compute a
W0 outcome.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .common import canonical_json_bytes


MODEL_DIMENSIONS = {"minilm": 384, "nomic": 768}
UNIVERSE_SIZE = 8_448
CORE_SIZE = 8_192
RESERVE_SIZE = 256
MISSING_NO_CANDIDATE = "MISSING_NO_ELIGIBLE_CROSS_DOCUMENT_UNIQUE_PAYLOAD"
CONTROL_NAME = "B_DISTANCE_MATCHED_CROSS_DOCUMENT"


@dataclass(frozen=True)
class UniverseItem:
    canonical_chunk_id: str
    source: str
    document_path: str
    payload_sha256: str


@dataclass(frozen=True)
class SelectedRealPair:
    pair_id: str
    source: str
    document_path: str


@dataclass(frozen=True)
class ControlBResult:
    model: str
    rows: tuple[dict[str, object], ...]
    complete_count: int
    missing_count: int
    counts_by_source: dict[str, dict[str, int]]
    jsonl_sha256: str
    jsonl_bytes: bytes

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.jsonl_bytes)


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")


def _validate_matrix(
    value: np.ndarray,
    *,
    rows: int,
    dimension: int,
    field: str,
) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.float32:
        raise TypeError(f"{field} must have dtype float32")
    if array.shape != (rows, dimension):
        raise ValueError(f"{field} must have shape ({rows}, {dimension})")
    if not np.isfinite(array).all():
        raise ValueError(f"{field} contains a non-finite value")
    norms = np.linalg.norm(array, axis=1)
    if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
        raise ValueError(f"{field} rows must be L2-normalized")
    return np.ascontiguousarray(array)


def _validate_source_membership(
    *,
    universe_items: Sequence[UniverseItem],
    core_ids_by_source: Mapping[str, Sequence[str]],
    reserve_ids_by_source: Mapping[str, Sequence[str]],
    expected_universe_size: int,
    expected_core_size: int,
    expected_reserve_size: int,
) -> tuple[dict[str, int], dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    item_index: dict[str, int] = {}
    universe_by_source: dict[str, set[str]] = {}
    for index, item in enumerate(universe_items):
        for field_name, field_value in (
            ("canonical_chunk_id", item.canonical_chunk_id),
            ("source", item.source),
            ("document_path", item.document_path),
            ("payload_sha256", item.payload_sha256),
        ):
            _require_text(field_value, field_name)
        if item.canonical_chunk_id in item_index:
            raise ValueError(f"duplicate canonical_chunk_id: {item.canonical_chunk_id}")
        item_index[item.canonical_chunk_id] = index
        universe_by_source.setdefault(item.source, set()).add(item.canonical_chunk_id)

    declared_sources = set(core_ids_by_source) | set(reserve_ids_by_source)
    if declared_sources != set(universe_by_source):
        raise ValueError("core/reserve source keys must exactly match universe sources")

    normalized_core: dict[str, tuple[str, ...]] = {}
    normalized_reserve: dict[str, tuple[str, ...]] = {}
    for source in sorted(declared_sources):
        core = tuple(core_ids_by_source[source])
        reserve = tuple(reserve_ids_by_source[source])
        if len(core) != expected_core_size or len(set(core)) != len(core):
            raise ValueError(
                f"{source} core must contain exactly {expected_core_size} unique IDs"
            )
        if len(reserve) != expected_reserve_size or len(set(reserve)) != len(reserve):
            raise ValueError(
                f"{source} reserve must contain exactly {expected_reserve_size} unique IDs"
            )
        if set(core) & set(reserve):
            raise ValueError(f"{source} core and reserve overlap")
        source_universe = universe_by_source[source]
        if len(source_universe) != expected_universe_size:
            raise ValueError(
                f"{source} universe must contain exactly {expected_universe_size} items"
            )
        if set(core) | set(reserve) != source_universe:
            raise ValueError(f"{source} core plus reserve does not equal its universe")
        normalized_core[source] = core
        normalized_reserve[source] = reserve
    return item_index, normalized_core, normalized_reserve


def generate_control_b(
    *,
    model: str,
    selected_pairs: Sequence[SelectedRealPair],
    old_embeddings: np.ndarray,
    new_embeddings: np.ndarray,
    universe_items: Sequence[UniverseItem],
    universe_embeddings: np.ndarray,
    core_ids_by_source: Mapping[str, Sequence[str]],
    reserve_ids_by_source: Mapping[str, Sequence[str]],
    expected_dimension: int | None = None,
    expected_universe_size: int = UNIVERSE_SIZE,
    expected_core_size: int = CORE_SIZE,
    expected_reserve_size: int = RESERVE_SIZE,
) -> ControlBResult:
    """Select one model-specific distance-matched Control B per real pair.

    Candidate eligibility is fixed before distance inspection: the anchor must
    be in the same-source core, in a different document, and its payload hash
    must have multiplicity one in that source's full ordered universe.  There
    is no distance caliper and no fallback candidate.
    """

    if model not in MODEL_DIMENSIONS:
        raise ValueError(f"model must be one of {sorted(MODEL_DIMENSIONS)}")
    dimension = MODEL_DIMENSIONS[model] if expected_dimension is None else expected_dimension
    if dimension <= 0:
        raise ValueError("expected_dimension must be positive")
    if not selected_pairs:
        raise ValueError("selected_pairs must not be empty")

    seen_pairs: set[str] = set()
    for pair in selected_pairs:
        _require_text(pair.pair_id, "pair_id")
        _require_text(pair.source, "pair source")
        _require_text(pair.document_path, "pair document_path")
        if pair.pair_id in seen_pairs:
            raise ValueError(f"duplicate pair_id: {pair.pair_id}")
        seen_pairs.add(pair.pair_id)

    old = _validate_matrix(
        old_embeddings,
        rows=len(selected_pairs),
        dimension=dimension,
        field="old_embeddings",
    )
    new = _validate_matrix(
        new_embeddings,
        rows=len(selected_pairs),
        dimension=dimension,
        field="new_embeddings",
    )
    universe = _validate_matrix(
        universe_embeddings,
        rows=len(universe_items),
        dimension=dimension,
        field="universe_embeddings",
    )
    item_index, core_by_source, reserve_by_source = _validate_source_membership(
        universe_items=universe_items,
        core_ids_by_source=core_ids_by_source,
        reserve_ids_by_source=reserve_ids_by_source,
        expected_universe_size=expected_universe_size,
        expected_core_size=expected_core_size,
        expected_reserve_size=expected_reserve_size,
    )
    item_by_id = {item.canonical_chunk_id: item for item in universe_items}

    payload_multiplicity: dict[str, Counter[str]] = {}
    for item in universe_items:
        payload_multiplicity.setdefault(item.source, Counter())[item.payload_sha256] += 1

    rows: list[dict[str, object]] = []
    for pair_index, pair in enumerate(selected_pairs):
        if pair.source not in core_by_source:
            raise ValueError(f"pair source is absent from universe: {pair.source}")
        core_ids = core_by_source[pair.source]
        eligible_ids = [
            candidate_id
            for candidate_id in core_ids
            if item_by_id[candidate_id].document_path != pair.document_path
            and payload_multiplicity[pair.source][item_by_id[candidate_id].payload_sha256] == 1
        ]
        replacement_id = reserve_by_source[pair.source][0]
        base: dict[str, object] = {
            "control": CONTROL_NAME,
            "fixed_reference_core_size": expected_core_size,
            "first_reserve_replacement_id": replacement_id,
            "model": model,
            "pair_id": pair.pair_id,
            "source": pair.source,
        }
        if not eligible_ids:
            rows.append(
                {
                    **base,
                    "candidate_id": None,
                    "missing_reason": MISSING_NO_CANDIDATE,
                    "status": "MISSING",
                }
            )
            continue

        eligible_indices = np.asarray([item_index[item] for item in eligible_ids], dtype=np.int64)
        target_distance = np.float32(1.0) - np.dot(old[pair_index], new[pair_index])
        candidate_distances = np.float32(1.0) - universe[eligible_indices] @ new[pair_index]
        absolute_errors = np.abs(candidate_distances - target_distance)
        minimum_error = np.min(absolute_errors)
        tied_local_indices = np.flatnonzero(absolute_errors == minimum_error)
        selected_local_index = min(
            (int(index) for index in tied_local_indices),
            key=lambda index: eligible_ids[index].encode("utf-8"),
        )
        candidate_id = eligible_ids[selected_local_index]
        candidate = item_by_id[candidate_id]
        rows.append(
            {
                **base,
                "absolute_distance_error": float(absolute_errors[selected_local_index]),
                "candidate_document_path": candidate.document_path,
                "candidate_id": candidate_id,
                "candidate_payload_sha256": candidate.payload_sha256,
                "candidate_target_cosine_distance": float(
                    candidate_distances[selected_local_index]
                ),
                "missing_reason": None,
                "old_target_cosine_distance": float(target_distance),
                "status": "COMPLETE",
            }
        )

    rows.sort(key=lambda row: (str(row["source"]).encode("utf-8"), str(row["pair_id"]).encode("utf-8")))
    jsonl_bytes = b"".join(canonical_json_bytes(row) for row in rows)
    complete_count = sum(row["status"] == "COMPLETE" for row in rows)
    missing_count = len(rows) - complete_count
    counts_by_source: dict[str, dict[str, int]] = {}
    for source in sorted({str(row["source"]) for row in rows}):
        source_rows = [row for row in rows if row["source"] == source]
        source_complete = sum(row["status"] == "COMPLETE" for row in source_rows)
        counts_by_source[source] = {
            "complete": source_complete,
            "missing": len(source_rows) - source_complete,
            "total": len(source_rows),
        }
    return ControlBResult(
        model=model,
        rows=tuple(rows),
        complete_count=complete_count,
        missing_count=missing_count,
        counts_by_source=counts_by_source,
        jsonl_sha256=hashlib.sha256(jsonl_bytes).hexdigest(),
        jsonl_bytes=jsonl_bytes,
    )
