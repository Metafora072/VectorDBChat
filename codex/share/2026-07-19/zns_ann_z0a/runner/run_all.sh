#!/usr/bin/env bash
set -euo pipefail
[[ ${Z0A_AUTHORIZED:-0} == 1 ]] || exit 64
share=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
run_root="$root/z0a_trace_model_preflight_0719"
mkdir -p "$run_root/inputs"
[[ -e "$run_root/inputs/sanity-sift10k-fresh-replace2k" ]] || { echo 'prepared 2K sanity input missing' >&2; exit 1; }
python3 "$share/space_preflight.py" --target-root "$run_root" --allowed-prefix "$root" --output "$run_root/space_preflight.json"
# Interleaved AB/BA ordering controls drift without clearing global caches.
for system in DGAI OdinANN; do
  for spec in 1:off 1:on 2:on 2:off 3:off 3:on; do
    IFS=: read -r repeat mode <<<"$spec"
    "$share/runner/run_one.sh" "$system" "$mode" "$repeat"
  done
done
python3 "$share/runner/summarize_runs.py" --root "$run_root/results" --output "$run_root/z0a_run_summary.json"
