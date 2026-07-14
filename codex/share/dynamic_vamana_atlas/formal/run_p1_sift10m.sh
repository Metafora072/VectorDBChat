#!/usr/bin/env bash
# Strictly serial P1 controller. Invoke only inside a dedicated tmux session.
set -Eeuo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m}
LOG_DIR="$ROOT/results/$RUN_NAME/p1_controller"
LOG="$LOG_DIR/p1.log"
mkdir -p "$LOG_DIR"
export TMPDIR="$ROOT/tmp/$RUN_NAME/p1_controller"
mkdir -p "$TMPDIR"
exec > >(tee -a "$LOG") 2>&1

notify() {
  "$CHAT/formal/notify_owner.sh" "$1" "$2" || echo "MailSender failed; main P1 state remains authoritative" >&2
}
fail() {
  local code=$?
  notify "Dynamic Vamana P1 failed" "exit=$code phase=${P1_PHASE:-preflight} log=$LOG; subsequent stages stopped"
  exit "$code"
}
trap fail ERR

require_source() {
  [[ "${SIFT10M_SOURCE_FORMAT:-u8bin}" =~ ^(u8bin|bvecs)$ ]] \
    || { echo "SIFT10M_SOURCE_FORMAT must be u8bin or bvecs" >&2; exit 2; }
  [[ -n "${SIFT10M_BASE_INPUT:-}${SIFT10M_BASE_URL:-}" ]] \
    || { echo "set SIFT10M_BASE_INPUT or SIFT10M_BASE_URL" >&2; exit 2; }
  [[ -n "${SIFT10M_QUERY_INPUT:-}${SIFT10M_QUERY_URL:-}" ]] \
    || { echo "set SIFT10M_QUERY_INPUT or SIFT10M_QUERY_URL" >&2; exit 2; }
}
run_stage() {
  local phase=$1 remaining=$2; shift 2
  export P1_PHASE="$phase"
  export P1_ESTIMATED_REMAINING="$remaining"
  export P1_EXPECTED_FINISH_UTC="roughly $(date -u -d "+${P1_REMAINING_HOURS:-24} hours" +%Y-%m-%dT%H:%M:%SZ)"
  export P1_EXPECTED_FINISH_SHANGHAI="roughly $(TZ=Asia/Shanghai date -d "+${P1_REMAINING_HOURS:-24} hours" +%Y-%m-%dT%H:%M:%S%z)"
  notify "Dynamic Vamana P1 started: $phase" "command=$*; log=$LOG"
  "$@"
}

case "$(realpath -m "$ROOT")" in /home/ubuntu/pz/VectorDB/data|/home/ubuntu/pz/VectorDB/data/*) ;; *) exit 2 ;; esac
require_source
sudo -n true

export F0_ATTEMPT=${F0_ATTEMPT:-p1-01}
export ATLAS_NOTIFY_EMAIL=${ATLAS_NOTIFY_EMAIL:-1}
P1_REMAINING_HOURS=24 run_stage runtime-canary "约 12--24 小时" \
  env F0_ATTEMPT=p1-canary-01 "$CHAT/formal/f0_runtime_canary.sh"
P1_REMAINING_HOURS=20 run_stage sift10m-prepare "约 10--20 小时" "$CHAT/prepare_sift10m.sh"
P1_REMAINING_HOURS=14 run_stage checkpoint0-gt-validation "约 5--14 小时" "$CHAT/validate_sift10m.sh"
P1_REMAINING_HOURS=9 run_stage diskann-f0 "约 3--9 小时" "$CHAT/formal/f0_diskann.sh"
P1_REMAINING_HOURS=6 run_stage dgai-f0 "约 1.5--6 小时" "$CHAT/formal/f0_dgai.sh"
P1_REMAINING_HOURS=3 run_stage odinann-f0 "约 0.5--3 小时" "$CHAT/formal/f0_odinann.sh"

export P1_PHASE=p1-complete
export P1_ESTIMATED_REMAINING=0
export P1_EXPECTED_FINISH_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export P1_EXPECTED_FINISH_SHANGHAI="$(TZ=Asia/Shanghai date +%Y-%m-%dT%H:%M:%S%z)"
notify "Dynamic Vamana P1 F0 complete" "all three systems completed; STOPPED pending review; log=$LOG"
touch "$LOG_DIR/P1_F0_COMPLETE"
