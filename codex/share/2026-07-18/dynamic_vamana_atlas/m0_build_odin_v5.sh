#!/usr/bin/env bash
set -euo pipefail
[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]]||exit 64
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas};device=${ATLAS_NVME_MAJMIN:-259:10};chat18=$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd);chat17=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-17/dynamic_vamana_atlas;canonical="$root/build/w1-canonical-v6/runs/run1/OdinANN/src";out=${M0_BUILD_ROOT:-$root/build/write-attribution-m0-v5-r01}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN|awk 'NR==1{print;exit}') == "$device" ]]||exit 1;[[ ! -e $out ]]||{ echo 'refusing V5 build reuse' >&2;exit 1;}
mkdir -p "$out/lib" "$out/install/OdinANN" "$out/evidence/OdinANN" "$out/OdinANN/build" "$out/selftest"
g++ -std=c++17 -O2 -fPIC -shared "$chat17/m0_write_profiler_v4.cpp" -o "$out/lib/libm0write.so" -ldl -pthread -Wall -Wextra -Werror
g++ -std=c++17 -O2 "$chat17/m0_v4_selftest.cpp" -o "$out/selftest/m0_v5_selftest" -L"$out/lib" -lm0write -laio -luring -Wl,-rpath,"$out/lib" -Wall -Wextra -Werror
g++ -std=c++17 -O2 "$chat18/m0_r04_copy_synthetic.cpp" -o "$out/selftest/copy_synthetic" -Wall -Wextra -Werror
cp -a "$canonical" "$out/OdinANN/src";git -C "$out/OdinANN/src" apply "$chat17/patches/OdinANN_m0_v4.patch"
src="$out/OdinANN/src";build="$out/OdinANN/build";maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m0-v5/OdinANN -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m0-v5/OdinANN -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m0-v5/OdinANN -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m0-v5-build/OdinANN -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m0-v5-build/OdinANN"
export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1 LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3 -DIO_ENGINE=uring -DPIPEANN_IO_URING_COMPILE_RESULT=TRUE -DPIPEANN_IO_URING_RUN_RESULT=0 >"$out/evidence/OdinANN/cmake.log" 2>&1
cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/OdinANN/build.log" 2>&1;install -m 0755 "$build/tests/w1_canary" "$out/install/OdinANN/w1_canary";patchelf --add-needed libm0write.so "$out/install/OdinANN/w1_canary";patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/OdinANN/w1_canary"
for mode in empty posix boundary fdreuse aio;do d="$out/selftest/$mode";mkdir -p "$d/index";ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" "$out/selftest/m0_v5_selftest" "$mode" "$d/index";done
d="$out/selftest/filesystem-copy";mkdir -p "$d/index";install -m 0600 /bin/true "$d/index/index_shadow_disk.index.tags";stat -c '%d %i %s' "$d/index/index_shadow_disk.index.tags" >"$d/destination_before.txt";ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" LD_PRELOAD="$out/lib/libm0write.so" "$out/selftest/copy_synthetic" "$out/selftest/copy_synthetic" "$d/index/index_shadow_disk.index.tags" >"$d/result.json";stat -c '%d %i %s' "$d/index/index_shadow_disk.index.tags" >"$d/destination_after.txt"
d="$out/selftest/filesystem-copy-zero";mkdir -p "$d/index";install -m 0600 /dev/null "$d/source.empty";install -m 0600 /bin/true "$d/index/index_shadow_disk.index.tags";ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" LD_PRELOAD="$out/lib/libm0write.so" "$out/selftest/copy_synthetic" "$d/source.empty" "$d/index/index_shadow_disk.index.tags" >"$d/result.json"
echo "$out"
