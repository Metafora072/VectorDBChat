#!/usr/bin/env bash
set -euo pipefail

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
SOURCE=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
OPQ=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index

mkdir -p "${DATA}/canary" "${DATA}/tmp" "${WORK}/logs"
for mode in low high; do
  env TMPDIR="${DATA}/tmp" \
    MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PQR_OPQ_ROTATION_IMPL=v1 PQR_ENABLE_WARMUP=0 \
    SOPQ_SECONDARY_PIVOTS="${OPQ}/index/opq64/gist_opq64_pq_pivots.bin" \
    SOPQ_SECONDARY_CODES="${OPQ}/index/opq64/gist_opq64_pq_compressed.bin" \
    SOPQ_MODE="${mode}" \
    "${SEARCH}" \
    --data_type float --dist_fn l2 \
    --index_path_prefix "${OPQ}/index/opq32/gist_opq32" \
    --result_path "${DATA}/canary/adapter_${mode}" \
    --query_file "${SOURCE}/converted/gist_query_canary200.bin" \
    --gt_file "${SOURCE}/converted/gist_gt100.truthset" \
    -K 10 -L 100 -W 4 --num_nodes_to_cache 0 --num_threads 1 \
    >"${WORK}/logs/adapter_${mode}_canary.log" 2>&1
done

python3 - <<'PY'
from pathlib import Path
import numpy as np
root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB")
stage = root / "selective_opq_oracle_a0_0724/canary"
prior = root / "uniform_quantizer_baseline_a0_0724/results/search"
checks = {
    "low": prior / "canary_opq32_r1_100_idx_uint32.bin",
    "high": prior / "canary_opq64_r1_100_idx_uint32.bin",
}
for mode, reference in checks.items():
    actual = np.memmap(stage / f"adapter_{mode}_100_idx_uint32.bin", dtype="<u4", mode="r", offset=8)
    expected = np.memmap(reference, dtype="<u4", mode="r", offset=8)
    if not np.array_equal(actual, expected):
        mismatch = int(np.count_nonzero(actual != expected))
        raise SystemExit(f"{mode} endpoint mismatch: {mismatch}")
print("adapter endpoint parity passed")
PY
