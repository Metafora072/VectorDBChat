#!/usr/bin/env bash
# GPT/Claude-approved P2-A-R1: F0 reproduction, then only the Tq=1 calibration grid.
set -Eeuo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p2a_r1}
OPERATOR_USER=${ATLAS_OPERATOR_USER:-ubuntu}
VALIDATION_RUN=pilot3_sift10m_p1r07
LOG_DIR="$ROOT/results/$RUN_NAME/p2a_r1_controller"
LOG="$LOG_DIR/p2a_r1.log"
mkdir -p "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/results/$RUN_NAME" "$ROOT/manifests/$RUN_NAME/artifacts"
chown "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" \
  "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/results/$RUN_NAME" "$ROOT/manifests/$RUN_NAME" "$ROOT/manifests/$RUN_NAME/artifacts"
exec > >(tee -a "$LOG") 2>&1

notify() { "$CHAT/formal/notify_owner.sh" "$1" "$2" || echo "MailSender failure does not change P2-A-R1 state" >&2; }
fail() { local code=$?; notify "Dynamic Vamana P2-A-R1 failed" "phase=${P2A_PHASE:-preflight} exit=$code log=$LOG; subsequent stages stopped"; exit "$code"; }
trap fail ERR
run_as_operator() { runuser -u "$OPERATOR_USER" --preserve-environment -- "$@"; }

valid_point_path() {
  local stage=$1 system=$2 l=$3 tq=${4:-1}
  local point
  for point in "$ROOT/results/$RUN_NAME/$stage/$system/tq${tq}/L$l"/r*/point.json; do
    [[ -f "$point" ]] || continue
    python3 - "$point" <<'PY' >/dev/null || continue
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("valid") is True else 1)
PY
    printf '%s\n' "$point"
    return 0
  done
  return 1
}

point_valid() { valid_point_path "$@" >/dev/null; }

valid_repeat_count() {
  local stage=$1 system=$2 l=$3 tq=$4 count=0 point
  for point in "$ROOT/results/$RUN_NAME/$stage/$system/tq${tq}/L$l"/r*/point.json; do
    [[ -f "$point" ]] || continue
    python3 - "$point" <<'PY' >/dev/null || fail "invalid existing point: $point"
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("valid") is True else 1)
PY
    ((count += 1))
  done
  printf '%s\n' "$count"
}

next_repeat() {
  local stage=$1 system=$2 l=$3 tq=${4:-1} repeat=1
  while [[ -e "$ROOT/results/$RUN_NAME/$stage/$system/tq${tq}/L$l/r$repeat" || \
           -e "$ROOT/formal/$RUN_NAME/$stage/$system/tq${tq}/L$l/r$repeat" ]]; do
    ((repeat += 1))
  done
  printf '%s\n' "$repeat"
}

run_one() {
  local stage=$1 system=$2 l=$3 repeat=$4 tq=${5:-1}
  P2A_STAGE="$stage" P2A_SYSTEM="$system" P2A_L="$l" P2A_TQ="$tq" P2A_REPEAT="$repeat" \
    "$CHAT/formal/p2a_r1_query_point.sh"
}

freeze_system() {
  local system=$1 prefix bin patch source_repo point
  case "$system" in
    DiskANN) prefix="$ROOT/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index/index"; bin="$ROOT/build/DiskANN/apps/search_disk_index"; patch=DiskANN_system_blas.patch; source_repo="$ROOT/src/DiskANN-cpp_main" ;;
    DGAI) prefix="$ROOT/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index/index"; bin="$ROOT/build/DGAI/tests/search_disk_index"; patch=DGAI_mkl_cblas_compat.patch; source_repo="$ROOT/src/DGAI-clean" ;;
    OdinANN) prefix="$ROOT/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index/index"; bin="$ROOT/build/OdinANN-uring/tests/search_disk_index"; patch=OdinANN_system_uring_cblas.patch; source_repo="$ROOT/src/OdinANN-PipeANN" ;;
  esac
  run_as_operator python3 "$CHAT/freeze_artifact_identity.py" --system "$system" --binary "$bin" --index "${prefix}_disk.index" \
    --query "$ROOT/datasets/sift10m/query.bin" --groundtruth "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00" \
    --compat-patch "$CHAT/patches/$patch" --source-repo "$source_repo" --output "$ROOT/manifests/$RUN_NAME/artifacts/$system.json"
  for point in "$ROOT/results/$RUN_NAME/canary/$system/tq8/L40"/r*/point.json; do
    [[ -f "$point" ]] || continue
    run_as_operator python3 "$CHAT/freeze_artifact_identity.py" --system "$system" --binary "$bin" --index "${prefix}_disk.index" \
      --query "$ROOT/datasets/sift10m/query.bin" --groundtruth "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00" \
      --compat-patch "$CHAT/patches/$patch" --source-repo "$source_repo" --output "$ROOT/manifests/$RUN_NAME/artifacts/$system.json" --attach-point "$point"
  done
}

