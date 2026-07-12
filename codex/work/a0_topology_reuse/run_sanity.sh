#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse
CHAT=/home/ubuntu/pz/VectorDB/chat
PY="$ROOT/venv/bin/python"
PIPE="$CHAT/codex/work/a0_topology_reuse/a0_pipeline.py"
DISKANN=/home/ubuntu/pz/VectorDB/repos/DiskANN/build/apps
TAG=sanity_2k
TRANS=minilm_l6_v1_v2
E="$ROOT/embeddings/$TAG/$TRANS"
I="$ROOT/indexes/$TAG/$TRANS"
R="$ROOT/runs/$TAG/$TRANS"

export HF_HOME="$ROOT/cache/huggingface"
export HF_DATASETS_CACHE="$ROOT/cache/datasets"
export TMPDIR="$ROOT/tmp"
mkdir -p "$E" "$I" "$R"

"$PY" "$PIPE" prepare --dataset quora --tag "$TAG" --n-corpus 2000 --n-queries 100
for role in old new; do
  "$PY" "$PIPE" encode --tag "$TAG" --transition "$TRANS" --role "$role" --kind corpus --batch-size 128 --threads 28
  "$PY" "$PIPE" encode --tag "$TAG" --transition "$TRANS" --role "$role" --kind queries --batch-size 128 --threads 28
  "$PY" "$PIPE" exact-corpus --input "$E/${role}_corpus.fbin" --output "$R/${role}_exact64.npy" --threads 28
done
"$PY" "$PIPE" overlap --old "$R/old_exact64.npy" --new "$R/new_exact64.npy" --output "$R/overlap.json"
"$PY" "$PIPE" query-gt --base "$E/new_corpus.fbin" --queries "$E/new_queries.fbin" --output "$R/query_gt100.bin" --threads 28
"$PY" "$PIPE" random --like "$E/new_corpus.fbin" --output "$E/random_corpus.fbin"

for graph in old new random; do
  "$DISKANN/build_memory_index" --data_type float --dist_fn l2 --data_path "$E/${graph}_corpus.fbin" \
    --index_path_prefix "$I/${graph}_mem" -R 16 -L 32 -T 28 >"$R/build_${graph}.log" 2>&1
done

"$DISKANN/build_disk_index" --data_type float --dist_fn l2 --data_path "$E/new_corpus.fbin" \
  --index_path_prefix "$I/pq_new" -R 16 -L 32 -B 0.001 -M 4 -T 28 --QD 16 >"$R/build_pq_carrier.log" 2>&1
for variant in fresh old_topology random_topology; do
  ln -f "$I/pq_new_pq_pivots.bin" "$I/${variant}_pq_pivots.bin"
  ln -f "$I/pq_new_pq_compressed.bin" "$I/${variant}_pq_compressed.bin"
done
"$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/new_mem" "$I/fresh_disk.index" >"$R/layout_fresh.log" 2>&1
"$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/old_mem" "$I/old_topology_disk.index" >"$R/layout_old.log" 2>&1
"$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/random_mem" "$I/random_topology_disk.index" >"$R/layout_random.log" 2>&1

"$PY" "$PIPE" graph-stats --graph "$I/old_mem" --new-exact "$R/new_exact64.npy" --output "$R/old_graph_stats.json"
for variant in fresh old_topology random_topology; do
  "$DISKANN/search_disk_index" --data_type float --dist_fn l2 --index_path_prefix "$I/$variant" \
    --query_file "$E/new_queries.fbin" --gt_file "$R/query_gt100.bin" --result_path "$R/${variant}_result" \
    -K 10 -L 10 20 40 80 -W 2 -T 8 >"$R/search_${variant}.log" 2>&1
done

echo "SANITY_DONE $R"
