#!/usr/bin/env bash
# R12 CP05->CP10 continuation; CP20 remains HOLD.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ulimit -c 0
[[ ${W1_CP10_R12_AUTHORIZED:-0} == 1 ]] || { echo 'R12 authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'R12 controller must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
r02=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas
run=pilot3_sift10m_w1_cp10_trajectory_r12
result="$root/results/$run"; formal="$root/formal/$run"; tmp="$root/tmp/$run"
r10="$root/results/pilot3_sift10m_w1_cp05_trajectory_r10"
r11="$root/results/pilot3_sift10m_w1_cp05_diskann_closure_r11"
closure="$r11/closure_manifest.json"
artifact="$old/artifact_rebuild_manifest.json"
runtime="$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json"
query="$root/datasets/sift10m/query.bin"; gt="$root/groundtruth/sift10m/w1_trajectory/cp10/gt_cp10"
preflight="$result/preflight/execution_preflight.json"; manifest="$result/execution_manifest.json"
report="$new/../dynamic_vamana_w1_cp10_trajectory_r12_results_0717.md"
phase=initializing; armed=0

notify() { [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0; "$old/formal/notify_owner.sh" "$1" "$2" || true; }
stop_units() {
  local unit
  while read -r unit; do [[ -z $unit ]] || systemctl stop "$unit" >/dev/null 2>&1 || true; done \
    < <(systemctl list-units --all --plain --no-legend 'dv-w1-cp10-r12-*' 2>/dev/null | awk '{print $1}')
}
on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    stop_units
    if (( armed == 1 )) && [[ -f $manifest ]]; then
      python3 "$new/w1_cp10_r12_execution_manifest.py" stop --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true
    fi
    notify "Dynamic Vamana CP10 R12 failed" "exit=$rc phase=$phase; fail-closed; CP20 remains HOLD"
  fi
}
trap on_exit EXIT

for target in "$result" "$formal" "$tmp" "$report"; do [[ ! -e $target ]] || { echo "R12 target is not fresh: $target" >&2; exit 1; }; done
mkdir -p "$root/locks" "$tmp"; chmod 0770 "$tmp"; chown ubuntu:ubuntu "$tmp"
export TMPDIR="$tmp" TMP="$tmp" TEMP="$tmp"
exec 9>"$root/locks/pilot3_w1_global.lock"; flock -n 9 || { echo 'another W1 path owns the global flock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$
if systemctl list-units --all --plain --no-legend 'dv-w1-cp10-r12-*' 2>/dev/null | awk 'NF{bad=1} END{exit !bad}'; then
  echo 'stale R12 transient unit exists' >&2; exit 1
fi
free_bytes=$(df -PB1 "$root" | awk 'NR==2{print $4}'); mem_bytes=$(awk '/^MemAvailable:/{print $2*1024}' /proc/meminfo)
(( free_bytes >= 128 * 1024 * 1024 * 1024 )) || { echo 'R12 free-space guard failed' >&2; exit 1; }
(( mem_bytes >= 64 * 1024 * 1024 * 1024 )) || { echo 'R12 memory guard failed' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'R12 root not on project NVMe' >&2; exit 1; }

phase=derive_cp05_to_cp10_input
install -d -m 0755 "$result" "$result/preflight"
python3 "$new/w1_cp10_prepare_r12.py" --root "$root" --helper "$r02/w1_cumulative_prepare.py" --output-root "$result/inputs"
phase=r12_preflight
python3 "$new/w1_cp10_r12_preflight.py" --root "$root" --input-manifest "$result/inputs/input_manifest.json" \
  --closure "$closure" --output "$preflight"
python3 "$new/w1_cp10_r12_execution_manifest.py" activate --manifest "$manifest" --preflight "$preflight"
armed=1

canonical="$root/build/w1-canonical-v6/install"
for system in DGAI OdinANN; do
  phase="cp10_${system}"
  python3 "$new/w1_cp10_r12_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
  freeze="$r10/$system/trajectory-cp05-10/checkpoints/cp05/cp05_freeze_evidence.json"
  base=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["root_realpath"])' "$freeze")
  if [[ $system == DGAI ]]; then ls=64,128; else ls=29,46; fi
  W1_CP10_R12_AUTHORIZED=1 "$new/w1_run_cp10_system_r12.sh" "$system" "$base" "$freeze" \
    "$canonical/$system/w1_canary" "$canonical/$system/search_disk_index" "$ls"
done

phase=diskann_cp10_stale_control
python3 "$new/w1_cp10_r12_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
install -d -o ubuntu -g ubuntu "$result/DiskANN"
unit=dv-w1-cp10-r12-diskann-stale
systemd-run --scope --collect --unit "$unit" --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
  --property=IOAccounting=yes --property=MemoryMax=4G --property=RuntimeMaxSec=2700 \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
    W1_CP10_DISKANN_R12_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" \
    ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" W1_EXPECTED_SCOPE="$unit.scope" \
  prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 \
  "$new/w1_run_diskann_cp10_stale_r12.sh" "$query" "$gt" "$result/DiskANN/stale-cp10-12" \
    "$artifact" "$runtime" "$r10/preflight/execution_preflight.json" "$preflight"

phase=finalize
python3 "$new/w1_cp10_r12_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cp10_r12_finalize.py" --root "$root" --output-report "$report"
python3 "$new/w1_cp10_r12_execution_manifest.py" complete --manifest "$manifest"
touch "$result/FORMAL_W1_CP10_R12_COMPLETE"
notify "Dynamic Vamana CP10 R12 complete" "DGAI/OdinANN CP05->CP10 and DiskANN stale control completed; CP20 remains HOLD"
