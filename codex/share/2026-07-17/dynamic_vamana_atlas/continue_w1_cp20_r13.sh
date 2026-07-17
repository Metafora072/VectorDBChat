#!/usr/bin/env bash
# Authorized control-plane continuation after pre-query capability-name rejection.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_CP20_R13_CONTINUATION_AUTHORIZED:-0} == 1 ]] || exit 64
(( EUID == 0 )) || exit 1
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
result="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13"; r12="$root/results/pilot3_sift10m_w1_cp10_trajectory_r12"
manifest="$result/continuation_manifest.json"; execution="$result/execution_manifest.json"; phase=initializing; armed=0
report="$new/../dynamic_vamana_w1_cp20_trajectory_r13_results_0717.md"; artifact="$old/artifact_rebuild_manifest.json"
runtime="$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json"; query="$root/datasets/sift10m/query.bin"; gt="$root/groundtruth/sift10m/w1_trajectory/cp20/gt_cp20"
notify(){ [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0; "$old/formal/notify_owner.sh" "$1" "$2" || true; }
stop_units(){ local unit; while read -r unit; do [[ -z $unit ]] || systemctl stop "$unit" >/dev/null 2>&1 || true; done < <(systemctl list-units --all --plain --no-legend 'dv-w1-cp20-r13-*' 'dv-w1-cum-r03-r13-*' 2>/dev/null | awk '{print $1}'); }
on_exit(){ rc=$?; if ((rc));then stop_units;if ((armed));then python3 "$new/w1_cp20_r13_continuation_manifest.py" stop --manifest "$manifest" --phase "$phase" --exit-code "$rc"||true;fi;notify 'Dynamic Vamana CP20 R13 continuation failed' "exit=$rc phase=$phase; fail-closed";fi;};trap on_exit EXIT
[[ ! -e $manifest && ! -e $report ]] || exit 1
exec 9>"$root/locks/pilot3_w1_global.lock";flock -n 9||exit 1;export W1_GLOBAL_LOCK_HELD=1
python3 "$new/w1_cp20_r13_continuation_manifest.py" activate --manifest "$manifest" --r13-execution "$execution";armed=1
phase=resume_DGAI_query;W1_CP20_R13_CONTINUATION_AUTHORIZED=1 "$new/w1_resume_dgai_query_r13.sh"
canonical="$root/build/w1-canonical-v6/install";phase=cp20_OdinANN;python3 "$new/w1_cp20_r13_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase"
freeze="$r12/OdinANN/trajectory-cp10-12/checkpoints/cp10/cp10_freeze_evidence.json";base=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["root_realpath"])' "$freeze")
W1_CP20_R13_AUTHORIZED=1 "$new/w1_run_cp20_system_r13.sh" OdinANN "$base" "$freeze" "$canonical/OdinANN/w1_canary" "$canonical/OdinANN/search_disk_index" 29,46
phase=diskann_cp20_stale_control;python3 "$new/w1_cp20_r13_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase";install -d -o ubuntu -g ubuntu "$result/DiskANN"
unit=dv-w1-cp20-r13-diskann-stale
systemd-run --scope --collect --unit "$unit" --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes --property=MemoryMax=4G --property=RuntimeMaxSec=2700 \
 env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 W1_CP20_DISKANN_R13_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" W1_EXPECTED_SCOPE="$unit.scope" \
 prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 "$new/w1_run_diskann_cp20_stale_r13.sh" "$query" "$gt" "$result/DiskANN/stale-cp20-13" "$artifact" "$runtime" "$result/preflight/r10_execution_preflight_bound.json" "$result/preflight/execution_preflight.json"
phase=finalize;python3 "$new/w1_cp20_r13_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase";python3 "$new/w1_cp20_r13_finalize.py" --root "$root" --output-report "$report"
chown ubuntu:ubuntu "$report";chmod 0644 "$report"
python3 "$new/w1_cp20_r13_continuation_manifest.py" complete --manifest "$manifest";touch "$result/FORMAL_W1_CP20_R13_COMPLETE";notify 'Dynamic Vamana CP20 R13 complete' 'query-only continuation composed after control-plane stop; STOP and await review'
