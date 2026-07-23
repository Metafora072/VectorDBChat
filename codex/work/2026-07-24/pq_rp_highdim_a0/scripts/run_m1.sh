#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
# shellcheck source=../config.env
source "${WORK_ROOT}/config.env"

export TMPDIR="${DATA_ROOT}/tmp"
BASE="${SELECTED_BASE}"
M0="${WORK_ROOT}/results/m0_gist_audit.json"
BUILD=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/build_disk_index
GEN=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/utils/generate_pq
SHARED="${DATA_ROOT}/index/shared/${SELECTED_STEM}_shared"
SAMPLE="${DATA_ROOT}/pq_training/shared_sample.bin"
IDS="${DATA_ROOT}/pq_training/shared_sample_ids.bin"

SOURCE="$(findmnt -T "${DATA_ROOT}" -n -o SOURCE | head -n 1)"
[[ "${SOURCE}" == "/dev/nvme8n1" ]] || { echo "hard stop: ${SOURCE}" >&2; exit 2; }
python3 - "${M0}" <<'PY'
import json, sys
if json.load(open(sys.argv[1]))["status"] != "PASS":
    raise SystemExit("Cohere M0 did not pass")
PY

mkdir -p "${TMPDIR}" "${DATA_ROOT}/index/shared" "${DATA_ROOT}/pq_training" \
  "${WORK_ROOT}/logs" "${WORK_ROOT}/results"

if [[ ! -s "${IDS}" || ! -s "${SAMPLE}" ]]; then
  python3 "${WORK_ROOT}/scripts/prepare_shared_sample.py" \
    --base "${BASE}" --rows "${PQ_SAMPLE_ROWS}" --seed "${PQ_SAMPLE_SEED}" \
    --ids "${IDS}" --sample "${SAMPLE}" \
    --manifest "${WORK_ROOT}/results/shared_sample_manifest.json"
fi

if [[ ! -s "${SHARED}_disk.index" ]]; then
  /usr/bin/time -v -o "${WORK_ROOT}/logs/m1_graph.time" \
    "${BUILD}" \
    --data_type float --dist_fn l2 \
    --data_path "${BASE}" --index_path_prefix "${SHARED}" \
    -R "${BUILD_R}" -L "${BUILD_L}" -B 0.1 -M "${BUILD_DRAM_GB}" \
    -T "${BUILD_THREADS}" --build_PQ_bytes 0 \
    > "${WORK_ROOT}/logs/m1_graph.log" 2>&1
fi

for code_bytes in 16 32 64; do
  out_dir="${DATA_ROOT}/index/pq${code_bytes}"
  prefix="${out_dir}/${SELECTED_STEM}_pq${code_bytes}"
  mkdir -p "${out_dir}"
  if [[ ! -s "${prefix}_pq_pivots.bin" || ! -s "${prefix}_pq_compressed.bin" ]]; then
    /usr/bin/time -v -o "${WORK_ROOT}/logs/m1_pq${code_bytes}.time" \
      "${GEN}" float "${BASE}" "${prefix}" "${code_bytes}" 0.1 0 "${SAMPLE}" \
      > "${WORK_ROOT}/logs/m1_pq${code_bytes}.log" 2>&1
  fi
  if [[ ! -e "${prefix}_disk.index" ]]; then
    ln -s "${SHARED}_disk.index" "${prefix}_disk.index"
  fi
done

python3 "${WORK_ROOT}/scripts/m1_audit.py" \
  --data-root "${DATA_ROOT}" \
  --dimension "${SELECTED_DIM}" \
  --stem "${SELECTED_STEM}" \
  --output "${WORK_ROOT}/results/m1_artifact_audit.json"
