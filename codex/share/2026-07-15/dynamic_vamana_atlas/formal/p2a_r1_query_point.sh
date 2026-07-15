#!/usr/bin/env bash
# One immutable full-10K P2-A-R1 query point.  No truthset prefix is used.
set -euo pipefail

SYSTEM=${P2A_SYSTEM:?set P2A_SYSTEM}
P2A_L=${P2A_L:?set P2A_L}
P2A_TQ=${P2A_TQ:-1}
P2A_REPEAT=${P2A_REPEAT:-1}
P2A_STAGE=${P2A_STAGE:-raw}
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

RUN_ROOT="$ROOT/formal/$RUN_NAME/$P2A_STAGE/$SYSTEM/tq${P2A_TQ}/L${P2A_L}/r${P2A_REPEAT}"
RESULT_DIR="$ROOT/results/$RUN_NAME/$P2A_STAGE/$SYSTEM/tq${P2A_TQ}/L${P2A_L}/r${P2A_REPEAT}"
MANIFEST_DIR="$ROOT/manifests/$RUN_NAME/$P2A_STAGE/$SYSTEM/tq${P2A_TQ}/L${P2A_L}/r${P2A_REPEAT}"
TMP_WORK="$ROOT/tmp/$RUN_NAME/$P2A_STAGE/$SYSTEM/tq${P2A_TQ}/L${P2A_L}/r${P2A_REPEAT}"
QUERY="$ROOT/datasets/sift10m/query.bin"
GT="$ROOT/groundtruth/sift10m/$VALIDATION_RUN_NAME/gt_cp00"

case "$SYSTEM" in
  DiskANN) PREFIX="$ROOT/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index/index"; BIN="$ROOT/build/DiskANN/apps/search_disk_index"; PATCH=DiskANN_system_blas.patch; SOURCE_REPO="$ROOT/src/DiskANN-cpp_main" ;;
  DGAI) PREFIX="$ROOT/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index/index"; BIN="$ROOT/build/DGAI/tests/search_disk_index"; PATCH=DGAI_mkl_cblas_compat.patch; SOURCE_REPO="$ROOT/src/DGAI-clean" ;;
  OdinANN) PREFIX="$ROOT/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index/index"; BIN="$ROOT/build/OdinANN-uring/tests/search_disk_index"; PATCH=OdinANN_system_uring_cblas.patch; SOURCE_REPO="$ROOT/src/OdinANN-PipeANN" ;;
  *) fail "unknown P2-A-R1 system: $SYSTEM" ;;
esac

check_paths; check_sources; write_environment_manifest; enable_error_trap
require_file "$QUERY"; require_file "$GT"; require_executable "$BIN"
ARTIFACT_MANIFEST="$ROOT/manifests/$RUN_NAME/artifacts/$SYSTEM.json"
require_file "$ARTIFACT_MANIFEST"
[[ ! -e "$RESULT_DIR/point.json" ]] || fail "immutable P2-A-R1 point already exists: $RESULT_DIR"
{
  echo "schema=dynamic-vamana-p2a-r1-provenance-v1"
  echo "query_file=$(realpath "$QUERY")"; sha256sum "$QUERY"
  echo "groundtruth_file=$(realpath "$GT")"; sha256sum "$GT"
  echo "binary_file=$(realpath "$BIN")"; sha256sum "$BIN"
  echo "odin_query_reader_semantics=force_recopy=false opens read-only O_RDONLY; negative io_uring CQEs are fatal"
  echo "odin_patch_sha256=$(sha256sum "$CHAT/patches/OdinANN_system_uring_cblas.patch" | awk '{print $1}')"
} >"$MANIFEST_DIR/p2a_r1_provenance.txt"
root_managed sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'

case "$SYSTEM" in
  DiskANN)
    cmd=("$BIN" --data_type float --dist_fn l2 --index_path_prefix "$PREFIX" --result_path "$RESULT_DIR/result"
      --query_file "$QUERY" --gt_file "$GT" -K 10 -L "$P2A_L" -T "$P2A_TQ" -W 4)
    ;;
  DGAI)
    cmd=("$BIN" float "$PREFIX" "$P2A_TQ" 16 "$QUERY" "$GT" 10 l2 2 0 23 "$P2A_L")
    ;;
  OdinANN)
    cmd=("$BIN" float "$PREFIX" "$P2A_TQ" 16 "$QUERY" "$GT" 10 l2 pq 2 0 "$P2A_L")
    ;;
esac
run_scoped query 1800 "$RUN_ROOT" "$RESULT_DIR/resources.json" \
  python3 "$CHAT/timed_query_runner.py" --system "$SYSTEM" --query-count 10000 \
    --log "$RESULT_DIR/driver.log" --timing "$RESULT_DIR/timing.json" -- "${cmd[@]}"
if [[ "$SYSTEM" == DiskANN ]]; then
  python3 "$CHAT/validate_query_result.py" --result "$RESULT_DIR/result_${P2A_L}_idx_uint32.bin" \
    --active-tags "$DATASET/active_cp00.tags.bin" --query "$QUERY" --log "$RESULT_DIR/driver.log" --k 10 \
    --output "$RESULT_DIR/query_validation.json"
else
  python3 "$CHAT/validate_aggregate_query_log.py" --log "$RESULT_DIR/driver.log" --output "$RESULT_DIR/query_validation.json"
fi
python3 "$CHAT/parse_p2_point.py" --system "$SYSTEM" --query-threads "$P2A_TQ" --L "$P2A_L" --repeat "$P2A_REPEAT" \
  --log "$RESULT_DIR/driver.log" --timing "$RESULT_DIR/timing.json" --resources "$RESULT_DIR/resources.json" \
  --query-file "$QUERY" --gt-file "$GT" --output "$RESULT_DIR/point.json"
python3 "$CHAT/freeze_artifact_identity.py" --system "$SYSTEM" --binary "$BIN" --index "${PREFIX}_disk.index" \
  --query "$QUERY" --groundtruth "$GT" --compat-patch "$CHAT/patches/$PATCH" --source-repo "$SOURCE_REPO" \
  --output "$ARTIFACT_MANIFEST" --attach-point "$RESULT_DIR/point.json"
python3 - "$RESULT_DIR/point.json" <<'PY'
import json, sys
point = json.load(open(sys.argv[1]))
if point.get("valid") is not True:
    raise SystemExit("invalid point: " + str(point.get("invalid_reason")))
PY
write_state complete passed
finalize_operator_ownership
