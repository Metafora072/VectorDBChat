#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SYSTEM DATASET" >&2
  exit 2
fi

system=$1
dataset=$2
root=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas
query="$root/datasets/$dataset/query.bin"
gt="$root/groundtruth/$dataset/gt_cp00"
index_dir="$root/index/atlas1m/$system/$dataset"
result_dir="$root/results/atlas1m/$system/$dataset"
prefix="$index_dir/index"
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"

mkdir -p "$result_dir"
exec > >(tee "$result_dir/query.log") 2>&1
export LD_LIBRARY_PATH="$libs"
export OPENBLAS_NUM_THREADS=8
export OMP_NUM_THREADS=8

case "$system" in
  DiskANN)
    /usr/bin/time -v -o "$result_dir/query_time.txt" \
      "$root/build/DiskANN/apps/search_disk_index" \
      --data_type float --dist_fn l2 --index_path_prefix "$prefix" \
      --result_path "$result_dir/result" --query_file "$query" --gt_file "$gt" \
      -K 10 -L 20 40 80 120 -T 8 -W 4
    ;;
  Fresh)
    /usr/bin/time -v -o "$result_dir/query_time.txt" \
      setarch x86_64 -R "$root/build/FreshDiskANN/tests/search_disk_index" \
      float "$prefix" 0 1 0 8 4 "$query" "$gt" 10 "$result_dir/result" l2 \
      20 40 80 120
    ;;
  DGAI)
    /usr/bin/time -v -o "$result_dir/query_time.txt" \
      "$root/build/DGAI/tests/search_disk_index" \
      float "$prefix" 8 16 "$query" "$gt" 10 l2 2 0 23 20 40 80 120
    ;;
  OdinANN)
    /usr/bin/time -v -o "$result_dir/query_time.txt" \
      "$root/build/OdinANN-uring/tests/search_disk_index" \
      float "$prefix" 8 16 "$query" "$gt" 10 l2 pq 2 0 20 40 80 120
    ;;
  *)
    echo "unknown system: $system" >&2
    exit 2
    ;;
esac

touch "$result_dir/QUERY_OK"
