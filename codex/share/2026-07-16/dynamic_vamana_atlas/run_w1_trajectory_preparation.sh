#!/usr/bin/env bash
# Data-only CP05/CP10/CP20 trajectory preparation. No index execution is allowed.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_TRAJECTORY_PREP_AUTHORIZED:-0} == 1 ]] || { echo 'trajectory preparation authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'trajectory preparation launcher must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
artifact="$old/artifact_rebuild_manifest.json"
run=pilot3_sift10m_w1_trajectory_prep
result="$root/results/$run"; resources="$result/resources"
dataset="$root/datasets/sift10m"; cp01="$dataset/w1_cp01"; trajectory="$dataset/w1_trajectory"
gtroot="$root/groundtruth/sift10m/w1_trajectory"; tmp="$root/tmp/w1_trajectory_prep"
audited="$new/../dynamic_vamana_w1_composed_one_percent_canary_r07_audited_0716.md"
report="$new/../dynamic_vamana_w1_trajectory_preparation_results_0716.md"
manifest="$result/execution_manifest.json"; preflight="$result/preflight/execution_preflight.json"
controller_log=${ATLAS_CONTROLLER_LOG_PATH:-}; phase=initializing
attempt_armed=0

notify() { [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0; "$old/formal/notify_owner.sh" "$1" "$2" || true; }
on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    if (( attempt_armed == 1 )); then
      python3 "$new/w1_mark_recovery_stopped.py" --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true
      if [[ -f $preflight && ! -e $result/preflight/preservation_after_stop.json ]]; then
        python3 "$new/w1_trajectory_preservation.py" --preflight "$preflight" --cp01 "$cp01" --output "$result/preflight/preservation_after_stop.json" || true
      fi
      python3 "$new/w1_trajectory_freeze_failure.py" --root "$root" --trajectory "$trajectory" --groundtruth "$gtroot" \
        --result "$result" --execution "$manifest" --launcher "$new/run_w1_trajectory_preparation.sh" \
        --controller-pid "$$" --phase "$phase" --exit-code "$rc" --output "$result/failed_output_manifest.json" || true
    fi
    notify "Dynamic Vamana W1 trajectory preparation failed" "phase=$phase exit=$rc; fail-closed, no retry or dynamic-index execution"
  fi
}
trap on_exit EXIT

