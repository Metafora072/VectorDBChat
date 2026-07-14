#!/usr/bin/env bash
set -euo pipefail
SYSTEM=DGAI
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

check_paths; check_sources; write_environment_manifest; assert_fresh_attempt; enable_error_trap
require_executable "$ROOT/build/DGAI/tests/build_disk_index"
require_executable "$ROOT/build/DGAI/tests/search_disk_index"
require_executable "$ROOT/build/DGAI/tests/split_index"
require_executable "$ROOT/build/DGAI/tests/reorder_by_map"
prefix="$INDEX_DIR/index"

if [[ ! -f "$INDEX_DIR/BUILD_OK" ]]; then
  [[ -z "$(find "$INDEX_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)" ]] \
    || fail "partial index directory exists; use a new F0_ATTEMPT instead of overwriting it"
  mkdir -p "$INDEX_DIR"
  run_scoped build 10800 "$INDEX_DIR" "$RESULT_DIR/build_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/build_time.txt" \
    "$ROOT/build/DGAI/tests/build_disk_index" float "$DATASET/active_cp00.bin" "$prefix" \
    32 75 1 64 "$BUILD_THREADS" l2 0
  cp "$DATASET/active_cp00.tags.bin" "${prefix}_disk.index.tags"
  cp "${prefix}_pq_compressed_refined.bin" "${prefix}_pq_compressed_2.bin"
  cp "${prefix}_pq_pivots_refined.bin" "${prefix}_pq_pivots_2.bin"
  run_scoped postprocess 3600 "$INDEX_DIR" "$RESULT_DIR/postprocess_resources.json" \
    bash -c '"$0" "$1" "$2" "$3" "$4" "$5" && "$6" 8000000 132 "$3" "$7" "$8"' \
    "$ROOT/build/DGAI/tests/split_index" "${prefix}_disk.index" "$INDEX_DIR/dram_index_graph" \
    "$INDEX_DIR/disk_index_graph" "$INDEX_DIR/disk_index_data" float \
    "$ROOT/build/DGAI/tests/reorder_by_map" "$INDEX_DIR/reorder_map_graph_2" \
    "$INDEX_DIR/reordered_disk_index_graph_2"
  touch "$INDEX_DIR/BUILD_OK"
  write_space_report
fi

if [[ ! -f "$RESULT_DIR/QUERY_OK" ]]; then
  run_scoped query 3600 "$INDEX_DIR" "$RESULT_DIR/query_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/query_time.txt" \
    "$ROOT/build/DGAI/tests/search_disk_index" float "$prefix" "$QUERY_THREADS" 16 \
    "$DATASET/query.bin" "$GT" 10 l2 2 0 23 40
  assert_query_recall "$RESULT_DIR/query.log"
  touch "$RESULT_DIR/QUERY_OK"
fi
make_immutable_base
touch "$RESULT_DIR/F0_OK"
write_state complete passed
notify_owner "Dynamic Vamana F0 complete: DGAI/$ATTEMPT" "result=$RESULT_DIR"
note "F0 ready: DGAI/$ATTEMPT"
