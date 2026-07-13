#!/usr/bin/env bash
set -euo pipefail

BIN=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/tests/decouple_search_r
ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB
OUT=${OUT:-"$ROOT/decouplevs_gate/results/r0_batched"}
mkdir -p "$OUT"

common=(
  --graph "$ROOT/decouplevs_gate/layout/sift900k_graph.bin"
  --vectors "$ROOT/decouplevs_gate/layout/sift900k_vectors.bin"
  --pq-codes "$ROOT/oracle_gate/index/odin_sift900k/index_pq_compressed.bin"
  --pq-pivots "$ROOT/oracle_gate/index/odin_sift900k/index_pq_pivots.bin"
  --queries "$ROOT/datasets/real/sift-128-euclidean/query.bin"
  --truth "$ROOT/datasets/real/sift-128-euclidean/groundtruth.bin"
  --k 10 --L 100 --width 4 --query-start 1000 --query-limit 1000
)

for rep in 1 2 3
do
  if (( rep % 2 == 1 )); then order=(naive fixed); else order=(fixed naive); fi
  for mode in "${order[@]}"
  do
    if [[ "$mode" == fixed ]]; then b=80; else b=10; fi
    "$BIN" "${common[@]}" --mode "$mode" --B "$b" --output "$OUT/${mode}_rep${rep}.csv"
  done
done
