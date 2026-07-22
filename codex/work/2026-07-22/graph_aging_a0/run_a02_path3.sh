#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0
large=/home/ubuntu/pz/VectorDB/data/VectorDB/graph_aging_a0_0722
query=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin
gt=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m/gt_cp00
binary="$root/PipeANN/build-a0/tests/graph_aging_a0"

pids=()
for seed in 11 22 33 44 55; do
  OMP_NUM_THREADS=12 "$binary" path3 \
    --data "$large/overfill/data_1p2m_seed${seed}.bin" \
    --tags "$large/overfill/initial_tags_1p2m_seed${seed}.bin" \
    --full-tags "$large/overfill/tags_1p2m_seed${seed}.bin" \
    --initial-n 500000 --npoints 1200000 --final-n 1000000 \
    --query "$query" --gt "$gt" --nqueries 1000 \
    --R 64 --L 96 --search-L 96 --threads 12 --build-seed "$seed" --update-seed "$seed" \
    --label "path3_1p2m_delete_seed${seed}" --baseline-edges "$large/g0_1m.edges" \
    --oracle-shadow 1 --out "$root/results/a02_path3_seed${seed}_v2.jsonl" \
    >"$root/logs/a02_path3_seed${seed}_v2.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do
  wait "$pid"
done
