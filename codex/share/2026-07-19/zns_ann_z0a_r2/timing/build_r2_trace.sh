#!/usr/bin/env bash
set -euo pipefail

[[ ${Z0A_R2_BUILD_AUTHORIZED:-0} == 1 ]] || {
  echo 'Z0A-R2 build authorization absent' >&2
  exit 64
}

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
z0a_dir=$(cd "$source_dir/../../zns_ann_z0a" && pwd)
atlas_root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
build_root=${Z0A_R2_BUILD_ROOT:-$atlas_root/build/zns-ann-z0a-r2-trace-v1}
[[ $build_root == "$atlas_root"/build/zns-ann-z0a-r2-* ]] || {
  echo "build root escapes approved R2 namespace: $build_root" >&2
  exit 65
}
[[ ! -e $build_root ]] || {
  echo "refusing to reuse build root: $build_root" >&2
  exit 65
}

mkdir -p "$build_root/full" "$build_root/native" "$build_root/common" "$build_root/selftest"
g++ -std=c++17 -O3 -fPIC -shared -pthread -ldl \
  -I"$source_dir" "$source_dir/z0a_trace_r2.cpp" \
  -Wl,-soname,libz0atrace.so -o "$build_root/full/libz0atrace.so"
g++ -std=c++17 -O3 -fPIC -shared \
  -I"$source_dir" "$source_dir/z0a_native_abi.cpp" \
  -Wl,-soname,libz0atrace.so -o "$build_root/native/libz0atrace.so"
g++ -std=c++17 -O3 -fPIC -shared -pthread \
  "$source_dir/r2_structure_oracle.cpp" \
  -Wl,-soname,libr2oracle.so -o "$build_root/common/libr2oracle.so"
g++ -std=c++17 -O3 -I"$source_dir" "$source_dir/z0a_trace_selftest.cpp" \
  -L"$build_root/full" -lz0atrace -Wl,-rpath,"$build_root/full" \
  -o "$build_root/selftest/z0a_trace_selftest"

for mode in native shim-control full-trace; do
  root="$build_root/selftest/$mode"
  mkdir -p "$root/index"
  touch "$root/index/index_disk.index" "$root/index/index_shadow_disk.index"
  python3 "$z0a_dir/trace/z0a_initial_manifest.py" --root "$root/index" --run-id "selftest-$mode" \
    --system DGAI --object-map "$root/objects.tsv" --manifest "$root/initial.jsonl" --summary "$root/initial_summary.json"
  if [[ $mode == native ]]; then
    env LD_LIBRARY_PATH="$build_root/native" \
      "$build_root/selftest/z0a_trace_selftest" "$root/index"
  else
    env LD_LIBRARY_PATH="$build_root/full" LD_PRELOAD="$build_root/full/libz0atrace.so" \
      ATLAS_Z0A_MODE="$mode" ATLAS_Z0A_TRACE_OUTPUT="$root/trace.bin" \
      ATLAS_Z0A_META_OUTPUT="$root/meta.json" ATLAS_Z0A_LEDGER_OUTPUT="$root/ledger.json" \
      ATLAS_Z0A_LIFECYCLE_OUTPUT="$root/lifecycle.jsonl" \
      ATLAS_Z0A_INDEX_ROOT="$root/index" ATLAS_Z0A_SYSTEM=DGAI ATLAS_Z0A_RUN_ID="selftest-$mode" \
      ATLAS_Z0A_OBJECT_MAP="$root/objects.tsv" ATLAS_Z0A_TRACE_CAPACITY=16 \
      "$build_root/selftest/z0a_trace_selftest" "$root/index"
  fi
done
[[ ! -e $build_root/selftest/native/trace.bin && ! -e $build_root/selftest/shim-control/trace.bin ]]
[[ ! -e $build_root/selftest/native/lifecycle.jsonl && ! -e $build_root/selftest/shim-control/lifecycle.jsonl ]]
python3 "$source_dir/z0a_trace_validate_r2.py" \
  --trace "$build_root/selftest/full-trace/trace.bin" \
  --pages-output "$build_root/selftest/full-trace/pages.bin" \
  --summary "$build_root/selftest/full-trace/validation.json"
python3 - "$build_root/selftest/full-trace/validation.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['status']=='pass' and d['request_count']==3 and d['page_event_count']==4
assert d['successful_returned_bytes']==11144 and d['dropped_events']==0
PY
python3 - "$build_root/selftest/full-trace/lifecycle.jsonl" <<'PY'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1])]
events=[row for row in rows if row['record_type']=='lifecycle_event']
assert len(events)==1 and events[0]['event_kind']=='TRUNCATE'
assert events[0]['old_size_bytes']==20480 and events[0]['new_size_bytes']==12288
assert events[0]['status']==0 and events[0]['global_seq']==4
assert rows[-1]['record_type']=='lifecycle_trailer' and rows[-1]['status']=='complete'
PY

sha256sum "$build_root/full/libz0atrace.so" "$build_root/native/libz0atrace.so" \
  "$build_root/common/libr2oracle.so" \
  "$build_root/selftest/z0a_trace_selftest" > "$build_root/SHA256SUMS"
touch "$build_root/Z0A_R2_TRACE_SELFTEST_OK"
printf '%s\n' "$build_root"
