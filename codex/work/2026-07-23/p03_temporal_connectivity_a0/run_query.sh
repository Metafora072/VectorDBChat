#!/usr/bin/env bash
set -euo pipefail

work_root=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$work_root/../../../.." && pwd)
pipeann_root="$repo_root/codex/work/2026-07-22/graph_aging_a0/PipeANN"
binary="$pipeann_root/build-a0/tests/p03_query_a0"
nvme_root="/home/ubuntu/pz/VectorDB/data/VectorDB/p03_temporal_connectivity_a0_0723/full"
dataset_root="/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas"
result_root="$work_root/results/full"
log_root="$work_root/logs/full"
mkdir -p "$result_root" "$log_root"

run_one() {
  local variant=$1
  local seed=$2
  "$binary" --index "$nvme_root/indexes/${variant}_seed${seed}.index" \
    --query "$dataset_root/datasets/sift1m/query.bin" \
    --gt "$dataset_root/groundtruth/sift1m/smoke/gt_100.bin" \
    --cohort-size 250000 --nqueries 10000 --search-L 96 --threads 12 \
    --seed "$seed" --label "${variant}_seed${seed}" \
    > "$result_root/query_${variant}_seed${seed}.json" \
    2> "$log_root/query_${variant}_seed${seed}.log"
}

for seed in 11 22 33; do
  run_one static "$seed" & static_pid=$!
  run_one time "$seed" & time_pid=$!
  run_one shuffle "$seed" & shuffle_pid=$!
  wait "$static_pid"
  wait "$time_pid"
  wait "$shuffle_pid"
done

: > "$result_root/query_metrics.jsonl"
for seed in 11 22 33; do
  for variant in static time shuffle; do
    sed -n '1p' "$result_root/query_${variant}_seed${seed}.json" >> "$result_root/query_metrics.jsonl"
  done
done
python3 "$work_root/summarize_query.py" --input "$result_root/query_metrics.jsonl" \
  --output "$result_root/query_summary.json" > "$log_root/query_summary.log"
