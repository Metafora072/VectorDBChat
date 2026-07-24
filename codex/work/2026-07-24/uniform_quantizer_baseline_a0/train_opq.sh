#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0
SOURCE_DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724
GEN=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/utils/generate_pq
BASE="${SOURCE_DATA}/converted/gist_base.bin"
TRAIN="${SOURCE_DATA}/pq_training/shared_sample.bin"
GRAPH="${SOURCE_DATA}/index/shared/gist_shared_disk.index"

mkdir -p "${DATA_ROOT}/index/opq32" "${DATA_ROOT}/index/opq64" \
  "${DATA_ROOT}/tmp" "${WORK_ROOT}/logs" "${WORK_ROOT}/results"

data_source=$(findmnt -n -o SOURCE -T "${DATA_ROOT}" | sort -u)
if [[ "${data_source}" != "/dev/nvme8n1" ]]; then
  echo "DATA_ROOT is not on /dev/nvme8n1" >&2
  exit 4
fi
avail_kib=$(df --output=avail "${DATA_ROOT}" | tail -n 1)
if (( avail_kib < 30 * 1024 * 1024 )); then
  echo "less than 30 GiB available" >&2
  exit 4
fi

pids=()
labels=()
for bytes in 32 64; do
  prefix="${DATA_ROOT}/index/opq${bytes}/gist_opq${bytes}"
  if [[ ! -e "${prefix}_disk.index" ]]; then
    ln -s "${GRAPH}" "${prefix}_disk.index"
  fi
  if [[ -e "${prefix}_pq_pivots.bin" || -e "${prefix}_pq_compressed.bin" ]]; then
    echo "refusing to overwrite existing OPQ artifacts for ${prefix}" >&2
    exit 3
  fi
  (
    env TMPDIR="${DATA_ROOT}/tmp" OMP_NUM_THREADS=24 \
      PQR_KMEANS_SEED=20260724 \
      /usr/bin/time -v -o "${WORK_ROOT}/logs/train_opq${bytes}.time" \
      "${GEN}" float "${BASE}" "${prefix}" "${bytes}" 1.0 1 "${TRAIN}" \
      > "${WORK_ROOT}/logs/train_opq${bytes}.log" 2>&1
  ) &
  pids+=("$!")
  labels+=("opq${bytes}")
done

for index in "${!pids[@]}"; do
  if ! wait "${pids[$index]}"; then
    echo "${labels[$index]} training failed" >&2
    for pid in "${pids[@]}"; do
      kill "${pid}" 2>/dev/null || true
    done
    exit 5
  fi
done
