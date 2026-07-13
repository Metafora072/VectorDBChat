#!/usr/bin/env bash
set -euo pipefail

BIN=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/tests/decouple_search_r
ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB
OUT=${OUT:-"$ROOT/decouplevs_gate/results/r1_batched"}
mkdir -p "$OUT"

common=(
  --graph "$ROOT/decouplevs_gate/layout/sift900k_graph.bin"
  --vectors "$ROOT/decouplevs_gate/layout/sift900k_vectors.bin"
  --pq-codes "$ROOT/oracle_gate/index/odin_sift900k/index_pq_compressed.bin"
  --pq-pivots "$ROOT/oracle_gate/index/odin_sift900k/index_pq_pivots.bin"
  --queries "$ROOT/datasets/real/sift-128-euclidean/query.bin"
  --truth "$ROOT/datasets/real/sift-128-euclidean/groundtruth.bin"
  --mode fixed --k 10 --query-start 2000 --query-limit 1000
)

# Full B x W slice at L=100.
for w in 2 4 8 16
do
  for b in 10 20 40 80
  do
    "$BIN" "${common[@]}" --L 100 --width "$w" --B "$b" \
      --output "$OUT/fixed_L100_W${w}_B${b}.csv"
  done
done

# Full L x B slice at W=4; L=100 files above are reused.
for l in 80 160 240
do
  for b in 10 20 40 80
  do
    "$BIN" "${common[@]}" --L "$l" --width 4 --B "$b" \
      --output "$OUT/fixed_L${l}_W4_B${b}.csv"
  done
done
