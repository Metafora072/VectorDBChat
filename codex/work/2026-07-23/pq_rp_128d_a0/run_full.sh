#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/pq_rp_128d_a0"
ART=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_128d_a0_0723
QUERY=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin
GT="$ART/sift1m_official_gt100.truthset"

python3 - "$WORK/results/canary_gate.json" <<'PY'
import json
import sys
if json.load(open(sys.argv[1]))["status"] != "PASS":
    raise SystemExit("canary did not pass")
PY

for repeat in 1 2 3; do
    "$WORK/run_batch.sh" full pq8 pq "$ART/sift1m_pq8" "$QUERY" "$GT" "$repeat"
    "$WORK/run_batch.sh" full pq16 pq "$ART/sift1m_pq16" "$QUERY" "$GT" "$repeat"
    "$WORK/run_batch.sh" full pq32 pq "$ART/sift1m_pq32" "$QUERY" "$GT" "$repeat"
    "$WORK/run_batch.sh" full exact exact "$ART/sift1m_pq16" "$QUERY" "$GT" "$repeat"
done

python3 "$WORK/analyze_results.py"
