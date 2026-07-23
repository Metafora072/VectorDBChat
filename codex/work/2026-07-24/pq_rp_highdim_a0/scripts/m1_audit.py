#!/usr/bin/env python3
"""Audit one shared graph, shared PQ sample, and PQ16/32/64 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_pivots(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with path.open("rb") as handle:
        nr, nc = struct.unpack("<II", handle.read(8))
        offsets = np.frombuffer(handle.read(nr * nc * 8), dtype="<u8")
        if nr not in (4, 5) or nc != 1:
            raise ValueError(f"{path}: invalid offset table {nr}x{nc}")
        handle.seek(int(offsets[0]))
        centers, dim = struct.unpack("<II", handle.read(8))
        tables = np.frombuffer(handle.read(centers * dim * 4), dtype="<f4").reshape(centers, dim)
        handle.seek(int(offsets[1]))
        c_rows, c_cols = struct.unpack("<II", handle.read(8))
        centroid = np.frombuffer(handle.read(c_rows * c_cols * 4), dtype="<f4")
        chunk_index = 3 if nr == 5 else 2
        handle.seek(int(offsets[chunk_index]))
        o_rows, o_cols = struct.unpack("<II", handle.read(8))
        chunk_offsets = np.frombuffer(handle.read(o_rows * o_cols * 4), dtype="<u4")
    if centers != 256 or len(centroid) != dim or chunk_offsets[-1] != dim:
        raise ValueError(f"{path}: inconsistent pivot dimensions")
    return tables, centroid, chunk_offsets


def matrix(path: Path, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        rows, dim = struct.unpack("<II", handle.read(8))
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(rows, dim))


parser = argparse.ArgumentParser()
parser.add_argument("--data-root", type=Path, required=True)
parser.add_argument("--dimension", type=int, required=True)
parser.add_argument("--stem", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

graph = args.data_root / f"index/shared/{args.stem}_shared_disk.index"
sample = matrix(args.data_root / "pq_training/shared_sample.bin", np.dtype("<f4"))
ids = matrix(args.data_root / "pq_training/shared_sample_ids.bin", np.dtype("<u4")).reshape(-1)
if sample.shape != (100_000, args.dimension) or len(ids) != 100_000:
    raise ValueError("shared sample has wrong shape")

graph_realpaths = {}
artifacts = {}
for code_bytes in (16, 32, 64):
    prefix = args.data_root / f"index/pq{code_bytes}/{args.stem}_pq{code_bytes}"
    disk = Path(str(prefix) + "_disk.index")
    pivots = Path(str(prefix) + "_pq_pivots.bin")
    compressed = Path(str(prefix) + "_pq_compressed.bin")
    graph_realpaths[str(code_bytes)] = os.path.realpath(disk)
    if os.path.realpath(disk) != str(graph):
        raise ValueError(f"PQ{code_bytes} does not share the frozen graph")

    codes = matrix(compressed, np.dtype("u1"))
    if codes.shape != (1_000_000, code_bytes):
        raise ValueError(f"PQ{code_bytes}: code shape {codes.shape}")
    tables, centroid, offsets = load_pivots(pivots)
    if len(offsets) != code_bytes + 1:
        raise ValueError(f"PQ{code_bytes}: pivot chunk count mismatch")
    if not np.isfinite(tables).all() or not np.isfinite(centroid).all():
        raise ValueError(f"PQ{code_bytes}: non-finite pivots")

    sample_codes = np.asarray(codes[ids], dtype=np.uint8)
    errors = np.zeros(len(sample), dtype=np.float64)
    for chunk in range(code_bytes):
        start, stop = int(offsets[chunk]), int(offsets[chunk + 1])
        reconstructed = tables[sample_codes[:, chunk], start:stop] + centroid[start:stop]
        delta = np.asarray(sample[:, start:stop]) - reconstructed
        errors += np.einsum("ij,ij->i", delta, delta)

    artifacts[str(code_bytes)] = {
        "code_bytes": code_bytes,
        "bits_per_dimension": 8.0 * code_bytes / args.dimension,
        "raw_float_compression": args.dimension * 4 / code_bytes,
        "pq_resident_bytes": compressed.stat().st_size - 8,
        "compressed_sha256": sha256(compressed),
        "pivots_sha256": sha256(pivots),
        "reconstruction_l2sq": {
            "median": float(np.median(errors)),
            "p90": float(np.quantile(errors, 0.90)),
            "p99": float(np.quantile(errors, 0.99)),
            "mean": float(np.mean(errors)),
        },
    }

result = {
    "status": "PASS",
    "graph": str(graph),
    "graph_bytes": graph.stat().st_size,
    "graph_sha256": sha256(graph),
    "graph_realpaths": graph_realpaths,
    "all_graph_realpaths_identical": len(set(graph_realpaths.values())) == 1,
    "shared_sample_ids_sha256": sha256(args.data_root / "pq_training/shared_sample_ids.bin"),
    "shared_sample_sha256": sha256(args.data_root / "pq_training/shared_sample.bin"),
    "artifacts": artifacts,
    "exact_nav": {
        "auxiliary_code_bytes": 16,
        "auxiliary_pq_resident_bytes": 16_000_000,
        "full_vector_resident_bytes": 1_000_000 * args.dimension * 4,
    },
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
