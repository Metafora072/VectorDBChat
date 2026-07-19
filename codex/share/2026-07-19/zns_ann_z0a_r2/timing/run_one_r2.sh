#!/usr/bin/env bash
set -euo pipefail

[[ ${Z0A_R2_RUN_AUTHORIZED:-0} == 1 && $# == 1 ]] || {
  echo "usage: Z0A_R2_RUN_AUTHORIZED=1 $0 PREREGISTERED_LABEL" >&2
  exit 64
}

label=$1
atlas=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
root=${Z0A_R2_RUN_ROOT:-$atlas/z0a_r2_final_closure_0719}
share=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
old=$(cd "$share/../zns_ann_z0a" && pwd)
trace_build=$atlas/build/zns-ann-z0a-r2-trace-v1-r03
system_build=$atlas/build/zns-ann-z0a-r2-systems-v1-r03
input=$atlas/z0a_trace_model_preflight_0719/inputs/sanity-sift10k-fresh-replace2k
dataset=$atlas/datasets/sift1m/full_1m.bin

read -r system mode triplet position warmup run_uuid < <(python3 - "$root/schedule.json" "$label" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); rows=[r for r in d['runs'] if r['label']==sys.argv[2]]
if len(rows)!=1: raise SystemExit('label absent/duplicated in preregistration')
r=rows[0]; print(r['system'],r['mode'],r['triplet'],r['position'],int(r['warmup']),r['run_uuid'])
PY
)
work=$root/work/$label
result=$root/results/$label
index=$work/index
prefix=$index/index
[[ -f $root/PREPARED_OK && -d $index && -d $work/initial_snapshot && -d $result && ! -e $result/RUN_STARTED ]] || {
  echo "run not prepared or already started: $label" >&2; exit 65;
}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | head -n1) == 259:10 ]] || { echo 'R2 root is not project NVMe' >&2; exit 65; }
touch "$result/RUN_STARTED"

case $mode in
  native) binary=$system_build/native/$system/w1_canary ;;
  shim|full) binary=$system_build/shimfull/$system/z0a_canary ;;
  *) echo "bad mode: $mode" >&2; exit 2 ;;
esac
for path in "$binary" "$dataset" "$input/trace.bin" "$input/expected_active.tags.bin" \
  "$trace_build/common/libr2oracle.so"; do [[ -f $path ]] || { echo "missing: $path" >&2; exit 65; }; done

raw=$result/raw_trace.bin
meta=$result/trace_meta.json
ledger=$result/trace_ledger.json
lifecycle=$result/ordered_lifecycle.jsonl
oracle=$result/common_structure_oracle.json
markers=$result/markers.jsonl
m3=$result/m3_write_lifecycle.json
libs=$trace_build/common:$atlas/build/gperftools-install/lib:$atlas/build/openblas-install/lib:$atlas/build/jemalloc-install/lib
runtime=(PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/home/ubuntu OPENBLAS_NUM_THREADS=32 OMP_NUM_THREADS=32
  LD_LIBRARY_PATH=$libs ATLAS_R2_ORACLE_INDEX_ROOT=$index ATLAS_R2_ORACLE_OUTPUT=$oracle
  ATLAS_M3_LIFECYCLE_OUTPUT=$m3 ATLAS_W1_MARKERS=$markers)
if [[ $mode != native ]]; then
  libs=$trace_build/full:$libs
  runtime+=(LD_LIBRARY_PATH=$libs LD_PRELOAD=$trace_build/full/libz0atrace.so
    ATLAS_Z0A_MODE=$([[ $mode == shim ]] && echo shim-control || echo full-trace)
    ATLAS_Z0A_TRACE_OUTPUT=$raw ATLAS_Z0A_META_OUTPUT=$meta ATLAS_Z0A_LEDGER_OUTPUT=$ledger
    ATLAS_Z0A_LIFECYCLE_OUTPUT=$lifecycle ATLAS_Z0A_INDEX_ROOT=$index ATLAS_Z0A_SYSTEM=$system
    ATLAS_Z0A_RUN_ID=$run_uuid ATLAS_Z0A_OBJECT_MAP=$result/object_registry.tsv ATLAS_Z0A_TRACE_CAPACITY=65536)
fi

readelf -d "$binary" > "$result/binary.readelf.txt"
sha256sum "$binary" "$trace_build/common/libr2oracle.so" > "$result/runtime_sha256.txt"
if [[ $mode != native ]]; then sha256sum "$trace_build/full/libz0atrace.so" >> "$result/runtime_sha256.txt"; fi
if [[ $mode == native ]] && rg -q 'libz0atrace' "$result/binary.readelf.txt"; then echo 'native linkage contaminated' >&2; exit 66; fi

start=$(date +%s%N)
set +e
/usr/bin/time -v -o "$result/time.txt" env -i "${runtime[@]}" \
  /usr/bin/numactl --physcpubind=0-27,56-59 --membind=0 \
  "$binary" run "$dataset" "$prefix" "$input/trace.bin" > "$result/controller.log" 2>&1
rc=$?
set -e
end=$(date +%s%N)
python3 - "$result/run_status.json" "$rc" "$start" "$end" "$system" "$mode" "$triplet" "$position" "$warmup" "$label" <<'PY'
import json,sys
o,rc,start,end,system,mode,triplet,position,warmup,label=sys.argv[1:]
d={'schema':'zns-ann-z0a-r2-run-status-v1','returncode':int(rc),'system':system,'mode':mode,
   'triplet':int(triplet),'position':int(position),'warmup':bool(int(warmup)),'label':label,
   'start_ns':int(start),'end_ns':int(end),'wall_seconds':(int(end)-int(start))/1e9,
   'timezone':'UTC; reporting converted to UTC+8'}
open(o,'x').write(json.dumps(d,indent=2,sort_keys=True)+'\n')
PY
(( rc == 0 )) || exit "$rc"

[[ -s $oracle && -s $m3 && -s $markers ]] || { echo 'common evidence missing' >&2; exit 67; }
python3 "$old/runner/active_audit.py" --actual "${prefix}_disk.index.tags" \
  --expected "$input/expected_active.tags.bin" --output "$result/active_audit.json"

if [[ $mode == full ]]; then
  python3 "$share/timing/z0a_trace_validate_r2.py" --trace "$raw" \
    --pages-output "$result/normalized_pages.bin" --summary "$result/trace_summary.json"
  python3 "$share/independent_readback.py" --initial-manifest "$result/initial_live.jsonl" \
    --initial-snapshot "$work/initial_snapshot" --physical-map "$result/initial_physical_map.jsonl" \
    --physical-image "$result/initial_zns_image.bin" --raw-trace "$raw" \
    --normalized-pages "$result/normalized_pages.bin" --trace-meta "$meta" --lifecycle "$lifecycle" \
    --final-snapshot "$index" --final-live-output "$result/final_live.json" \
    --replay-spec-output "$result/replay_spec.json" --summary "$result/independent_readback.json"
  python3 "$share/r2_replay_validate.py" --spec "$result/replay_spec.json" \
    --final-live "$result/final_live.json" --output "$result/replay_validation.json"
else
  [[ ! -e $raw && ! -e $meta && ! -e $ledger && ! -e $lifecycle ]] || {
    echo "$mode unexpectedly emitted trace evidence" >&2; exit 68;
  }
fi

du -s -B1 "$work" "$result" > "$result/space_bytes.txt"
touch "$result/Z0A_R2_RUN_OK"
echo "$result"
