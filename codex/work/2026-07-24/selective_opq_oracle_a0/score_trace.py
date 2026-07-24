#!/usr/bin/env python3
"""Merge low/high endpoint traces and build per-L Stage-A selectors."""

from __future__ import annotations

import argparse
import gzip
import json
import struct
import time
from pathlib import Path

import numpy as np

SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
OPQ = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724")
WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
N = 1_000_000
DIM = 960
BUDGETS = {40: 250_000, 48: 500_000, 56: 750_000}
HEADER = struct.Struct("<QIII")


def bin_header(path: Path, offset: int = 0) -> tuple[int, int]:
    with path.open("rb") as handle:
        handle.seek(offset)
        return struct.unpack("<II", handle.read(8))


def embedded(path: Path, dtype: str, offset: int) -> np.ndarray:
    rows, cols = bin_header(path, offset)
    return np.memmap(path, dtype=dtype, mode="r", offset=offset + 8, shape=(rows, cols))


def load_model(
    chunks: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    prefix = OPQ / f"index/opq{chunks}/gist_opq{chunks}"
    pivots_path = Path(f"{prefix}_pq_pivots.bin")
    with pivots_path.open("rb") as handle:
        rows, cols = struct.unpack("<II", handle.read(8))
        if (rows, cols) != (4, 1):
            raise RuntimeError("bad pivot header")
        offsets = np.fromfile(handle, dtype="<u8", count=4)
    pivots = embedded(pivots_path, "<f4", int(offsets[0]))
    centroid = embedded(pivots_path, "<f4", int(offsets[1])).reshape(-1)
    chunk_offsets = embedded(pivots_path, "<u4", int(offsets[2])).reshape(-1)
    rotation_path = Path(f"{pivots_path}_rotation_matrix.bin")
    rotation = np.memmap(rotation_path, dtype="<f4", mode="r", offset=8, shape=(DIM, DIM))
    code_path = Path(f"{prefix}_pq_compressed.bin")
    codes = np.memmap(code_path, dtype="u1", mode="r", offset=8, shape=(N, chunks))
    return pivots, centroid, chunk_offsets, rotation, codes


def adc_table(
    query: np.ndarray,
    pivots: np.ndarray,
    centroid: np.ndarray,
    offsets: np.ndarray,
    rotation: np.ndarray,
) -> np.ndarray:
    transformed = (query - centroid) @ rotation
    table = np.empty((len(offsets) - 1, 256), dtype=np.float32)
    for chunk, (lo, hi) in enumerate(zip(offsets[:-1], offsets[1:])):
        diff = np.asarray(pivots[:, int(lo) : int(hi)]) - transformed[int(lo) : int(hi)]
        table[chunk] = np.einsum("ij,ij->i", diff, diff, optimize=True)
    return table


def read_record(handle: gzip.GzipFile) -> tuple[int, int, np.ndarray, np.ndarray] | None:
    raw = handle.read(HEADER.size)
    if not raw:
        return None
    if len(raw) != HEADER.size:
        raise RuntimeError("truncated trace header")
    qid, search_l, node_count, pair_count = HEADER.unpack(raw)
    nodes_raw = handle.read(node_count * 4)
    pairs_raw = handle.read(pair_count * 8)
    if len(nodes_raw) != node_count * 4 or len(pairs_raw) != pair_count * 8:
        raise RuntimeError("truncated trace payload")
    nodes = np.frombuffer(nodes_raw, dtype="<u4").copy()
    pairs = np.frombuffer(pairs_raw, dtype="<u8").copy()
    return int(qid), int(search_l), nodes, pairs


def lookup(table: np.ndarray, codes: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    selected = np.asarray(codes[nodes]).T
    return table[np.arange(table.shape[0])[:, None], selected].sum(axis=0, dtype=np.float32)


def exact_distances(base: np.ndarray, query: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    result = np.empty(len(nodes), dtype=np.float32)
    for start in range(0, len(nodes), 4096):
        end = min(start + 4096, len(nodes))
        diff = np.asarray(base[nodes[start:end]], dtype=np.float32) - query
        result[start:end] = np.einsum("ij,ij->i", diff, diff, optimize=True)
    return result


def score_stats(values: np.ndarray) -> dict[str, float | int]:
    percentiles = np.percentile(values, [25, 50, 75, 90, 95, 99])
    return {
        "count": int(values.size),
        "min": float(values.min()),
        "p25": float(percentiles[0]),
        "median": float(percentiles[1]),
        "p75": float(percentiles[2]),
        "p90": float(percentiles[3]),
        "p95": float(percentiles[4]),
        "p99": float(percentiles[5]),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std()),
        "zero_fraction": float(np.mean(values == 0)),
        "positive_fraction": float(np.mean(values > 0)),
    }


def deterministic_top(scores: np.ndarray, count: int) -> np.ndarray:
    node_ids = np.arange(N, dtype=np.int32)
    sortable = np.asarray(scores, dtype=np.float64)
    order = np.lexsort((node_ids, -sortable))
    return order[:count]


def save_selection(
    selector: str,
    search_l: int,
    budget: int,
    chosen: np.ndarray,
    visits: np.ndarray,
    score: np.ndarray,
) -> dict[str, object]:
    selected = np.zeros(N, dtype=np.uint8)
    selected[chosen] = 1
    out_dir = DATA / "selectors" / f"L{search_l}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{selector}_b{budget}.u8"
    selected.tofile(path)
    total_visits = int(visits.sum())
    selected_visits = int(visits[chosen].sum())
    visited_mask = visits > 0
    return {
        "path": str(path),
        "selected_nodes": int(len(chosen)),
        "selected_trace_visits": selected_visits,
        "all_trace_visits": total_visits,
        "visit_coverage": float(selected_visits / total_visits) if total_visits else 0.0,
        "selected_unique_visited": int(np.count_nonzero(visited_mask[chosen])),
        "all_unique_visited": int(np.count_nonzero(visited_mask)),
        "selected_score_sum": float(score[chosen].sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--L", type=int, required=True)
    args = parser.parse_args()
    search_l = args.L
    if search_l not in (50, 100, 200, 400, 800):
        raise SystemExit("invalid L")

    base = np.memmap(
        SOURCE / "converted/gist_base.bin", dtype="<f4", mode="r", offset=8, shape=(N, DIM)
    )
    queries = np.memmap(
        SOURCE / "converted/gist_query.bin", dtype="<f4", mode="r", offset=8, shape=(1000, DIM)
    )
    p32, c32, o32, r32, codes32 = load_model(32)
    p64, c64, o64, r64, codes64 = load_model(64)

    score_dr = np.zeros(N, dtype=np.float64)
    score_ra = np.zeros(N, dtype=np.float64)
    visits = np.zeros(N, dtype=np.uint64)
    trace_summary = {
        "queries": 0,
        "union_node_events": 0,
        "union_boundary_events": 0,
    }
    timing = {
        "adc_and_lookup_seconds": 0.0,
        "exact_distance_seconds": 0.0,
        "score_accumulation_seconds": 0.0,
        "selection_and_write_seconds": 0.0,
    }
    total_started = time.perf_counter()

    low_path = DATA / f"trace/L{search_l}_low.bin.gz"
    high_path = DATA / f"trace/L{search_l}_high.bin.gz"
    with gzip.open(low_path, "rb") as low, gzip.open(high_path, "rb") as high:
        while True:
            low_record = read_record(low)
            high_record = read_record(high)
            if low_record is None and high_record is None:
                break
            if low_record is None or high_record is None:
                raise RuntimeError("endpoint trace length mismatch")
            qid0, l0, nodes0, pairs0 = low_record
            qid1, l1, nodes1, pairs1 = high_record
            if qid0 != qid1 or l0 != search_l or l1 != search_l:
                raise RuntimeError("endpoint trace identity mismatch")

            nodes = np.union1d(nodes0, nodes1).astype(np.uint32, copy=False)
            pairs = np.union1d(pairs0, pairs1).astype(np.uint64, copy=False)
            query = np.asarray(queries[qid0], dtype=np.float32)
            started = time.perf_counter()
            table32 = adc_table(query, p32, c32, o32, r32)
            table64 = adc_table(query, p64, c64, o64, r64)
            d32 = lookup(table32, codes32, nodes)
            d64 = lookup(table64, codes64, nodes)
            timing["adc_and_lookup_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            exact = exact_distances(base, query, nodes)
            timing["exact_distance_seconds"] += time.perf_counter() - started

            started = time.perf_counter()
            delta = np.square(d32 - exact, dtype=np.float64) - np.square(
                d64 - exact, dtype=np.float64
            )
            np.add.at(score_dr, nodes, delta)
            np.add.at(visits, nodes, 1)

            if len(pairs):
                a = (pairs >> np.uint64(32)).astype(np.uint32)
                b = (pairs & np.uint64(0xFFFFFFFF)).astype(np.uint32)
                ai = np.searchsorted(nodes, a)
                bi = np.searchsorted(nodes, b)
                if np.any(nodes[ai] != a) or np.any(nodes[bi] != b):
                    raise RuntimeError("boundary node absent from union node trace")
                y = exact[ai] < exact[bi]
                y0 = d32[ai] < d32[bi]
                ya = d64[ai] < d32[bi]
                yb = d32[ai] < d64[bi]
                np.add.at(score_ra, a, (y0 != y).astype(np.int8) - (ya != y).astype(np.int8))
                np.add.at(score_ra, b, (y0 != y).astype(np.int8) - (yb != y).astype(np.int8))
            timing["score_accumulation_seconds"] += time.perf_counter() - started

            trace_summary["queries"] += 1
            trace_summary["union_node_events"] += int(len(nodes))
            trace_summary["union_boundary_events"] += int(len(pairs))

    if trace_summary["queries"] != 1000:
        raise RuntimeError("incomplete full-query trace")

    score_dir = DATA / "scores"
    score_dir.mkdir(parents=True, exist_ok=True)
    np.save(score_dir / f"L{search_l}_distance_regret.npy", score_dr)
    np.save(score_dir / f"L{search_l}_routing_aware.npy", score_ra)
    np.save(score_dir / f"L{search_l}_visit_frequency.npy", visits)

    rng = np.random.default_rng(20260724 + search_l)
    random_order = rng.permutation(N)
    selection_started = time.perf_counter()
    report: dict[str, object] = {
        "L": search_l,
        "trace": trace_summary,
        "score_distributions": {
            "distance_regret": score_stats(score_dr),
            "routing_aware": score_stats(score_ra),
            "visit_frequency": score_stats(visits.astype(np.float64)),
        },
        "selectors": {},
    }
    for budget, count in BUDGETS.items():
        choices = {
            "random": random_order[:count],
            "visit_frequency": deterministic_top(visits, count),
            "distance_regret": deterministic_top(score_dr, count),
            "routing_aware": deterministic_top(score_ra, count),
        }
        report["selectors"][str(budget)] = {}
        for selector, chosen in choices.items():
            score = {
                "random": np.zeros(N, dtype=np.float64),
                "visit_frequency": visits,
                "distance_regret": score_dr,
                "routing_aware": score_ra,
            }[selector]
            report["selectors"][str(budget)][selector] = save_selection(
                selector, search_l, budget, chosen, visits, score
            )
    timing["selection_and_write_seconds"] = time.perf_counter() - selection_started
    timing["total_seconds"] = time.perf_counter() - total_started
    report["timing"] = timing

    output = WORK / "results" / f"selector_L{search_l}.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
