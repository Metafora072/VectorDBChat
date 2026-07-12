#!/usr/bin/env python3
"""P0/P1 PageMaxSim gate with real ColQwen2 embeddings and candidate sets."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.cluster import AgglomerativeClustering


SEED = 20260712
PAGE_BYTES = 4096
HEADER_BYTES = 64
PAGE_HEADER_BYTES = 16
MAGIC = b"PMAXSIM0"


@dataclass(frozen=True)
class Representation:
    name: str
    merge_factor: int
    codec: str


REPRESENTATIONS = (
    Representation("raw_fp16", 1, "fp16"),
    Representation("raw_int8", 1, "int8_per_token"),
    Representation("light_f9_fp16", 9, "fp16"),
    Representation("light_f9_int8", 9, "int8_per_token"),
    Representation("light_f49_fp16", 49, "fp16"),
    Representation("single_fp16", 10**9, "fp16"),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--embeddings", type=Path, required=True)
    p.add_argument("--artifacts", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--candidates", type=int, default=32)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--repeats", type=int, default=5)
    return p.parse_args()


def load_ragged(path: Path) -> tuple[list[np.ndarray], list[str], dict[str, np.ndarray]]:
    obj = np.load(path, allow_pickle=False)
    values = obj["values"].astype(np.float32)
    offsets = obj["offsets"]
    arrays = [values[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)]
    ids = [str(x) for x in obj["ids"]]
    extras = {k: obj[k] for k in obj.files if k not in {"values", "offsets", "ids"}}
    return arrays, ids, extras


def normalize_rows(x: np.ndarray) -> np.ndarray:
    return (x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)).astype(np.float32)


def merge_semantic(x: np.ndarray, factor: int) -> np.ndarray:
    if factor >= len(x):
        return normalize_rows(x.mean(axis=0, keepdims=True))
    target = max(1, math.ceil(len(x) / factor))
    clustering = AgglomerativeClustering(
        n_clusters=target,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(x)
    merged = np.stack([x[labels == i].mean(axis=0) for i in range(target)])
    return normalize_rows(merged)


def representation_arrays(
    documents: list[np.ndarray], rep: Representation, cache: Path
) -> list[np.ndarray]:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"merge_factor_{rep.merge_factor}.npz"
    if path.exists():
        arrays, _, _ = load_ragged(path)
        return arrays
    base_factor = rep.merge_factor
    arrays: list[np.ndarray] = []
    for i, document in enumerate(documents):
        tick = time.perf_counter()
        merged = document if base_factor == 1 else merge_semantic(document, base_factor)
        arrays.append(merged.astype(np.float32, copy=False))
        print(
            json.dumps(
                {
                    "stage": "merge",
                    "representation": rep.name,
                    "done": i + 1,
                    "total": len(documents),
                    "tokens": len(merged),
                    "seconds": time.perf_counter() - tick,
                }
            ),
            flush=True,
        )
    lengths = np.asarray([len(x) for x in arrays], dtype=np.int32)
    offsets = np.concatenate(([0], np.cumsum(lengths, dtype=np.int64)))
    np.savez(path, values=np.concatenate(arrays).astype(np.float16), offsets=offsets, ids=np.arange(len(arrays)).astype(str))
    return arrays


def quantize_dequantize(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scales = np.maximum(np.max(np.abs(x), axis=1), 1e-12) / 127.0
    codes = np.rint(x / scales[:, None]).clip(-127, 127).astype(np.int8)
    restored = normalize_rows(codes.astype(np.float32) * scales[:, None])
    return restored, codes, scales.astype(np.float16)


def materialize_representation(
    root: Path, rep: Representation, arrays: list[np.ndarray]
) -> tuple[list[np.ndarray], list[dict[str, int | str]]]:
    rep_dir = root / rep.name
    rep_dir.mkdir(parents=True, exist_ok=True)
    scored: list[np.ndarray] = []
    records: list[dict[str, int | str]] = []
    for doc_index, x in enumerate(arrays):
        path = rep_dir / f"doc_{doc_index:04d}.bin"
        if rep.codec == "fp16":
            payload = x.astype("<f2", copy=False).tobytes(order="C")
            scored_x = x
            row_bytes = x.shape[1] * 2
            metadata_bytes = 0
            codec_id = 1
        elif rep.codec == "int8_per_token":
            scored_x, codes, scales = quantize_dequantize(x)
            # Interleave each token's fp16 scale and int8 vector so every row is
            # independently decodable after a page read.
            rows = [scales[i].tobytes() + codes[i].tobytes() for i in range(len(x))]
            payload = b"".join(rows)
            row_bytes = x.shape[1] + 2
            metadata_bytes = len(x) * 2
            codec_id = 2
        else:
            raise ValueError(rep.codec)
        header = struct.pack(
            "<8sIIIIQQ",
            MAGIC,
            1,
            codec_id,
            len(x),
            x.shape[1],
            len(payload),
            row_bytes,
        ).ljust(HEADER_BYTES, b"\0")
        logical_bytes = len(header) + len(payload)
        # Direct-I/O pages must independently contain complete token rows.  Add
        # real inter-page padding instead of letting a vector straddle pages.
        serialized_bytes = bytearray(header)
        continuation_pages = 0
        for offset in range(0, len(payload), row_bytes):
            row = payload[offset : offset + row_bytes]
            in_page = len(serialized_bytes) % PAGE_BYTES
            if in_page + len(row) > PAGE_BYTES:
                serialized_bytes.extend(b"\0" * (PAGE_BYTES - in_page))
                serialized_bytes.extend(struct.pack("<IIII", 1, continuation_pages + 1, len(row), 0))
                continuation_pages += 1
            serialized_bytes.extend(row)
        logical_bytes += continuation_pages * PAGE_HEADER_BYTES
        aligned_bytes = math.ceil(len(serialized_bytes) / PAGE_BYTES) * PAGE_BYTES
        serialized_bytes.extend(b"\0" * (aligned_bytes - len(serialized_bytes)))
        with path.open("wb") as handle:
            handle.write(serialized_bytes)
        actual_bytes = path.stat().st_size
        assert actual_bytes == aligned_bytes and actual_bytes % PAGE_BYTES == 0
        scored.append(scored_x)
        records.append(
            {
                "representation": rep.name,
                "document": doc_index,
                "tokens": len(x),
                "dimension": x.shape[1],
                "codec": rep.codec,
                "header_bytes": HEADER_BYTES,
                "continuation_page_header_bytes": continuation_pages * PAGE_HEADER_BYTES,
                "quantization_metadata_bytes": metadata_bytes,
                "payload_bytes": len(payload),
                "logical_bytes": logical_bytes,
                "alignment_padding_bytes": aligned_bytes - logical_bytes,
                "actual_serialized_bytes": actual_bytes,
                "pages": actual_bytes // PAGE_BYTES,
                "row_bytes": row_bytes,
            }
        )
    return scored, records


def maxsim_cells(query: np.ndarray, documents: Iterable[np.ndarray]) -> np.ndarray:
    return np.stack([(query @ document.T).max(axis=1) for document in documents])


def score_all(queries: list[np.ndarray], documents: list[np.ndarray]) -> np.ndarray:
    return np.stack([maxsim_cells(q, documents).sum(axis=1) for q in queries])


def mean_scores(queries: list[np.ndarray], documents: list[np.ndarray]) -> np.ndarray:
    doc_mean = normalize_rows(np.stack([x.mean(axis=0) for x in documents]))
    query_mean = normalize_rows(np.stack([x.mean(axis=0) for x in queries]))
    return query_mean @ doc_mean.T


def topk_overlap(reference: np.ndarray, candidate: np.ndarray, k: int) -> float:
    values = []
    for a, b in zip(reference, candidate, strict=True):
        aa = set(np.argsort(-a)[:k])
        bb = set(np.argsort(-b)[:k])
        values.append(len(aa & bb) / k)
    return float(np.mean(values))


def reciprocal_rank(scores: np.ndarray, candidate_indices: list[np.ndarray], positive_indices: list[int]) -> float:
    rr = []
    for qi, candidates in enumerate(candidate_indices):
        ranking = candidates[np.argsort(-scores[qi, candidates])]
        position = np.flatnonzero(ranking == positive_indices[qi])
        rr.append(0.0 if len(position) == 0 else 1.0 / (int(position[0]) + 1))
    return float(np.mean(rr))


def exact_bounded_interaction_oracle(cells: np.ndarray, top_k: int) -> np.ndarray:
    """Minimum reveals for an exact top-k certificate under cell bounds [-1, 1].

    For a chosen separating threshold, each true top-k document reveals its
    largest cells to raise its score lower bound; each other document reveals
    its smallest cells to lower its upper bound.  Enumerating all attainable
    thresholds makes the resulting count exact for this deterministic
    certificate model.
    """
    docs, tokens = cells.shape
    true_scores = cells.sum(axis=1)
    top = set(np.argsort(-true_scores)[:top_k].tolist())
    low_sequences: dict[int, np.ndarray] = {}
    high_sequences: dict[int, np.ndarray] = {}
    thresholds: list[float] = []
    for d in range(docs):
        if d in top:
            improvements = np.sort(cells[d] + 1.0)[::-1]
            seq = -tokens + np.concatenate(([0.0], np.cumsum(improvements)))
            low_sequences[d] = seq
        else:
            reductions = np.sort(1.0 - cells[d])[::-1]
            seq = tokens - np.concatenate(([0.0], np.cumsum(reductions)))
            high_sequences[d] = seq
        thresholds.extend(seq.tolist())
    thresholds = sorted(set(thresholds))
    # Midpoints handle strict separation; endpoints handle equality on the top side.
    probes = thresholds + [(a + b) / 2 for a, b in zip(thresholds[:-1], thresholds[1:])]
    best_count = docs * tokens + 1
    best_threshold = 0.0
    best_counts: dict[int, int] = {}
    for threshold in probes:
        counts: dict[int, int] = {}
        feasible = True
        for d in range(docs):
            seq = low_sequences[d] if d in top else high_sequences[d]
            valid = np.flatnonzero(seq >= threshold) if d in top else np.flatnonzero(seq < threshold)
            if len(valid) == 0:
                feasible = False
                break
            counts[d] = int(valid[0])
        if feasible and sum(counts.values()) < best_count:
            best_count = sum(counts.values())
            best_threshold = threshold
            best_counts = counts
    if not best_counts:
        raise RuntimeError("no exact bounded top-k certificate")
    reveal = np.zeros_like(cells, dtype=bool)
    for d, count in best_counts.items():
        if count == 0:
            continue
        order = np.argsort(-(cells[d] + 1.0)) if d in top else np.argsort(-(1.0 - cells[d]))
        reveal[d, order[:count]] = True
    # Audit the certificate instead of trusting the construction.
    lower = np.where(reveal, cells, -1.0).sum(axis=1)
    upper = np.where(reveal, cells, 1.0).sum(axis=1)
    assert min(lower[list(top)]) > max(upper[d] for d in range(docs) if d not in top) - 1e-6
    _ = best_threshold
    return reveal


def col_bandit(
    cells: np.ndarray,
    top_k: int,
    alpha: float,
    seed: int,
    margin: int = 5,
    batch: int = 4,
    delta: float = 0.01,
) -> tuple[np.ndarray, np.ndarray]:
    """Faithful Python realization of Col-Bandit Algorithm 1 / Eq. 7-8."""
    docs, tokens = cells.shape
    rng = np.random.default_rng(seed)
    permutation = rng.permutation(tokens)
    active = np.ones(docs, dtype=bool)
    reveal = np.zeros_like(cells, dtype=bool)
    cursor = 0
    while int(active.sum()) > top_k + margin and cursor < tokens:
        selected = permutation[cursor : min(cursor + batch, tokens)]
        reveal[np.ix_(active, selected)] = True
        cursor += len(selected)
        lcb = np.full(docs, -np.inf, dtype=np.float64)
        ucb = np.full(docs, np.inf, dtype=np.float64)
        for d in np.flatnonzero(active):
            observed = cells[d, reveal[d]]
            n = len(observed)
            hard_low = float(observed.sum() - (tokens - n))
            hard_high = float(observed.sum() + (tokens - n))
            if n <= 1:
                lcb[d], ucb[d] = hard_low, hard_high
                continue
            estimate = float(tokens * observed.mean())
            sigma = float(observed.std(ddof=1))
            if n <= tokens / 2:
                rho = 1.0 - (n - 1) / tokens
            else:
                rho = (1.0 - n / tokens) * (1.0 + 1.0 / n)
            radius = alpha * tokens * sigma * math.sqrt(2.0 * math.log(docs * tokens / delta) / n) * math.sqrt(max(rho, 0.0))
            lcb[d] = max(hard_low, estimate - radius)
            ucb[d] = min(hard_high, estimate + radius)
        active_lcb = lcb[active]
        threshold = float(np.partition(active_lcb, -top_k)[-top_k])
        active &= ucb >= threshold
    survivors = np.flatnonzero(active)
    reveal[survivors, :] = True
    survivor_scores = cells[survivors].sum(axis=1)
    returned = survivors[np.argsort(-survivor_scores)[:top_k]]
    return reveal, returned


def token_page(token_index: int, row_bytes: int) -> int:
    offset = HEADER_BYTES
    for _ in range(token_index + 1):
        in_page = offset % PAGE_BYTES
        if in_page + row_bytes > PAGE_BYTES:
            offset += PAGE_BYTES - in_page + PAGE_HEADER_BYTES
        page = offset // PAGE_BYTES
        offset += row_bytes
    return page


def page_oracle_counts(cells: np.ndarray, reveal: np.ndarray, documents: list[np.ndarray], rows: list[dict]) -> tuple[int, int]:
    oracle_pages: set[tuple[int, int]] = set()
    ordinary_documents: set[int] = set()
    for d, query_token in zip(*np.nonzero(reveal), strict=True):
        similarities = documents[d] @ CURRENT_QUERY[query_token]
        maximum_token = int(np.argmax(similarities))
        oracle_pages.add((d, token_page(maximum_token, int(rows[d]["row_bytes"]))))
        ordinary_documents.add(d)
    ordinary_pages = sum(int(rows[d]["pages"]) for d in ordinary_documents)
    return len(oracle_pages), ordinary_pages


# Bound to the current query only during page-oracle calculation; kept explicit
# to avoid materializing every query-token/document-token matrix simultaneously.
CURRENT_QUERY: np.ndarray


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    global CURRENT_QUERY
    args = parse_args()
    np.random.seed(SEED)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    args.results.mkdir(parents=True, exist_ok=True)
    documents, document_ids, _ = load_ragged(args.embeddings / "documents.npz")
    queries, _, query_extras = load_ragged(args.embeddings / "queries.npz")
    manifest = json.loads((args.embeddings / "manifest.json").read_text())
    positive_lookup = {doc_id: i for i, doc_id in enumerate(document_ids)}
    positive_indices = [positive_lookup[x] for x in manifest["positive_document_ids"]]

    raw_scores = score_all(queries, documents)
    coarse_scores = mean_scores(queries, documents)
    candidate_indices: list[np.ndarray] = []
    for qi, row in enumerate(coarse_scores):
        selected = np.argsort(-row)[: args.candidates].tolist()
        positive = positive_indices[qi]
        if positive not in selected:
            selected[-1] = positive
        candidate_indices.append(np.asarray(selected, dtype=np.int32))

    representation_rows: list[dict] = []
    summary_rows: list[dict] = []
    p1_rows: list[dict] = []
    scored_by_rep: dict[str, list[np.ndarray]] = {}
    serialized_by_rep: dict[str, list[dict]] = {}
    scores_by_rep: dict[str, np.ndarray] = {}

    for rep in REPRESENTATIONS:
        base = representation_arrays(documents, rep, args.artifacts / "merged_cache")
        scored, serialized = materialize_representation(args.artifacts / "objects", rep, base)
        scored_by_rep[rep.name] = scored
        serialized_by_rep[rep.name] = serialized
        representation_rows.extend(serialized)
        scores = score_all(queries, scored) if rep.name != "raw_fp16" else raw_scores
        scores_by_rep[rep.name] = scores
        pages = np.asarray([r["pages"] for r in serialized], dtype=np.int32)
        candidate_pages = [int(pages[c].sum()) for c in candidate_indices]
        tick = time.perf_counter()
        for _ in range(args.repeats):
            for qi, candidates in enumerate(candidate_indices):
                _ = maxsim_cells(queries[qi], [scored[d] for d in candidates]).sum(axis=1)
        maxsim_seconds = (time.perf_counter() - tick) / args.repeats / len(queries)
        summary_rows.append(
            {
                "representation": rep.name,
                "codec": rep.codec,
                "merge_factor": rep.merge_factor,
                "tokens_median": float(np.median([len(x) for x in scored])),
                "pages_p50": float(np.percentile(pages, 50)),
                "pages_p95": float(np.percentile(pages, 95)),
                "objects_pages_le_2_fraction": float(np.mean(pages <= 2)),
                "bytes_total": int(sum(int(r["actual_serialized_bytes"]) for r in serialized)),
                "candidate_pages_p50": float(np.percentile(candidate_pages, 50)),
                "candidate_pages_p95": float(np.percentile(candidate_pages, 95)),
                "top5_overlap_vs_raw": topk_overlap(raw_scores, scores, min(5, len(documents))),
                "mrr_in_real_candidates": reciprocal_rank(scores, candidate_indices, positive_indices),
                "maxsim_cpu_ms_per_query": 1000.0 * maxsim_seconds,
                "page_latency_break_even_us": 1e6 * maxsim_seconds / max(float(np.median(candidate_pages)), 1.0),
            }
        )

    write_csv(args.results / "p0_object_footprints.csv", representation_rows)
    write_csv(args.results / "p0_representation_summary.csv", summary_rows)

    light9 = next(x for x in summary_rows if x["representation"] == "light_f9_fp16")
    p0_kill = float(light9["objects_pages_le_2_fraction"]) > 0.5
    if not p0_kill:
        # P1 uses raw and both strong footprint levels.  The deterministic exact
        # interaction certificate is evaluated separately for every query and
        # representation on the same real first-stage candidate sets.
        for rep_name in ("raw_fp16", "raw_int8", "light_f9_fp16", "light_f9_int8", "light_f49_fp16"):
            scored = scored_by_rep[rep_name]
            serialized = serialized_by_rep[rep_name]
            for qi, candidates in enumerate(candidate_indices):
                CURRENT_QUERY = queries[qi]
                local_docs = [scored[d] for d in candidates]
                cells = maxsim_cells(CURRENT_QUERY, local_docs)
                local_rows = [serialized[d] for d in candidates]
                full_pages = sum(int(r["pages"]) for r in local_rows)
                top_k = min(args.top_k, len(candidates) - 1)
                true_top = set(np.argsort(-cells.sum(axis=1))[:top_k].tolist())
                policies: list[tuple[str, np.ndarray, float]] = []
                oracle_reveal = exact_bounded_interaction_oracle(cells, top_k)
                policies.append(("deterministic_interaction_oracle", oracle_reveal, 1.0))
                for alpha in (0.2, 1.0):
                    cb_reveal, cb_top = col_bandit(cells, top_k, alpha, SEED + qi)
                    overlap = len(true_top & set(cb_top.tolist())) / top_k
                    policies.append((f"colbandit_alpha_{alpha:.1f}", cb_reveal, overlap))
                for policy, reveal, overlap in policies:
                    oracle_pages, ordinary_pages = page_oracle_counts(cells, reveal, local_docs, local_rows)
                    p1_rows.append({
                        "representation": rep_name,
                        "policy": policy,
                        "query": qi,
                        "candidate_count": len(candidates),
                        "query_tokens": len(CURRENT_QUERY),
                        "full_interaction_cells": int(cells.size),
                        "interaction_oracle_cells": int(reveal.sum()),
                        "interaction_materialization_lower_bound_cells": int(args.top_k * len(CURRENT_QUERY)),
                        "full_contiguous_pages": full_pages,
                        "page_contribution_oracle_pages": oracle_pages,
                        "colbandit_ordinary_layout_pages": ordinary_pages,
                        "interaction_fraction": float(reveal.mean()),
                        "page_oracle_fraction_of_full": oracle_pages / full_pages,
                        "ordinary_fraction_of_full": ordinary_pages / full_pages,
                        "topk_overlap_vs_full": overlap,
                    })
        write_csv(args.results / "p1_oracles.csv", p1_rows)

    aggregate: dict[str, dict[str, float]] = {}
    for rep_name in sorted({r["representation"] for r in p1_rows}):
      for policy in sorted({r["policy"] for r in p1_rows if r["representation"] == rep_name}):
        selected = [r for r in p1_rows if r["representation"] == rep_name and r["policy"] == policy]
        aggregate[f"{rep_name}/{policy}"] = {
            key: float(np.mean([float(r[key]) for r in selected]))
            for key in (
                "full_interaction_cells",
                "interaction_oracle_cells",
                "interaction_fraction",
                "full_contiguous_pages",
                "page_contribution_oracle_pages",
                "page_oracle_fraction_of_full",
                "colbandit_ordinary_layout_pages",
                "ordinary_fraction_of_full",
                "topk_overlap_vs_full",
            )
        }

    # P1's formal decision is finalized in the report after checking the joint
    # bytes/fidelity/page Pareto.  Preserve all raw evidence here.
    result = {
        "seed": SEED,
        "page_bytes": PAGE_BYTES,
        "header_bytes": HEADER_BYTES,
        "candidate_selector": "normalized mean-vector top-C, positive forced if absent",
        "candidates": args.candidates,
        "top_k": args.top_k,
        "p0_kill": p0_kill,
        "p0_reason": "majority of Light-f9 objects occupy <=2 pages" if p0_kill else "Light-f9 retains multi-page objects",
        "p0": summary_rows,
        "p1": aggregate,
    }
    (args.results / "gate_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
