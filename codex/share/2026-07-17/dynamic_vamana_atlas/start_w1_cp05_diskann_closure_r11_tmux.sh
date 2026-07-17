#!/usr/bin/env bash
# Start the root-owned, NVMe-logged DiskANN-only R11 closure controller.
set -euo pipefail
(( EUID == 0 )) || { echo 'DiskANN R11 tmux launcher must run as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
script=$(realpath "$(dirname "${BASH_SOURCE[0]}")/run_w1_cp05_diskann_closure_r11.sh")
session=dv-w1-cp05-diskann-closure-r11
log="$root/results/pilot3_sift10m_w1_cp05_diskann_closure_r11.controller.log"
[[ ! -e $log ]] || { echo 'DiskANN R11 controller log reuse refused' >&2; exit 1; }
tmux has-session -t "$session" 2>/dev/null && { echo 'DiskANN R11 tmux already exists' >&2; exit 1; }
tmux new-session -d -s "$session" \
  "exec timeout --foreground --signal=TERM --kill-after=5m 90m env W1_CP05_DISKANN_R11_AUTHORIZED=1 ATLAS_CONTROLLER_LOG_PATH='$log' '$script' >'$log' 2>&1"
printf 'started session=%s log=%s\n' "$session" "$log"
