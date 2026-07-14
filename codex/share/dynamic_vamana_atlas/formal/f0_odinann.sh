#!/usr/bin/env bash
set -euo pipefail
SYSTEM=OdinANN
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

check_paths; check_sources; write_environment_manifest; assert_fresh_attempt; enable_error_trap
require_executable "$ROOT/build/OdinANN-uring/tests/build_disk_index"
require_executable "$ROOT/build/OdinANN-uring/tests/search_disk_index"
prefix="$INDEX_DIR/index"

if [[ ! -f "$INDEX_DIR/BUILD_OK" ]]; then
  [[ -z "$(find "$INDEX_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)" ]] \
    || fail "partial index directory exists; use a new F0_ATTEMPT instead of overwriting it"
  mkdir -p "$INDEX_DIR"
  run_scoped build 7200 "$INDEX_DIR" "$RESULT_DIR/build_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/build_time.txt" \
    "$ROOT/build/OdinANN-uring/tests/build_disk_index" float "$DATASET/active_cp00.bin" \
    "$prefix" 96 128 32 64 "$BUILD_THREADS" l2 pq
  touch "$INDEX_DIR/BUILD_OK"
  write_space_report
fi

if [[ ! -f "$RESULT_DIR/QUERY_OK" ]]; then
  run_scoped query 3600 "$INDEX_DIR" "$RESULT_DIR/query_resources.json" \
    /usr/bin/time -v -o "$RESULT_DIR/query_time.txt" \
    "$ROOT/build/OdinANN-uring/tests/search_disk_index" float "$prefix" "$QUERY_THREADS" 16 \
    "$DATASET/query.bin" "$GT" 10 l2 pq 2 0 40
  python3 "$CHAT/validate_aggregate_query_log.py" --log "$RESULT_DIR/query.log" \
    --output "$RESULT_DIR/query_validation.json"
  touch "$RESULT_DIR/QUERY_OK"
fi
make_immutable_base
touch "$RESULT_DIR/F0_OK"
write_state complete passed
notify_owner "Dynamic Vamana F0 complete: OdinANN/$ATTEMPT" "result=$RESULT_DIR"
note "F0 ready: OdinANN/$ATTEMPT"
