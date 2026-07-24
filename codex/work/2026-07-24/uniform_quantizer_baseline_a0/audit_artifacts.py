#!/usr/bin/env python3
"""Audit frozen-graph OPQ artifacts and the 200-query canary."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724")
GRAPH = SOURCE / "index/shared/gist_shared_disk.index"
BASE = SOURCE / "converted/gist_base.bin"
GT = SOURCE / "converted/gist_gt100.truthset"
EXPECTED = {
    "graph": "52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37",
    "training": "2108aa0cfac2f409c16223ebfbd74ff34fb5dbf8b2cf2f57275de7c2bf07e857",
    "training_ids": "44b5794112f5aa4025d930d3403240de99df75a863054a9598ed02f7c157024f",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def header(path: Path, offset: int = 0) -> tuple[int, int]:
    with path.open("rb") as handle:
        handle.seek(offset)
        return struct.unpack("<II", handle.read(8))


def embedded(path: Path, dtype: str, offset: int) -> np.ndarray:
    rows, cols = header(path, offset)
    return np.memmap(path, dtype=dtype, mode="r", offset=offset + 8, shape=(rows, cols))


def load_pivots(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with path.open("rb") as handle:
        rows, cols = struct.unpack("<II", handle.read(8))
        if (rows, cols) != (4, 1):
            raise ValueError(f"unexpected pivot metadata in {path}: {(rows, cols)}")
        offsets = np.fromfile(handle, dtype="<u8", count=4)
    pivots = embedded(path, "<f4", int(offsets[0]))
    centroid = embedded(path, "<f4", int(offsets[1])).reshape(-1)
    chunks = embedded(path, "<u4", int(offsets[2])).reshape(-1)
    return pivots, centroid, chunks


gt_n, gt_k = header(GT)
gt_ids = np.memmap(GT, dtype="<u4", mode="r", offset=8, shape=(gt_n, gt_k))
base_n, base_d = header(BASE)
base = np.memmap(BASE, dtype="<f4", mode="r", offset=8, shape=(base_n, base_d))
sample_ids = np.random.default_rng(20260724).choice(base_n, size=2048, replace=False)

audit: dict[str, object] = {
    "frozen_graph": {
        "source_realpath": str(GRAPH.resolve()),
        "sha256": sha256(GRAPH),
        "expected_sha256": EXPECTED["graph"],
    },
    "shared_training": {
        "sha256": sha256(SOURCE / "pq_training/shared_sample.bin"),
        "ids_sha256": sha256(SOURCE / "pq_training/shared_sample_ids.bin"),
        "rows": header(SOURCE / "pq_training/shared_sample.bin")[0],
        "dimension": header(SOURCE / "pq_training/shared_sample.bin")[1],
    },
    "representations": {},
}
if audit["frozen_graph"]["sha256"] != EXPECTED["graph"]:
    raise RuntimeError("frozen graph SHA mismatch")
if audit["shared_training"]["sha256"] != EXPECTED["training"]:
    raise RuntimeError("shared training SHA mismatch")
if audit["shared_training"]["ids_sha256"] != EXPECTED["training_ids"]:
    raise RuntimeError("shared training ID SHA mismatch")

for code_bytes in (32, 64):
    label = f"opq{code_bytes}"
    prefix = DATA / f"index/{label}/gist_{label}"
    graph_link = Path(f"{prefix}_disk.index")
    piv_path = Path(f"{prefix}_pq_pivots.bin")
    rot_path = Path(f"{piv_path}_rotation_matrix.bin")
    code_path = Path(f"{prefix}_pq_compressed.bin")
    if graph_link.resolve() != GRAPH.resolve():
        raise RuntimeError(f"{label}: graph realpath mismatch")
    if not graph_link.is_symlink():
        raise RuntimeError(f"{label}: graph is not an explicit shared symlink")

    pivots, centroid, chunks = load_pivots(piv_path)
    rot_rows, rot_cols = header(rot_path)
    rotation = np.memmap(
        rot_path, dtype="<f4", mode="r", offset=8, shape=(rot_rows, rot_cols)
    )
    code_rows, code_cols = header(code_path)
    codes = np.memmap(
        code_path, dtype="u1", mode="r", offset=8, shape=(code_rows, code_cols)
    )
    if (rot_rows, rot_cols) != (960, 960):
        raise RuntimeError(f"{label}: wrong rotation shape")
    if (code_rows, code_cols) != (1_000_000, code_bytes):
        raise RuntimeError(f"{label}: wrong code shape")
    if tuple(chunks[[0, -1]]) != (0, 960) or len(chunks) != code_bytes + 1:
        raise RuntimeError(f"{label}: invalid chunk offsets")

    gram = np.asarray(rotation, dtype=np.float64).T @ np.asarray(rotation, dtype=np.float64)
    orth_max = float(np.max(np.abs(gram - np.eye(960))))
    if orth_max > 2e-4:
        raise RuntimeError(f"{label}: rotation is not sufficiently orthogonal: {orth_max}")

    original = np.asarray(base[sample_ids], dtype=np.float32)
    transformed = (original - np.asarray(centroid)) @ np.asarray(rotation)
    reconstructed = np.empty_like(transformed)
    selected_codes = np.asarray(codes[sample_ids])
    for chunk in range(code_bytes):
        lo, hi = int(chunks[chunk]), int(chunks[chunk + 1])
        reconstructed[:, lo:hi] = np.asarray(pivots)[selected_codes[:, chunk], lo:hi]
    l2_sq = np.sum((transformed - reconstructed) ** 2, axis=1)

    recalls = {}
    with gzip.open(WORK / f"results/per_query/canary_{label}_r1.csv.gz", "rt", newline="") as handle:
        raw = list(csv.DictReader(handle))
    for search_l in (100, 200, 400, 800):
        rows = [row for row in raw if int(row["L"]) == search_l]
        if len(rows) != 200:
            raise RuntimeError(f"{label} L{search_l}: incomplete canary")
        recall = []
        for row in rows:
            qid = int(row["qid"])
            returned = {int(row[f"id{k}"]) for k in range(10)}
            recall.append(len(returned & set(map(int, gt_ids[qid, :10]))) / 10)
        recalls[str(search_l)] = float(np.mean(recall))
    values = [recalls[str(search_l)] for search_l in (100, 200, 400, 800)]
    if any(right + 1e-12 < left for left, right in zip(values, values[1:])):
        raise RuntimeError(f"{label}: canary recall is not monotonic")

    timing_log = (WORK / f"logs/train_{label}.log").read_text()
    timing_match = re.search(
        r"PQR_TIMING train_seconds=([0-9.eE+-]+) code_seconds=([0-9.eE+-]+)",
        timing_log,
    )
    audit["representations"][label] = {
        "graph_realpath": str(graph_link.resolve()),
        "graph_sha256": audit["frozen_graph"]["sha256"],
        "rotation_shape": [rot_rows, rot_cols],
        "rotation_file_bytes": rot_path.stat().st_size,
        "rotation_orthogonality_max_abs": orth_max,
        "pivot_file_bytes": piv_path.stat().st_size,
        "code_shape": [code_rows, code_cols],
        "code_file_bytes": code_path.stat().st_size,
        "resident_bytes": (
            rot_path.stat().st_size + piv_path.stat().st_size + code_path.stat().st_size
        ),
        "reconstruction_l2_sq": {
            "sample_rows": len(sample_ids),
            "median": float(np.median(l2_sq)),
            "p90": float(np.percentile(l2_sq, 90)),
            "p99": float(np.percentile(l2_sq, 99)),
        },
        "canary_recall_at_10": recalls,
        "training_seconds": float(timing_match.group(1)) if timing_match else None,
        "code_generation_seconds": float(timing_match.group(2)) if timing_match else None,
    }

audit["passed"] = True
(WORK / "results/artifact_audit.json").write_text(
    json.dumps(audit, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(audit, indent=2, sort_keys=True))
