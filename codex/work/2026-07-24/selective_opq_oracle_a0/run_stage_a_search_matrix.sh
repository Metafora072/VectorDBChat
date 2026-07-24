#!/usr/bin/env bash
set -euo pipefail

WORK=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724
# Training began at 2026-07-24 11:58:39 UTC. Stop all Stage-A work at 10 h.
HARD_STOP_EPOCH=1784930319

check_limits() {
  if (( $(date -u +%s) >= HARD_STOP_EPOCH )); then
    echo "Stage-A 10 h hard wall reached" >&2
    exit 124
  fi
  local bytes
  bytes=$(du -sb "${DATA}" | awk '{print $1}')
  if (( bytes > 2 * 1024 * 1024 * 1024 )); then
    echo "Stage-A new-NVMe cap exceeded: ${bytes} bytes" >&2
    exit 125
  fi
}

for budget in 40 48 56; do
  check_limits
  echo "UNIFORM budget=${budget} started $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${WORK}/run_uniform.sh" "${budget}"
done

for search_l in 50 100 200 400 800; do
  for budget in 40 48 56; do
    for selector in random visit_frequency distance_regret routing_aware; do
      check_limits
      echo "MIXED L=${search_l} budget=${budget} selector=${selector} started $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      "${WORK}/run_mixed.sh" "${search_l}" "${budget}" "${selector}"
    done
  done
done

check_limits
date -u +%Y-%m-%dT%H:%M:%SZ >"${WORK}/results/search_matrix_complete.utc"
