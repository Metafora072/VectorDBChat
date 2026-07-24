#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/dense_opq_kernel_gate_a0
SOURCE_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
OPQ_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
SRC=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/dense_opq_kernel_gate_a0/rotation_kernel_bench.cpp
BIN="${WORK_ROOT}/rotation_kernel_bench"
OUT="${WORK_ROOT}/results/rotation_kernel_bench.jsonl"
PERF_OUT="${WORK_ROOT}/results/rotation_kernel_bench.perf.txt"

mkdir -p "${WORK_ROOT}/results" "${WORK_ROOT}/logs"
g++ -O3 -march=native -DDISKANN_USE_SYSTEM_BLAS \
  -I/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/DiskANN_trace/include \
  "${SRC}" /usr/lib/x86_64-linux-gnu/libblas.so.3 -o "${BIN}"

env MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${BIN}" \
  "${OPQ_DATA}/index/opq32/gist_opq32_pq_pivots.bin_rotation_matrix.bin" \
  "${SOURCE_DATA}/converted/gist_query.bin" \
  "${OUT}" > "${WORK_ROOT}/logs/rotation_kernel_bench.log" 2>&1

if command -v perf >/dev/null 2>&1; then
  env MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    perf stat -x, -e cycles,instructions \
    "${BIN}" \
    "${OPQ_DATA}/index/opq32/gist_opq32_pq_pivots.bin_rotation_matrix.bin" \
    "${SOURCE_DATA}/converted/gist_query.bin" \
    "${WORK_ROOT}/results/rotation_kernel_bench_perf_run.jsonl" \
    > "${WORK_ROOT}/logs/rotation_kernel_bench_perf.log" 2> "${PERF_OUT}" || true
fi
