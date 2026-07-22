#!/usr/bin/env bash
set -euo pipefail

scale=${1:-smoke}
work_root=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$work_root/../../../.." && pwd)
pipeann_root="$repo_root/codex/work/2026-07-22/graph_aging_a0/PipeANN"
binary="$pipeann_root/build-a0/tests/graph_aging_a0"
analyzer="$pipeann_root/build-a0/tests/p03_graph_analyzer"
nvme_root="/home/ubuntu/pz/VectorDB/data/VectorDB/p03_temporal_connectivity_a0_0723"
source_root="/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m"

if [[ "$scale" == "smoke" ]]; then
  npoints=10000
  seeds=11
  expected_seeds=1
  input="/home/ubuntu/pz/VectorDB/data/VectorDB/graph_aging_a0_0722/smoke/data_10k.bin"
  threads=8
else
  npoints=1000000
  seeds=11,22,33
  expected_seeds=3
  input="$source_root/full_1m.bin"
  threads=12
fi
cohort_size=$((npoints / 4))
run_root="$nvme_root/$scale"
order_root="$run_root/orders"
result_root="$work_root/results/$scale"
log_root="$work_root/logs/$scale"
mkdir -p "$order_root" "$run_root/edges" "$run_root/indexes" "$result_root" "$log_root"

python3 "$work_root/prepare_orders.py" \
  --input "$input" --output-root "$order_root" --npoints "$npoints" --seeds "$seeds"

run_variant() {
  local variant=$1
  local seed=$2
  local data tags initial_tags
  if [[ "$variant" == "time" ]]; then
    data="$order_root/time_seed${seed}.bin"
    tags="$order_root/time_seed${seed}.tags.bin"
    initial_tags="$order_root/time_seed${seed}.initial.tags.bin"
  else
    data="$order_root/shuffle_seed${seed}.bin"
    tags="$order_root/shuffle_seed${seed}.tags.bin"
    initial_tags="$order_root/shuffle_seed${seed}.initial.tags.bin"
  fi
  local edge_file="$run_root/edges/${variant}_seed${seed}.edges"
  local index_file="$run_root/indexes/${variant}_seed${seed}.index"
  local build_metric="$result_root/build_${variant}_seed${seed}.jsonl"
  local structure_metric="$result_root/structure_${variant}_seed${seed}.json"
  : > "$build_metric"
  local common=(p03-structure --variant "$([[ "$variant" == "static" ]] && echo static || echo stream)"
    --data "$data" --npoints "$npoints" --R 64 --L 96 --alpha 1.2 --threads "$threads"
    --build-seed "$seed" --update-seed "$seed" --label "${variant}_seed${seed}"
    --save-edges "$edge_file" --save-index "$index_file" --out "$build_metric")
  if [[ "$variant" == "static" ]]; then
    "$binary" "${common[@]}" --tags "$tags" > "$log_root/${variant}_seed${seed}.log" 2>&1
  else
    "$binary" "${common[@]}" --initial-n "$cohort_size" --batch "$cohort_size" \
      --tags "$initial_tags" --full-tags "$tags" --final-prune 1 > "$log_root/${variant}_seed${seed}.log" 2>&1
  fi
  "$analyzer" --edges "$edge_file" --npoints "$npoints" --cohort-size "$cohort_size" \
    --R 64 --seed "$seed" --label "${variant}_seed${seed}" \
    > "$structure_metric" 2> "$log_root/${variant}_seed${seed}_analyzer.log"
}

IFS=',' read -r -a seed_values <<< "$seeds"
for seed in "${seed_values[@]}"; do
  if [[ "$scale" == "smoke" ]]; then
    run_variant static "$seed"
    run_variant time "$seed"
    run_variant shuffle "$seed"
  else
    run_variant static "$seed" &
    static_pid=$!
    run_variant time "$seed" &
    time_pid=$!
    run_variant shuffle "$seed" &
    shuffle_pid=$!
    wait "$static_pid"
    wait "$time_pid"
    wait "$shuffle_pid"
  fi
done

: > "$result_root/build_metrics.jsonl"
: > "$result_root/structure_metrics.jsonl"
for seed in "${seed_values[@]}"; do
  for variant in static time shuffle; do
    sed -n '1p' "$result_root/build_${variant}_seed${seed}.jsonl" >> "$result_root/build_metrics.jsonl"
    sed -n '1p' "$result_root/structure_${variant}_seed${seed}.json" >> "$result_root/structure_metrics.jsonl"
  done
done

python3 "$work_root/summarize_structure.py" --input "$result_root/structure_metrics.jsonl" \
  --output "$result_root/structure_summary.json" --expected-seeds "$expected_seeds" \
  > "$log_root/summary.log"
