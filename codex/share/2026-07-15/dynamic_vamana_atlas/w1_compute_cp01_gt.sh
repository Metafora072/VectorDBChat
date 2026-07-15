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
chat=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
python3 "$chat/validate_groundtruth.py" --dataset "$dataset" --groundtruth "$out" --base-file "$dataset/active_cp01.bin" --tags-file "$dataset/active_cp01.tags.bin" --query-file "$root/datasets/sift10m/query.bin" --truthset-file "$out/gt_cp01" --checkpoint 1 --audit-query-ids 0,17,9999 --output "$out/gt_cp01_validation.json"
python3 - "$dataset" "$out" "$root/datasets/sift10m/query.bin" <<'PY'
import hashlib, json, sys
from pathlib import Path
def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
ds,out,query=map(Path,sys.argv[1:]); manifest=json.loads((ds/'replace_cp01_manifest.json').read_text())
manifest.update({'active_vector_realpath':str((ds/'active_cp01.bin').resolve()),'active_vector_sha256':digest(ds/'active_cp01.bin'),'active_tag_realpath':str((ds/'active_cp01.tags.bin').resolve()),'active_tag_sha256':digest(ds/'active_cp01.tags.bin'),'query_realpath':str(query.resolve()),'query_sha256':digest(query),'truthset_realpath':str((out/'gt_cp01').resolve()),'truthset_sha256':digest(out/'gt_cp01'),'truthset_shape':'10000x100'})
(out/'gt_cp01_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
