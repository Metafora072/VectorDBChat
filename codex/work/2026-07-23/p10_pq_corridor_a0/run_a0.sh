#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/p10_pq_corridor_a0"
SEARCH="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index"
INDEX="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/index/sift1m"
QUERY="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/queries_1000.bin"
FULL=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin

mkdir -p "$WORK/logs" "$WORK/results" "$WORK/traces"

RUN="$WORK/run_variant.sh"

"$RUN" pq_l100_w2 pq 100 2
"$RUN" exact_l100_w2 exact 100 2
"$RUN" early1_l100_w2 early 100 2 1
"$RUN" early2_l100_w2 early 100 2 2
"$RUN" early4_l100_w2 early 100 2 4
"$RUN" early8_l100_w2 early 100 2 8

late_start=$(python3 "$WORK/scripts/choose_late_start.py" "$WORK/results/pq_l100_w2.csv" --exact-blocks 4)
"$RUN" late4_l100_w2 late 100 2 0 "$late_start"

"$RUN" pq_l100_w4 pq 100 4
"$RUN" pq_l150_w4 pq 150 4
"$RUN" pq_l200_w4 pq 200 4

python3 "$WORK/analyze_p10.py"
