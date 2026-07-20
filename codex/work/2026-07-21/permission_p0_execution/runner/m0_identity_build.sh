#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=${RUN_ROOT:?RUN_ROOT is required}
SOURCE_REPO=${SOURCE_REPO:?SOURCE_REPO is required}
COMMIT=${COMMIT:?COMMIT is required}
DATASET_ROOT=${DATASET_ROOT:?DATASET_ROOT is required}
HARNESS_ROOT=${HARNESS_ROOT:?HARNESS_ROOT is required}

case "$(realpath -m "$RUN_ROOT")" in
  /home/ubuntu/pz/VectorDB/data/*) ;;
  *) echo "RUN_ROOT is not on /dev/nvme8n1" >&2; exit 70 ;;
esac

SRC="$RUN_ROOT/src/PipeANN-clean"
BUILD="$RUN_ROOT/build/PipeANN-clean"
MANIFEST="$RUN_ROOT/manifests"
RESULT="$RUN_ROOT/results/m0"
ADAPTER="$RUN_ROOT/adapters"
mkdir -p "$RUN_ROOT/src" "$BUILD" "$MANIFEST" "$RESULT" "$ADAPTER"

if [[ ! -e "$SRC/.git" ]]; then
  git clone --local --no-hardlinks "$SOURCE_REPO" "$SRC"
  git -C "$SRC" checkout --detach "$COMMIT"
fi

test "$(git -C "$SRC" rev-parse HEAD)" = "$COMMIT"
test -z "$(git -C "$SRC" status --porcelain)"
git -C "$SRC" fsck --no-dangling

cp "$HARNESS_ROOT/adapters/cblas.h" "$ADAPTER/cblas.h"
cp "$HARNESS_ROOT/adapters/uring_probe.cpp" "$ADAPTER/uring_probe.cpp"
cp "$HARNESS_ROOT/adapters/force_uring.patch" "$ADAPTER/force_uring.patch"
sha256sum "$ADAPTER"/* > "$MANIFEST/adapter_sha256.txt"

git -C "$SRC" apply --check "$ADAPTER/force_uring.patch"
git -C "$SRC" apply "$ADAPTER/force_uring.patch"
git -C "$SRC" diff --check
git -C "$SRC" diff --binary > "$MANIFEST/tracked_adapter.diff"
git -C "$SRC" status --porcelain > "$MANIFEST/source_status_before_build.txt"
test "$(wc -l < "$MANIFEST/source_status_before_build.txt")" -eq 1
grep -q '^ M CMakeLists.txt$' "$MANIFEST/source_status_before_build.txt"

g++ -O2 "$ADAPTER/uring_probe.cpp" -o "$ADAPTER/uring_probe"
"$ADAPTER/uring_probe" > "$MANIFEST/uring_probe.txt"

{
  echo "commit=$COMMIT"
  echo "source_repo=$SOURCE_REPO"
  echo "source_origin=$(git -C "$SRC" remote get-url origin)"
  echo "official_origin=$(git -C "$SOURCE_REPO" remote get-url origin)"
  echo "source_worktree=$SRC"
  echo "source_status=clean"
  echo "kernel=$(uname -r)"
  echo "cmake=$(cmake --version | head -n1)"
  echo "compiler=$(g++ --version | head -n1)"
  echo "configured_io_engine=uring"
  echo "use_tcmalloc=OFF"
  echo "allocator_deviation=system-default-malloc"
  echo "adapter=external-cblas-abi-header-plus-force-regular-uring-after-probe"
} > "$MANIFEST/identity.env"

sha256sum \
  "$DATASET_ROOT/full.bin" \
  "$DATASET_ROOT/query.bin" \
  "$DATASET_ROOT/groundtruth.bin" \
  > "$MANIFEST/input_sha256.txt"

cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DIO_ENGINE=uring \
  -DPIPEANN_FORCE_URING=ON \
  -DUSE_TCMALLOC=OFF \
  -DBUILD_PYTHON_INTERFACE=OFF \
  -DBUILD_MILVUS_SERVER=OFF \
  -DBLAS_LIBRARIES=/lib/x86_64-linux-gnu/libblas.so.3 \
  -DCMAKE_C_COMPILER_LAUNCHER= \
  -DCMAKE_CXX_COMPILER_LAUNCHER= \
  -DCMAKE_CXX_FLAGS="-I$ADAPTER"

grep -q '^IO_ENGINE:STRING=uring$' "$BUILD/CMakeCache.txt"
grep -q -- '-DUSE_URING' "$BUILD/compile_commands.json"
sha256sum "$BUILD/CMakeCache.txt" "$BUILD/compile_commands.json" \
  > "$MANIFEST/build_config_sha256.txt"

cmake --build "$BUILD" -j8 --target \
  build_disk_index_filtered search_disk_index_filtered compute_groundtruth

sha256sum \
  "$BUILD/tests/build_disk_index_filtered" \
  "$BUILD/tests/search_disk_index_filtered" \
  "$BUILD/tests/utils/compute_groundtruth" \
  > "$MANIFEST/binary_sha256.txt"

ldd "$BUILD/tests/build_disk_index_filtered" > "$MANIFEST/build_disk_index_filtered.ldd"
ldd "$BUILD/tests/search_disk_index_filtered" > "$MANIFEST/search_disk_index_filtered.ldd"
if grep -q 'not found' "$MANIFEST/build_disk_index_filtered.ldd"; then
  echo "unresolved runtime dependency" >&2
  exit 71
fi

grep -q 'liburing.so' "$MANIFEST/build_disk_index_filtered.ldd"
grep -q '/lib/x86_64-linux-gnu/libblas.so.3' "$MANIFEST/build_disk_index_filtered.ldd"
git -C "$SRC" status --porcelain > "$MANIFEST/source_status_after_build.txt"
cmp "$MANIFEST/source_status_before_build.txt" "$MANIFEST/source_status_after_build.txt"

df -B1 "$RUN_ROOT" > "$RESULT/df_after.txt"
du -sb "$RUN_ROOT" > "$RESULT/du_after.txt"
echo PASS > "$RESULT/M0_PASS"
