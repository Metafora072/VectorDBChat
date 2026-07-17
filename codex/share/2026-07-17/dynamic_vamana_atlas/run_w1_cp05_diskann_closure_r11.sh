#!/usr/bin/env bash
# Fail-closed DiskANN-only R11 continuation composing with terminal R10 dynamic evidence.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ulimit -c 0
[[ ${W1_CP05_DISKANN_R11_AUTHORIZED:-0} == 1 ]] || { echo 'DiskANN R11 authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'DiskANN R11 controller must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
r01=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
r02=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas
run=pilot3_sift10m_w1_cp05_diskann_closure_r11
result="$root/results/$run"; tmp="$root/tmp/$run"
r10_result="$root/results/pilot3_sift10m_w1_cp05_trajectory_r10"
r10_formal="$root/formal/pilot3_sift10m_w1_cp05_trajectory_r10"
r10_replay_formal="$root/formal/pilot3_w1_cp05_trajectory_replay_r10"
r10_preflight="$r10_result/preflight/execution_preflight.json"
r10_execution="$r10_result/execution_manifest.json"
r10_preservation="$r10_result/preflight/preservation_after_stop.json"
artifact="$r01/artifact_rebuild_manifest.json"
runtime="$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json"
base="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
query="$root/datasets/sift10m/query.bin"; gt="$root/groundtruth/sift10m/w1_trajectory/cp05/gt_cp05"
preflight="$result/preflight/execution_preflight.json"; manifest="$result/execution_manifest.json"
closure="$result/closure_manifest.json"
report="$new/../dynamic_vamana_w1_cp05_cumulative_trajectory_r10_r11_closure_results_0717.md"
phase=initializing; attempt_armed=0

notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$r01/formal/notify_owner.sh" "$1" "$2" || true
}

on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    systemctl stop dv-w1-cp05-diskann-r11-stale.scope >/dev/null 2>&1 || true
    if (( attempt_armed == 1 )) && [[ -f $manifest ]]; then
      python3 "$new/w1_diskann_r11_execution_manifest.py" stop --manifest "$manifest" \
        --phase "$phase" --exit-code "$rc" || true
      if [[ ! -e $result/preflight/r10_preservation_after_r11_stop.json ]]; then
        python3 "$new/w1_cp05_r10_preservation.py" --preflight "$r10_preflight" \
          --phase r11_stop --output "$result/preflight/r10_preservation_after_r11_stop.json" || true
      fi
    fi
    notify "Dynamic Vamana DiskANN R11 $phase failed" \
      "exit=$rc phase=$phase; R10 remains terminal and CP10/CP20 remain HOLD"
  fi
}
trap on_exit EXIT

for target in "$result" "$tmp" "$report"; do
  [[ ! -e $target ]] || { echo "DiskANN R11 launch target is not fresh: $target" >&2; exit 1; }
done
mkdir -p "$root/locks" "$tmp"; chmod 0770 "$tmp"; chown ubuntu:ubuntu "$tmp"
export TMPDIR="$tmp" TMP="$tmp" TEMP="$tmp"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global flock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$
if systemctl list-units --all --plain --no-legend 'dv-w1-cp05-diskann-r11-*' 2>/dev/null | awk 'NF{bad=1} END{exit !bad}'; then
  echo 'stale DiskANN R11 unit exists' >&2; exit 1
fi

phase=r11_preflight
python3 "$new/w1_cp05_diskann_r11_preflight.py" self-test --scratch "$tmp" \
  --output "$tmp/r11_preflight_self_test.json"
python3 "$new/w1_cp05_r10_preservation.py" --preflight "$r10_preflight" --phase r11_preflight \
  --output "$tmp/r10_preservation_revalidation.json"
python3 "$r01/w1_file_manifest.py" --root "$base" --output "$tmp/DiskANN.content.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$tmp/DiskANN.mode.tsv"
install -d -m 0755 "$result/preflight"
install -m 0444 "$tmp/r11_preflight_self_test.json" "$result/preflight/r11_preflight_self_test.json"
install -m 0444 "$tmp/r10_preservation_revalidation.json" "$result/preflight/r10_preservation_revalidation.json"
install -m 0444 "$tmp/DiskANN.content.tsv" "$result/preflight/DiskANN.content.before.tsv"
install -m 0444 "$tmp/DiskANN.mode.tsv" "$result/preflight/DiskANN.mode.before.tsv"
python3 "$new/w1_cp05_diskann_r11_preflight.py" validate --root "$root" \
  --r10-result "$r10_result" --r10-formal "$r10_formal" --r10-replay-formal "$r10_replay_formal" \
  --r11-result "$result" --artifact-manifest "$artifact" --runtime-manifest "$runtime" \
  --base-root "$base" --base-content "$result/preflight/DiskANN.content.before.tsv" \
  --base-mode "$result/preflight/DiskANN.mode.before.tsv" --query "$query" --cp05-gt "$gt" \
  --r10-preservation-revalidation "$result/preflight/r10_preservation_revalidation.json" \
  --report "$report" --closure-manifest "$closure" --device "${ATLAS_NVME_MAJMIN:-259:10}" \
  --output "$preflight"
python3 "$new/w1_diskann_r11_execution_manifest.py" activate --manifest "$manifest" \
  --preflight "$preflight" --r10-execution "$r10_execution" --r10-preservation "$r10_preservation" \
  --phase diskann_cp05_stale_control
attempt_armed=1

phase=diskann_cp05_stale_control
install -d -o ubuntu -g ubuntu "$result/DiskANN"
unit=dv-w1-cp05-diskann-r11-stale
systemd-run --scope --collect --unit "$unit" --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
  --property=IOAccounting=yes --property=MemoryMax=4G --property=RuntimeMaxSec=2700 \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
    W1_CP05_DISKANN_R11_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" \
    ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" W1_EXPECTED_SCOPE="$unit.scope" \
  prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 \
    "$new/w1_run_diskann_cp05_stale_r11.sh" "$query" "$gt" \
      "$result/DiskANN/stale-cp05-11" "$artifact" "$runtime" "$r10_preflight" "$preflight"

phase=post_r11_preservation
python3 "$new/w1_diskann_r11_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cp05_r10_preservation.py" --preflight "$r10_preflight" --phase after_r11 \
  --output "$result/preflight/r10_preservation_after_r11.json"

phase=composed_closure
python3 "$new/w1_diskann_r11_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cp05_r10_r11_closure_finalize.py" --root "$root" --r10-result "$r10_result" \
  --r10-formal "$r10_formal" --r11-result "$result" --r11-preflight "$preflight" \
  --r10-post-preservation "$result/preflight/r10_preservation_after_r11.json" \
  --closure-manifest "$closure" --output-report "$report"
python3 "$new/w1_diskann_r11_execution_manifest.py" complete --manifest "$manifest" \
  --closure-manifest "$closure"
touch "$result/FORMAL_W1_CP05_R10_R11_CLOSURE_COMPLETE"
notify "Dynamic Vamana R10 + R11 closure complete" \
  "R11 DiskANN stale control and composed closure completed; CP10/CP20 remain HOLD"
