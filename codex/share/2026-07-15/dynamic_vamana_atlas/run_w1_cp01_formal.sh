#!/usr/bin/env bash
# The only W1 launcher: read-only preflight, 1M replay, or separately gated SIFT10M CP01.
set -euo pipefail
[[ $# == 1 && ( $1 == micro || $1 == formal || $1 == preflight ) ]] || { echo "usage: $0 micro|formal|preflight" >&2; exit 2; }
mode=$1
[[ ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'formal-path integration gate not granted' >&2; exit 64; }
[[ $mode != formal || ${W1_SIFT10M_AUTHORIZED:-0} == 1 ]] || { echo 'SIFT10M formal W1 remains denied' >&2; exit 64; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
artifact_manifest="$chat/artifact_rebuild_manifest.json"
if [[ ${ATLAS_SUDO_STDIN:-0} == 1 ]]; then sudo_cmd=(sudo -S); else sudo_cmd=(sudo -n); fi
lock="$root/locks/pilot3_w1_global.lock"
mkdir -p "$(dirname "$lock")"
exec 9>"$lock"
flock -n 9 || { echo 'another W1 formal path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
[[ -f "$artifact_manifest" ]] || { echo 'missing frozen artifact manifest' >&2; exit 1; }

dgai_driver="$root/build/w1-canonical-v4/install/DGAI/w1_canary"
dgai_query="$root/build/w1-canonical-v4/install/DGAI/search_disk_index"
odin_driver="$root/build/w1-canonical-v4/install/OdinANN/w1_canary"
odin_query="$root/build/w1-canonical-v4/install/OdinANN/search_disk_index"
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
  run=${W1_REPLAY_RUN:-pilot3_w1_formal_execution_preflight_replay_r01}
  dataset="$root/datasets/sift1m"
  prep="$root/tmp/$run/inputs"
  replacement=16
  attempt=replay-01
  [[ ! -e "$prep" ]] || { echo 'micro replay input path already exists' >&2; exit 1; }
  python3 "$chat/w1_micro_prepare.py" --authorized --dataset "$dataset" --output "$prep"
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$dataset/active_cp00.bin" --tags-file "$dataset/active_cp00.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp00_18" --checkpoint 0 --audit-query-ids 0,17 --output "$prep/gt_cp00_validation.json" >/dev/null
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$prep/active_cp01.bin" --tags-file "$prep/active.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp01_18" --checkpoint 1 --audit-query-ids 0,17 --output "$prep/gt_cp01_validation.json" >/dev/null
  full_corpus="$dataset/full_1m.bin"
  trace="$prep/trace.bin"; active_tags="$prep/active.tags.bin"; probes="$prep/probes.bin"; probe_spec="$prep/probes.json"
  cp0_query="$prep/query_18.bin"; cp1_query="$prep/query_18.bin"; cp0_gt="$prep/gt_cp00_18"; cp1_gt="$prep/gt_cp01_18"
else
  run=pilot3_sift10m_w1
  dataset="$root/datasets/sift10m"
  prep="$dataset/w1_cp01"
  replacement=80000
  attempt=cp01-01
  preflight="$root/results/$run/preflight/formal_preflight.json"
  [[ -f "$preflight" ]] || { echo 'reviewed formal preflight is required' >&2; exit 1; }
  python3 "$chat/w1_prepare_cp01_trace.py" --authorized --dataset "$dataset" --output-dir "$prep" --count 80000 --materialize-active
  python3 "$chat/w1_validate_cp01_trace.py" --initial-active-tags "$dataset/active_cp00.tags.bin" --work-dir "$prep" --output "$prep/trace_validation.json"
  W1_EXECUTE_AUTHORIZED=1 "$chat/w1_compute_cp01_gt.sh" "$prep" "$root/groundtruth/sift10m/w1"
  full_corpus="$dataset/full_10m.bin"
  trace="$prep/replace_cp01_80k.bin"; active_tags="$prep/active_cp01.tags.bin"; probes="$prep/visibility_probes.bin"; probe_spec="$prep/visibility_probes.json"
  cp0_query="$dataset/query.bin"; cp1_query="$dataset/query.bin"; cp0_gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"; cp1_gt="$root/groundtruth/sift10m/w1/gt_cp01"
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
  [[ $mode == micro || $(realpath "$base") == "$root/formal/pilot3_sift10m_p1r08/f0/$system/"* ]] || { echo "formal base mismatch for $system" >&2; exit 1; }
  scope="dv-w1-${mode}-${system,,}-${attempt//-}"
  "${sudo_cmd[@]}" systemd-run --scope --collect --unit "$scope" --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$chat/w1_run_system_canary.sh" \
      --system "$system" --mode "$mode" --dataset-dir "$dataset" --full-corpus "$full_corpus" --base-index "$base" --trace "$trace" --expected-active-tags "$active_tags" --probe-queries "$probes" --probe-spec "$probe_spec" \
      --cp0-query "$cp0_query" --cp0-gt "$cp0_gt" --cp1-query "$cp1_query" --cp1-gt "$cp1_gt" --attempt-dir "$root/formal/$run/$system/$attempt" --result-dir "$root/results/$run/$system/$attempt" --replacements "$replacement" --pre-ls "$ls" --post-ls "$ls" --driver "$driver" --query-binary "$query_bin" --artifact-manifest "$artifact_manifest"
done

if [[ $mode == formal ]]; then
  "$chat/w1_diskann_stale_control.sh" "$cp1_query" "$cp1_gt" "$root/results/$run/DiskANN/stale-cp00-01"
fi
touch "$root/results/$run/FORMAL_PATH_REPLAY_OK"
