#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0

mkdir -p "${WORK_ROOT}/results" "${WORK_ROOT}/logs"
date +%s > "${WORK_ROOT}/results/start_epoch.txt"
"${WORK_ROOT}/train_opq.sh"

"${WORK_ROOT}/run_batch.sh" canary opq32 1
"${WORK_ROOT}/run_batch.sh" canary opq64 1
python3 "${WORK_ROOT}/audit_artifacts.py"
"${WORK_ROOT}/run_rotation_bench.sh"

for repeat in 1 2; do
  "${WORK_ROOT}/run_batch.sh" full opq32 "${repeat}"
  "${WORK_ROOT}/run_batch.sh" full opq64 "${repeat}"
done

triggered=$(python3 "${WORK_ROOT}/check_repeats.py")
for label in ${triggered}; do
  "${WORK_ROOT}/run_batch.sh" full "${label}" 3
done

python3 "${WORK_ROOT}/analyze_opq.py" \
  > "${WORK_ROOT}/results/analysis_stdout.json"
date +%s > "${WORK_ROOT}/results/end_epoch.txt"
