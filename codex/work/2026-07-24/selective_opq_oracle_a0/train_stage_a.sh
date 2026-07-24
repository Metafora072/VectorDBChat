#!/usr/bin/env bash
set -euo pipefail

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
SOURCE=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
GEN=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/utils/generate_pq
BASE="${SOURCE}/converted/gist_base.bin"
TRAIN="${SOURCE}/pq_training/shared_sample.bin"
GRAPH="${SOURCE}/index/shared/gist_shared_disk.index"

mkdir -p "${DATA}/index" "${DATA}/tmp" "${WORK}/logs" "${WORK}/results"

data_source=$(findmnt -n -o SOURCE -T "${DATA}")
if [[ "${data_source}" != "/dev/nvme8n1" ]]; then
  echo "DATA root is not on /dev/nvme8n1" >&2
  exit 4
fi
avail_kib=$(df --output=avail "${DATA}" | tail -n 1)
if (( avail_kib < 4 * 1024 * 1024 )); then
  echo "less than 4 GiB available on data NVMe" >&2
  exit 4
fi

pids=()
labels=()
for chunks in 40 48 56; do
  label="opq${chunks}"
  dir="${DATA}/index/${label}"
  prefix="${dir}/gist_${label}"
  mkdir -p "${dir}"
  if [[ ! -e "${prefix}_disk.index" ]]; then
    ln -s "${GRAPH}" "${prefix}_disk.index"
  fi
  if [[ -e "${prefix}_pq_pivots.bin" || -e "${prefix}_pq_compressed.bin" ]]; then
    echo "refusing to overwrite existing ${label} artifacts" >&2
    exit 3
  fi
  (
    env TMPDIR="${DATA}/tmp" OMP_NUM_THREADS=24 \
      PQR_KMEANS_SEED=20260724 \
      /usr/bin/time -v -o "${WORK}/logs/train_${label}.time" \
      "${GEN}" float "${BASE}" "${prefix}" "${chunks}" 1.0 1 "${TRAIN}" \
      >"${WORK}/logs/train_${label}.log" 2>&1
  ) &
  pids+=("$!")
  labels+=("${label}")
done

failed=0
for index in "${!pids[@]}"; do
  if ! wait "${pids[$index]}"; then
    echo "${labels[$index]} failed" >&2
    failed=1
  fi
done
if (( failed != 0 )); then
  exit 5
fi

date -u +%Y-%m-%dT%H:%M:%SZ >"${WORK}/results/training_complete.utc"
