#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 DATASET_DIR OUTPUT_DIR" >&2
  exit 2
fi

dataset_dir=$(realpath "$1")
output_dir=$(realpath -m "$2")
atlas_root=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas
gt_tool="$atlas_root/build/DiskANN/apps/utils/compute_groundtruth"
openblas="$atlas_root/build/openblas-install/lib/libopenblas.so"

mkdir -p "$output_dir"
for pct in 00 05 10 20; do
  base="$dataset_dir/active_cp${pct}.bin"
  tags="$dataset_dir/active_cp${pct}.tags.bin"
  prefix="$output_dir/gt_cp${pct}"
  log="$output_dir/gt_cp${pct}.log"
  OPENBLAS_NUM_THREADS=56 OMP_NUM_THREADS=56 LD_PRELOAD="$openblas" \
    "$gt_tool" --data_type float --dist_fn l2 --base_file "$base" \
    --query_file "$dataset_dir/query.bin" --gt_file "$prefix" --K 100 \
    --tags_file "$tags" >"$log" 2>&1
done
