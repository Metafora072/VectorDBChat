#!/usr/bin/env bash
# The only W1 launcher.  Formal mode remains denied until a later explicit gate.
set -euo pipefail
[[ $# == 1 && ( $1 == micro || $1 == formal ) ]] || { echo "usage: $0 micro|formal" >&2; exit 2; }
mode=$1
[[ ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'formal-path integration gate not granted' >&2; exit 64; }
[[ $mode == micro || ${W1_SIFT10M_AUTHORIZED:-0} == 1 ]] || { echo 'SIFT10M formal W1 remains denied' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lock="$root/locks/pilot3_w1_global.lock"; mkdir -p "$(dirname "$lock")"; exec 9>"$lock"; flock -n 9 || { echo 'another W1 formal path owns the global lock' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN) == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }

if [[ $mode == micro ]]; then
  run=${W1_REPLAY_RUN:-pilot3_w1_formal_path_replay_r02}; dataset="$root/datasets/sift1m"; prep="$root/tmp/$run/inputs"; replacement=16
  [[ ! -e "$prep" ]] || { echo 'micro replay input path already exists' >&2; exit 1; }
  python3 "$chat/w1_micro_prepare.py" --authorized --dataset "$dataset" --output "$prep"
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$dataset/active_cp00.bin" --tags-file "$dataset/active_cp00.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp00_18" --checkpoint 0 --audit-query-ids 0,17 --output "$prep/gt_cp00_validation.json" >/dev/null
  python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$prep" --base-file "$prep/active_cp01.bin" --tags-file "$prep/active.tags.bin" --query-file "$prep/query_18.bin" --truthset-file "$prep/gt_cp01_18" --checkpoint 1 --audit-query-ids 0,17 --output "$prep/gt_cp01_validation.json" >/dev/null
  data_file="$dataset/full_1m.bin"; cp0_query="$prep/query_18.bin"; cp1_query="$prep/query_18.bin"; cp0_gt="$prep/gt_cp00_18"; cp1_gt="$prep/gt_cp01_18"
else
  run=pilot3_sift10m_w1; dataset="$root/datasets/sift10m/w1_cp01"; prep="$dataset"; replacement=80000
  data_file="$root/datasets/sift10m/full_10m.bin"; cp0_query="$root/datasets/sift10m/query.bin"; cp1_query="$root/datasets/sift10m/query.bin"; cp0_gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"; cp1_gt="$root/groundtruth/sift10m/w1/gt_cp01"
fi

for system in DGAI OdinANN; do
  [[ ! -e "$root/formal/$run/$system/replay-01" && ! -e "$root/results/$run/$system/replay-01" ]] || { echo "attempt exists for $system" >&2; exit 1; }
  if [[ $system == DGAI ]]; then
    base="$root/index/atlas1m/DGAI/sift1m"; driver="$root/build/DGAI/tests/w1_canary"; query_bin="$root/build/DGAI/tests/search_disk_index"; ls=64,128
  else
    base="$root/index/atlas1m/OdinANN/sift1m"; driver="$root/build/OdinANN-uring/tests/w1_canary"; query_bin="$root/build/OdinANN-uring/tests/search_disk_index"; ls=29,46
  fi
  [[ $mode == micro || $base == *"sift10m"* ]] || true
  scope="dv-w1-${mode}-${system,,}-replay01"
  sudo -n systemd-run --scope --collect --unit "$scope" --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
    env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" \
    numactl --physcpubind=0-23 --membind=0 "$chat/w1_run_system_canary.sh" \
      --system "$system" --mode "$mode" --dataset-dir "$dataset" --base-index "$base" --trace "$prep/trace.bin" --expected-active-tags "$prep/active.tags.bin" --probe-queries "$prep/probes.bin" --probe-spec "$prep/probes.json" \
      --cp0-query "$cp0_query" --cp0-gt "$cp0_gt" --cp1-query "$cp1_query" --cp1-gt "$cp1_gt" --attempt-dir "$root/formal/$run/$system/replay-01" --result-dir "$root/results/$run/$system/replay-01" --replacements "$replacement" --pre-ls "$ls" --post-ls "$ls" --driver "$driver" --query-binary "$query_bin"
done
touch "$root/results/$run/FORMAL_PATH_REPLAY_OK"
