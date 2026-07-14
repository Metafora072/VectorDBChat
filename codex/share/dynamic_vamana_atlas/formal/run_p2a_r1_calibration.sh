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
mkdir -p "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/results/$RUN_NAME"
chown "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/results/$RUN_NAME"
exec > >(tee -a "$LOG") 2>&1

notify() { "$CHAT/formal/notify_owner.sh" "$1" "$2" || echo "MailSender failure does not change P2-A-R1 state" >&2; }
fail() { local code=$?; notify "Dynamic Vamana P2-A-R1 failed" "phase=${P2A_PHASE:-preflight} exit=$code log=$LOG; subsequent stages stopped"; exit "$code"; }
trap fail ERR
run_as_operator() { runuser -u "$OPERATOR_USER" --preserve-environment -- "$@"; }

point_valid() {
  local stage=$1 system=$2 l=$3
  local point
  for point in "$ROOT/results/$RUN_NAME/$stage/$system/tq1/L$l"/r*/point.json; do
    [[ -f "$point" ]] || continue
    python3 - "$point" <<'PY' >/dev/null && return 0
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("valid") is True else 1)
PY
  done
  return 1
}

next_repeat() {
  local stage=$1 system=$2 l=$3 repeat=1
  while [[ -e "$ROOT/results/$RUN_NAME/$stage/$system/tq1/L$l/r$repeat" || \
           -e "$ROOT/formal/$RUN_NAME/$stage/$system/tq1/L$l/r$repeat" ]]; do
    ((repeat += 1))
  done
  printf '%s\n' "$repeat"
}

run_one() {
  local stage=$1 system=$2 l=$3 repeat=$4
  P2A_STAGE="$stage" P2A_SYSTEM="$system" P2A_L="$l" P2A_TQ=1 P2A_REPEAT="$repeat" \
    "$CHAT/formal/p2a_r1_query_point.sh"
}

export ATLAS_GT_DIR="$ROOT/groundtruth/sift10m/$VALIDATION_RUN"
export ATLAS_VALIDATION_RUN_NAME=$VALIDATION_RUN
export ATLAS_NOTIFY_EMAIL=1
export P1_ESTIMATED_REMAINING="约 20--50 分钟"
export P1_EXPECTED_FINISH_UTC="roughly $(date -u -d '+50 minutes' +%Y-%m-%dT%H:%M:%SZ)"
export P1_EXPECTED_FINISH_SHANGHAI="roughly $(TZ=Asia/Shanghai date -d '+50 minutes' +%Y-%m-%dT%H:%M:%S%z)"

P2A_PHASE=mark-old-gt-invalid
run_as_operator python3 "$CHAT/mark_invalid_gt_layout.py" --old-run-root "$ROOT/results/pilot3_sift10m_p2" \
  --truthset "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00_2000"

P2A_PHASE=f0-reproduction-canary
notify "Dynamic Vamana P2-A-R1 started: full-10K F0 reproduction" "run=$RUN_NAME; full GT; L=40; controller=$LOG"
for system in DiskANN DGAI OdinANN; do
  if point_valid canary "$system" 40; then
    echo "resume: retaining valid F0 canary system=$system L=40"
    continue
  fi
  repeat=$(next_repeat canary "$system" 40)
  run_one canary "$system" 40 "$repeat"
  run_as_operator python3 "$CHAT/verify_f0_reproduction.py" \
    --point "$ROOT/results/$RUN_NAME/canary/$system/tq1/L40/r$repeat/point.json"
done
touch "$LOG_DIR/F0_REPRODUCTION_PASSED"
notify "Dynamic Vamana P2-A-R1 F0 reproduction passed" "run=$RUN_NAME; grid may begin; controller=$LOG"

for system in DiskANN DGAI OdinANN; do
  P2A_PHASE="calibration-$system"
  case "$system" in
    DiskANN) levels=(10 12 16 20 24 32 40 60 80) ;;
    DGAI|OdinANN) levels=(20 40 80 120 160 240 320) ;;
  esac
  for l in "${levels[@]}"; do
    if point_valid raw "$system" "$l"; then
      echo "resume: retaining valid point system=$system L=$l"
      continue
    fi
    repeat=$(next_repeat raw "$system" "$l")
    echo "running P2-A-R1 point system=$system L=$l repeat=$repeat"
    run_one raw "$system" "$l" "$repeat"
  done
  notify "Dynamic Vamana P2-A-R1 calibration complete: $system" "run=$RUN_NAME; valid Tq=1 points recorded; controller=$LOG"
done

P2A_PHASE=calibration-summary
run_as_operator python3 "$CHAT/collect_p2_points.py" --raw-root "$ROOT/results/$RUN_NAME/raw" \
  --output-tsv "$ROOT/results/$RUN_NAME/calibration.tsv" --summary "$ROOT/results/$RUN_NAME/calibration_summary.json"
touch "$LOG_DIR/P2A_R1_CALIBRATION_COMPLETE"
chown -R "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR"
notify "Dynamic Vamana P2-A-R1 calibration complete" "run=$RUN_NAME; STOPPED for GPT review; P2-B/W1/churn were not started."
