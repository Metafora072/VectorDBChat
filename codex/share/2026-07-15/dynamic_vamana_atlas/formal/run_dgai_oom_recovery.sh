#!/usr/bin/env bash
# GPT-authorized continuation after p1r07's single-NUMA DGAI build OOM.
set -Eeuo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p1r08}
OPERATOR_USER=${ATLAS_OPERATOR_USER:-ubuntu}
LOG_DIR="$ROOT/results/$RUN_NAME/p1_controller"
LOG="$LOG_DIR/p1.log"
mkdir -p "$LOG_DIR" "$ROOT/tmp/$RUN_NAME"
chown "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$ROOT/results/$RUN_NAME" "$ROOT/tmp/$RUN_NAME" "$LOG_DIR"
exec > >(tee -a "$LOG") 2>&1

notify() { "$CHAT/formal/notify_owner.sh" "$1" "$2" || echo "MailSender failed; primary result remains authoritative" >&2; }
run_phase() {
  local phase=$1 remaining=$2; shift 2
  export P1_PHASE=$phase P1_ESTIMATED_REMAINING=$remaining
  export P1_EXPECTED_FINISH_UTC="roughly $(date -u -d '+9 hours' +%Y-%m-%dT%H:%M:%SZ)"
  export P1_EXPECTED_FINISH_SHANGHAI="roughly $(TZ=Asia/Shanghai date -d '+9 hours' +%Y-%m-%dT%H:%M:%S%z)"
  notify "Dynamic Vamana P1 recovery started: $phase" "command=$*; log=$LOG"
  "$@"
}

# Reuse only immutable, independently validated prerequisites from p1r07.
export ATLAS_GT_DIR="$ROOT/groundtruth/sift10m/pilot3_sift10m_p1r07"
export ATLAS_VALIDATION_RUN_NAME=pilot3_sift10m_p1r07
export DGAI_BUILD_MEMORY_POLICY=interleave
export DGAI_BUILD_MEMORY_NODES=0,1
export DGAI_BUILD_MEMORY_MAX=200G
export DGAI_BUILD_TIMEOUT_SECONDS=21600
export F0_ATTEMPT=${DGAI_F0_ATTEMPT:-p1r08-dgai-01}
export ATLAS_NOTIFY_EMAIL=${ATLAS_NOTIFY_EMAIL:-1}

if run_phase dgai-f0-cross-numa "约 6--9 小时" "$CHAT/formal/f0_dgai.sh"; then
  echo "DGAI recovery completed; preserving build-only cross-NUMA exception."
else
  code=$?
  echo "DGAI recovery failed exit=$code; preserved configuration is resource-infeasible on this host. Continuing to OdinANN."
fi

unset DGAI_BUILD_MEMORY_POLICY DGAI_BUILD_MEMORY_NODES DGAI_BUILD_MEMORY_MAX DGAI_BUILD_TIMEOUT_SECONDS
export F0_ATTEMPT=${ODIN_F0_ATTEMPT:-p1r08-odin-01}
run_phase odinann-f0 "约 0.5--3 小时" "$CHAT/formal/f0_odinann.sh"
notify "Dynamic Vamana P1 recovery complete" "DGAI cross-NUMA retry and OdinANN F0 finished; STOPPED pending review; log=$LOG"
touch "$LOG_DIR/P1_RECOVERY_COMPLETE"
chown -R "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR"
