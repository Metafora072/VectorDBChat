#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse
CHAT=/home/ubuntu/pz/VectorDB/chat
PY="$ROOT/venv/bin/python"
PIPE="$CHAT/codex/work/a0_topology_reuse/a0_pipeline.py"
DISKANN=/home/ubuntu/pz/VectorDB/repos/DiskANN/build/apps
TAG=formal_100k
THREADS=56
SEARCH_THREADS=16
SEARCH_L=(10 20 40 80 120 160)
TRANSITIONS=(minilm_l6_v1_v2 e5_small_v1_v2 bge_small_v1_v15)
WINDOWS=0

export HF_HOME="$ROOT/cache/huggingface"
export HF_DATASETS_CACHE="$ROOT/cache/datasets"
export TMPDIR="$ROOT/tmp"

"$PY" "$PIPE" prepare --dataset quora --tag "$TAG" --n-corpus 100000 --n-queries 2000
"$PY" "$PIPE" prepare --dataset nq_top50 --tag "$TAG" --n-corpus 100000 --n-queries 2000

for index in "${!TRANSITIONS[@]}"; do
  trans="${TRANSITIONS[$index]}"
  E="$ROOT/embeddings/$TAG/$trans"
  I="$ROOT/indexes/$TAG/$trans"
  R="$ROOT/runs/$TAG/$trans"
  mkdir -p "$E" "$I" "$R"

  for role in old new; do
    "$PY" "$PIPE" encode --tag "$TAG" --transition "$trans" --role "$role" --kind corpus --batch-size 128 --threads "$THREADS"
    "$PY" "$PIPE" encode --tag "$TAG" --transition "$trans" --role "$role" --kind queries --batch-size 128 --threads "$THREADS"
    "$PY" "$PIPE" exact-corpus --input "$E/${role}_corpus.fbin" --output "$R/${role}_exact64.npy" --threads "$THREADS"
  done

  "$PY" "$PIPE" overlap --old "$R/old_exact64.npy" --new "$R/new_exact64.npy" --output "$R/overlap.json"
  "$PY" "$PIPE" query-gt --base "$E/new_corpus.fbin" --queries "$E/new_queries.fbin" --output "$R/query_gt100.bin" --threads "$THREADS"
  "$PY" "$PIPE" random --like "$E/new_corpus.fbin" --output "$E/random_corpus.fbin"

  for graph in old new random; do
    /usr/bin/time -v "$DISKANN/build_memory_index" --data_type float --dist_fn l2 \
      --data_path "$E/${graph}_corpus.fbin" --index_path_prefix "$I/${graph}_mem" \
      -R 32 -L 64 -T "$THREADS" >"$R/build_${graph}.log" 2>&1
  done

  /usr/bin/time -v "$DISKANN/build_disk_index" --data_type float --dist_fn l2 --data_path "$E/new_corpus.fbin" \
    --index_path_prefix "$I/pq_carrier" -R 32 -L 64 -B 0.01 -M 32 -T "$THREADS" --QD 32 \
    >"$R/build_pq_carrier.log" 2>&1

  for variant in fresh old_topology random_topology; do
    ln -f "$I/pq_carrier_pq_pivots.bin" "$I/${variant}_pq_pivots.bin"
    ln -f "$I/pq_carrier_pq_compressed.bin" "$I/${variant}_pq_compressed.bin"
  done
  "$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/new_mem" "$I/fresh_disk.index" >"$R/layout_fresh.log" 2>&1
  "$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/old_mem" "$I/old_topology_disk.index" >"$R/layout_old.log" 2>&1
  "$DISKANN/utils/create_disk_layout" float "$E/new_corpus.fbin" "$I/random_mem" "$I/random_topology_disk.index" >"$R/layout_random.log" 2>&1

  for graph in old new random; do
    "$PY" "$PIPE" graph-stats --graph "$I/${graph}_mem" --new-exact "$R/new_exact64.npy" \
      --output "$R/${graph}_graph_stats.json"
  done

  parse_args=()
  for variant in fresh old_topology random_topology; do
    for rep in 0 1 2; do
      log="$R/search_${variant}_rep${rep}.log"
      "$DISKANN/search_disk_index" --data_type float --dist_fn l2 --index_path_prefix "$I/$variant" \
        --query_file "$E/new_queries.fbin" --gt_file "$R/query_gt100.bin" \
        --result_path "$R/${variant}_rep${rep}_result" -K 10 -L "${SEARCH_L[@]}" -W 2 -T "$SEARCH_THREADS" \
        >"$log" 2>&1
      parse_args+=(--log "$variant=$rep=$log")
    done
  done

  "$PY" "$PIPE" compare-search --gt "$R/query_gt100.bin" \
    --run "fresh=$R/fresh_rep0_result" --run "old_topology=$R/old_topology_rep0_result" \
    --run "random_topology=$R/random_topology_rep0_result" --search-l "${SEARCH_L[@]}" \
    --output "$R/search_recall_comparison.json"
  "$PY" "$PIPE" parse-search "${parse_args[@]}" --output "$R/search_performance.json"
  if "$PY" "$PIPE" gate-window --comparison "$R/search_recall_comparison.json" --output "$R/reuse_window_gate.json"; then
    WINDOWS=$((WINDOWS + 1))
  fi
  echo "TRANSITION_DONE $trans $R"

  remaining=$((${#TRANSITIONS[@]} - index - 1))
  if (( WINDOWS + remaining < 2 )); then
    echo "A0_1_KILL only $WINDOWS confirmed window(s), $remaining transition(s) remain; two windows are impossible"
    exit 20
  fi
done

echo "A0_1_DONE $ROOT/runs/$TAG"
