#!/usr/bin/env bash
set -euo pipefail
[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]] || { echo 'M0 V4 build authorization absent' >&2; exit 64; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
canonical="$root/build/w1-canonical-v6/runs/run1"
out=${M0_BUILD_ROOT:-$root/build/write-attribution-m0-v4-r02}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'M0 V4 build root is not project NVMe' >&2; exit 1; }
[[ ! -e $out ]] || { echo "refusing to reuse M0 V4 build: $out" >&2; exit 1; }
mkdir -p "$out/lib" "$out/install/DGAI" "$out/install/OdinANN" "$out/evidence" "$out/selftest"
g++ -std=c++17 -O2 -fPIC -shared "$chat/m0_write_profiler_v4.cpp" -o "$out/lib/libm0write.so" -ldl -pthread -Wall -Wextra -Werror
g++ -std=c++17 -O2 "$chat/m0_v4_selftest.cpp" -o "$out/selftest/m0_v4_selftest" -L"$out/lib" -lm0write -laio -luring -Wl,-rpath,"$out/lib" -Wall -Wextra -Werror

export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1
export LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
for system in DGAI OdinANN; do
  src="$out/$system/src"; build="$out/$system/build"; mkdir -p "$out/$system" "$build" "$out/evidence/$system"
  cp -a "$canonical/$system/src" "$src"
  git -C "$src" apply "$chat/patches/${system}_m0_v4.patch"
  maps="-ffile-prefix-map=$src=/usr/src/dynamic-vamana-m0-v4/$system -fdebug-prefix-map=$src=/usr/src/dynamic-vamana-m0-v4/$system -fmacro-prefix-map=$src=/usr/src/dynamic-vamana-m0-v4/$system -ffile-prefix-map=$build=/usr/src/dynamic-vamana-m0-v4-build/$system -fdebug-prefix-map=$build=/usr/src/dynamic-vamana-m0-v4-build/$system"
  args=(-S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3)
  [[ $system == OdinANN ]] && args+=(-DIO_ENGINE=uring -DPIPEANN_IO_URING_COMPILE_RESULT=TRUE -DPIPEANN_IO_URING_RUN_RESULT=0)
  cmake "${args[@]}" >"$out/evidence/$system/cmake.log" 2>&1
  cmake --build "$build" --target w1_canary --parallel 8 >"$out/evidence/$system/build.log" 2>&1
  install -m 0755 "$build/tests/w1_canary" "$out/install/$system/w1_canary"
  patchelf --add-needed libm0write.so "$out/install/$system/w1_canary"
  patchelf --add-rpath '$ORIGIN/../../lib' "$out/install/$system/w1_canary"
  nm -D "$out/install/$system/w1_canary" >"$out/evidence/$system/w1_canary.nm"
  rg -q 'm0_set_phase|m0_record_role_page|m0_record_async_request' "$out/evidence/$system/w1_canary.nm"
done

for mode in empty posix boundary fdreuse aio uring; do
  d="$out/selftest/$mode"; mkdir -p "$d/index"
  ATLAS_M0_INDEX_ROOT="$d/index" ATLAS_M0_PROFILE_OUTPUT="$d/profile.json" "$out/selftest/m0_v4_selftest" "$mode" "$d/index"
done
python3 - "$out/selftest" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]); load=lambda m:json.loads((r/m/'profile.json').read_text())
assert load('empty')['ledger_totals']=={}
assert load('posix')['ledger_totals']['posix']=={'requested_bytes':4096,'request_count':1}
b=load('boundary')['buckets']; assert sum(x['requested_bytes'] for x in b)==4096 and {x['component'] for x in b}=={'metadata','graph_vector_combined'}
f=load('fdreuse')['buckets']; assert {Path(x['path']).name for x in f}=={'index_disk.index','index_pq_compressed.bin'}
for m,e in [('aio','linux_aligned.execute_io.libaio'),('uring','linux_aligned.execute_io.io_uring')]:
 d=load(m); assert d['ledger_totals']['async']=={'requested_bytes':4096,'request_count':1}; assert d['entry_totals'][0]['entry']==e
PY
python3 - "$out" "$root/build/w1-canonical-v6/install" <<'PY'
import hashlib,json,sys
from pathlib import Path
out,canonical=map(Path,sys.argv[1:]); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
systems={}
for s in ('DGAI','OdinANN'):
 b=out/'install'/s/'w1_canary'; c=canonical/s/'w1_canary'; systems[s]={'instrumented_binary':str(b.resolve()),'instrumented_sha256':sha(b),'canonical_binary':str(c.resolve()),'canonical_sha256':sha(c),'binary_is_independent':sha(b)!=sha(c),'source_patch':f'{s}_m0_v4.patch'}
 assert systems[s]['binary_is_independent']
m={'schema':'dynamic-vamana-write-attribution-m0-build-v4','status':'pass','profiler_library':str((out/'lib/libm0write.so').resolve()),'profiler_sha256':sha(out/'lib/libm0write.so'),'selftests':['empty','posix','boundary','fdreuse','aio','uring'],'systems':systems}
(out/'build_manifest.json').write_text(json.dumps(m,indent=2)+'\n')
PY
chmod -R a-w "$out/install" "$out/lib"; touch "$out/M0_V4_BUILD_OK"; echo "$out"
