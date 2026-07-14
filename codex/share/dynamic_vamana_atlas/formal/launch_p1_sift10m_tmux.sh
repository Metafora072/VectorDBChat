#!/usr/bin/env bash
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
SESSION=${P1_TMUX_SESSION:-p1-sift10m}
LOG="$ROOT/results/pilot3_sift10m/p1_controller/p1.log"

tmux has-session -t "$SESSION" 2>/dev/null && { echo "tmux session already exists: $SESSION" >&2; exit 1; }
sudo -n true
mkdir -p "$(dirname "$LOG")"
tmux new-session -d -s "$SESSION" "exec env ATLAS_ROOT='$ROOT' ATLAS_CHAT_ROOT='$CHAT' '$CHAT/formal/run_p1_sift10m.sh'"
echo "started tmux:$SESSION log=$LOG"
