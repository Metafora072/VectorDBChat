#!/usr/bin/env python3
"""Audit Stage-A OPQ40/48/56 artifacts after training."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724")
GRAPH = SOURCE / "index/shared/gist_shared_disk.index"


def header(path: Path, offset: int = 0) -> tuple[int, int]:
    with path.open("rb") as handle:
        handle.seek(offset)
        return struct.unpack("<II", handle.read(8))


def chunks_from_pivots(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        if struct.unpack("<II", handle.read(8)) != (4, 1):
            raise RuntimeError("bad pivot metadata")
        offsets = np.fromfile(handle, dtype="<u8", count=4)
    rows, cols = header(path, int(offsets[2]))
    return np.memmap(
        path, dtype="<u4", mode="r", offset=int(offsets[2]) + 8, shape=(rows * cols,)
    )


expected_widths = {
    40: [24] * 40,
    48: [20] * 48,
    56: [18] * 8 + [17] * 48,
}
report: dict[str, object] = {"representations": {}}
for chunks, widths in expected_widths.items():
    label = f"opq{chunks}"
    prefix = DATA / f"index/{label}/gist_{label}"
    graph = Path(f"{prefix}_disk.index")
    pivots = Path(f"{prefix}_pq_pivots.bin")
    rotation_path = Path(f"{pivots}_rotation_matrix.bin")
    codes = Path(f"{prefix}_pq_compressed.bin")
    if not graph.is_symlink() or graph.resolve() != GRAPH.resolve():
        raise RuntimeError(f"{label}: graph link mismatch")
    offsets = chunks_from_pivots(pivots)
    actual_widths = np.diff(offsets).astype(int).tolist()
    if actual_widths != widths:
        raise RuntimeError(f"{label}: chunk widths mismatch")
    if header(codes) != (1_000_000, chunks):
        raise RuntimeError(f"{label}: code shape mismatch")
    if header(rotation_path) != (960, 960):
        raise RuntimeError(f"{label}: rotation shape mismatch")
    rotation = np.memmap(
        rotation_path, dtype="<f4", mode="r", offset=8, shape=(960, 960)
    )
    gram = np.asarray(rotation, dtype=np.float64).T @ np.asarray(rotation, dtype=np.float64)
    orth_max = float(np.max(np.abs(gram - np.eye(960))))
    if orth_max > 2e-4:
        raise RuntimeError(f"{label}: orthogonality failure {orth_max}")
    log = (WORK / f"logs/train_{label}.log").read_text()
    timing = re.search(
        r"PQR_TIMING train_seconds=([0-9.eE+-]+) code_seconds=([0-9.eE+-]+)", log
    )
    time_log = (WORK / f"logs/train_{label}.time").read_text()
    rss = re.search(r"Maximum resident set size \(kbytes\):\s+(\d+)", time_log)
    report["representations"][label] = {
        "chunk_widths": actual_widths,
        "rotation_orthogonality_max_abs": orth_max,
        "code_bytes": codes.stat().st_size,
        "pivot_bytes": pivots.stat().st_size,
        "rotation_bytes": rotation_path.stat().st_size,
        "training_seconds": float(timing.group(1)) if timing else None,
        "code_seconds": float(timing.group(2)) if timing else None,
        "peak_rss_kib": int(rss.group(1)) if rss else None,
    }

report["passed"] = True
(WORK / "results/trained_artifact_audit.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(report, indent=2, sort_keys=True))
