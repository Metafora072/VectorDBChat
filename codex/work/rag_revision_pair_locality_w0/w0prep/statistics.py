"""Document-clustered inference and frozen W0 label routing."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class BootstrapResult:
    n_documents: int
    observed_mean: float
    raw_p: float
    simultaneous_lcb: float
    bootstrap_replicates: int
    family_size: int


def document_mean_effects(
    rows: Iterable[Mapping[str, object]],
    *,
    document_key: str = "document_id",
    effect_key: str = "effect",
) -> np.ndarray:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[document_key])].append(float(row[effect_key]))
    if not grouped:
        raise ValueError("no document effects")
    return np.asarray(
        [float(np.mean(grouped[key], dtype=np.float64)) for key in sorted(grouped)],
        dtype=np.float64,
    )


def clustered_bootstrap(
    document_effects: Sequence[float] | np.ndarray,
    *,
    seed: int,
    replicates: int = 20_000,
    alpha: float = 0.05,
    family_size: int = 1,
) -> BootstrapResult:
    values = np.asarray(document_effects, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("at least two document-level effects are required")
    if replicates < 1 or family_size < 1 or not 0.0 < alpha < 1.0:
        raise ValueError("invalid bootstrap parameters")

    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    observed = float(values.mean(dtype=np.float64))
    centered = values - observed
    null_ge = 0
    uncentered_means = np.empty(replicates, dtype=np.float64)
    # Chunk allocation bounds peak memory while retaining the exact frozen RNG stream.
    done = 0
    while done < replicates:
        count = min(1024, replicates - done)
        indices = rng.integers(0, len(values), size=(count, len(values)))
        null_means = centered[indices].mean(axis=1, dtype=np.float64)
        null_ge += int(np.count_nonzero(null_means >= observed))
        uncentered_means[done : done + count] = values[indices].mean(
            axis=1, dtype=np.float64
        )
        done += count

    raw_p = (1.0 + null_ge) / (replicates + 1.0)
    ordered = np.sort(uncentered_means)
    order_index = math.ceil((alpha / family_size) * (replicates + 1.0)) - 1
    order_index = min(max(order_index, 0), replicates - 1)
    return BootstrapResult(
        n_documents=len(values),
        observed_mean=observed,
        raw_p=float(raw_p),
        simultaneous_lcb=float(ordered[order_index]),
        bootstrap_replicates=replicates,
        family_size=family_size,
    )


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    values = np.asarray(p_values, dtype=np.float64)
    if values.ndim != 1 or np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("p-values must be a one-dimensional array in [0,1]")
    order = np.argsort(values, kind="stable")
    adjusted_sorted = np.empty(len(values), dtype=np.float64)
    running = 0.0
    m = len(values)
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * float(values[index]))
        adjusted_sorted[rank] = min(running, 1.0)
    adjusted = np.empty(len(values), dtype=np.float64)
    adjusted[order] = adjusted_sorted
    return adjusted


def endpoint_pass(result: BootstrapResult, holm_p: float, alpha: float = 0.05) -> bool:
    return holm_p < alpha and result.simultaneous_lcb > 0.0


def classify_final_label(
    *,
    closure_ok: bool,
    control_a_pass: bool,
    control_b_pass: bool,
    control_c_pass: bool,
) -> str:
    if not closure_ok:
        return "FAIL-W0-WORKLOAD-CLOSURE"
    if not control_a_pass:
        return "KILL-NO-PAIR-LOCALITY"
    if not control_b_pass:
        return "HOLD-GEOMETRIC-REPLACEMENT-ONLY"
    if not control_c_pass:
        return "KILL-NO-TEMPORAL-LINEAGE-SIGNAL"
    return "HOLD-PAIR-LOCALITY-NOVELTY-REVIEW"

