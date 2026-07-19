#!/usr/bin/env bash
set -euo pipefail

[[ ${Z0A_R2_SYSTEM_BUILD_AUTHORIZED:-0} == 1 ]] || {
  echo 'Z0A-R2 system build authorization absent' >&2
  exit 64
}

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
atlas_root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
trace_build=${Z0A_R2_TRACE_BUILD:-$atlas_root/build/zns-ann-z0a-r2-trace-v1-r01}
build_root=${Z0A_R2_SYSTEM_BUILD_ROOT:-$atlas_root/build/zns-ann-z0a-r2-systems-v1-r01}
m3_root=$atlas_root/build/write-supersession-m3-v1-r01
z0a_root=$atlas_root/build/zns-ann-z0a-system-v1-r01
oracle=$trace_build/common/libr2oracle.so

[[ -f $oracle && -f $trace_build/Z0A_R2_TRACE_SELFTEST_OK ]] || {
  echo 'validated R2 tracer/oracle build missing' >&2
  exit 65
}
[[ $build_root == "$atlas_root"/build/zns-ann-z0a-r2-systems-* && ! -e $build_root ]] || {
  echo "invalid or reused build root: $build_root" >&2
  exit 65
}

mkdir -p "$build_root/native/DGAI" "$build_root/native/OdinANN" \
  "$build_root/shimfull/DGAI" "$build_root/shimfull/OdinANN" "$build_root/evidence"

for system in DGAI OdinANN; do
  work=$build_root/native/$system
  cp -a "$m3_root/$system/src" "$work/src"
  if [[ $system == DGAI ]]; then
    cp "$source_dir/native_canary_dgai.cpp" "$work/src/tests/w1_canary.cpp"
  else
    cp "$source_dir/native_canary_odin.cpp" "$work/src/tests/w1_canary.cpp"
    # These are the only two deterministic-control edits in the Z0A source.
    cp "$z0a_root/OdinANN/src/include/dynamic_index.h" "$work/src/include/dynamic_index.h"
    cp "$z0a_root/OdinANN/src/include/utils/prune_neighbors.h" "$work/src/include/utils/prune_neighbors.h"
  fi
  sed -i "/target_link_libraries(w1_canary/a target_link_libraries(w1_canary $oracle)" "$work/src/tests/CMakeLists.txt"
  env CCACHE_DISABLE=1 cmake -S "$work/src" -B "$work/build" \
    -DCMAKE_BUILD_TYPE=Release -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3
  env CCACHE_DISABLE=1 \
    LIBRARY_PATH="$atlas_root/build/gperftools-install/lib:$atlas_root/build/jemalloc-install/lib" \
    cmake --build "$work/build" --target w1_canary -j8
  cp "$work/build/tests/w1_canary" "$work/w1_canary"

  cp "$z0a_root/install/$system/z0a_canary" "$build_root/shimfull/$system/z0a_canary"
  patchelf --add-needed libr2oracle.so "$build_root/shimfull/$system/z0a_canary"
done

for binary in \
  "$build_root/native/DGAI/w1_canary" "$build_root/native/OdinANN/w1_canary" \
  "$build_root/shimfull/DGAI/z0a_canary" "$build_root/shimfull/OdinANN/z0a_canary"; do
  name=$(echo "$binary" | sed "s#^$build_root/##; s#/#_#g")
  readelf -d "$binary" > "$build_root/evidence/$name.readelf.txt"
  sha256sum "$binary" >> "$build_root/SHA256SUMS"
done

if rg -q 'libz0atrace' "$build_root/evidence/native_DGAI_w1_canary.readelf.txt" \
  "$build_root/evidence/native_OdinANN_w1_canary.readelf.txt"; then
  echo 'native binary unexpectedly depends on libz0atrace' >&2
  exit 66
fi
rg -q 'libr2oracle.so' "$build_root/evidence/native_DGAI_w1_canary.readelf.txt"
rg -q 'libr2oracle.so' "$build_root/evidence/shimfull_DGAI_z0a_canary.readelf.txt"
touch "$build_root/Z0A_R2_SYSTEM_BUILD_OK"
printf '%s\n' "$build_root"
