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
# P1 only needs checkpoint 0. Later stages may request every formal checkpoint
# without duplicating this driver: ATLAS_CHECKPOINTS='00 05 10 20'.
for pct in ${ATLAS_CHECKPOINTS:-"00 05 10 20"}; do
  base="$dataset_dir/active_cp${pct}.bin"
  tags="$dataset_dir/active_cp${pct}.tags.bin"
  prefix="$output_dir/gt_cp${pct}"
  log="$output_dir/gt_cp${pct}.log"
  tag_args=(--tags_file "$tags")
  if [[ "$pct" == 00 ]]; then
    # DiskANN's GT utility treats tag 0 as an absent tag.  checkpoint 0 is
    # deliberately the sequential 0..N-1 active prefix, so row IDs are the
    # logical tags and are the only safe representation for this utility.
    python3 - "$tags" <<'PY'
import struct, sys
from pathlib import Path
import numpy as np
p = Path(sys.argv[1])
with p.open('rb') as f:
    n, d = struct.unpack('<II', f.read(8))
if d != 1 or p.stat().st_size != 8 + n * 4:
    raise SystemExit('invalid checkpoint-0 tag file')
tags = np.memmap(p, dtype='<u4', mode='r', offset=8, shape=(n,))
if not np.array_equal(tags, np.arange(n, dtype=np.uint32)):
    raise SystemExit('checkpoint-0 tags are not sequential row IDs')
PY
    tag_args=()
  fi
  OPENBLAS_NUM_THREADS=56 OMP_NUM_THREADS=56 LD_PRELOAD="$openblas" \
    "$gt_tool" --data_type float --dist_fn l2 --base_file "$base" \
    --query_file "$dataset_dir/query.bin" --gt_file "$prefix" --K 100 \
    "${tag_args[@]}" >"$log" 2>&1
done
