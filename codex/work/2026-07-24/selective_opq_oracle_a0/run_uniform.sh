#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then echo "usage: $0 40|48|56" >&2; exit 2; fi
CHUNKS=$1
case "${CHUNKS}" in 40|48|56) ;; *) exit 2 ;; esac

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
SOURCE=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index
INDEX="${DATA}/index/opq${CHUNKS}/gist_opq${CHUNKS}"
METRICS="${DATA}/results/uniform_opq${CHUNKS}.csv"
RESULT="${DATA}/results/search/uniform_opq${CHUNKS}"
LOG="${WORK}/logs/uniform_opq${CHUNKS}.log"

mkdir -p "${DATA}/results/search" "${DATA}/tmp" "${WORK}/logs"
if [[ -e "${METRICS}" || -e "${METRICS}.gz" ]]; then exit 3; fi
env TMPDIR="${DATA}/tmp" \
  MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  PQR_OPQ_ROTATION_IMPL=v1 PQR_ENABLE_WARMUP=0 \
  P10_METRICS_PATH="${METRICS}" \
  "${SEARCH}" \
  --data_type float --dist_fn l2 \
  --index_path_prefix "${INDEX}" \
  --result_path "${RESULT}" \
  --query_file "${SOURCE}/converted/gist_query.bin" \
  --gt_file "${SOURCE}/converted/gist_gt100.truthset" \
  -K 10 -L 50 100 200 400 800 -W 4 \
  --num_nodes_to_cache 0 --num_threads 1 \
  >"${LOG}" 2>&1
gzip -1 "${METRICS}"
