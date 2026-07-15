#!/usr/bin/env bash
# Root-owned tmux launcher; workers remain in dedicated scopes as ubuntu.
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p1r08}
SESSION=${P1_TMUX_SESSION:-p1-sift10m-r08}
ENV_FILE="$ROOT/results/$RUN_NAME/p1_controller/p1.tmux.env"
(( EUID == 0 )) || { echo "invoke through sudo" >&2; exit 2; }
tmux has-session -t "$SESSION" 2>/dev/null && { echo "tmux session already exists: $SESSION" >&2; exit 1; }
mkdir -p "$(dirname "$ENV_FILE")"
umask 077
{
  printf 'export ATLAS_ROOT=%q\n' "$ROOT"
  printf 'export ATLAS_CHAT_ROOT=%q\n' "$CHAT"
  printf 'export ATLAS_RUN_NAME=%q\n' "$RUN_NAME"
  printf 'export ATLAS_OPERATOR_USER=%q\n' "${ATLAS_OPERATOR_USER:-ubuntu}"
  printf 'export ATLAS_NOTIFY_EMAIL=%q\n' "${ATLAS_NOTIFY_EMAIL:-1}"
  printf 'export DGAI_F0_ATTEMPT=%q\n' "${DGAI_F0_ATTEMPT:-p1r08-dgai-01}"
  printf 'export ODIN_F0_ATTEMPT=%q\n' "${ODIN_F0_ATTEMPT:-p1r08-odin-01}"
} >"$ENV_FILE"
umask 022
printf -v command 'set -a; source %q; exec %q' "$ENV_FILE" "$CHAT/formal/run_dgai_oom_recovery.sh"
tmux new-session -d -s "$SESSION" "$command"
echo "started tmux:$SESSION"
