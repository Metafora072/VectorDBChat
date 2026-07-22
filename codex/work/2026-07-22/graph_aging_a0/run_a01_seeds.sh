#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0
large=/home/ubuntu/pz/VectorDB/data/VectorDB/graph_aging_a0_0722
data=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin
query=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin
gt=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m/gt_cp00
binary="$root/PipeANN/build-a0/tests/graph_aging_a0"

pids=()
for seed in 1001 1002 1003 1004 1005; do
  OMP_NUM_THREADS=12 "$binary" a01 \
    --index "$large/g0_1m.index" --data "$data" --query "$query" --gt "$gt" \
    --nqueries 1000 --batch 100000 --checkpoints 1,10,100 \
    --R 64 --L 96 --search-L 96 --threads 12 --build-seed 0 --update-seed "$seed" \
    --label "insert_delete_seed${seed}" --baseline-edges "$large/g0_1m.edges" \
    --oracle-shadow 1 --out "$root/results/a01_seed${seed}_v2.jsonl" \
    >"$root/logs/a01_seed${seed}_v2.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do
  wait "$pid"
done
