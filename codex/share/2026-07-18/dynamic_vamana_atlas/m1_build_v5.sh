#!/usr/bin/env bash
set -euo pipefail
[[ ${M1_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]] || { echo 'M1 V5 build authorization absent' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
chat18=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
chat17=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-17/dynamic_vamana_atlas
accepted="$root/build/write-attribution-m0-v5-r01"
canonical="$root/build/w1-canonical-v6/runs/run1/DGAI/src"
out=${M1_BUILD_ROOT:-$root/build/write-attribution-m1-v5-r01}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'M1 build root is not project NVMe' >&2; exit 1; }
for path in "$accepted/M0_V5_BUILD_OK" "$accepted/build_manifest.json" "$accepted/lib/libm0write.so" "$accepted/install/OdinANN/w1_canary"; do
  [[ -f $path ]] || { echo "missing accepted V5 artifact: $path" >&2; exit 1; }
done
[[ ! -e $out ]] || { echo "refusing M1 build reuse: $out" >&2; exit 1; }
mkdir -p "$out/lib" "$out/install/DGAI" "$out/install/OdinANN" "$out/evidence/DGAI" "$out/DGAI/build" "$out/selftest"
install -m 0444 "$accepted/lib/libm0write.so" "$out/lib/libm0write.so"
install -m 0555 "$accepted/install/OdinANN/w1_canary" "$out/install/OdinANN/w1_canary"
g++ -std=c++17 -O2 "$chat17/m0_v4_selftest.cpp" -o "$out/selftest/m1_v5_selftest" -L"$out/lib" -lm0write -laio -luring -Wl,-rpath,"$out/lib" -Wall -Wextra -Werror
g++ -std=c++17 -O2 "$chat18/m0_r04_copy_synthetic.cpp" -o "$out/selftest/copy_synthetic" -Wall -Wextra -Werror

cp -a "$canonical" "$out/DGAI/src"
git -C "$out/DGAI/src" apply "$chat17/patches/DGAI_m0_v4.patch"
src="$out/DGAI/src"; build="$out/DGAI/build"
maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m1-v5/DGAI -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m1-v5/DGAI -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m1-v5/DGAI -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m1-v5-build/DGAI -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m1-v5-build/DGAI"
export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1
export LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3 >"$out/evidence/DGAI/cmake.log" 2>&1
cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/DGAI/build.log" 2>&1
install -m 0755 "$build/tests/w1_canary" "$out/install/DGAI/w1_canary"
patchelf --add-needed libm0write.so "$out/install/DGAI/w1_canary"
patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/DGAI/w1_canary"
nm -D "$out/install/DGAI/w1_canary" >"$out/evidence/DGAI/w1_canary.nm"
rg -q 'm0_set_phase|m0_record_role_page|m0_record_async_request' "$out/evidence/DGAI/w1_canary.nm"

for mode in empty posix boundary fdreuse aio; do
  d="$out/selftest/$mode"; mkdir -p "$d/index"
  ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" "$out/selftest/m1_v5_selftest" "$mode" "$d/index"
done
d="$out/selftest/filesystem-copy"; mkdir -p "$d/index"
install -m 0600 /bin/true "$d/index/index_shadow_disk.index.tags"
ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" LD_PRELOAD="$out/lib/libm0write.so" "$out/selftest/copy_synthetic" "$out/selftest/copy_synthetic" "$d/index/index_shadow_disk.index.tags" >"$d/result.json"
python3 "$chat18/m1_finalize_build_v5.py" --root "$root" --build "$out" --accepted "$accepted"
chmod -R a-w "$out/install" "$out/lib"
echo "$out/build_manifest.json"
