#!/usr/bin/env bash
# The only tmux launcher.  It refuses to run without a post-review capability.
set -euo pipefail
[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing tmux launch' >&2; exit 64; }
[[ $# == 1 && ( $1 == DGAI || $1 == OdinANN ) ]] || { echo "usage: $0 DGAI|OdinANN" >&2; exit 2; }
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); system=$1
case "$system" in DGAI) slug=dgai ;; OdinANN) slug=odin ;; esac
session="dynamic-vamana-w1-${slug}"
tmux has-session -t "$session" 2>/dev/null && { echo "session exists: $session" >&2; exit 1; }
script="$chat/w1_${slug}_1pct_canary.sh"; [[ -x "$script" ]] || { echo "missing executable: $script" >&2; exit 1; }
tmux new-session -d -s "$session" "exec env W1_EXECUTE_AUTHORIZED=1 $script"
