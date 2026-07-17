#!/usr/bin/env bash
# R13-only accepted P1R07 DiskANN CP00 index queried against exact CP20 GT.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_CP20_DISKANN_R13_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || {
  echo 'CP20 DiskANN R13 authorization/global lock absent' >&2; exit 64;
}
[[ $# == 7 ]] || {
  echo "usage: $0 QUERY CP20_GT RESULT_DIR ARTIFACT RUNTIME R10_PREFLIGHT R13_PREFLIGHT" >&2; exit 2;
}
query=$(realpath "$1"); gt=$(realpath "$2"); out=$(realpath -m "$3")
artifact=$(realpath "$4"); runtime=$(realpath "$5")
r10_preflight=$(realpath "$6"); r13_preflight=$(realpath "$7")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=$(cd "$new/../../2026-07-15/dynamic_vamana_atlas" && pwd)
r02=${ATLAS_W1_R02_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas}
expected_out="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/DiskANN/stale-cp20-13"
expected_query="$root/datasets/sift10m/query.bin"
expected_gt="$root/groundtruth/sift10m/w1_trajectory/cp20/gt_cp20"
expected_r10_preflight="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/preflight/r10_execution_preflight_bound.json"
expected_r13_preflight="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/preflight/execution_preflight.json"
[[ $out == "$expected_out" && $query == "$expected_query" && $gt == "$expected_gt" \
  && $r10_preflight == "$expected_r10_preflight" && $r13_preflight == "$expected_r13_preflight" \
  && ! -e $out ]] || { echo 'DiskANN R13 target/input capability mismatch' >&2; exit 1; }

binary="$root/build/DiskANN/apps/search_disk_index"
base_dir="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
base="$base_dir/index"; scope=${W1_EXPECTED_SCOPE:?expected DiskANN scope absent}
runtime_path=$(python3 - "$runtime" "$binary" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_text()); binary=Path(sys.argv[2]).resolve()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if manifest.get('status')!='pass' or manifest.get('not_found_dependencies')!=[]: raise SystemExit('runtime manifest invalid')
if manifest['binary']['realpath']!=str(binary) or manifest['binary']['sha256']!=sha(binary): raise SystemExit('runtime binary mismatch')
print(manifest['runtime_library_path'])
PY
)
export LD_LIBRARY_PATH="$runtime_path"
mkdir -p "$out"
python3 "$old/w1_file_manifest.py" --root "$base_dir" --output "$out/cp00_index_manifest.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base_dir" --output "$out/cp00_index_mode.tsv"
python3 "$r02/w1_diskann_runtime_environment.py" --manifest "$runtime" --binary "$binary" \
  --expected-scope "$scope" --expected-cpus 0-23 --expected-numa 0 --output "$out/runtime_environment.json"
for l_value in 29 53; do
  for repetition in 1 2 3; do
    stem="$out/L${l_value}_r${repetition}"
    "$old/resource_probe.py" --output "$stem.resources.json" --interval-ms 25 --space-root "$base_dir" -- \
      "$old/w1_diskann_query_worker.sh" "$binary" "$base" "$query" "$gt" "$stem" "$l_value" "$stem.log"
  done
done
python3 "$old/w1_file_manifest.py" --root "$base_dir" --output "$out/cp00_index_manifest_after.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base_dir" --output "$out/cp00_index_mode_after.tsv"
python3 "$new/w1_diskann_cp20_validate_r13.py" --result-dir "$out" --binary "$binary" \
  --base-root "$base_dir" --base-manifest "$out/cp00_index_manifest.tsv" \
  --base-mode-manifest "$out/cp00_index_mode.tsv" --query "$query" --gt "$gt" \
  --artifact-manifest "$artifact" --runtime-manifest "$runtime" \
  --execution-preflight "$r10_preflight" --closure-preflight "$r13_preflight" \
  --runtime-environment "$out/runtime_environment.json" --expected-scope "$scope" \
  --device "${ATLAS_NVME_MAJMIN:-259:10}" --output "$out/stale_control.json"
touch "$out/DISKANN_STALE_CP20_OK"
