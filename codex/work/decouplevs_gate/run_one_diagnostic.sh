#!/usr/bin/env bash
set +e

BIN=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/tests/decouple_search_r
ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB

"$BIN" \
  --graph "$ROOT/decouplevs_gate/layout/sift900k_graph.bin" \
  --vectors "$ROOT/decouplevs_gate/layout/sift900k_vectors.bin" \
  --pq-codes "$ROOT/oracle_gate/index/odin_sift900k/index_pq_compressed.bin" \
  --pq-pivots "$ROOT/oracle_gate/index/odin_sift900k/index_pq_pivots.bin" \
  --queries "$ROOT/datasets/real/sift-128-euclidean/query.bin" \
  --truth "$ROOT/datasets/real/sift-128-euclidean/groundtruth.bin" \
  --output "$ROOT/decouplevs_gate/results/sanity/diagnostic_1q.csv" \
  --mode fixed --k 10 --L 100 --width 4 --B 10 --query-limit 1
status=$?
echo "$status" > "$ROOT/decouplevs_gate/results/sanity/diagnostic_1q.exit"
exit 0