mkdir -p "$root/locks"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$
if [[ -z ${W1_ALLOWED_SESSION:-} ]]; then W1_ALLOWED_SESSION=$(tmux display-message -p '#S' 2>/dev/null || true); fi
export W1_ALLOWED_SESSION
export TMPDIR="$tmp"
for path in "$result" "$trajectory" "$gtroot" "$tmp" "$report"; do [[ ! -e $path ]] || { echo "fresh trajectory target exists: $path" >&2; exit 1; }; done
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == ${ATLAS_NVME_MAJMIN:-259:10} ]] || { echo 'experiment root not on project NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 107374182400 )) || { echo 'trajectory 100 GiB free-space guard failed' >&2; exit 1; }
install -d -o ubuntu -g ubuntu "$tmp"
python3 "$new/w1_trajectory_execution_manifest.py" --root "$root" --launcher "$new/run_w1_trajectory_preparation.sh" \
  --mode initialize --output "$manifest"
attempt_armed=1

phase=process_identity_regressions
python3 "$new/w1_process_identity.py" test-fixtures --root "$root" --artifact-manifest "$artifact" --output "$result/preflight/process_identity_tests.json"
phase=trajectory_sanity
python3 "$new/w1_trajectory_sanity.py" --scratch "$tmp/sanity" --output "$result/preflight/trajectory_sanity.json"

phase=continuation_preflight
python3 "$new/w1_trajectory_preflight.py" --root "$root" --artifact-manifest "$artifact" \
  --process-tests "$result/preflight/process_identity_tests.json" --sanity "$result/preflight/trajectory_sanity.json" --audited-report "$audited" \
  --launcher "$new/run_w1_trajectory_preparation.sh" --execution "$manifest" --output "$preflight"
python3 "$new/w1_trajectory_execution_manifest.py" --root "$root" --preflight "$preflight" \
  --launcher "$new/run_w1_trajectory_preparation.sh" --mode activate --output "$manifest"
install -d -o ubuntu -g ubuntu "$resources"
if [[ -n $controller_log && -f $controller_log ]]; then ln -s "$controller_log" "$result/formal_controller.log"; fi
notify 'Dynamic Vamana W1 trajectory preparation started' 'data-only CP05/CP10/CP20 preparation; no dynamic index execution'

run_stage() {
  local unit=$1 memory=$2 limit=$3 space=$4 output=$5; shift 5
  systemd-run --scope --collect --unit "$unit" --uid ubuntu \
    --property=AllowedCPUs=0-55 --property=AllowedMemoryNodes=0,1 --property=MemoryMax="$memory" \
    --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env -i PATH=/usr/bin:/bin HOME=/home/ubuntu LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 TMPDIR="$tmp" \
    numactl --physcpubind=0-55 --interleave=0,1 python3 "$new/w1_trajectory_resource_probe.py" \
      --output "$output" --interval-ms 100 --space-root "$space" --io-device "${ATLAS_NVME_MAJMIN:-259:10}" -- \
      timeout --signal=TERM --kill-after=30 "$limit" "$@"
}

phase=master_trace
run_stage dv-w1-trajectory-master 8G 600 "$trajectory" "$resources/master_trace.resources.json" \
  python3 "$new/w1_trajectory_generate.py" --dataset "$dataset" --cp01 "$cp01" --output "$trajectory"

for pct in 5 10 20; do
  cp=$(printf 'cp%02d' "$pct")
  phase="${cp}_derive"
  run_stage "dv-w1-trajectory-${cp}-derive" 8G 600 "$trajectory/$cp" "$resources/${cp}_derive.resources.json" \
    python3 "$new/w1_trajectory_derive_checkpoint.py" --trajectory "$trajectory" --checkpoint "$pct"
  phase="${cp}_materialize"
  run_stage "dv-w1-trajectory-${cp}-materialize" 16G 900 "$trajectory/$cp" "$resources/${cp}_materialize.resources.json" \
    python3 "$new/w1_trajectory_materialize.py" --dataset "$dataset" --checkpoint "$pct" --directory "$trajectory/$cp"
  phase="${cp}_exact_gt"
  run_stage "dv-w1-trajectory-${cp}-gt" 32G 1800 "$gtroot/$cp" "$resources/${cp}_gt.resources.json" \
    python3 "$new/w1_trajectory_gt.py" --root "$root" --checkpoint "$pct" --checkpoint-dir "$trajectory/$cp" \
      --preflight "$preflight" --output "$gtroot/$cp"
done

phase=freeze_outputs
chmod -R a-w "$trajectory" "$gtroot"

phase=cross_checkpoint_validation
python3 "$new/w1_trajectory_cross_validate.py" --root "$root" --trajectory "$trajectory" --groundtruth "$gtroot" \
  --resources "$resources" --preflight "$preflight" --device "${ATLAS_NVME_MAJMIN:-259:10}" --output "$result/trajectory_validation.json"
python3 "$new/w1_trajectory_preservation.py" --preflight "$preflight" --cp01 "$cp01" --output "$result/preflight/preservation_final.json"

phase=final_report
python3 "$new/w1_trajectory_finalize.py" --root "$root" --validation "$result/trajectory_validation.json" \
  --execution "$manifest" --preservation "$result/preflight/preservation_final.json" --output "$report"
touch "$result/FORMAL_TRAJECTORY_PREPARATION_COMPLETE"
chmod -R a-w "$result"
notify 'Dynamic Vamana W1 trajectory preparation complete' 'CP05/CP10/CP20 frozen inputs and exact GT complete; stopped before index execution'
phase=complete
