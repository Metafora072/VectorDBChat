#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/pq_rp_128d_a0"
ART=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_128d_a0_0723
QUERY="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/queries_1000.bin"
GT="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/results/gt_1000_top100"

for repeat in 1 2; do
    "$WORK/run_batch.sh" canary pq16 pq "$ART/sift1m_pq16" "$QUERY" "$GT" "$repeat"
    "$WORK/run_batch.sh" canary exact exact "$ART/sift1m_pq16" "$QUERY" "$GT" "$repeat"
done

python3 "$WORK/check_canary.py"

