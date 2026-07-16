#!/usr/bin/env bash
# Query the immutable CP00 DiskANN index against CP01 GT; deliberately no updates.
set -euo pipefail
[[ ${W1_SIFT10M_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || { echo 'formal W1 gate/global lock absent' >&2; exit 64; }
[[ $# == 5 ]] || { echo "usage: $0 QUERY CP01_GT RESULT_DIR ARTIFACT_MANIFEST RUNTIME_MANIFEST" >&2; exit 2; }
query=$(realpath "$1"); gt=$(realpath "$2"); out=$(realpath -m "$3"); artifact_manifest=$(realpath "$4"); runtime_manifest=$(realpath "$5")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
new_chat=$(cd "$chat/../../2026-07-16/dynamic_vamana_atlas" && pwd)
binary="$root/build/DiskANN/apps/search_disk_index"
base_dir="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"; base="$base_dir/index"
expected_query=$(realpath "$root/datasets/sift10m/query.bin")
expected_gt=$(realpath "$root/groundtruth/sift10m/w1_r02/gt_cp01")
expected_out=$(realpath -m "$root/results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07")
expected_artifact=$(realpath "$chat/artifact_rebuild_manifest.json")
expected_runtime=$(realpath -m "$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json")
[[ $query == "$expected_query" && $gt == "$expected_gt" && $out == "$expected_out" \
   && $artifact_manifest == "$expected_artifact" && $runtime_manifest == "$expected_runtime" ]] \
  || { echo 'R07 stale-control exact target/input identity mismatch' >&2; exit 1; }
[[ -x "$binary" && -f "${base}_disk.index" && -f "$runtime_manifest" && ! -e "$out" ]] || { echo 'invalid/reused DiskANN stale-control artifact' >&2; exit 1; }
runtime_libs=$(python3 - "$runtime_manifest" "$binary" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_text()); binary=Path(sys.argv[2]).resolve()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if manifest.get('status')!='pass' or manifest.get('not_found_dependencies')!=[]: raise SystemExit('runtime manifest invalid')
if str(binary)!=manifest['binary']['realpath'] or sha(binary)!=manifest['binary']['sha256']: raise SystemExit('runtime binary mismatch')
paths=manifest['runtime_library_directories']
if not paths or any(str(Path(p).resolve(strict=True))!=p for p in paths): raise SystemExit('runtime directories invalid')
print(':'.join(paths))
PY
)
export LD_LIBRARY_PATH="$runtime_libs"
mkdir -p "$out"
python3 "$chat/w1_file_manifest.py" --root "$base_dir" --output "$out/cp00_index_manifest.tsv"
python3 "$new_chat/w1_diskann_runtime_environment.py" --manifest "$runtime_manifest" --binary "$binary" \
  --expected-scope dv-w1-r07-diskann-stale.scope --expected-cpus 0-23 --expected-numa 0 --output "$out/runtime_environment.json"
for l in 29 53; do
  for repetition in 1 2 3; do
    "$chat/resource_probe.py" --output "$out/L${l}_r${repetition}.resources.json" --interval-ms 25 --space-root "$base_dir" -- \
      "$chat/w1_diskann_query_worker.sh" "$binary" "$base" "$query" "$gt" "$out/L${l}_r${repetition}" "$l" "$out/L${l}_r${repetition}.log"
  done
done
python3 "$chat/w1_file_manifest.py" --root "$base_dir" --output "$out/cp00_index_manifest_after.tsv"
cmp -s "$out/cp00_index_manifest.tsv" "$out/cp00_index_manifest_after.tsv" || { echo 'DiskANN immutable base changed' >&2; exit 1; }
python3 "$chat/w1_validate_stale_control.py" --result-dir "$out" --binary "$binary" --base-manifest "$out/cp00_index_manifest.tsv" \
  --query "$query" --gt "$gt" --artifact-manifest "$artifact_manifest" --runtime-manifest "$runtime_manifest" \
  --runtime-environment "$out/runtime_environment.json" --device "${ATLAS_NVME_MAJMIN:-259:10}" --output "$out/stale_control.json"
touch "$out/DISKANN_STALE_CONTROL_OK"
