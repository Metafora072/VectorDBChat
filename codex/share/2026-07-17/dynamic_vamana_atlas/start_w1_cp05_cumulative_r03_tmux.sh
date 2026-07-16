#!/usr/bin/env bash
# Start the root-owned, NVMe-logged CP05 cumulative R03 controller in detached tmux.
set -euo pipefail
(( EUID == 0 )) || { echo 'tmux launcher must run as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
script=$(realpath "$(dirname "${BASH_SOURCE[0]}")/run_w1_cp05_cumulative_trajectory_r03.sh")
session=dv-w1-cp05-trajectory-r03
log="$root/results/pilot3_sift10m_w1_cp05_trajectory_r03.controller.log"
[[ ! -e $log ]] || { echo 'controller log reuse refused' >&2; exit 1; }
tmux has-session -t "$session" 2>/dev/null && { echo 'CP05 cumulative R03 tmux already exists' >&2; exit 1; }
tmux new-session -d -s "$session" \
  "exec timeout --foreground --signal=TERM --kill-after=5m 3h env W1_CP05_R03_CUMULATIVE_AUTHORIZED=1 ATLAS_CONTROLLER_LOG_PATH='$log' '$script' >'$log' 2>&1"
printf 'started session=%s log=%s\n' "$session" "$log"
