#!/usr/bin/env bash
# The only fail-closed W1 launcher: read-only preflight, gated 1M replay, or SIFT10M CP01.
set -euo pipefail
[[ $# == 1 && ( $1 == micro || $1 == formal || $1 == preflight ) ]] || { echo "usage: $0 micro|formal|preflight" >&2; exit 2; }
mode=$1
[[ ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'formal-path integration gate not granted' >&2; exit 64; }
[[ $mode != formal || ${W1_SIFT10M_AUTHORIZED:-0} == 1 ]] || { echo 'SIFT10M formal W1 gate absent' >&2; exit 64; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
artifact_manifest="$chat/artifact_rebuild_manifest.json"
if (( EUID == 0 )); then sudo_cmd=(); else
  if [[ ${ATLAS_SUDO_STDIN:-0} == 1 ]]; then sudo_cmd=(sudo -S); else sudo_cmd=(sudo -n); fi
fi
as_operator_dir() {
  if (( EUID == 0 )); then install -d -o ubuntu -g ubuntu "$@"; else mkdir -p "$@"; fi
}
notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$chat/formal/notify_owner.sh" "$1" "$2" || { echo "notification failed: $1" >&2; return 0; }
}
phase=initializing
on_exit() {
  local rc=$?
  if [[ $mode == formal && $rc != 0 ]]; then
    notify "Dynamic Vamana W1 $phase failed" "exit=$rc phase=$phase; global run stopped and later stages were not started"
  fi
}
trap on_exit EXIT

lock="$root/locks/pilot3_w1_global.lock"
mkdir -p "$(dirname "$lock")"
exec 9>"$lock"
flock -n 9 || { echo 'another W1 formal path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
[[ -f "$artifact_manifest" ]] || { echo 'missing frozen artifact manifest' >&2; exit 1; }

canonical="$root/build/w1-canonical-v6/install"
dgai_driver="$canonical/DGAI/w1_canary"; dgai_query="$canonical/DGAI/search_disk_index"
odin_driver="$canonical/OdinANN/w1_canary"; odin_query="$canonical/OdinANN/search_disk_index"
python3 "$chat/w1_verify_artifacts.py" --manifest "$artifact_manifest" --system DGAI --driver "$dgai_driver" --query-binary "$dgai_query" >/dev/null
python3 "$chat/w1_verify_artifacts.py" --manifest "$artifact_manifest" --system OdinANN --driver "$odin_driver" --query-binary "$odin_query" >/dev/null

if [[ $mode == preflight ]]; then
  out="$root/results/pilot3_sift10m_w1/preflight/formal_preflight.json"
  [[ ! -e "$out" ]] || { echo 'formal preflight output already exists' >&2; exit 1; }
  "${sudo_cmd[@]}" systemd-run --scope --collect --unit dv-w1-formal-preflight --uid ubuntu \
    --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    numactl --physcpubind=0 --membind=0 /usr/bin/true
  ATLAS_NOTIFY_EMAIL=${ATLAS_NOTIFY_EMAIL:-1} python3 "$chat/w1_formal_preflight.py" --root "$root" --artifact-manifest "$artifact_manifest" --output "$out" --runtime-canary-passed
  exit 0
fi

if [[ $mode == micro ]]; then
  run=${W1_REPLAY_RUN:-pilot3_w1_formal_path_replay_r08}
  dataset="$root/datasets/sift1m"; prep="$root/tmp/$run/inputs"; replacement=16; attempt=replay-01
  [[ ! -e "$prep" ]] || { echo 'micro replay input path already exists' >&2; exit 1; }
  python3 "$chat/w1_micro_prepare.py" --authorized --dataset "$dataset" --output "$prep"
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$dataset/active_cp00.bin" --tags-file "$dataset/active_cp00.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp00_18" --checkpoint 0 --audit-query-ids 0,17 --output "$prep/gt_cp00_validation.json" >/dev/null
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$prep/active_cp01.bin" --tags-file "$prep/active.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp01_18" --checkpoint 1 --audit-query-ids 0,17 --output "$prep/gt_cp01_validation.json" >/dev/null
  full_corpus="$dataset/full_1m.bin"; trace="$prep/trace.bin"; active_tags="$prep/active.tags.bin"
  probes="$prep/probes.bin"; probe_spec="$prep/probes.json"; cp0_query="$prep/query_18.bin"; cp1_query="$cp0_query"
  cp0_gt="$prep/gt_cp00_18"; cp1_gt="$prep/gt_cp01_18"
else
  (( EUID == 0 )) || { echo 'formal launcher must run once as root so long stages never depend on an expiring sudo ticket' >&2; exit 1; }
  run=pilot3_sift10m_w1; dataset="$root/datasets/sift10m"; prep="$dataset/w1_cp01"; replacement=80000; attempt=cp01-01
  result_root="$root/results/$run"; execution_preflight="$result_root/preflight/execution_preflight.json"
  [[ ! -e "$execution_preflight" ]] || { echo 'execution preflight already exists' >&2; exit 1; }
  phase=fresh_execution_preflight
  systemd-run --scope --collect --unit dv-w1-execution-preflight --uid ubuntu \
    --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    numactl --physcpubind=0 --membind=0 /usr/bin/true
  W1_ALLOWED_SESSION=${W1_ALLOWED_SESSION:-} ATLAS_NOTIFY_EMAIL=${ATLAS_NOTIFY_EMAIL:-1} \
    python3 "$chat/w1_formal_preflight.py" --execution --root "$root" --artifact-manifest "$artifact_manifest" --output "$execution_preflight" --runtime-canary-passed
  python3 "$chat/w1_execution_manifest.py" --root "$root" --artifact-manifest "$artifact_manifest" \
    --preflight "$execution_preflight" --output "$result_root/execution_manifest.json"
  notify "Dynamic Vamana W1 formal started" "fresh execution preflight passed; project NVMe=${ATLAS_NVME_MAJMIN:-259:10}"
  as_operator_dir "$result_root/preparation"
  phase=cp01_preparation
  systemd-run --scope --collect --unit dv-w1-cp01-preparation --uid ubuntu \
    --property=AllowedCPUs=0-55 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_EXECUTE_AUTHORIZED=1 ATLAS_ROOT="$root" \
    numactl --physcpubind=0-55 --interleave=0,1 "$chat/resource_probe.py" \
      --output "$result_root/preparation/cp01_preparation_resources.json" --interval-ms 100 --space-root "$prep" --space-interval-seconds 10 -- \
      "$chat/w1_cp01_prepare_worker.sh" "$dataset" "$prep"
  notify "Dynamic Vamana W1 CP01 preparation complete" "trace validation and active/probe materialization passed"
  phase=gt_cp01
  as_operator_dir "$root/groundtruth/sift10m/w1"
  systemd-run --scope --collect --unit dv-w1-gt-cp01 --uid ubuntu \
    --property=AllowedCPUs=0-55 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_EXECUTE_AUTHORIZED=1 ATLAS_ROOT="$root" ATLAS_CHAT_ROOT="$chat" \
    numactl --physcpubind=0-55 --interleave=0,1 "$chat/resource_probe.py" \
      --output "$result_root/preparation/gt_cp01_resources.json" --interval-ms 250 --space-root "$root/groundtruth/sift10m/w1" --space-interval-seconds 10 -- \
      "$chat/w1_compute_cp01_gt.sh" "$prep" "$root/groundtruth/sift10m/w1"
  notify "Dynamic Vamana W1 checkpoint-1 GT complete" "exact GT and independent validation passed"
  full_corpus="$dataset/full_10m.bin"; trace="$prep/replace_cp01_80k.bin"; active_tags="$prep/active_cp01.tags.bin"
  probes="$prep/visibility_probes.bin"; probe_spec="$prep/visibility_probes.json"; cp0_query="$dataset/query.bin"; cp1_query="$dataset/query.bin"
  cp0_gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"; cp1_gt="$root/groundtruth/sift10m/w1/gt_cp01"
fi

for system in DGAI OdinANN; do
  [[ ! -e "$root/formal/$run/$system/$attempt" && ! -e "$root/results/$run/$system/$attempt" ]] || { echo "attempt exists for $system" >&2; exit 1; }
  if [[ $system == DGAI ]]; then
    if [[ $mode == micro ]]; then base="$root/index/atlas1m/DGAI/sift1m"; else base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"; fi
    driver=$dgai_driver; query_bin=$dgai_query; ls=64,128
  else
    if [[ $mode == micro ]]; then base="$root/index/atlas1m/OdinANN/sift1m"; else base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"; fi
    driver=$odin_driver; query_bin=$odin_query; ls=29,46
  fi
  if [[ $mode == formal ]]; then
    phase=${system}_canary
    notify "Dynamic Vamana W1 $system started" "pre-update gate precedes all 80K update operations"
    as_operator_dir "$root/formal/$run/$system" "$root/results/$run/$system"
  fi
  scope="dv-w1-${mode}-${system,,}-${attempt//-}"
  "${sudo_cmd[@]}" systemd-run --scope --collect --unit "$scope" --uid ubuntu --property=AllowedCPUs=0-23 \
    --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$chat/w1_run_system_canary.sh" \
      --system "$system" --mode "$mode" --dataset-dir "$dataset" --full-corpus "$full_corpus" --base-index "$base" --trace "$trace" --expected-active-tags "$active_tags" --probe-queries "$probes" --probe-spec "$probe_spec" \
      --cp0-query "$cp0_query" --cp0-gt "$cp0_gt" --cp1-query "$cp1_query" --cp1-gt "$cp1_gt" --attempt-dir "$root/formal/$run/$system/$attempt" --result-dir "$root/results/$run/$system/$attempt" --replacements "$replacement" --pre-ls "$ls" --post-ls "$ls" --driver "$driver" --query-binary "$query_bin" --artifact-manifest "$artifact_manifest"
  [[ $mode != formal ]] || notify "Dynamic Vamana W1 $system complete" "pre gate, update, visibility, post queries and final integrity audit passed"
done

if [[ $mode == formal ]]; then
  phase=diskann_stale_static_control
  notify "Dynamic Vamana W1 DiskANN stale control started" "CP00 immutable index versus CP01 GT; negative control only"
  as_operator_dir "$root/results/$run/DiskANN"
  systemd-run --scope --collect --unit dv-w1-formal-diskann-stale --uid ubuntu --property=AllowedCPUs=0-23 \
    --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_SIFT10M_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$chat/w1_diskann_stale_control.sh" "$cp1_query" "$cp1_gt" "$root/results/$run/DiskANN/stale-cp00-01" "$artifact_manifest"
  notify "Dynamic Vamana W1 DiskANN stale control complete" "all six stale-static negative-control queries passed evidence validation"
  phase=final_report
  python3 "$chat/w1_finalize_report.py" --root "$root" --chat "$chat" --output "$chat/../dynamic_vamana_w1_one_percent_canary_results_0715.md"
  touch "$root/results/$run/FORMAL_W1_COMPLETE"
  notify "Dynamic Vamana W1 formal complete" "W1 1% canary complete; higher churn and later workloads were not started"
else
  touch "$root/results/$run/FORMAL_PATH_REPLAY_OK"
fi
phase=complete
