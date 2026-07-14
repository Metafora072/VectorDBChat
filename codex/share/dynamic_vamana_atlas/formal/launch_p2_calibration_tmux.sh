#!/usr/bin/env bash
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p2}
SESSION=${P2_TMUX_SESSION:-p2-sift10m-calibration}
ENV_FILE="$ROOT/results/$RUN_NAME/p2_controller/p2.tmux.env"
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
  printf 'export P2_CANARY_ATTEMPT=%q\n' "${P2_CANARY_ATTEMPT:-events-canary-01}"
} >"$ENV_FILE"
umask 022
printf -v command 'set -a; source %q; exec %q' "$ENV_FILE" "$CHAT/formal/run_p2_calibration.sh"
tmux new-session -d -s "$SESSION" "$command"
echo "started tmux:$SESSION"
