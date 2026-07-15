#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SYSTEM DATASET" >&2
  exit 2
fi

system=$1
dataset=$2
root=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas
chat=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
data="$root/datasets/$dataset/active_cp00.bin"
tags="$root/datasets/$dataset/active_cp00.tags.bin"
index_dir="$root/index/atlas1m/$system/$dataset"
result_dir="$root/results/atlas1m/$system/$dataset"
prefix="$index_dir/index"
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"

mkdir -p "$index_dir" "$result_dir"
if [[ -f "$index_dir/BUILD_OK" ]]; then
  echo "already built: $system/$dataset"
  exit 0
fi

export LD_LIBRARY_PATH="$libs"
export OPENBLAS_NUM_THREADS=24
export OMP_NUM_THREADS=24

case "$system" in
  DiskANN)
    /usr/bin/time -v -o "$result_dir/build_time.txt" \
      "$root/build/DiskANN/apps/build_disk_index" \
      --data_type float --dist_fn l2 --data_path "$data" \
      --index_path_prefix "$prefix" -R 64 -L 100 -B 1 -M 64 -T 24
    ;;
  Fresh)
    fresh_r=64
    if [[ "$dataset" == "gist1m" ]]; then
      # 960D + R64 produces a 4100-byte record in this legacy artifact,
      # whose layout code cannot represent a record crossing 4 KiB.
      fresh_r=32
    fi
    /usr/bin/time -v -o "$result_dir/build_time.txt" \
      "$root/build/FreshDiskANN/tests/build_disk_index" \
      float "$data" "$prefix" "$fresh_r" 75 1 64 24 l2 0
    cp "$tags" "${prefix}_disk.index.tags"
    python3 "$chat/materialize_fresh_centroid.py" --base "$data" --index-prefix "$prefix"
    ;;
  DGAI)
    /usr/bin/time -v -o "$result_dir/build_time.txt" \
      "$root/build/DGAI/tests/build_disk_index" \
      float "$data" "$prefix" 32 75 1 64 24 l2 0
    cp "$tags" "${prefix}_disk.index.tags"
    cp "${prefix}_pq_compressed_refined.bin" "${prefix}_pq_compressed_2.bin"
    cp "${prefix}_pq_pivots_refined.bin" "${prefix}_pq_pivots_2.bin"
    "$root/build/DGAI/tests/split_index" \
      "${prefix}_disk.index" "$index_dir/dram_index_graph" \
      "$index_dir/disk_index_graph" "$index_dir/disk_index_data" float
    "$root/build/DGAI/tests/reorder_by_map" \
      800000 132 "$index_dir/disk_index_graph" \
      "$index_dir/reorder_map_graph_2" "$index_dir/reordered_disk_index_graph_2"
    ;;
  OdinANN)
    /usr/bin/time -v -o "$result_dir/build_time.txt" \
      "$root/build/OdinANN-uring/tests/build_disk_index" \
      float "$data" "$prefix" 96 128 32 64 24 l2 pq
    ;;
  *)
    echo "unknown system: $system" >&2
    exit 2
    ;;
esac

touch "$index_dir/BUILD_OK"
