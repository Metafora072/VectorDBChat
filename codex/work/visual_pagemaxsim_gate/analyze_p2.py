#!/usr/bin/env python3
"""P2 centroid-radius safe-bound feasibility gate for PageMaxSim."""

from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import time
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering

import analyze_p0_p1 as p1


SYNOPSIS_RECORD_BYTES = 288  # fp16[128] centroid + radius/count/page/offset + pad


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--p0-p1-artifacts", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--candidates", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def pack_pages(x: np.ndarray, row_bytes: int, layout: str) -> list[np.ndarray]:
    count = len(x)
    if layout == "spatial_contiguous":
        order = np.arange(count)
    elif layout == "representative_first":
        centroid = x.mean(axis=0)
        order = np.argsort(-(x @ centroid))
    elif layout == "centroid_grouped":
        first_capacity = (p1.PAGE_BYTES - p1.HEADER_BYTES) // row_bytes
        next_capacity = (p1.PAGE_BYTES - p1.PAGE_HEADER_BYTES) // row_bytes
        groups = 1 + max(0, math.ceil((count - first_capacity) / next_capacity))
        if groups == 1:
            order = np.arange(count)
        else:
            labels = AgglomerativeClustering(
                n_clusters=groups, metric="cosine", linkage="average"
            ).fit_predict(x)
            # Cluster IDs are query-independent; sort clusters by their first
            # original token so the layout remains deterministic.
            cluster_order = sorted(range(groups), key=lambda label: int(np.flatnonzero(labels == label)[0]))
            order = np.concatenate([np.flatnonzero(labels == label) for label in cluster_order])
    else:
        raise ValueError(layout)

    pages: list[np.ndarray] = []
    cursor = 0
    first_capacity = (p1.PAGE_BYTES - p1.HEADER_BYTES) // row_bytes
    next_capacity = (p1.PAGE_BYTES - p1.PAGE_HEADER_BYTES) // row_bytes
    capacity = first_capacity
    while cursor < count:
        pages.append(order[cursor : cursor + capacity])
        cursor += capacity
        capacity = next_capacity
    return pages


