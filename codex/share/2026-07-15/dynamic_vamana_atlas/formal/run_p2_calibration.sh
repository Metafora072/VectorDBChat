#!/usr/bin/env bash
# GPT-authorized P2-A: measurement canary then three-system Tq=1 Recall calibration.
set -Eeuo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p2}
OPERATOR_USER=${ATLAS_OPERATOR_USER:-ubuntu}
VALIDATION_RUN=pilot3_sift10m_p1r07
LOG_DIR="$ROOT/results/$RUN_NAME/p2_controller"
LOG="$LOG_DIR/p2.log"
mkdir -p "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/datasets/sift10m_p2" "$ROOT/results/$RUN_NAME"
chown "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$ROOT/datasets/sift10m_p2" "$ROOT/results/$RUN_NAME"
exec > >(tee -a "$LOG") 2>&1

notify() { "$CHAT/formal/notify_owner.sh" "$1" "$2" || echo "MailSender failure does not change P2 state" >&2; }
fail() { local code=$?; notify "Dynamic Vamana P2 failed" "phase=${P2_PHASE:-preflight} exit=$code log=$LOG"; exit "$code"; }
trap fail ERR
run_as_operator() { runuser -u "$OPERATOR_USER" --preserve-environment -- "$@"; }

# A completed point is immutable evidence: retain it and resume only the
# missing points.  A failed partial attempt receives a fresh rN directory so
# its logs cannot be overwritten by the retry.
point_complete() {
  local system=$1 l=$2
  compgen -G "$ROOT/results/$RUN_NAME/raw/$system/tq1/L$l/r*/point.json" >/dev/null
}

next_repeat() {
  local system=$1 l=$2 repeat=1
  while [[ -e "$ROOT/results/$RUN_NAME/raw/$system/tq1/L$l/r$repeat" || \
           -e "$ROOT/formal/$RUN_NAME/raw/$system/tq1/L$l/r$repeat" ]]; do
    ((repeat += 1))
  done
  printf '%s\n' "$repeat"
}

export ATLAS_GT_DIR="$ROOT/groundtruth/sift10m/$VALIDATION_RUN"
export ATLAS_VALIDATION_RUN_NAME=$VALIDATION_RUN
export ATLAS_NOTIFY_EMAIL=1
export P1_ESTIMATED_REMAINING="约 20--50 分钟"
export P1_EXPECTED_FINISH_UTC="roughly $(date -u -d '+50 minutes' +%Y-%m-%dT%H:%M:%SZ)"
export P1_EXPECTED_FINISH_SHANGHAI="roughly $(TZ=Asia/Shanghai date -d '+50 minutes' +%Y-%m-%dT%H:%M:%S%z)"

P2_PHASE=memory-events-canary
notify "Dynamic Vamana P2 started: memory-events canary" "run=$RUN_NAME; log=$LOG"
F0_ATTEMPT=${P2_CANARY_ATTEMPT:-events-canary-01} "$CHAT/formal/f0_runtime_canary.sh"

P2_PHASE=prepare-query-prefix
run_as_operator python3 "$CHAT/make_binary_prefix.py" --input "$ROOT/datasets/sift10m/query.bin" \
  --output "$ROOT/datasets/sift10m_p2/query_2000.bin" --rows 2000
run_as_operator python3 "$CHAT/make_binary_prefix.py" --input "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00" \
  --output "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00_2000" --rows 2000

for system in DiskANN DGAI OdinANN; do
  P2_PHASE="calibration-$system"
  for L in 20 40 80 120 160 240 320; do
    if point_complete "$system" "$L"; then
      echo "resume: retaining completed point system=$system L=$L"
      continue
    fi
    repeat=$(next_repeat "$system" "$L")
    echo "resume: running missing point system=$system L=$L repeat=$repeat"
    P2_SYSTEM="$system" P2_L="$L" P2_TQ=1 P2_REPEAT="$repeat" "$CHAT/formal/p2_query_point.sh"
  done
  notify "Dynamic Vamana P2 calibration complete: $system" "run=$RUN_NAME; seven Tq=1 L points complete; log=$LOG"
done

P2_PHASE=calibration-summary
run_as_operator python3 "$CHAT/collect_p2_points.py" --raw-root "$ROOT/results/$RUN_NAME/raw" \
  --output-tsv "$ROOT/results/$RUN_NAME/calibration.tsv" --summary "$ROOT/results/$RUN_NAME/calibration_summary.json"
notify "Dynamic Vamana P2 calibration complete" "run=$RUN_NAME; common Recall targets are recorded in calibration_summary.json; STOPPED pending automatic P2-B selection."
touch "$LOG_DIR/P2_CALIBRATION_COMPLETE"
chown -R "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR"
