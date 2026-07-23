#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
  echo "usage: $0 PHASE LABEL MODE INDEX_PREFIX QUERY GT REPEAT" >&2
  exit 2
fi

PHASE=$1
LABEL=$2
MODE=$3
INDEX=$4
QUERY=$5
GT=$6
REPEAT=$7

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
# shellcheck source=config.env
source "${WORK_ROOT}/config.env"
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index
FULL="${SELECTED_BASE}"
WARMUP="${SELECTED_WARMUP_QUERY}"
PREFIX="${PHASE}_${LABEL}_r${REPEAT}"
RAW_DIR="${DATA_ROOT}/results/raw"
METRICS="${RAW_DIR}/${PREFIX}.csv"
RESULT="${DATA_ROOT}/results/search/${PREFIX}"
LOG="${WORK_ROOT}/logs/${PREFIX}.log"
TIME_LOG="${WORK_ROOT}/logs/${PREFIX}.time"
SUMMARY="${WORK_ROOT}/results/${PREFIX}_summary.csv"

mkdir -p "${RAW_DIR}" "${DATA_ROOT}/results/search" "${WORK_ROOT}/results/per_query" "${WORK_ROOT}/logs"
rm -f "${METRICS}"

if [[ "${PHASE}" == "canary" ]]; then
  SEARCH_L=(100 200 400 800)
elif [[ "${PHASE}" == "full" ]]; then
  SEARCH_L=(50 100 200 400 800)
else
  echo "invalid phase: ${PHASE}" >&2
  exit 2
fi

mode_env=(P10_NAV_MODE="${MODE}")
if [[ "${MODE}" == "exact" ]]; then
  mode_env+=(P10_FULL_DATA="${FULL}")
fi

env "${mode_env[@]}" \
  PQR_ENABLE_WARMUP=1 \
  PQR_WARMUP_FILE="${WARMUP}" \
  PQR_WARMUP_COUNT=100 \
  P10_METRICS_PATH="${METRICS}" \
  /usr/bin/time -v -o "${TIME_LOG}" \
  "${SEARCH}" \
  --data_type float --dist_fn l2 \
  --index_path_prefix "${INDEX}" \
  --result_path "${RESULT}" \
  --query_file "${QUERY}" --gt_file "${GT}" \
  -K 10 -L "${SEARCH_L[@]}" -W "${SEARCH_W}" \
  --num_nodes_to_cache 0 --num_threads "${SEARCH_THREADS}" \
  > "${LOG}" 2>&1

python3 "${WORK_ROOT}/scripts/summarize_run.py" \
  --phase "${PHASE}" --label "${LABEL}" --mode "${MODE}" --repeat "${REPEAT}" \
  --dimension "${SELECTED_DIM}" --metrics "${METRICS}" --time-log "${TIME_LOG}" \
  --output "${SUMMARY}"

gzip -c "${METRICS}" > "${WORK_ROOT}/results/per_query/${PREFIX}.csv.gz"
