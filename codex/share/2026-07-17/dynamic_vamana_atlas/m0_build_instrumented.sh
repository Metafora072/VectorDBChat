#!/usr/bin/env bash
set -euo pipefail

[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]] || { echo 'M0 build authorization absent' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
canonical="$root/build/w1-canonical-v6/runs/run1"
out=${M0_BUILD_ROOT:-$root/build/write-attribution-m0-v3}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'M0 build root is not project NVMe' >&2; exit 1; }
[[ ! -e $out ]] || { echo "refusing to reuse M0 build: $out" >&2; exit 1; }
for system in DGAI OdinANN; do [[ -d $canonical/$system/src ]] || { echo "missing canonical source: $system" >&2; exit 1; }; done

mkdir -p "$out/lib" "$out/install/DGAI" "$out/install/OdinANN" "$out/evidence"
g++ -std=c++17 -O2 -fPIC -shared "$chat/m0_write_profiler.cpp" -o "$out/lib/libm0write.so" \
  -ldl -pthread -laio -luring -Wall -Wextra -Werror

export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1
export LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
for system in DGAI OdinANN; do
  src="$out/$system/src"; build="$out/$system/build"
  mkdir -p "$out/$system" "$build" "$out/evidence/$system"
  cp -a "$canonical/$system/src" "$src"
  git -C "$src" apply "$chat/patches/${system}_m0_instrumentation.patch"
  maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m0/$system -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m0/$system -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m0/$system -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m0-build/$system -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m0-build/$system -fmacro-prefix-map=$build=/usr/src/dynamic-vamana-m0-build/$system"
  args=(-S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3)
  [[ $system == OdinANN ]] && args+=(-DIO_ENGINE=uring -DPIPEANN_IO_URING_COMPILE_RESULT=TRUE -DPIPEANN_IO_URING_RUN_RESULT=0)
  cmake "${args[@]}" >"$out/evidence/$system/cmake.log" 2>&1
  cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/$system/build.log" 2>&1
  install -m 0755 "$build/tests/w1_canary" "$out/install/$system/w1_canary"
  patchelf --add-needed libm0write.so "$out/install/$system/w1_canary"
  patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/$system/w1_canary"
  nm -D "$out/install/$system/w1_canary" >"$out/evidence/$system/w1_canary.nm"
  LD_LIBRARY_PATH="$out/lib:$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib" \
    ldd "$out/install/$system/w1_canary" >"$out/evidence/$system/w1_canary.ldd"
  rg -q 'm0_set_phase|m0_record_role_page' "$out/evidence/$system/w1_canary.nm"
  rg -q 'libm0write.so' "$out/evidence/$system/w1_canary.ldd"
done

python3 - "$out" "$root/build/w1-canonical-v6/install" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
out,canonical=map(Path,sys.argv[1:])
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''): h.update(block)
 return h.hexdigest()
systems={}
for system in ('DGAI','OdinANN'):
 binary=out/'install'/system/'w1_canary'; base=canonical/system/'w1_canary'
 systems[system]={'instrumented_binary':str(binary.resolve()),'instrumented_sha256':sha(binary),
                  'canonical_binary':str(base.resolve()),'canonical_sha256':sha(base),
                  'binary_is_independent':sha(binary)!=sha(base),
                  'source_patch':f'{system}_m0_instrumentation.patch'}
 if not systems[system]['binary_is_independent']: raise SystemExit('instrumented binary equals canonical binary')
manifest={'schema':'dynamic-vamana-write-attribution-m0-build-v1','status':'pass',
          'profiler_library':str((out/'lib/libm0write.so').resolve()),
          'profiler_sha256':sha(out/'lib/libm0write.so'),'systems':systems}
(out/'build_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
chmod -R a-w "$out/install" "$out/lib"
touch "$out/M0_BUILD_OK"
echo "$out"
