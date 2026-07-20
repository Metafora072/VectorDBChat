#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=${RUN_ROOT:?RUN_ROOT is required}

test -f "$RUN_ROOT/results/m2/M2_PASS"
test ! -f "$RUN_ROOT/state/STOP_BEFORE_NEXT_STAGE"

BUILD="$RUN_ROOT/build/PipeANN-clean"
INPUT="$RUN_ROOT/input/m2_smoke"
PREFIX="$RUN_ROOT/index/m2_smoke/sift1m_all_role0"
RESULT="$RUN_ROOT/results/m2_trace"
mkdir -p "$RESULT"

strace -ff -qq \
  -e trace=open,openat,io_uring_setup,io_uring_enter \
  -o "$RESULT/strace" \
  "$BUILD/tests/search_disk_index_filtered" \
    float "$PREFIX" 1 32 \
    "$INPUT/query_16.bin" "$INPUT/groundtruth_16.bin" \
    10 l2 pq "$INPUT/filter_all_role0.json" 0 40 \
    > "$RESULT/search_stdout.txt" 2> "$RESULT/search_stderr.txt"

grep -h 'disk.index.*O_DIRECT' "$RESULT"/strace* > "$RESULT/direct_graph_open.txt"
grep -h 'io_uring_setup' "$RESULT"/strace* > "$RESULT/io_uring_setup.txt"
grep -h 'io_uring_enter' "$RESULT"/strace* > "$RESULT/io_uring_enter.txt"
test -s "$RESULT/direct_graph_open.txt"
test -s "$RESULT/io_uring_setup.txt"
test -s "$RESULT/io_uring_enter.txt"
grep -q 'IO size (normal): 4096' "$RESULT/search_stderr.txt"
grep -q 'Recall@10' "$RESULT/search_stdout.txt"

sha256sum "$RESULT"/strace* "$RESULT/search_stdout.txt" "$RESULT/search_stderr.txt" \
  > "$RESULT/sha256.txt"
echo PASS > "$RESULT/M2_TRACE_PASS"
