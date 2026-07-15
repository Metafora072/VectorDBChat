#!/usr/bin/env bash
# Compute only checkpoint-1 exact GT after trace preparation has been approved.
set -euo pipefail
[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing GT computation' >&2; exit 64; }
[[ $# == 2 ]] || { echo "usage: $0 CP01_DATASET_DIR OUTPUT_DIR" >&2; exit 2; }
dataset=$(realpath "$1"); out=$(realpath -m "$2")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
tool="$root/build/DiskANN/apps/utils/compute_groundtruth"; openblas="$root/build/openblas-install/lib/libopenblas.so"
for f in "$dataset/active_cp01.bin" "$dataset/active_cp01.tags.bin" "$dataset/replace_cp01_manifest.json" "$dataset/trace_validation.json" "$tool"; do [[ -f "$f" ]] || { echo "missing required file: $f" >&2; exit 1; }; done
mkdir -p "$out"; [[ ! -e "$out/gt_cp01" ]] || { echo 'refusing to overwrite checkpoint-1 GT' >&2; exit 1; }
OPENBLAS_NUM_THREADS=56 OMP_NUM_THREADS=56 LD_PRELOAD="$openblas" "$tool" --data_type float --dist_fn l2 \
  --base_file "$dataset/active_cp01.bin" --query_file "$root/datasets/sift10m/query.bin" --gt_file "$out/gt_cp01" --K 100 --tags_file "$dataset/active_cp01.tags.bin" >"$out/gt_cp01.log" 2>&1
python3 "${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}/validate_groundtruth.py" \
  --dataset "$dataset" --groundtruth "$out" --checkpoints 1 --audit-query-ids 0,17,9999 --output "$out/gt_cp01_validation.json"
