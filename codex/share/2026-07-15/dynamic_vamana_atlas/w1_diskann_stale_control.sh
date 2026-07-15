#!/usr/bin/env bash
# Query the immutable CP00 DiskANN index against CP01 GT; deliberately no updates.
set -euo pipefail
[[ ${W1_SIFT10M_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || { echo 'formal W1 gate/global lock absent' >&2; exit 64; }
[[ $# == 3 ]] || { echo "usage: $0 QUERY CP01_GT RESULT_DIR" >&2; exit 2; }
query=$(realpath "$1"); gt=$(realpath "$2"); out=$(realpath -m "$3")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
binary="$root/build/DiskANN/apps/search_disk_index"
base="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index/index"
[[ -x "$binary" && -f "${base}_disk.index" && ! -e "$out" ]] || { echo 'invalid/reused DiskANN stale-control artifact' >&2; exit 1; }
mkdir -p "$out"
for l in 29 53; do
  for repetition in 1 2 3; do
    "$binary" --data_type float --dist_fn l2 --index_path_prefix "$base" --result_path "$out/L${l}_r${repetition}" \
      --query_file "$query" --gt_file "$gt" -K 10 -L "$l" -T 1 -W 4 >"$out/L${l}_r${repetition}.log" 2>&1
  done
done
touch "$out/DISKANN_STALE_CONTROL_OK"
