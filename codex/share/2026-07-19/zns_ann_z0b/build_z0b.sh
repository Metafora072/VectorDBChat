#!/usr/bin/env bash
set -euo pipefail

[[ ${Z0B_BUILD_AUTHORIZED:-0} == 1 ]] || { echo 'Z0B build authorization absent' >&2; exit 64; }

share=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
chat=$(cd "$share/../../../.." && pwd)
atlas=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
build=${Z0B_BUILD_ROOT:-$atlas/build/zns-ann-z0b-endpoint-v1-r01}
m3=$atlas/build/write-supersession-m3-v1-r01
z0a=$atlas/build/zns-ann-z0a-system-v1-r01
r2=$chat/codex/share/2026-07-19/zns_ann_z0a_r2/timing

[[ $(findmnt -rn -T "$atlas" -o MAJ:MIN | head -n1) == 259:10 ]] || { echo 'atlas is not /dev/nvme8n1' >&2; exit 65; }
[[ $build == "$atlas"/build/zns-ann-z0b-endpoint-* && ! -e $build ]] || { echo 'invalid/reused build root' >&2; exit 65; }
for path in "$m3/M3_BUILD_OK" "$m3/build_manifest.json" "$z0a/include/z0a_trace.h" "$r2/z0a_trace.h"; do
  [[ -f $path ]] || { echo "missing frozen prerequisite: $path" >&2; exit 65; }
done

mkdir -p "$build/trace" "$build/systems" "$build/evidence" "$build/selftest/index"
g++ -std=c++17 -O3 -fPIC -shared -pthread -ldl -I"$r2" "$share/z0b_trace.cpp" \
  -Wl,-soname,libz0btrace.so -o "$build/trace/libz0btrace.so"
g++ -std=c++17 -O3 -I"$r2" "$share/namespace_selftest.cpp" \
  -L"$build/trace" -lz0btrace -Wl,-rpath,"$build/trace" -o "$build/selftest/namespace_selftest"

printf '# incarnation device inode ctime_ns role absolute_path\n' > "$build/selftest/objects.tsv"
env LD_LIBRARY_PATH="$build/trace" LD_PRELOAD="$build/trace/libz0btrace.so" \
  ATLAS_Z0A_MODE=full-trace ATLAS_Z0A_TRACE_OUTPUT="$build/selftest/raw.bin" \
  ATLAS_Z0A_META_OUTPUT="$build/selftest/meta.json" ATLAS_Z0A_LEDGER_OUTPUT="$build/selftest/ledger.json" \
  ATLAS_Z0A_LIFECYCLE_OUTPUT="$build/selftest/lifecycle.jsonl" ATLAS_Z0A_INDEX_ROOT="$build/selftest/index" \
  ATLAS_Z0A_SYSTEM=DGAI ATLAS_Z0A_RUN_ID=z0b-namespace-selftest \
  ATLAS_Z0A_OBJECT_MAP="$build/selftest/objects.tsv" ATLAS_Z0A_TRACE_CAPACITY=16 \
  "$build/selftest/namespace_selftest" "$build/selftest/index"
python3 "$share/stream_normalize.py" --raw "$build/selftest/raw.bin" \
  --lifecycle "$build/selftest/lifecycle.jsonl" --output "$build/selftest/normalized.bin" \
  --summary "$build/selftest/normalization.json"
python3 - "$build/selftest/lifecycle.jsonl" <<'PY'
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1])]
events=rows[1:-1]
sources=[int(row['source_entrypoint']) for row in events]
assert rows[0]['dropped']==0 and rows[-1]['status']=='complete'
assert 2 in sources and 3 in sources and 1 in sources
PY

for system in DGAI OdinANN; do
  work="$build/systems/$system"
  cp -a "$m3/$system/src" "$work"
  cp "$z0a/$system/src/include/z0a_trace.h" "$work/include/z0a_trace.h"
  cp "$z0a/$system/src/include/ssd_index.h" "$work/include/ssd_index.h"
  cp "$z0a/$system/src/src/update/direct_insert.cpp" "$work/src/update/direct_insert.cpp"
  cp "$z0a/$system/src/src/utils/linux_aligned_file_reader.cpp" "$work/src/utils/linux_aligned_file_reader.cpp"
  if [[ $system == OdinANN ]]; then cp "$z0a/$system/src/src/ssd_index.cpp" "$work/src/ssd_index.cpp"; fi
  patch_name=dgai_driver_context.patch
  [[ $system == OdinANN ]] && patch_name=odin_driver_context.patch
  patch -p1 -d "$work" < "$share/$patch_name"
  sed -i "/target_link_libraries(w1_canary/a target_link_libraries(w1_canary $build/trace/libz0btrace.so)" "$work/tests/CMakeLists.txt"
  env CCACHE_DISABLE=1 cmake -S "$work" -B "$work/build" -DCMAKE_BUILD_TYPE=Release \
    -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3
  env CCACHE_DISABLE=1 \
    LIBRARY_PATH="$atlas/build/gperftools-install/lib:$atlas/build/jemalloc-install/lib" \
    cmake --build "$work/build" --target w1_canary -j8
  cp "$work/build/tests/w1_canary" "$build/systems/$system/w1_canary"
  readelf -d "$build/systems/$system/w1_canary" > "$build/evidence/$system.readelf.txt"
  rg -q 'libz0btrace.so' "$build/evidence/$system.readelf.txt"
done

sha256sum "$share/build_z0b.sh" "$share/z0b_trace.cpp" "$share/namespace_selftest.cpp" "$share"/*.patch \
  "$build/trace/libz0btrace.so" "$build/systems/DGAI/w1_canary" "$build/systems/OdinANN/w1_canary" \
  > "$build/evidence/SHA256SUMS"
cp "$m3/build_manifest.json" "$build/evidence/frozen_m3_build_manifest.json"
touch "$build/Z0B_BUILD_OK"
chmod -R a-w "$build"
printf '%s\n' "$build"
