#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SYSTEM DATASET" >&2
  exit 2
fi

system=$1
dataset=$2
root=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas
chat=/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas
source_index="$root/index/atlas1m/$system/$dataset"
attempt=${ATLAS_ATTEMPT:-1}
trace_kind=${ATLAS_TRACE_KIND:-replace_new}
work="$root/index/dynamic_smoke/$trace_kind/$system/$dataset/attempt${attempt}"
result="$root/results/dynamic_smoke/$trace_kind/$system/$dataset/attempt${attempt}"
prefix="$work/index"
data="$root/datasets/$dataset/full_1m.bin"
query="$root/datasets/$dataset/query.bin"
case "$trace_kind" in
  replace_new)
    trace="$root/datasets/$dataset/smoke_replace_new_trace.bin"
    truth="$root/groundtruth/$dataset/smoke"
    ;;
  same_vector)
    trace="$root/datasets/$dataset/same_vector_control.bin"
    truth="$root/groundtruth/$dataset/same_vector_control"
    ;;
  *)
    echo "unsupported ATLAS_TRACE_KIND: $trace_kind" >&2
    exit 2
    ;;
esac
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"

mkdir -p "$work" "$result"
exec > >(tee "$result/dynamic.log") 2>&1
if [[ -f "$result/DYNAMIC_OK" ]]; then
  echo "already passed: $system/$dataset attempt=$attempt"
  exit 0
fi
if [[ ! -f "$work/COPY_OK" ]]; then
  cp -a --reflink=auto "$source_index/." "$work/"
  touch "$work/COPY_OK"
fi

export LD_LIBRARY_PATH="$libs"
export OPENBLAS_NUM_THREADS=8
export OMP_NUM_THREADS=8
export ATLAS_TRACE_BIN="$trace"

case "$system" in
  Fresh)
    fresh_r=64
    # The legacy Fresh layout stores one full record per 4 KiB sector.
    # GIST-960 crosses that artifact boundary at R=64, so use the largest
    # smoke-safe degree while keeping the failure evidence from the R=64 try.
    [[ "$dataset" == gist1m ]] && fresh_r=32
    command=(setarch x86_64 -R "$root/build/FreshDiskANN/tests/overall_performance"
      float "$data" 75 "$fresh_r" 1.2 800000 0 "$prefix" "$query" "$truth"
      10 16 1 0 10000 80)
    ;;
  DGAI)
    command=("$root/build/DGAI/tests/overall_performance"
      float "$data" 75 "$prefix" "$query" "$truth" 10 16 1 100 2 23 80)
    ;;
  OdinANN)
    command=("$root/build/OdinANN-uring/tests/overall_performance"
      float "$data" 128 "$prefix" "$query" "$truth" 10 1 80)
    ;;
  *)
    echo "dynamic smoke unsupported for: $system" >&2
    exit 2
    ;;
esac

/usr/bin/time -v -o "$result/time_v.txt" \
  "$chat/resource_probe.py" --output "$result/resources.json" \
  --interval-ms 100 --space-root "$work" -- "${command[@]}"
touch "$result/DYNAMIC_OK"
