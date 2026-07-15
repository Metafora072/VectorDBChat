#!/usr/bin/env bash
# One-shot fail-closed R02: audit preserved CP01, recover GT, then run the authorized W1 canary.
set -euo pipefail
[[ ${W1_RECOVERY_AUTHORIZED:-0} == 1 ]] || { echo 'W1 R02 recovery gate absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'R02 launcher must run as root so long stages do not depend on a sudo ticket' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
run=pilot3_sift10m_w1_r02; attempt=cp01-02; stale=stale-cp00-02
result="$root/results/$run"; formal="$root/formal/$run"; gt="$root/groundtruth/sift10m/w1_r02"
parent="$root/results/pilot3_sift10m_w1/execution_manifest.json"; cp01="$root/datasets/sift10m/w1_cp01"
artifact="$old/artifact_rebuild_manifest.json"; scratch="$root/tmp/${run}_preflight"
manifest="$result/execution_manifest.json"; phase=initializing
gt_report="$new/../dynamic_vamana_w1_gt_recovery_results_0716.md"
final_report="$new/../dynamic_vamana_w1_one_percent_canary_r02_results_0716.md"

notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$old/formal/notify_owner.sh" "$1" "$2" || { echo "notification failed: $1" >&2; return 0; }
}
as_operator_dir() { install -d -o ubuntu -g ubuntu "$@"; }
on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    python3 "$new/w1_mark_recovery_stopped.py" --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true
    if [[ $phase == gt_recovery && ! -e $gt_report ]]; then
      python3 "$new/w1_write_gt_recovery_failure_report.py" --result "$result" --gt "$gt" --phase "$phase" \
        --exit-code "$rc" --output "$gt_report" || true
    fi
    notify "Dynamic Vamana W1 R02 $phase failed" "exit=$rc phase=$phase; fail-closed stop, no later stage started"
  fi
}
trap on_exit EXIT

mkdir -p "$root/locks"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on project NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
for path in "$result" "$formal" "$gt" "$scratch" "$gt_report" "$final_report"; do [[ ! -e $path ]] || { echo "fresh R02 target exists: $path" >&2; exit 1; }; done

phase=runtime_canary
systemd-run --scope --collect --unit dv-w1-r02-runtime-canary --uid ubuntu \
  --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  numactl --physcpubind=0 --membind=0 /usr/bin/true

phase=cp01_reuse_audit
as_operator_dir "$scratch"
systemd-run --scope --collect --unit dv-w1-r02-cp01-audit --uid ubuntu \
  --property=AllowedCPUs=0-55 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env W1_RECOVERY_AUTHORIZED=1 numactl --physcpubind=0-55 --interleave=0,1 \
  "$old/resource_probe.py" --output "$scratch/cp01_reuse_resources.json" --interval-ms 250 \
    --space-root "$cp01" --space-interval-seconds 10 -- \
    "$new/w1_cp01_reuse_worker.sh" "$root" "$parent" "$scratch" "$old"

phase=recovery_execution_preflight
W1_ALLOWED_SESSION=${W1_ALLOWED_SESSION:-} python3 "$new/w1_recovery_preflight.py" --root "$root" \
  --artifact-manifest "$artifact" --parent-execution "$parent" --cp01-reuse "$scratch/cp01_reuse_validation.json" \
  --output "$result/preflight/execution_preflight.json" --runtime-canary-passed
cp "$scratch/trace_revalidation.json" "$scratch/cp01_reuse_validation.json" "$scratch/cp01_reuse_resources.json" "$result/preflight/"
chown -R ubuntu:ubuntu "$result"
python3 "$new/w1_recovery_execution_manifest.py" --root "$root" --artifact-manifest "$artifact" \
  --preflight "$result/preflight/execution_preflight.json" --cp01-reuse "$result/preflight/cp01_reuse_validation.json" \
  --parent-execution "$parent" --output "$manifest"
chown ubuntu:ubuntu "$manifest"
notify "Dynamic Vamana W1 R02 started" "recovery preflight and read-only CP01 reuse audit passed; project NVMe=${ATLAS_NVME_MAJMIN:-259:10}"

