#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 LABEL MODE REPEAT" >&2
  exit 2
fi

LABEL=$1
MODE=$2
REPEAT=$3

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery
A0_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DISCOVERY_DATA_ROOT="${DATA_ROOT}/discovery"
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index
QUERY="${DATA_ROOT}/converted/gist_query.bin"
WARMUP="${DATA_ROOT}/converted/gist_query_warmup900_999.bin"
GT="${DATA_ROOT}/converted/gist_gt100.truthset"
FULL="${DATA_ROOT}/converted/gist_base.bin"
PREFIX="discovery_${LABEL}_r${REPEAT}"
RAW_DIR="${DISCOVERY_DATA_ROOT}/raw"
METRICS="${RAW_DIR}/${PREFIX}.csv"
RESULT="${DISCOVERY_DATA_ROOT}/search/${PREFIX}"
LOG="${WORK_ROOT}/logs/${PREFIX}.log"
TIME_LOG="${WORK_ROOT}/logs/${PREFIX}.time"
SUMMARY="${WORK_ROOT}/results/${PREFIX}_summary.csv"

case "${LABEL}" in
  pq16) INDEX="${DATA_ROOT}/index/pq16/gist_pq16" ;;
  pq32) INDEX="${DATA_ROOT}/index/pq32/gist_pq32" ;;
  pq64) INDEX="${DATA_ROOT}/index/pq64/gist_pq64" ;;
  exact) INDEX="${DATA_ROOT}/index/pq16/gist_pq16" ;;
  *) echo "invalid label: ${LABEL}" >&2; exit 2 ;;
esac

mkdir -p "${RAW_DIR}" "${DISCOVERY_DATA_ROOT}/search" \
  "${WORK_ROOT}/results/per_query" "${WORK_ROOT}/logs"
if [[ -e "${METRICS}" || -e "${SUMMARY}" ]]; then
  echo "refusing to overwrite existing run: ${PREFIX}" >&2
  exit 3
fi

mode_env=(P10_NAV_MODE="${MODE}")
if [[ "${MODE}" == "exact" ]]; then
  mode_env+=(P10_FULL_DATA="${FULL}")
fi

env TMPDIR="${DATA_ROOT}/tmp" \
  "${mode_env[@]}" \
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
  -K 10 -L 50 100 200 400 800 -W 4 \
  --num_nodes_to_cache 0 --num_threads 1 \
  > "${LOG}" 2>&1

python3 "${A0_ROOT}/scripts/summarize_run.py" \
  --phase discovery --label "${LABEL}" --mode "${MODE}" \
  --repeat "${REPEAT}" --dimension 960 \
  --metrics "${METRICS}" --time-log "${TIME_LOG}" \
  --output "${SUMMARY}"

gzip -c "${METRICS}" > \
  "${WORK_ROOT}/results/per_query/${PREFIX}.csv.gz"

