#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 || $# -gt 6 ]]; then
    echo "usage: $0 NAME MODE L BEAM [EARLY_BLOCKS] [LATE_START]" >&2
    exit 2
fi

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/p10_pq_corridor_a0"
SEARCH="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index"
INDEX=${P10_INDEX:-"$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/index/sift1m"}
QUERY="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/queries_1000.bin"
FULL=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin

name=$1
mode=$2
list_size=$3
beam=$4
early_blocks=${5:-0}
late_start=${6:-4294967295}

mkdir -p "$WORK/logs" "$WORK/results" "$WORK/traces"
rm -f "$WORK/traces/$name.tsv"
env P10_NAV_MODE="$mode" \
    P10_FULL_DATA="$FULL" \
    P10_EARLY_BLOCKS="$early_blocks" \
    P10_LATE_START_BLOCK="$late_start" \
    P10_TRACE_PATH="$WORK/traces/$name.tsv" \
    P10_METRICS_PATH="$WORK/results/$name.csv" \
    "$SEARCH" \
    --data_type float --dist_fn l2 \
    --index_path_prefix "$INDEX" \
    --result_path "$WORK/results/$name" \
    --query_file "$QUERY" -K 10 -L "$list_size" -W "$beam" \
    --num_nodes_to_cache 0 --num_threads 1 \
    >"$WORK/logs/$name.log" 2>&1
