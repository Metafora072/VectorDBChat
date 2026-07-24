#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 IMPL REPEAT" >&2
  exit 2
fi

IMPL=$1
REPEAT=$2
case "${IMPL}" in
  v0|v1|v2) ;;
  *) echo "invalid impl: ${IMPL}" >&2; exit 2 ;;
esac

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/dense_opq_kernel_gate_a0
A0_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
SOURCE_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
OPQ_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/dense_opq_kernel_gate_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index

QUERY="${SOURCE_DATA}/converted/gist_query.bin"
GT="${SOURCE_DATA}/converted/gist_gt100.truthset"
WARMUP="${SOURCE_DATA}/converted/gist_query_warmup900_999.bin"
INDEX="${OPQ_DATA}/index/opq32/gist_opq32"
PREFIX="full_${IMPL}_r${REPEAT}"
RAW_DIR="${DATA_ROOT}/results/raw"
METRICS="${RAW_DIR}/${PREFIX}.csv"
RESULT="${DATA_ROOT}/results/search/${PREFIX}"
LOG="${WORK_ROOT}/logs/${PREFIX}.log"
TIME_LOG="${WORK_ROOT}/logs/${PREFIX}.time"
SUMMARY="${WORK_ROOT}/results/${PREFIX}_summary.csv"

mkdir -p "${RAW_DIR}" "${DATA_ROOT}/results/search" "${DATA_ROOT}/tmp" \
  "${WORK_ROOT}/results/per_query" "${WORK_ROOT}/logs"
if [[ -e "${METRICS}" || -e "${SUMMARY}" ]]; then
  echo "refusing to overwrite existing run: ${PREFIX}" >&2
  exit 3
fi

env TMPDIR="${DATA_ROOT}/tmp" \
  MKL_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 \
  P10_NAV_MODE=pq \
  PQR_OPQ_ROTATION_IMPL="${IMPL}" \
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
  --phase full --label "${IMPL}" --mode pq \
  --repeat "${REPEAT}" --dimension 960 \
  --metrics "${METRICS}" --time-log "${TIME_LOG}" \
  --output "${SUMMARY}"

gzip -c "${METRICS}" > "${WORK_ROOT}/results/per_query/${PREFIX}.csv.gz"
