#!/usr/bin/env bash
# Authorized control-plane continuation after pre-query unit-name rejection.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_CP10_R12_CONTINUATION_AUTHORIZED:-0} == 1 ]] || exit 64
(( EUID == 0 )) || exit 1
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
result="$root/results/pilot3_sift10m_w1_cp10_trajectory_r12"; r10="$root/results/pilot3_sift10m_w1_cp05_trajectory_r10"
manifest="$result/continuation_manifest.json"; execution="$result/execution_manifest.json"; phase=initializing; armed=0
report="$new/../dynamic_vamana_w1_cp10_trajectory_r12_results_0717.md"; artifact="$old/artifact_rebuild_manifest.json"
runtime="$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json"; query="$root/datasets/sift10m/query.bin"; gt="$root/groundtruth/sift10m/w1_trajectory/cp10/gt_cp10"
notify(){ [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0; "$old/formal/notify_owner.sh" "$1" "$2" || true; }
on_exit(){ rc=$?; if ((rc));then if ((armed));then python3 "$new/w1_cp10_r12_continuation_manifest.py" stop --manifest "$manifest" --phase "$phase" --exit-code "$rc"||true;fi;notify 'Dynamic Vamana CP10 R12 continuation failed' "exit=$rc phase=$phase; CP20 HOLD";fi;};trap on_exit EXIT
[[ ! -e $manifest && ! -e $report ]] || exit 1
exec 9>"$root/locks/pilot3_w1_global.lock";flock -n 9||exit 1;export W1_GLOBAL_LOCK_HELD=1
python3 "$new/w1_cp10_r12_continuation_manifest.py" activate --manifest "$manifest" --r12-execution "$execution";armed=1
phase=resume_DGAI_query;W1_CP10_R12_CONTINUATION_AUTHORIZED=1 "$new/w1_resume_dgai_query_r12.sh"
canonical="$root/build/w1-canonical-v6/install";phase=cp10_OdinANN;python3 "$new/w1_cp10_r12_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase"
freeze="$r10/OdinANN/trajectory-cp05-10/checkpoints/cp05/cp05_freeze_evidence.json";base=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["root_realpath"])' "$freeze")
W1_CP10_R12_AUTHORIZED=1 "$new/w1_run_cp10_system_r12.sh" OdinANN "$base" "$freeze" "$canonical/OdinANN/w1_canary" "$canonical/OdinANN/search_disk_index" 29,46
phase=diskann_cp10_stale_control;python3 "$new/w1_cp10_r12_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase";install -d -o ubuntu -g ubuntu "$result/DiskANN"
unit=dv-w1-cp10-r12-diskann-stale
systemd-run --scope --collect --unit "$unit" --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes --property=MemoryMax=4G --property=RuntimeMaxSec=2700 \
 env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 W1_CP10_DISKANN_R12_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" W1_EXPECTED_SCOPE="$unit.scope" \
 prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 "$new/w1_run_diskann_cp10_stale_r12.sh" "$query" "$gt" "$result/DiskANN/stale-cp10-12" "$artifact" "$runtime" "$r10/preflight/execution_preflight.json" "$result/preflight/execution_preflight.json"
phase=finalize;python3 "$new/w1_cp10_r12_continuation_manifest.py" phase --manifest "$manifest" --phase "$phase";python3 "$new/w1_cp10_r12_finalize.py" --root "$root" --output-report "$report"
python3 "$new/w1_cp10_r12_continuation_manifest.py" complete --manifest "$manifest";touch "$result/FORMAL_W1_CP10_R12_COMPLETE";notify 'Dynamic Vamana CP10 R12 complete' 'query-only continuation composed after control-plane stop; CP20 HOLD'
