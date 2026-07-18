#!/usr/bin/env bash
set -euo pipefail
[[ ${M2_NEIGHBOR_REPAIR_AUTHORIZED:-0} == 1 ]] || { echo 'M2 build authorization absent' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
m1="$root/build/write-attribution-m1-v5-r01"
odin_v5="$root/build/write-attribution-m0-v5-r01"
out=${M2_BUILD_ROOT:-$root/build/neighbor-repair-m2-v1-r01}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'M2 build root is not project NVMe' >&2; exit 1; }
for path in "$m1/M1_V5_BUILD_OK" "$m1/build_manifest.json" "$m1/lib/libm0write.so" "$odin_v5/M0_V5_BUILD_OK"; do
  [[ -f $path ]] || { echo "missing accepted M2 prerequisite: $path" >&2; exit 1; }
done
[[ ! -e $out ]] || { echo "refusing M2 build reuse: $out" >&2; exit 1; }
mkdir -p "$out/lib" "$out/install/DGAI" "$out/install/OdinANN" "$out/evidence/DGAI" "$out/evidence/OdinANN" \
  "$out/DGAI/build" "$out/OdinANN/build" "$out/selftest/m2-logical" "$out/source-evidence"
install -m 0444 "$m1/lib/libm0write.so" "$out/lib/libm0write.so"
install -m 0444 "$chat/m2_metrics.h" "$out/source-evidence/m2_metrics.h"

g++ -std=c++17 -O2 -pthread -I"$chat" "$chat/m2_metrics_selftest.cpp" -o "$out/selftest/m2_metrics_selftest" -Wall -Wextra -Werror
ATLAS_M2_LOGICAL_OUTPUT="$out/selftest/m2-logical/profile.json" "$out/selftest/m2_metrics_selftest"

cp -a "$m1/DGAI/src" "$out/DGAI/src"
install -m 0444 "$chat/m2_metrics.h" "$out/DGAI/src/include/m2_metrics.h"
git -C "$out/DGAI/src" apply "$chat/patches/DGAI_m2.patch"

cp -a "$odin_v5/OdinANN/src" "$out/OdinANN/src"
install -m 0444 "$chat/m2_metrics.h" "$out/OdinANN/src/include/m2_metrics.h"
git -C "$out/OdinANN/src" apply "$chat/patches/OdinANN_m2.patch"

export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1
export LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"

src="$out/DGAI/src"; build="$out/DGAI/build"
maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m2/DGAI -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m2/DGAI -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m2/DGAI -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m2-build/DGAI -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m2-build/DGAI"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3 >"$out/evidence/DGAI/cmake.log" 2>&1
cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/DGAI/build.log" 2>&1
install -m 0755 "$build/tests/w1_canary" "$out/install/DGAI/w1_canary"
patchelf --add-needed libm0write.so "$out/install/DGAI/w1_canary"
patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/DGAI/w1_canary"

src="$out/OdinANN/src"; build="$out/OdinANN/build"
maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m2/OdinANN -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m2/OdinANN -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m2/OdinANN -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m2-build/OdinANN -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m2-build/OdinANN"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3 -DIO_ENGINE=uring -DPIPEANN_IO_URING_COMPILE_RESULT=TRUE -DPIPEANN_IO_URING_RUN_RESULT=0 >"$out/evidence/OdinANN/cmake.log" 2>&1
cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/OdinANN/build.log" 2>&1
install -m 0755 "$build/tests/w1_canary" "$out/install/OdinANN/w1_canary"
patchelf --add-needed libm0write.so "$out/install/OdinANN/w1_canary"
patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/OdinANN/w1_canary"

strings "$out/install/DGAI/w1_canary" | rg -q 'dynamic-vamana-neighbor-repair-m2-logical-v1'
strings "$out/install/OdinANN/w1_canary" | rg -q 'dynamic-vamana-neighbor-repair-m2-logical-v1'
python3 "$chat/m2_finalize_build.py" --root "$root" --build "$out" --accepted "$m1"
chmod -R a-w "$out/install" "$out/lib" "$out/source-evidence"
echo "$out/build_manifest.json"
