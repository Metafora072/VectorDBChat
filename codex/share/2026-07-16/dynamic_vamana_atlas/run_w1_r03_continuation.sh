#!/usr/bin/env bash
# Fail-closed R03 continuation: reuse R02 GT/CP01 and start at the DGAI system stage.
set -euo pipefail
[[ ${W1_R03_AUTHORIZED:-0} == 1 ]] || { echo 'W1 R03 continuation gate absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'R03 launcher must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
run=pilot3_sift10m_w1_r03; attempt=cp01-03; stale=stale-cp00-03
result="$root/results/$run"; formal="$root/formal/$run"; cp01="$root/datasets/sift10m/w1_cp01"
r02_result="$root/results/pilot3_sift10m_w1_r02"; gt="$root/groundtruth/sift10m/w1_r02/gt_cp01"
artifact="$old/artifact_rebuild_manifest.json"; scratch="$root/tmp/${run}_clone_tests"
manifest="$result/execution_manifest.json"; phase=initializing
final_report="$new/../dynamic_vamana_w1_one_percent_canary_r03_results_0716.md"
controller_log=${ATLAS_CONTROLLER_LOG_PATH:-}

notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$old/formal/notify_owner.sh" "$1" "$2" || { echo "notification failed: $1" >&2; return 0; }
}
as_operator_dir() { install -d -o ubuntu -g ubuntu "$@"; }
on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    python3 "$new/w1_mark_recovery_stopped.py" --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true
    if [[ -f $result/preflight/execution_preflight.json && ! -e $result/preflight/preservation_after_stop.json ]]; then
      python3 "$new/w1_r03_assert_reused_inputs.py" --preflight "$result/preflight/execution_preflight.json" \
        --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_after_stop.json" || true
    fi
    if [[ -d $result && ! -e $final_report ]]; then
      python3 "$new/w1_write_r03_stop_report.py" --result "$result" --phase "$phase" --exit-code "$rc" --output "$final_report" || true
    fi
    notify "Dynamic Vamana W1 R03 $phase failed" "exit=$rc phase=$phase; fail-closed stop, no later system started"
  fi
}
trap on_exit EXIT

mkdir -p "$root/locks"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on project NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
for path in "$result" "$formal" "$scratch" "$final_report"; do [[ ! -e $path ]] || { echo "fresh R03 target exists: $path" >&2; exit 1; }; done

phase=runtime_canary
systemd-run --scope --collect --unit dv-w1-r03-runtime-canary --uid ubuntu \
  --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  numactl --physcpubind=0 --membind=0 /usr/bin/true

phase=continuation_preflight
W1_ALLOWED_SESSION=${W1_ALLOWED_SESSION:-} python3 "$new/w1_r03_continuation_preflight.py" --root "$root" \
  --artifact-manifest "$artifact" --gt-report "$new/../dynamic_vamana_w1_gt_recovery_results_0716.md" \
  --output "$result/preflight/execution_preflight.json" --runtime-canary-passed
if [[ -n $controller_log && -f $controller_log ]]; then ln -s "$controller_log" "$result/formal_controller.log"; fi

phase=clone_target_tests
python3 "$new/w1_r03_clone_target_tests.py" --root "$root" --helper "$old/w1_clone_base.sh" \
  --dgai-base "$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index" \
  --odin-base "$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index" \
  --scratch "$scratch" --output "$result/preflight/clone_target_tests.json"
python3 "$new/w1_r03_execution_manifest.py" --root "$root" --preflight "$result/preflight/execution_preflight.json" \
  --clone-tests "$result/preflight/clone_target_tests.json" --output "$manifest"
chown -R ubuntu:ubuntu "$result"
notify "Dynamic Vamana W1 R03 started" "continuation preflight and exact clone-target tests passed; R02 GT reused read-only"

dataset="$root/datasets/sift10m"; full="$dataset/full_10m.bin"; trace="$cp01/replace_cp01_80k.bin"
tags="$cp01/active_cp01.tags.bin"; probes="$cp01/visibility_probes.bin"; probe_spec="$cp01/visibility_probes.json"
query="$dataset/query.bin"; cp0gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"
canonical="$root/build/w1-canonical-v6/install"
for system in DGAI OdinANN; do
  phase=${system}_canary
  as_operator_dir "$formal/$system" "$result/$system"
  target="$formal/$system/$attempt"
  if [[ $system == DGAI ]]; then
    base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"
    driver="$canonical/DGAI/w1_canary"; query_bin="$canonical/DGAI/search_disk_index"; ls=64,128
  else
    base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"
    driver="$canonical/OdinANN/w1_canary"; query_bin="$canonical/OdinANN/search_disk_index"; ls=29,46
  fi
  notify "Dynamic Vamana W1 R03 $system started" "exact clone capability granted only for $target; pre-update gate precedes 80K updates"
  systemd-run --scope --collect --unit "dv-w1-r03-${system,,}-cp0103" --uid ubuntu \
    --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 W1_CLONE_PREFLIGHT_ONLY=0 W1_ALLOWED_CLONE_TARGET="$target" \
      ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$old/w1_run_system_canary.sh" \
      --system "$system" --mode formal --dataset-dir "$dataset" --full-corpus "$full" --base-index "$base" \
      --trace "$trace" --expected-active-tags "$tags" --probe-queries "$probes" --probe-spec "$probe_spec" \
      --cp0-query "$query" --cp0-gt "$cp0gt" --cp1-query "$query" --cp1-gt "$gt" \
      --attempt-dir "$target" --result-dir "$result/$system/$attempt" --replacements 80000 \
      --pre-ls "$ls" --post-ls "$ls" --driver "$driver" --query-binary "$query_bin" --artifact-manifest "$artifact"
  notify "Dynamic Vamana W1 R03 $system complete" "pre gate, 80K update, visibility, post queries and immutable-base audit passed"
done

phase=diskann_stale_static_control
as_operator_dir "$result/DiskANN"
notify "Dynamic Vamana W1 R03 DiskANN stale control started" "CP00 immutable index versus recovered R02 CP01 GT; negative control only"
systemd-run --scope --collect --unit dv-w1-r03-diskann-stale --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env W1_SIFT10M_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
  numactl --physcpubind=0-23 --membind=0 "$old/w1_diskann_stale_control.sh" "$query" "$gt" "$result/DiskANN/$stale" "$artifact"

phase=final_report
python3 "$new/w1_r03_assert_reused_inputs.py" --preflight "$result/preflight/execution_preflight.json" \
  --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_final.json"
python3 "$old/w1_finalize_report.py" --root "$root" --chat "$old" --run-name "$run" --attempt "$attempt" --stale-attempt "$stale" \
  --cp01-resource "$r02_result/preflight/cp01_reuse_resources.json" --gt-resource "$r02_result/preparation/gt_recovery_resources.json" \
  --continuation --output "$final_report"
touch "$result/FORMAL_W1_COMPLETE"
notify "Dynamic Vamana W1 R03 complete" "W1 1% canary complete; higher churn and later workloads were not started"
phase=complete
