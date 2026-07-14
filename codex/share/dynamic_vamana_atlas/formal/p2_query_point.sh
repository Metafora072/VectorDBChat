#!/usr/bin/env bash
# One isolated P2 query point. Invoked by the root-owned P2 controller.
set -euo pipefail

SYSTEM=${P2_SYSTEM:?set P2_SYSTEM}
P2_L=${P2_L:?set P2_L}
P2_TQ=${P2_TQ:?set P2_TQ}
P2_REPEAT=${P2_REPEAT:-1}
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

RUN_ROOT="$ROOT/formal/$RUN_NAME/raw/$SYSTEM/tq${P2_TQ}/L${P2_L}/r${P2_REPEAT}"
RESULT_DIR="$ROOT/results/$RUN_NAME/raw/$SYSTEM/tq${P2_TQ}/L${P2_L}/r${P2_REPEAT}"
MANIFEST_DIR="$ROOT/manifests/$RUN_NAME/raw/$SYSTEM/tq${P2_TQ}/L${P2_L}/r${P2_REPEAT}"
TMP_WORK="$ROOT/tmp/$RUN_NAME/raw/$SYSTEM/tq${P2_TQ}/L${P2_L}/r${P2_REPEAT}"
QUERY="$ROOT/datasets/sift10m_p2/query_2000.bin"
GT="$ROOT/groundtruth/sift10m/$VALIDATION_RUN_NAME/gt_cp00_2000"

case "$SYSTEM" in
  DiskANN) PREFIX="$ROOT/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index/index"; BIN="$ROOT/build/DiskANN/apps/search_disk_index" ;;
  DGAI) PREFIX="$ROOT/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index/index"; BIN="$ROOT/build/DGAI/tests/search_disk_index" ;;
  OdinANN) PREFIX="$ROOT/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index/index"; BIN="$ROOT/build/OdinANN-uring/tests/search_disk_index" ;;
  *) fail "unknown P2 system: $SYSTEM" ;;
esac

check_paths; check_sources; write_environment_manifest; enable_error_trap
require_file "$QUERY"; require_file "$GT"; require_executable "$BIN"
[[ ! -e "$RESULT_DIR/point.json" ]] || fail "P2 point already exists: $RESULT_DIR"
root_managed sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'

case "$SYSTEM" in
  DiskANN)
    cmd=("$BIN" --data_type float --dist_fn l2 --index_path_prefix "$PREFIX" --result_path "$RESULT_DIR/result"
      --query_file "$QUERY" --gt_file "$GT" -K 10 -L "$P2_L" -T "$P2_TQ" -W 4)
    ;;
  DGAI)
    cmd=("$BIN" float "$PREFIX" "$P2_TQ" 16 "$QUERY" "$GT" 10 l2 2 0 23 "$P2_L")
    ;;
  OdinANN)
    cmd=("$BIN" float "$PREFIX" "$P2_TQ" 16 "$QUERY" "$GT" 10 l2 pq 2 0 "$P2_L")
    ;;
esac
run_scoped query 1800 "$RUN_ROOT" "$RESULT_DIR/resources.json" \
  python3 "$CHAT/timed_query_runner.py" --system "$SYSTEM" --query-count 2000 \
    --log "$RESULT_DIR/driver.log" --timing "$RESULT_DIR/timing.json" -- "${cmd[@]}"
if [[ "$SYSTEM" == DiskANN ]]; then
  python3 "$CHAT/validate_query_result.py" --result "$RESULT_DIR/result_${P2_L}_idx_uint32.bin" \
    --active-tags "$DATASET/active_cp00.tags.bin" --query "$QUERY" --log "$RESULT_DIR/driver.log" --k 10 \
    --output "$RESULT_DIR/query_validation.json"
else
  python3 "$CHAT/validate_aggregate_query_log.py" --log "$RESULT_DIR/driver.log" --output "$RESULT_DIR/query_validation.json"
fi
python3 "$CHAT/parse_p2_point.py" --system "$SYSTEM" --query-threads "$P2_TQ" --L "$P2_L" --repeat "$P2_REPEAT" \
  --log "$RESULT_DIR/driver.log" --timing "$RESULT_DIR/timing.json" --resources "$RESULT_DIR/resources.json" \
  --output "$RESULT_DIR/point.json"
write_state complete passed
finalize_operator_ownership
