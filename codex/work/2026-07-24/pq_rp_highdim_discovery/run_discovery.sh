#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
START_FILE="${WORK_ROOT}/results/start_epoch.txt"
END_FILE="${WORK_ROOT}/results/end_epoch.txt"

mkdir -p "${WORK_ROOT}/results"
date +%s > "${START_FILE}"

data_source=$(findmnt -n -o SOURCE -T "${DATA_ROOT}" | sort -u)
if [[ "${data_source}" != "/dev/nvme8n1" ]]; then
  echo "DATA_ROOT is not on /dev/nvme8n1" >&2
  exit 4
fi
avail_kib=$(df --output=avail "${DATA_ROOT}" | tail -n 1)
if (( avail_kib < 30 * 1024 * 1024 )); then
  echo "less than 30 GiB available on DATA_ROOT" >&2
  exit 4
fi

for repeat in 1 2; do
  "${WORK_ROOT}/run_batch.sh" pq16 pq "${repeat}"
  "${WORK_ROOT}/run_batch.sh" pq32 pq "${repeat}"
  "${WORK_ROOT}/run_batch.sh" pq64 pq "${repeat}"
  "${WORK_ROOT}/run_batch.sh" exact exact "${repeat}"
done

triggered=$(python3 "${WORK_ROOT}/check_repeats.py")
for label in ${triggered}; do
  mode=pq
  [[ "${label}" == "exact" ]] && mode=exact
  "${WORK_ROOT}/run_batch.sh" "${label}" "${mode}" 3
done

python3 "${WORK_ROOT}/analyze_discovery.py" \
  > "${WORK_ROOT}/results/analysis_stdout.json"
date +%s > "${END_FILE}"
