#!/usr/bin/env bash
# Two independent clean builds with canonical path mapping and byte comparison.
set -euo pipefail
[[ ${W1_CANONICAL_REBUILD_AUTHORIZED:-0} == 1 ]] || { echo 'canonical rebuild gate not granted' >&2; exit 64; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
out=${W1_CANONICAL_ROOT:-$root/build/w1-canonical-v4}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'experiment root not on NVMe' >&2; exit 1; }
[[ ! -e "$out" ]] || { echo "canonical rebuild output already exists: $out" >&2; exit 1; }
mkdir -p "$out/runs" "$out/install/DGAI" "$out/install/OdinANN" "$out/evidence"

export SOURCE_DATE_EPOCH=1721001600 TZ=UTC LC_ALL=C LANG=C CCACHE_DISABLE=1
export LIBRARY_PATH="$root/build/gperftools-install/lib:$root/build/jemalloc-install/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"

declare -A repo commit
repo[DGAI]="$root/src/DGAI-clean"
repo[OdinANN]="$root/src/OdinANN-PipeANN"
commit[DGAI]=a0179b876a4bd453336dc2893b46ae890f680555
commit[OdinANN]=9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b

patches_DGAI=(
  DGAI_mkl_cblas_compat.patch
  DGAI_w1_result_ids.patch
  DGAI_w1_canary_driver.patch
  DGAI_w1_canary_cmake.patch
)
patches_OdinANN=(
  OdinANN_system_uring_cblas.patch
  OdinANN_uring_runtime_compat.patch
  OdinANN_uring_strict.patch
  OdinANN_w1_result_ids.patch
  OdinANN_w1_canary_driver.patch
  OdinANN_w1_canary_cmake.patch
)

for run in run1 run2; do
  for system in DGAI OdinANN; do
    src="$out/runs/$run/$system/src"; build="$out/runs/$run/$system/build"
    mkdir -p "$src" "$build" "$out/evidence/$run/$system"
    git -C "${repo[$system]}" archive "${commit[$system]}" | tar -x -C "$src"
    if [[ $system == DGAI ]]; then patches=("${patches_DGAI[@]}"); else patches=("${patches_OdinANN[@]}"); fi
    for name in "${patches[@]}"; do git -C "$src" apply "$chat/patches/$name"; done
    canonical_src="/usr/src/dynamic-vamana/$system"
    canonical_build="/usr/src/dynamic-vamana-build/$system"
    maps="-ffile-prefix-map=$src=$canonical_src -fdebug-prefix-map=$src=$canonical_src -fmacro-prefix-map=$src=$canonical_src -ffile-prefix-map=$build=$canonical_build -fdebug-prefix-map=$build=$canonical_build -fmacro-prefix-map=$build=$canonical_build"
    args=(-S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$maps" -DCMAKE_CXX_FLAGS="$maps" -DCMAKE_SKIP_RPATH=ON -DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3)
    [[ $system == OdinANN ]] && args+=(-DIO_ENGINE=uring)
    cmake "${args[@]}" 2>&1 | tee "$out/evidence/$run/$system/cmake.log"
    cmake --build "$build" --target w1_canary search_disk_index --parallel 8 2>&1 | tee "$out/evidence/$run/$system/build.log"
    cp "$build/compile_commands.json" "$out/evidence/$run/$system/compile_commands.json"
    sha256sum "$build/tests/w1_canary" "$build/tests/search_disk_index" >"$out/evidence/$run/$system/binary_sha256.txt"
    ldd "$build/tests/w1_canary" >"$out/evidence/$run/$system/w1_canary.ldd"
    ldd "$build/tests/search_disk_index" >"$out/evidence/$run/$system/search_disk_index.ldd"
  done
done

for system in DGAI OdinANN; do
  for binary in w1_canary search_disk_index; do
    one="$out/runs/run1/$system/build/tests/$binary"; two="$out/runs/run2/$system/build/tests/$binary"
    cmp -s "$one" "$two" || { echo "non-reproducible binary: $system/$binary" >&2; exit 1; }
    install -m 0755 "$one" "$out/install/$system/$binary"
  done
done

python3 - "$out" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
systems={}
for system in ('DGAI','OdinANN'):
 bins={name:root/'install'/system/name for name in ('w1_canary','search_disk_index')}
 systems[system]={'binary_sha256':{name:sha(path) for name,path in bins.items()},
                  'run1_sha256':{},'run2_sha256':{},
                  'byte_identical':True,
                  'ldd':{name:subprocess.run(['ldd',str(path)],check=True,text=True,capture_output=True).stdout.splitlines() for name,path in bins.items()}}
 for run in ('run1','run2'):
  systems[system][f'{run}_sha256']={name:sha(root/'runs'/run/system/'build'/'tests'/name) for name in bins}
(root/'rebuild_result.json').write_text(json.dumps({'schema':'dynamic-vamana-w1-canonical-rebuild-v1','source_date_epoch':1721001600,'systems':systems},indent=2)+'\n')
PY
touch "$out/CANONICAL_REBUILD_OK"
echo "$out"
