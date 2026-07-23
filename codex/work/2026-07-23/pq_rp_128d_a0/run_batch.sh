#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
    echo "usage: $0 PHASE LABEL MODE INDEX_PREFIX QUERY GT REPEAT" >&2
    exit 2
fi

PHASE=$1
LABEL=$2
MODE=$3
INDEX=$4
QUERY=$5
GT=$6
REPEAT=$7

ROOT=/home/ubuntu/pz/VectorDB/chat
WORK="$ROOT/codex/work/2026-07-23/pq_rp_128d_a0"
SEARCH="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/search_disk_index"
FULL=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin
PREFIX="${PHASE}_${LABEL}_r${REPEAT}"
METRICS="$WORK/results/per_query/${PREFIX}.csv"
RESULT="$WORK/results/${PREFIX}"
LOG="$WORK/logs/${PREFIX}.log"
TIME_LOG="$WORK/logs/${PREFIX}.time"

mkdir -p "$WORK/results/per_query" "$WORK/logs"
rm -f "$METRICS"

mode_env=(P10_NAV_MODE="$MODE")
if [[ "$MODE" == "exact" ]]; then
    mode_env+=(P10_FULL_DATA="$FULL")
fi

env "${mode_env[@]}" \
    PQR_ENABLE_WARMUP=1 \
    PQR_WARMUP_FILE="$QUERY" \
    PQR_WARMUP_COUNT=200 \
    P10_METRICS_PATH="$METRICS" \
    /usr/bin/time -v -o "$TIME_LOG" \
    "$SEARCH" \
    --data_type float --dist_fn l2 \
    --index_path_prefix "$INDEX" \
    --result_path "$RESULT" \
    --query_file "$QUERY" --gt_file "$GT" \
    -K 10 -L 50 100 150 200 300 -W 4 \
    --num_nodes_to_cache 0 --num_threads 1 \
    >"$LOG" 2>&1

python3 "$WORK/scripts/summarize_run.py" \
    --phase "$PHASE" --label "$LABEL" --mode "$MODE" --repeat "$REPEAT" \
    --metrics "$METRICS" --time-log "$TIME_LOG" \
    --output "$WORK/results/${PREFIX}_summary.csv"

gzip -kf "$METRICS"