run_to_count() {
  local stage=$1 system=$2 l=$3 tq=$4 target=$5 existing repeat
  existing=$(valid_repeat_count "$stage" "$system" "$l" "$tq")
  (( existing <= target )) || fail "too many existing repeats for $stage/$system/L$l/Tq$tq"
  while (( existing < target )); do
    repeat=$(next_repeat "$stage" "$system" "$l" "$tq")
    echo "running repeat stage=$stage system=$system L=$l Tq=$tq r=$repeat"
    run_one "$stage" "$system" "$l" "$repeat" "$tq"
    ((existing += 1))
  done
}

export ATLAS_GT_DIR="$ROOT/groundtruth/sift10m/$VALIDATION_RUN"
export ATLAS_VALIDATION_RUN_NAME=$VALIDATION_RUN
export ATLAS_NOTIFY_EMAIL=1
export P1_ESTIMATED_REMAINING="约 20--50 分钟"
export P1_EXPECTED_FINISH_UTC="roughly $(date -u -d '+50 minutes' +%Y-%m-%dT%H:%M:%SZ)"
export P1_EXPECTED_FINISH_SHANGHAI="roughly $(TZ=Asia/Shanghai date -d '+50 minutes' +%Y-%m-%dT%H:%M:%S%z)"

# Preserve the first R1 canary attempts, but explicitly exclude them from the
# F0 gate: they used calibration Tq=1 instead of original-F0 Tq=8.
if compgen -G "$ROOT/results/$RUN_NAME/canary/*/tq1/L40/r*/point.json" >/dev/null; then
  run_as_operator python3 - "$ROOT/results/$RUN_NAME/CANARY_TQ1_CONFIGURATION_INVALID.json" <<'PY'
import json, sys, time
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema": "dynamic-vamana-canary-configuration-invalid-v1",
    "marked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "status": "INVALID_CANARY_CONFIGURATION",
    "reason": "F0 reproduction gate requires original-F0 Tq=8; these diagnostic attempts used Tq=1.",
    "preservation": "artifacts retained unchanged and excluded from the F0 gate and calibration summary",
}, indent=2) + "\n")
PY
fi

P2A_PHASE=mark-old-gt-invalid
run_as_operator python3 "$CHAT/mark_invalid_gt_layout.py" --old-run-root "$ROOT/results/pilot3_sift10m_p2" \
  --truthset "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00_2000"

P2A_PHASE=artifact-freeze
for system in DiskANN DGAI OdinANN; do freeze_system "$system"; done

P2A_PHASE=f0-repeatability
notify "Dynamic Vamana P2-A-R1 started: F0 repeatability" "run=$RUN_NAME; full GT; L=40; Tq=8; controller=$LOG"
for system in DiskANN DGAI OdinANN; do
  case "$system" in
    DiskANN) target=3; historical=0.9688 ;;
    DGAI) target=10; historical=0.9216 ;;
    OdinANN) target=10; historical=0.9738 ;;
  esac
  run_to_count canary "$system" 40 8 "$target"
  run_as_operator python3 "$CHAT/analyze_repeatability.py" --points-root "$ROOT/results/$RUN_NAME/canary/$system/tq8/L40" \
    --expected-count "$target" --historical-recall "$historical" --output "$ROOT/results/$RUN_NAME/repeatability_${system}.json"
done
touch "$LOG_DIR/F0_REPEATABILITY_PASSED"
notify "Dynamic Vamana P2-A-R1 F0 repeatability passed" "run=$RUN_NAME; grid may begin; controller=$LOG"

for system in DiskANN DGAI OdinANN; do
  P2A_PHASE="calibration-$system"
  case "$system" in
    DiskANN) levels=(10 12 16 20 24 32 40 60 80) ;;
    DGAI|OdinANN) levels=(20 40 80 120 160 240 320) ;;
  esac
  for l in "${levels[@]}"; do
    run_to_count raw "$system" "$l" 1 3
  done
  notify "Dynamic Vamana P2-A-R1 calibration complete: $system" "run=$RUN_NAME; valid Tq=1 points recorded; controller=$LOG"
done

P2A_PHASE=calibration-summary
run_as_operator python3 "$CHAT/collect_p2_points.py" --raw-root "$ROOT/results/$RUN_NAME/raw" \
  --output-tsv "$ROOT/results/$RUN_NAME/calibration.tsv" --raw-output-tsv "$ROOT/results/$RUN_NAME/calibration_raw_points.tsv" \
  --summary "$ROOT/results/$RUN_NAME/calibration_summary.json"
touch "$LOG_DIR/P2A_R1_CALIBRATION_COMPLETE"
chown -R "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR"
notify "Dynamic Vamana P2-A-R1 calibration complete" "run=$RUN_NAME; STOPPED for GPT review; P2-B/W1/churn were not started."
