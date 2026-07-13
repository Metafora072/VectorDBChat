#!/usr/bin/env bash
set -euo pipefail

BIN=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/tests/decouple_search_r
ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB
OUT=${OUT:-"$ROOT/decouplevs_gate/results/r2_batched"}
mkdir -p "$OUT"

common=(
  --graph "$ROOT/decouplevs_gate/layout/sift900k_graph.bin"
  --vectors "$ROOT/decouplevs_gate/layout/sift900k_vectors.bin"
  --pq-codes "$ROOT/oracle_gate/index/odin_sift900k/index_pq_compressed.bin"
  --pq-pivots "$ROOT/oracle_gate/index/odin_sift900k/index_pq_pivots.bin"
  --queries "$ROOT/datasets/real/sift-128-euclidean/query.bin"
  --truth "$ROOT/datasets/real/sift-128-euclidean/groundtruth.bin"
  --k 10 --L 100 --B 80 --query-start 2000 --query-limit 1000
)

run_one() {
  local mode=$1 width=$2 quota=$3
  local path="$OUT/${mode}_L100_W${width}_B80_Q${quota}.csv"
  if [[ -s "$path" ]] && [[ $(wc -l < "$path") -eq 1001 ]]; then
    echo "skip_complete=$path"
    return
  fi
  echo "begin=$mode width=$width quota=$quota"
  "$BIN" "${common[@]}" --output "$path" --mode "$mode" --width "$width" --vector-quota "$quota"
}

for width in 4 8 16; do
  run_one oracle_final "$width" 1
  run_one oracle_safe "$width" "$width"
  quota=1
  while [[ $quota -le $width ]]; do
    run_one oracle_bw "$width" "$quota"
    quota=$((quota * 2))
  done
done
