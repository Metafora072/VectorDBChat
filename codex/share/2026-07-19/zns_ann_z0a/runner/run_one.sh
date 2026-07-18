#!/usr/bin/env bash
set -euo pipefail
[[ ${Z0A_AUTHORIZED:-0} == 1 ]] || { echo 'Z0A authorization absent' >&2; exit 64; }
[[ $# == 3 && ( $1 == DGAI || $1 == OdinANN ) && ( $2 == off || $2 == on ) && $3 =~ ^[1-8]$ ]] || {
  echo "usage: $0 DGAI|OdinANN off|on REPEAT_IN_1_TO_8" >&2; exit 2;
}
system=$1 mode=$2 repeat=$3
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
share=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
run_root="$root/z0a_trace_model_preflight_0719"
build="$root/build/zns-ann-z0a-system-v1-r01"
input="$run_root/inputs/sanity-sift10k-fresh-replace2k"
run_id="z0a-${system,,}-${mode}-r${repeat}"
run_uuid=$(python3 - "$run_id" <<'PY'
import sys,uuid
print(uuid.uuid5(uuid.UUID('16ae19f0-16b7-4f1c-aaf6-5e714086f25f'),sys.argv[1]))
PY
)
work="$run_root/formal/$run_id"
result="$run_root/results/$run_id"
base="$root/index/sanity/$system"
dataset="$root/datasets/sift1m/full_1m.bin"
prefix="$work/index/index"
bin="$build/install/$system/z0a_canary"
lib="$build/lib/libz0atrace.so"
m0lib="$build/lib/libm0write.so"

[[ $(findmnt -rn -T "$root" -o MAJ:MIN | head -n1) == "$device" ]] || { echo 'not project NVMe' >&2; exit 1; }
for p in "$bin" "$lib" "$m0lib" "$input/trace.bin" "$input/expected_active.tags.bin" "$dataset"; do [[ -f $p ]] || { echo "missing $p" >&2; exit 1; }; done
[[ -d $base && ! -e $work && ! -e $result ]] || { echo 'base missing or attempt reused' >&2; exit 1; }
free=$(df -PB1 "$run_root" | awk 'NR==2{print $4}')
(( free > 26113401160 )) || { echo '24.32 GiB 1.5x free-space guard failed' >&2; exit 1; }
mkdir -p "$run_root/formal" "$run_root/results"; tmp="$work.partial.$$"; trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp" "$result"; cp -a --reflink=auto "$base" "$tmp/index"
find "$tmp/index" -type d -exec chmod u+rwx {} +
find "$tmp/index" -type f -exec chmod u+w {} +
for path in "$tmp"/index/sift10k_*; do [[ -e $path ]] || continue; mv "$path" "${path/sift10k_/index_}"; done
touch "$tmp/index/BUILD_OK"
printf '%s\n' zns-ann-z0a-owned-v1 >"$tmp/.z0a-owned"
printf '%s\n' zns-ann-z0a-owned-v1 >"$result/.z0a-owned"
mv "$tmp" "$work"; trap - EXIT

python3 "$share/initial_manifest.py" --system "$system" --run-id "$run_uuid" --clone-root "$work/index" --output "$result/initial_live.jsonl" --z0a-root "$run_root"
python3 "$share/runner/manifest_to_registry.py" --manifest "$result/initial_live.jsonl" --output "$result/object_registry.tsv"
markers="$result/markers.jsonl"; ledger="$result/trace_ledger.json"; meta="$result/trace_meta.json"; raw="$result/raw_trace.bin"; profile="$result/accepted_m0_profile.json"
lifecycle="$result/m3_lifecycle.json"
libs="$build/lib:$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
args=("$bin" run "$dataset" "$prefix" "$input/trace.bin")
start=$(date +%s%N)
set +e
/usr/bin/time -v -o "$result/time.txt" env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/home/ubuntu \
  OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 LD_LIBRARY_PATH="$libs" LD_PRELOAD="$lib:$m0lib" \
  ATLAS_M0_INDEX_ROOT="$work/index" ATLAS_M0_PROFILE_OUTPUT="$profile" \
  ATLAS_M3_LIFECYCLE_OUTPUT="$lifecycle" \
  ATLAS_W1_MARKERS="$markers" ATLAS_Z0A_ENABLED="$([[ $mode == on ]] && echo 1 || echo 0)" \
  ATLAS_Z0A_TRACE_OUTPUT="$raw" ATLAS_Z0A_META_OUTPUT="$meta" ATLAS_Z0A_LEDGER_OUTPUT="$ledger" \
  ATLAS_Z0A_INDEX_ROOT="$work/index" ATLAS_Z0A_SYSTEM="$system" ATLAS_Z0A_RUN_ID="$run_uuid" \
  ATLAS_Z0A_OBJECT_MAP="$result/object_registry.tsv" \
  taskset -c 0-23 "${args[@]}" >"$result/controller.log" 2>&1
rc=$?; set -e; end=$(date +%s%N)
python3 - "$result/run_status.json" "$rc" "$start" "$end" "$system" "$mode" "$repeat" <<'PY'
import json,sys
o,rc,start,end,system,mode,repeat=sys.argv[1:]
d={'schema':'zns-ann-z0a-run-status-v1','returncode':int(rc),'system':system,'mode':mode,'repeat':int(repeat),'start_ns':int(start),'end_ns':int(end),'wall_seconds':(int(end)-int(start))/1e9}
open(o,'w').write(json.dumps(d,indent=2)+'\n')
PY
(( rc == 0 )) || exit "$rc"
python3 "$share/runner/active_audit.py" --actual "${prefix}_disk.index.tags" --expected "$input/expected_active.tags.bin" --output "$result/active_audit.json"
python3 "$share/runner/m0_profile_summary.py" --profile "$profile" --output "$result/accepted_summary.json"
if [[ $mode == on ]]; then
  python3 "$share/trace/z0a_trace_validate.py" --trace "$raw" --pages-output "$result/normalized_pages.bin" --summary "$result/trace_summary.json"
  python3 "$share/runner/validate_closure.py" --raw "$result/trace_summary.json" --accepted "$result/accepted_summary.json" --ledger "$ledger" --meta "$meta" --output "$result/closure.json"
fi
touch "$result/Z0A_RUN_OK"
echo "$result"