phase=gt_recovery
as_operator_dir "$result/preparation"
systemd-run --scope --collect --unit dv-w1-r02-gt-recovery --uid ubuntu \
  --property=AllowedCPUs=0-55 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env W1_RECOVERY_AUTHORIZED=1 ATLAS_ROOT="$root" ATLAS_W1_V1_CHAT="$old" \
  numactl --physcpubind=0-55 --interleave=0,1 "$old/resource_probe.py" \
    --output "$result/preparation/gt_recovery_resources.json" --interval-ms 250 --space-root "$root/groundtruth/sift10m" --space-interval-seconds 10 -- \
    "$new/w1_gt_recovery_worker.sh" "$root" "$result" "$gt"
python3 "$new/w1_write_gt_recovery_report.py" --root "$root" --result "$result" --gt "$gt" \
  --output "$gt_report"
notify "Dynamic Vamana W1 R02 GT recovery complete" "all three regressions, full GT validation and failed-GT comparison passed"

dataset="$root/datasets/sift10m"; full="$dataset/full_10m.bin"; trace="$cp01/replace_cp01_80k.bin"
tags="$cp01/active_cp01.tags.bin"; probes="$cp01/visibility_probes.bin"; probe_spec="$cp01/visibility_probes.json"
query="$dataset/query.bin"; cp0gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"; cp1gt="$gt/gt_cp01"
canonical="$root/build/w1-canonical-v6/install"
for system in DGAI OdinANN; do
  phase=${system}_canary
  as_operator_dir "$formal/$system" "$result/$system"
  if [[ $system == DGAI ]]; then
    base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"
    driver="$canonical/DGAI/w1_canary"; query_bin="$canonical/DGAI/search_disk_index"; ls=64,128
  else
    base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"
    driver="$canonical/OdinANN/w1_canary"; query_bin="$canonical/OdinANN/search_disk_index"; ls=29,46
  fi
  notify "Dynamic Vamana W1 R02 $system started" "pre-update gate precedes all 80K update operations"
  systemd-run --scope --collect --unit "dv-w1-r02-${system,,}-cp0102" --uid ubuntu \
    --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$old/w1_run_system_canary.sh" \
      --system "$system" --mode formal --dataset-dir "$dataset" --full-corpus "$full" --base-index "$base" \
      --trace "$trace" --expected-active-tags "$tags" --probe-queries "$probes" --probe-spec "$probe_spec" \
      --cp0-query "$query" --cp0-gt "$cp0gt" --cp1-query "$query" --cp1-gt "$cp1gt" \
      --attempt-dir "$formal/$system/$attempt" --result-dir "$result/$system/$attempt" --replacements 80000 \
      --pre-ls "$ls" --post-ls "$ls" --driver "$driver" --query-binary "$query_bin" --artifact-manifest "$artifact"
  notify "Dynamic Vamana W1 R02 $system complete" "pre gate, update, visibility, post queries and final integrity audit passed"
done

phase=diskann_stale_static_control
as_operator_dir "$result/DiskANN"
notify "Dynamic Vamana W1 R02 DiskANN stale control started" "CP00 immutable index versus recovered CP01 GT; negative control only"
systemd-run --scope --collect --unit dv-w1-r02-diskann-stale --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env W1_SIFT10M_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
  numactl --physcpubind=0-23 --membind=0 "$old/w1_diskann_stale_control.sh" "$query" "$cp1gt" "$result/DiskANN/$stale" "$artifact"

phase=final_report
python3 "$new/w1_assert_preserved_inputs.py" --preflight "$result/preflight/execution_preflight.json" \
  --failed-gt "$root/groundtruth/sift10m/w1" --cp01 "$cp01" --output "$result/preflight/preservation_final.json"
python3 "$old/w1_finalize_report.py" --root "$root" --chat "$old" --run-name "$run" --attempt "$attempt" --stale-attempt "$stale" \
  --cp01-resource "$result/preflight/cp01_reuse_resources.json" --gt-resource "$result/preparation/gt_recovery_resources.json" --recovery \
  --output "$final_report"
touch "$result/FORMAL_W1_COMPLETE"
notify "Dynamic Vamana W1 R02 complete" "W1 1% canary complete; higher churn and later workloads were not started"
phase=complete
