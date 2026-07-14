#!/usr/bin/env bash
set -euo pipefail
SYSTEM=DiskANN
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

check_paths; check_sources; write_environment_manifest; assert_fresh_attempt; enable_error_trap
require_executable "$ROOT/build/DiskANN/apps/build_disk_index"
require_executable "$ROOT/build/DiskANN/apps/search_disk_index"
prefix="$INDEX_DIR/index"

if [[ ! -f "$INDEX_DIR/BUILD_OK" ]]; then
  [[ -z "$(find "$INDEX_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)" ]] \
    || fail "partial index directory exists; use a new F0_ATTEMPT instead of overwriting it"
  mkdir -p "$INDEX_DIR"
  run_scoped build 7200 "$INDEX_DIR" "$RESULT_DIR/build_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/build_time.txt" \
    "$ROOT/build/DiskANN/apps/build_disk_index" --data_type float --dist_fn l2 \
    --data_path "$DATASET/active_cp00.bin" --index_path_prefix "$prefix" \
    -R 64 -L 100 -B 1 -M 64 -T "$BUILD_THREADS"
  touch "$INDEX_DIR/BUILD_OK"
  write_space_report
fi

if [[ ! -f "$RESULT_DIR/QUERY_OK" ]]; then
  run_scoped query 3600 "$INDEX_DIR" "$RESULT_DIR/query_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/query_time.txt" \
    "$ROOT/build/DiskANN/apps/search_disk_index" --data_type float --dist_fn l2 \
    --index_path_prefix "$prefix" --result_path "$RESULT_DIR/result" \
    --query_file "$DATASET/query.bin" --gt_file "$GT" -K 10 -L 40 \
    -T "$QUERY_THREADS" -W 4
  python3 "$CHAT/validate_query_result.py" --result "$RESULT_DIR/result_40_idx_uint32.bin" \
    --active-tags "$DATASET/active_cp00.tags.bin" --query "$DATASET/query.bin" \
    --log "$RESULT_DIR/query.log" --k 10 --output "$RESULT_DIR/query_validation.json"
  touch "$RESULT_DIR/QUERY_OK"
fi
make_immutable_base
touch "$RESULT_DIR/F0_OK"
write_state complete passed
notify_owner "Dynamic Vamana F0 complete: DiskANN/$ATTEMPT" "result=$RESULT_DIR"
note "F0 ready: DiskANN/$ATTEMPT"
