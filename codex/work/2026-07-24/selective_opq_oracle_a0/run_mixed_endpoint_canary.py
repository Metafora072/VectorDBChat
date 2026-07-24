#!/usr/bin/env python3
"""Verify mixed-mode all-low/all-high routing against adapter endpoints."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
OPQ = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724")
SEARCH = Path(
    "/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/"
    "p07_page_bonus_a0/trace_build/apps/search_disk_index"
)

canary = DATA / "canary"
canary.mkdir(parents=True, exist_ok=True)
for name, value in (("all_low", 0), ("all_high", 1)):
    selection = canary / f"{name}.u8"
    mm = np.memmap(selection, dtype="u1", mode="w+", shape=(1_000_000,))
    mm[:] = value
    mm.flush()
    del mm
    result = canary / f"mixed_{name}"
    env = os.environ.copy()
    env.update(
        {
            "TMPDIR": str(DATA / "tmp"),
            "MKL_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "PQR_OPQ_ROTATION_IMPL": "v1",
            "PQR_ENABLE_WARMUP": "0",
            "SOPQ_SECONDARY_PIVOTS": str(
                OPQ / "index/opq64/gist_opq64_pq_pivots.bin"
            ),
            "SOPQ_SECONDARY_CODES": str(
                OPQ / "index/opq64/gist_opq64_pq_compressed.bin"
            ),
            "SOPQ_MODE": "mixed",
            "SOPQ_SELECTION_PATH": str(selection),
        }
    )
    command = [
        str(SEARCH),
        "--data_type",
        "float",
        "--dist_fn",
        "l2",
        "--index_path_prefix",
        str(OPQ / "index/opq32/gist_opq32"),
        "--result_path",
        str(result),
        "--query_file",
        str(SOURCE / "converted/gist_query_canary200.bin"),
        "--gt_file",
        str(SOURCE / "converted/gist_gt100.truthset"),
        "-K",
        "10",
        "-L",
        "100",
        "-W",
        "4",
        "--num_nodes_to_cache",
        "0",
        "--num_threads",
        "1",
    ]
    with (WORK / f"logs/mixed_{name}_canary.log").open("w") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

for name, endpoint in (("all_low", "low"), ("all_high", "high")):
    actual = np.memmap(
        canary / f"mixed_{name}_100_idx_uint32.bin", dtype="<u4", mode="r", offset=8
    )
    expected = np.memmap(
        canary / f"adapter_{endpoint}_100_idx_uint32.bin",
        dtype="<u4",
        mode="r",
        offset=8,
    )
    if not np.array_equal(actual, expected):
        raise SystemExit(f"mixed {name} endpoint mismatch")

print("mixed selection endpoint parity passed")
