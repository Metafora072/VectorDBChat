#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/p10_pq_corridor_a0"
PQ16=/home/ubuntu/pz/VectorDB/data/VectorDB/p10_pq_corridor_a0_0723/sift1m_pq16

for required in "${PQ16}_pq_pivots.bin" "${PQ16}_pq_compressed.bin" "${PQ16}_disk.index"; do
    if [[ ! -e "$required" ]]; then
        echo "missing PQ16 artifact: $required" >&2
        exit 1
    fi
done

run() {
    P10_INDEX="$PQ16" "$WORK/run_variant.sh" "$@"
}

run pq16_pq_l100_w2 pq 100 2
run pq16_exact_l100_w2 exact 100 2
run pq16_early1_l100_w2 early 100 2 1
run pq16_early2_l100_w2 early 100 2 2
run pq16_early4_l100_w2 early 100 2 4
run pq16_early8_l100_w2 early 100 2 8

late_start=$(python3 "$WORK/scripts/choose_late_start.py" "$WORK/results/pq16_pq_l100_w2.csv" --exact-blocks 4)
run pq16_late4_l100_w2 late 100 2 0 "$late_start"
run pq16_pq_l100_w4 pq 100 4
run pq16_pq_l150_w4 pq 150 4
run pq16_pq_l200_w4 pq 200 4

python3 "$WORK/analyze_p10.py" --tag pq16_
