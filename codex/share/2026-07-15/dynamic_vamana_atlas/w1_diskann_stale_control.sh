#!/usr/bin/env bash
# Query the immutable CP00 DiskANN index against CP01 GT; deliberately no updates.
set -euo pipefail
[[ ${W1_SIFT10M_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || { echo 'formal W1 gate/global lock absent' >&2; exit 64; }
[[ $# == 4 ]] || { echo "usage: $0 QUERY CP01_GT RESULT_DIR ARTIFACT_MANIFEST" >&2; exit 2; }
query=$(realpath "$1"); gt=$(realpath "$2"); out=$(realpath -m "$3"); artifact_manifest=$(realpath "$4")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
binary="$root/build/DiskANN/apps/search_disk_index"
base_dir="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"; base="$base_dir/index"
[[ -x "$binary" && -f "${base}_disk.index" && ! -e "$out" ]] || { echo 'invalid/reused DiskANN stale-control artifact' >&2; exit 1; }
mkdir -p "$out"
python3 "$chat/w1_file_manifest.py" --root "$base_dir" --output "$out/cp00_index_manifest.tsv"
for l in 29 53; do
  for repetition in 1 2 3; do
    "$chat/resource_probe.py" --output "$out/L${l}_r${repetition}.resources.json" --interval-ms 25 --space-root "$base_dir" -- \
      "$chat/w1_diskann_query_worker.sh" "$binary" "$base" "$query" "$gt" "$out/L${l}_r${repetition}" "$l" "$out/L${l}_r${repetition}.log"
  done
done
python3 "$chat/w1_validate_stale_control.py" --result-dir "$out" --binary "$binary" --base-manifest "$out/cp00_index_manifest.tsv" \
  --query "$query" --gt "$gt" --artifact-manifest "$artifact_manifest" --device "${ATLAS_NVME_MAJMIN:-259:10}" --output "$out/stale_control.json"
touch "$out/DISKANN_STALE_CONTROL_OK"
