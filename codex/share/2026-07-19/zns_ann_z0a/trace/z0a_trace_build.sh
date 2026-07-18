#!/usr/bin/env bash
set -euo pipefail

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
atlas_root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
build_root=${Z0A_BUILD_ROOT:-$atlas_root/build/zns-ann-z0a-trace-v1}
device=${ATLAS_NVME_MAJMIN:-259:10}

[[ ${Z0A_TRACE_BUILD_AUTHORIZED:-0} == 1 ]] || { echo 'Z0A trace build authorization absent' >&2; exit 64; }
[[ $(findmnt -rn -T "$build_root" -o MAJ:MIN 2>/dev/null | awk 'NR==1{print;exit}') == "$device" || ! -e $build_root ]] || {
  echo 'existing build root is not on project NVMe' >&2; exit 1;
}
[[ ! -e $build_root ]] || { echo "refusing to reuse build root: $build_root" >&2; exit 1; }
mkdir -p "$build_root/lib" "$build_root/include" "$build_root/selftest" "$build_root/install/DGAI" "$build_root/install/OdinANN"

c++ -std=c++17 -O2 -g -fPIC -shared -Wall -Wextra -Werror \
  "$source_dir/z0a_trace.cpp" -I"$source_dir" -ldl -pthread -o "$build_root/lib/libz0atrace.so"
c++ -std=c++17 -O2 -g -Wall -Wextra -Werror \
  "$source_dir/z0a_trace_selftest.cpp" -I"$source_dir" -L"$build_root/lib" -lz0atrace \
  -Wl,-rpath,"$build_root/lib" -o "$build_root/selftest/z0a_trace_selftest"
cp "$source_dir/z0a_trace.h" "$build_root/include/z0a_trace.h"

on="$build_root/selftest/on"; off="$build_root/selftest/off"
mkdir -p "$on/index" "$off/index"
touch "$on/index/index_disk.index" "$on/index/index_shadow_disk.index"
touch "$off/index/index_disk.index" "$off/index/index_shadow_disk.index"
ATLAS_Z0A_ENABLED=0 ATLAS_Z0A_INDEX_ROOT="$off/index" \
  "$build_root/selftest/z0a_trace_selftest" "$off/index"
[[ ! -e $off/trace.bin && ! -e $off/meta.json && ! -e $off/ledger.json ]]

python3 "$source_dir/z0a_initial_manifest.py" --root "$on/index" --run-id selftest-on \
  --system DGAI --object-map "$on/objects.tsv" --manifest "$on/initial_pages.jsonl" --summary "$on/initial_summary.json"
ATLAS_Z0A_ENABLED=1 ATLAS_Z0A_TRACE_OUTPUT="$on/trace.bin" ATLAS_Z0A_META_OUTPUT="$on/meta.json" \
  ATLAS_Z0A_LEDGER_OUTPUT="$on/ledger.json" ATLAS_Z0A_INDEX_ROOT="$on/index" ATLAS_Z0A_SYSTEM=DGAI \
  ATLAS_Z0A_RUN_ID=selftest-on ATLAS_Z0A_OBJECT_MAP="$on/objects.tsv" ATLAS_Z0A_TRACE_CAPACITY=16 \
  "$build_root/selftest/z0a_trace_selftest" "$on/index"
python3 "$source_dir/z0a_trace_validate.py" --trace "$on/trace.bin" --pages-output "$on/pages.bin" \
  --summary "$on/validation.json"
python3 - "$on/meta.json" "$on/ledger.json" "$on/validation.json" <<'PY'
import json,sys
m,l,v=(json.load(open(path)) for path in sys.argv[1:])
assert m['status']=='complete' and m['dropped_events']==0 and m['record_count']==3
assert l['status']=='complete' and l['accepted_requests']==l['completed_requests']==3
assert v['status']=='pass' and v['request_to_page_byte_closure'] and v['page_event_count']==4
assert v['object_count']==2 and v['successful_returned_bytes']==11144
PY

sha256sum "$build_root/lib/libz0atrace.so" "$build_root/selftest/z0a_trace_selftest" > "$build_root/SHA256SUMS"
touch "$build_root/Z0A_TRACE_LIBRARY_SELFTEST_OK"
echo "$build_root"
