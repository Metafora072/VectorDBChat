#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/dense_opq_kernel_gate_a0
mkdir -p "${WORK_ROOT}/results" "${WORK_ROOT}/logs"
date +%s > "${WORK_ROOT}/results/start_epoch.txt"

"${WORK_ROOT}/run_kernel_bench.sh"
for repeat in 1 2; do
  for impl in v0 v1 v2; do
    "${WORK_ROOT}/run_search_variant.sh" "${impl}" "${repeat}"
  done
done

python3 "${WORK_ROOT}/analyze_dense_opq.py" > "${WORK_ROOT}/results/analysis_stdout.json"
date +%s > "${WORK_ROOT}/results/end_epoch.txt"
