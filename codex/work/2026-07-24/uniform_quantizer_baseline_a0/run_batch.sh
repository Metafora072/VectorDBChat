#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 PHASE LABEL REPEAT" >&2
  exit 2
fi

PHASE=$1
LABEL=$2
REPEAT=$3

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0
A0_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
SOURCE_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index

case "${LABEL}" in
  opq32) INDEX="${DATA_ROOT}/index/opq32/gist_opq32" ;;
  opq64) INDEX="${DATA_ROOT}/index/opq64/gist_opq64" ;;
  *) echo "invalid label: ${LABEL}" >&2; exit 2 ;;
esac

if [[ "${PHASE}" == "canary" ]]; then
  QUERY="${SOURCE_DATA}/converted/gist_query_canary200.bin"
  SEARCH_L=(100 200 400 800)
elif [[ "${PHASE}" == "full" ]]; then
  QUERY="${SOURCE_DATA}/converted/gist_query.bin"
  SEARCH_L=(50 100 200 400 800)
else
  echo "invalid phase: ${PHASE}" >&2
  exit 2
fi

GT="${SOURCE_DATA}/converted/gist_gt100.truthset"
WARMUP="${SOURCE_DATA}/converted/gist_query_warmup900_999.bin"
PREFIX="${PHASE}_${LABEL}_r${REPEAT}"
RAW_DIR="${DATA_ROOT}/results/raw"
METRICS="${RAW_DIR}/${PREFIX}.csv"
RESULT="${DATA_ROOT}/results/search/${PREFIX}"
LOG="${WORK_ROOT}/logs/${PREFIX}.log"
TIME_LOG="${WORK_ROOT}/logs/${PREFIX}.time"
SUMMARY="${WORK_ROOT}/results/${PREFIX}_summary.csv"

mkdir -p "${RAW_DIR}" "${DATA_ROOT}/results/search" \
  "${WORK_ROOT}/results/per_query" "${WORK_ROOT}/logs"
if [[ -e "${METRICS}" || -e "${SUMMARY}" ]]; then
  echo "refusing to overwrite existing run: ${PREFIX}" >&2
  exit 3
fi

env TMPDIR="${DATA_ROOT}/tmp" \
  P10_NAV_MODE=pq \
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
  -K 10 -L "${SEARCH_L[@]}" -W 4 \
  --num_nodes_to_cache 0 --num_threads 1 \
  > "${LOG}" 2>&1

python3 "${A0_ROOT}/scripts/summarize_run.py" \
  --phase "${PHASE}" --label "${LABEL}" --mode pq \
  --repeat "${REPEAT}" --dimension 960 \
  --metrics "${METRICS}" --time-log "${TIME_LOG}" \
  --output "${SUMMARY}"

gzip -c "${METRICS}" > \
  "${WORK_ROOT}/results/per_query/${PREFIX}.csv.gz"

