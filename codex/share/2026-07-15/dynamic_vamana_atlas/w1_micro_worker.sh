#!/usr/bin/env bash
# Runs inside the caller's dedicated systemd scope; never touches SIFT10M.
set -euo pipefail
[[ $# == 5 ]] || { echo "usage: $0 SYSTEM WORK DATASET PREP CHAT" >&2; exit 2; }
system=$1; work=$2; dataset=$3; prep=$4; chat=$5; markers="$work/markers.jsonl"; prefix="$work/index/index"
root=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
case "$system" in
 DGAI) bin="$root/build/DGAI/tests/w1_canary"; ATLAS_W1_MARKERS="$markers" "$bin" run "$dataset/full_1m.bin" "$prefix" "$prep/trace.bin";;
 OdinANN) bin="$root/build/OdinANN-uring/tests/w1_canary"; ATLAS_W1_MARKERS="$markers" "$bin" run "$dataset/full_1m.bin" "$prefix" "$prep/trace.bin" "$prep/probes.bin" "$work/online.bin";;
 *) exit 2;; esac
python3 "$chat/w1_marker.py" --output "$markers" --name fresh_process_probe_begin
"$bin" probe "$prefix" "$prep/probes.bin" "$work/fresh.bin"
python3 "$chat/w1_marker.py" --output "$markers" --name fresh_process_visibility_verified
