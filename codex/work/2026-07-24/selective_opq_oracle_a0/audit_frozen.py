#!/usr/bin/env python3
"""Audit Stage-A frozen inputs and the reusable OPQ32/64 artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
OPQ = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724")

PATHS = {
    "graph": SOURCE / "index/shared/gist_shared_disk.index",
    "base": SOURCE / "converted/gist_base.bin",
    "query": SOURCE / "converted/gist_query.bin",
    "gt": SOURCE / "converted/gist_gt100.truthset",
    "training": SOURCE / "pq_training/shared_sample.bin",
    "training_ids": SOURCE / "pq_training/shared_sample_ids.bin",
}
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


def load_chunks(pivots: Path) -> np.ndarray:
    with pivots.open("rb") as handle:
        rows, cols = struct.unpack("<II", handle.read(8))
        if (rows, cols) != (4, 1):
            raise RuntimeError(f"unexpected pivot metadata: {(rows, cols)}")
        offsets = np.fromfile(handle, dtype="<u8", count=4)
    rows, cols = header(pivots, int(offsets[2]))
    return np.memmap(
        pivots, dtype="<u4", mode="r", offset=int(offsets[2]) + 8, shape=(rows * cols,)
    )


report: dict[str, object] = {
    "stage": "SELECTIVE-OPQ-ORACLE-A0-STAGE-A",
    "gpu": 0,
    "inputs": {},
    "opq": {},
}
for label, path in PATHS.items():
    digest = sha256(path)
    report["inputs"][label] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest,
        "shape": list(header(path)) if label != "graph" else None,
    }
    if label in EXPECTED and digest != EXPECTED[label]:
        raise RuntimeError(f"{label} SHA mismatch: {digest}")

if header(PATHS["base"]) != (1_000_000, 960):
    raise RuntimeError("base shape mismatch")
if header(PATHS["query"]) != (1_000, 960):
    raise RuntimeError("query shape mismatch")
if header(PATHS["gt"]) != (1_000, 100):
    raise RuntimeError("GT shape mismatch")
if header(PATHS["training"]) != (100_000, 960):
    raise RuntimeError("training shape mismatch")

for chunks in (32, 64):
    label = f"opq{chunks}"
    prefix = OPQ / f"index/{label}/gist_{label}"
    codes = Path(f"{prefix}_pq_compressed.bin")
    pivots = Path(f"{prefix}_pq_pivots.bin")
    rotation = Path(f"{pivots}_rotation_matrix.bin")
    offsets = load_chunks(pivots)
    if header(codes) != (1_000_000, chunks):
        raise RuntimeError(f"{label} code shape mismatch")
    if header(rotation) != (960, 960):
        raise RuntimeError(f"{label} rotation shape mismatch")
    if len(offsets) != chunks + 1 or int(offsets[0]) != 0 or int(offsets[-1]) != 960:
        raise RuntimeError(f"{label} chunk offsets mismatch")
    report["opq"][label] = {
        "codes": str(codes),
        "codes_sha256": sha256(codes),
        "pivots": str(pivots),
        "pivots_sha256": sha256(pivots),
        "rotation": str(rotation),
        "rotation_sha256": sha256(rotation),
        "chunk_widths": np.diff(offsets).astype(int).tolist(),
    }

data_mount = os.statvfs("/home/ubuntu/pz/VectorDB/data")
report["available_nvme_bytes"] = data_mount.f_bavail * data_mount.f_frsize
report["passed"] = True
(WORK / "results/frozen_audit.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(report, indent=2, sort_keys=True))
