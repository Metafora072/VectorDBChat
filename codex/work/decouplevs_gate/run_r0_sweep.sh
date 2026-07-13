#!/usr/bin/env bash
set -euo pipefail

BIN=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/tests/decouple_search_r
ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB
OUT="$ROOT/decouplevs_gate/results/r0"
mkdir -p "$OUT"

common=(
  --graph "$ROOT/decouplevs_gate/layout/sift900k_graph.bin"
  --vectors "$ROOT/decouplevs_gate/layout/sift900k_vectors.bin"
  --pq-codes "$ROOT/oracle_gate/index/odin_sift900k/index_pq_compressed.bin"
  --pq-pivots "$ROOT/oracle_gate/index/odin_sift900k/index_pq_pivots.bin"
  --queries "$ROOT/datasets/real/sift-128-euclidean/query.bin"
  --truth "$ROOT/datasets/real/sift-128-euclidean/groundtruth.bin"
  --k 10 --width 4 --B 10 --query-start 100 --query-limit 500
)

for spec in \
  naive:80 fixed:100 \
  naive:100 fixed:160 \
  naive:120 fixed:240 \
  naive:160 fixed:320
do
  mode=${spec%%:*}
  l=${spec##*:}
  "$BIN" "${common[@]}" --mode "$mode" --L "$l" --output "$OUT/${mode}_L${l}_W4_B10.csv"
done
