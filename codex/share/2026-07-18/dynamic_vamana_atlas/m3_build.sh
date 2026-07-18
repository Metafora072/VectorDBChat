#!/usr/bin/env bash
set -euo pipefail
[[ ${M3_WRITE_SUPERSESSION_AUTHORIZED:-0} == 1 ]] || { echo 'M3 build authorization absent' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); accepted="$root/build/neighbor-repair-m2-v1-r01"; out=${M3_BUILD_ROOT:-$root/build/write-supersession-m3-v1-r01}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || exit 1
[[ -f $accepted/M2_BUILD_OK && -f $accepted/build_manifest.json && ! -e $out ]] || exit 1
mkdir -p "$out"/{lib,source-evidence,selftest} "$out"/{DGAI,OdinANN}/{build} "$out/install"/{DGAI,OdinANN}
install -m 0444 "$accepted/lib/libm0write.so" "$out/lib/libm0write.so"; install -m 0444 "$chat/m2_metrics.h" "$out/source-evidence/m2_metrics.h"; install -m 0444 "$chat/m3_lifecycle.h" "$out/source-evidence/m3_lifecycle.h"
g++ -std=c++17 -O2 -pthread -I"$chat" "$chat/m3_lifecycle_selftest.cpp" -o "$out/selftest/m3_lifecycle_selftest" -Wall -Wextra -Werror; "$out/selftest/m3_lifecycle_selftest"
for system in DGAI OdinANN; do cp -a "$accepted/$system/src" "$out/$system/src"; chmod -R u+w "$out/$system/src"; install -m 0644 "$chat/m3_lifecycle.h" "$out/$system/src/include/m3_lifecycle.h"; patch -d "$out/$system/src" -p1 < "$chat/patches/${system}_m3.patch"; done
export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1 LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib"
cmake -S "$out/DGAI/src" -B "$out/DGAI/build" -DCMAKE_BUILD_TYPE=Release -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3
cmake --build "$out/DGAI/build" --target w1_canary --parallel 8
cmake -S "$out/OdinANN/src" -B "$out/OdinANN/build" -DCMAKE_BUILD_TYPE=Release -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3 -DIO_ENGINE=uring -DPIPEANN_IO_URING_COMPILE_RESULT=TRUE -DPIPEANN_IO_URING_RUN_RESULT=0
cmake --build "$out/OdinANN/build" --target w1_canary --parallel 8
for system in DGAI OdinANN; do install -m 0755 "$out/$system/build/tests/w1_canary" "$out/install/$system/w1_canary"; patchelf --add-needed libm0write.so "$out/install/$system/w1_canary"; patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/$system/w1_canary"; done
python3 "$chat/m3_finalize_build.py" --root "$root" --build "$out" --accepted "$accepted"; chmod -R a-w "$out/install" "$out/lib" "$out/source-evidence"