def page_synopses(x: np.ndarray, pages: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    centroids = np.stack([x[indices].mean(axis=0) for indices in pages]).astype(np.float32)
    radii = np.asarray(
        [np.linalg.norm(x[indices] - centroids[i], axis=1).max(initial=0.0) for i, indices in enumerate(pages)],
        dtype=np.float32,
    )
    return centroids, radii


def serialize_synopses(
    path: Path,
    all_centroids: list[np.ndarray],
    all_radii: list[np.ndarray],
    all_pages: list[list[np.ndarray]],
) -> int:
    payload = bytearray(struct.pack("<8sIIIIQ", b"PMXSYN00", 1, 128, SYNOPSIS_RECORD_BYTES, len(all_pages), sum(map(len, all_pages))).ljust(64, b"\0"))
    global_page = 0
    for doc_id, (centroids, radii, pages) in enumerate(zip(all_centroids, all_radii, all_pages, strict=True)):
        for local_page, (centroid, radius, token_indices) in enumerate(zip(centroids, radii, pages, strict=True)):
            record = bytearray(centroid.astype("<f2").tobytes())
            record.extend(struct.pack("<eHIIQ", float(radius), len(token_indices), doc_id, local_page, global_page * p1.PAGE_BYTES))
            record.extend(b"\0" * (SYNOPSIS_RECORD_BYTES - len(record)))
            assert len(record) == SYNOPSIS_RECORD_BYTES
            payload.extend(record)
            global_page += 1
    payload.extend(b"\0" * (math.ceil(len(payload) / p1.PAGE_BYTES) * p1.PAGE_BYTES - len(payload)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path.stat().st_size


def safe_search(
    query_tokens: np.ndarray,
    x: np.ndarray,
    pages: list[np.ndarray],
    centroids: np.ndarray,
    radii: np.ndarray,
    schedule: str,
) -> dict[str, float | int]:
    if len(query_tokens) == 0:
        return {"pages": 0, "useful_bytes_rows": 0, "bound_seconds": 0.0, "score_seconds": 0.0, "tightened_cells": 0, "inner_exact": 1.0}
    tick = time.perf_counter()
    upper = query_tokens @ centroids.T + radii[None, :]
    bound_seconds = time.perf_counter() - tick
    score_seconds = 0.0
    lower = np.full(len(query_tokens), -np.inf, dtype=np.float32)
    remaining = np.ones(len(pages), dtype=bool)
    pages_read = 0
    useful_rows = 0
    tightened_cells = 0
    while remaining.any():
        maximum_unread = upper[:, remaining].max(axis=1)
        unresolved = lower + 1e-7 < maximum_unread
        if not unresolved.any():
            break
        available = np.flatnonzero(remaining)
        if schedule == "sequential":
            chosen = int(available[0])
        elif schedule == "active_batch_greedy":
            tick = time.perf_counter()
            local_upper = upper[np.ix_(unresolved, available)]
            row_max = local_upper.max(axis=1, keepdims=True)
            critical = local_upper >= row_max - 1e-7
            gaps = np.maximum(local_upper - lower[unresolved, None], 0.0)
            priority = critical.sum(axis=0) * 1_000_000.0 + gaps.sum(axis=0)
            chosen = int(available[int(np.argmax(priority))])
            bound_seconds += time.perf_counter() - tick
        else:
            raise ValueError(schedule)
        tick = time.perf_counter()
        observed = (query_tokens @ x[pages[chosen]].T).max(axis=1)
        score_seconds += time.perf_counter() - tick
        improved = observed > lower
        tightened_cells += int(improved.sum())
        lower = np.maximum(lower, observed)
        remaining[chosen] = False
        pages_read += 1
        useful_rows += len(pages[chosen])
    exact = (query_tokens @ x.T).max(axis=1)
    return {
        "pages": pages_read,
        "useful_bytes_rows": useful_rows,
        "bound_seconds": bound_seconds,
        "score_seconds": score_seconds,
        "tightened_cells": tightened_cells,
        "inner_exact": float(np.allclose(lower, exact, atol=2e-6, rtol=0.0)),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    args.results.mkdir(parents=True, exist_ok=True)
    documents, document_ids, _ = p1.load_ragged(args.embeddings / "documents.npz")
    queries, _, _ = p1.load_ragged(args.embeddings / "queries.npz")
    manifest = json.loads((args.embeddings / "manifest.json").read_text())
    positive_lookup = {doc_id: i for i, doc_id in enumerate(document_ids)}
    positive_indices = [positive_lookup[x] for x in manifest["positive_document_ids"]]
    coarse = p1.mean_scores(queries, documents)
    candidate_indices: list[np.ndarray] = []
    for qi, scores in enumerate(coarse):
        selected = np.argsort(-scores)[: args.candidates].tolist()
        if positive_indices[qi] not in selected:
            selected[-1] = positive_indices[qi]
        candidate_indices.append(np.asarray(selected, dtype=np.int32))

    rep_specs = [
        next(rep for rep in p1.REPRESENTATIONS if rep.name == name)
        for name in ("raw_fp16", "raw_int8", "light_f9_int8")
    ]
    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    for rep in rep_specs:
        base = p1.representation_arrays(documents, rep, args.p0_p1_artifacts / "merged_cache")
        scored, serialized = p1.materialize_representation(args.p0_p1_artifacts / "objects", rep, base)
        row_bytes = int(serialized[0]["row_bytes"])
        rep_cells = [p1.maxsim_cells(query, scored) for query in queries]
        for layout in ("spatial_contiguous", "centroid_grouped", "representative_first"):
            all_pages = [pack_pages(x, row_bytes, layout) for x in scored]
            synopses = [page_synopses(x, pages) for x, pages in zip(scored, all_pages, strict=True)]
            all_centroids = [x[0] for x in synopses]
            all_radii = [x[1] for x in synopses]
            synopsis_path = args.artifacts / "synopses" / f"{rep.name}_{layout}.bin"
            synopsis_bytes = serialize_synopses(synopsis_path, all_centroids, all_radii, all_pages)
            data_bytes = sum(int(row["actual_serialized_bytes"]) for row in serialized)
            for qi, candidates in enumerate(candidate_indices):
                cells = rep_cells[qi][candidates]
                reveal, returned = p1.col_bandit(cells, min(args.top_k, len(candidates) - 1), 0.2, p1.SEED + qi)
                true_top = set(np.argsort(-cells.sum(axis=1))[: args.top_k].tolist())
                outer_overlap = len(true_top & set(returned.tolist())) / args.top_k
                for schedule in ("sequential", "active_batch_greedy"):
                    pages_read = 0
                    oracle_pages = 0
                    full_pages = 0
                    useful_rows = 0
                    bound_seconds = 0.0
                    score_seconds = 0.0
                    tightened = 0
                    active_cells = int(reveal.sum())
                    exact_flags: list[float] = []
                    candidate_synopsis_records = 0
                    for local_doc, global_doc in enumerate(candidates):
                        active_tokens = np.flatnonzero(reveal[local_doc])
                        if len(active_tokens) == 0:
                            continue
                        q = queries[qi][active_tokens]
                        pages = all_pages[int(global_doc)]
                        candidate_synopsis_records += len(pages)
                        full_pages += len(pages)
                        maxima = np.argmax(q @ scored[int(global_doc)].T, axis=1)
                        token_to_page = np.empty(len(scored[int(global_doc)]), dtype=np.int32)
                        for page_id, indices in enumerate(pages):
                            token_to_page[indices] = page_id
                        oracle_pages += len(set(token_to_page[maxima].tolist()))
                        metrics = safe_search(
                            q,
                            scored[int(global_doc)],
                            pages,
                            all_centroids[int(global_doc)],
                            all_radii[int(global_doc)],
                            schedule,
                        )
                        pages_read += int(metrics["pages"])
                        useful_rows += int(metrics["useful_bytes_rows"])
                        bound_seconds += float(metrics["bound_seconds"])
                        score_seconds += float(metrics["score_seconds"])
                        tightened += int(metrics["tightened_cells"])
                        exact_flags.append(float(metrics["inner_exact"]))
                    detail_rows.append(
                        {
                            "representation": rep.name,
                            "layout": layout,
                            "schedule": schedule,
                            "query": qi,
                            "active_documents": int(np.any(reveal, axis=1).sum()),
                            "active_cells": active_cells,
                            "full_pages": full_pages,
                            "page_oracle_pages": oracle_pages,
                            "safe_pages": pages_read,
                            "safe_fraction_of_full": pages_read / full_pages,
                            "oracle_fraction_of_full": oracle_pages / full_pages,
                            "useful_token_bytes": useful_rows * row_bytes,
                            "transferred_bytes": pages_read * p1.PAGE_BYTES,
                            "useful_fraction": useful_rows * row_bytes / max(pages_read * p1.PAGE_BYTES, 1),
                            "synopsis_bytes_total": synopsis_bytes,
                            "candidate_synopsis_bytes": candidate_synopsis_records * SYNOPSIS_RECORD_BYTES,
                            "synopsis_fraction_of_data": synopsis_bytes / data_bytes,
                            "bound_cpu_ms": bound_seconds * 1000.0,
                            "page_score_cpu_ms": score_seconds * 1000.0,
                            "tightened_cells_per_page": tightened / max(pages_read, 1),
                            "inner_exact_fraction": float(np.mean(exact_flags)),
                            "outer_topk_overlap": outer_overlap,
                        }
                    )
            selected = [r for r in detail_rows if r["representation"] == rep.name and r["layout"] == layout]
            for schedule in ("sequential", "active_batch_greedy"):
                policy = [r for r in selected if r["schedule"] == schedule]
                summary_rows.append(
                    {
                        "representation": rep.name,
                        "layout": layout,
                        "schedule": schedule,
                        **{
                            key: float(np.mean([float(row[key]) for row in policy]))
                            for key in (
                                "full_pages",
                                "page_oracle_pages",
                                "safe_pages",
                                "safe_fraction_of_full",
                                "oracle_fraction_of_full",
                                "useful_fraction",
                                "synopsis_bytes_total",
                                "candidate_synopsis_bytes",
                                "synopsis_fraction_of_data",
                                "bound_cpu_ms",
                                "page_score_cpu_ms",
                                "tightened_cells_per_page",
                                "inner_exact_fraction",
                                "outer_topk_overlap",
                            )
                        },
                    }
                )
    write_csv(args.results / "p2_detail.csv", detail_rows)
    write_csv(args.results / "p2_summary.csv", summary_rows)
    output = {"seed": p1.SEED, "synopsis_record_bytes": SYNOPSIS_RECORD_BYTES, "summary": summary_rows}
    (args.results / "p2_summary.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
