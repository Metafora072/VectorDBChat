#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0
SOURCE_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724

g++ -O3 -std=c++17 "${WORK_ROOT}/rotation_bench.cpp" \
  -o "${WORK_ROOT}/results/rotation_bench"
for label in opq32 opq64; do
  "${WORK_ROOT}/results/rotation_bench" \
    "${DATA_ROOT}/index/${label}/gist_${label}_pq_pivots.bin_rotation_matrix.bin" \
    "${SOURCE_DATA}/converted/gist_query.bin" \
    > "${WORK_ROOT}/results/rotation_${label}.json"
done
