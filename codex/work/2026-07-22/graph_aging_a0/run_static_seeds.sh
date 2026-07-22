#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0
large=/home/ubuntu/pz/VectorDB/data/VectorDB/graph_aging_a0_0722
source_data=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin
query=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin
gt=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m/gt_cp00
binary="$root/PipeANN/build-a0/tests/graph_aging_a0"

mkdir -p "$large/permutations" "$root/logs"
for seed in 11 22 33 44 55; do
  python3 "$root/prepare_permutation.py" \
    --input "$source_data" \
    --output-data "$large/permutations/data_seed${seed}.bin" \
    --output-tags "$large/permutations/tags_seed${seed}.bin" \
    --output-initial-tags "$large/permutations/initial_tags_seed${seed}.bin" \
    --initial-n 500000 --n 1000000 --seed "$seed"
done

pids=()
for seed in 11 22 33 44 55; do
  OMP_NUM_THREADS=12 "$binary" build \
    --data "$large/permutations/data_seed${seed}.bin" \
    --tags "$large/permutations/tags_seed${seed}.bin" \
    --npoints 1000000 --query "$query" --gt "$gt" --nqueries 1000 \
    --R 64 --L 96 --search-L 96 --threads 12 --build-seed "$seed" \
    --label "static_seed${seed}" --baseline-edges "$large/g0_1m.edges" \
    --out "$root/results/static_seeds.jsonl" \
    >"$root/logs/static_seed${seed}.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do
  wait "$pid"
done
