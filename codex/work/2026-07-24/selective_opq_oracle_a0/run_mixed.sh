#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 L budget selector" >&2
  exit 2
fi
L=$1
BUDGET=$2
SELECTOR=$3
case "${L}" in 50|100|200|400|800) ;; *) exit 2 ;; esac
case "${BUDGET}" in 40|48|56) ;; *) exit 2 ;; esac
case "${SELECTOR}" in random|visit_frequency|distance_regret|routing_aware) ;; *) exit 2 ;; esac

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
SOURCE=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
OPQ=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
SEARCH=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index
PRIMARY="${OPQ}/index/opq32/gist_opq32"
SELECTION="${DATA}/selectors/L${L}/${SELECTOR}_b${BUDGET}.u8"
LABEL="mixed_L${L}_b${BUDGET}_${SELECTOR}"
METRICS="${DATA}/results/${LABEL}.csv"
RESULT="${DATA}/results/search/${LABEL}"
LOG="${WORK}/logs/${LABEL}.log"

mkdir -p "${DATA}/results/search" "${DATA}/tmp" "${WORK}/logs"
if [[ ! -f "${SELECTION}" ]]; then echo "missing selection ${SELECTION}" >&2; exit 3; fi
if [[ -e "${METRICS}" || -e "${METRICS}.gz" ]]; then exit 3; fi
env TMPDIR="${DATA}/tmp" \
  MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  PQR_OPQ_ROTATION_IMPL=v1 PQR_ENABLE_WARMUP=0 \
  SOPQ_SECONDARY_PIVOTS="${OPQ}/index/opq64/gist_opq64_pq_pivots.bin" \
  SOPQ_SECONDARY_CODES="${OPQ}/index/opq64/gist_opq64_pq_compressed.bin" \
  SOPQ_MODE=mixed SOPQ_SELECTION_PATH="${SELECTION}" \
  P10_METRICS_PATH="${METRICS}" \
  "${SEARCH}" \
  --data_type float --dist_fn l2 \
  --index_path_prefix "${PRIMARY}" \
  --result_path "${RESULT}" \
  --query_file "${SOURCE}/converted/gist_query.bin" \
  --gt_file "${SOURCE}/converted/gist_gt100.truthset" \
  -K 10 -L "${L}" -W 4 \
  --num_nodes_to_cache 0 --num_threads 1 \
  >"${LOG}" 2>&1
gzip -1 "${METRICS}"
