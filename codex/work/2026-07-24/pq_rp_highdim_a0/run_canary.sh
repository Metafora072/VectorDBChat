#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
# shellcheck source=config.env
source "${WORK_ROOT}/config.env"
QUERY="${SELECTED_CANARY_QUERY}"
GT="${SELECTED_GT}"

python3 - "${WORK_ROOT}/results/m1_artifact_audit.json" <<'PY'
import json, sys
if json.load(open(sys.argv[1]))["status"] != "PASS":
    raise SystemExit("M1 artifact audit did not pass")
PY

for repeat in 1 2; do
  "${WORK_ROOT}/run_batch.sh" canary pq32 pq \
    "${DATA_ROOT}/index/pq32/${SELECTED_STEM}_pq32" "${QUERY}" "${GT}" "${repeat}"
  "${WORK_ROOT}/run_batch.sh" canary pq64 pq \
    "${DATA_ROOT}/index/pq64/${SELECTED_STEM}_pq64" "${QUERY}" "${GT}" "${repeat}"
  "${WORK_ROOT}/run_batch.sh" canary exact exact \
    "${DATA_ROOT}/index/pq16/${SELECTED_STEM}_pq16" "${QUERY}" "${GT}" "${repeat}"
done

python3 "${WORK_ROOT}/check_canary.py"
