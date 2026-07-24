#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 L low|high" >&2
  exit 2
fi
L=$1
MODE=$2
case "${L}" in 50|100|200|400|800) ;; *) exit 2 ;; esac
case "${MODE}" in low|high) ;; *) exit 2 ;; esac

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
SOURCE=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
OPQ=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index

PRIMARY="${OPQ}/index/opq32/gist_opq32"
SECONDARY_PIVOTS="${OPQ}/index/opq64/gist_opq64_pq_pivots.bin"
SECONDARY_CODES="${OPQ}/index/opq64/gist_opq64_pq_compressed.bin"
QUERY="${SOURCE}/converted/gist_query.bin"
GT="${SOURCE}/converted/gist_gt100.truthset"
RAW="${DATA}/trace/L${L}_${MODE}.bin"
METRICS="${DATA}/trace/L${L}_${MODE}_metrics.csv"
RESULT="${DATA}/trace/search/L${L}_${MODE}"
LOG="${WORK}/logs/trace_L${L}_${MODE}.log"

mkdir -p "${DATA}/trace/search" "${DATA}/tmp" "${WORK}/logs"
if [[ -e "${RAW}" || -e "${RAW}.gz" || -e "${METRICS}" ]]; then
  echo "refusing to overwrite trace L${L} ${MODE}" >&2
  exit 3
fi

env TMPDIR="${DATA}/tmp" \
  MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  PQR_OPQ_ROTATION_IMPL=v1 PQR_ENABLE_WARMUP=0 \
  SOPQ_SECONDARY_PIVOTS="${SECONDARY_PIVOTS}" \
  SOPQ_SECONDARY_CODES="${SECONDARY_CODES}" \
  SOPQ_MODE="${MODE}" SOPQ_TRACE_PATH="${RAW}" \
  P10_METRICS_PATH="${METRICS}" \
  "${SEARCH}" \
  --data_type float --dist_fn l2 \
  --index_path_prefix "${PRIMARY}" \
  --result_path "${RESULT}" \
  --query_file "${QUERY}" --gt_file "${GT}" \
  -K 10 -L "${L}" -W 4 \
  --num_nodes_to_cache 0 --num_threads 1 \
  >"${LOG}" 2>&1

gzip -1 "${RAW}"
gzip -1 "${METRICS}"
