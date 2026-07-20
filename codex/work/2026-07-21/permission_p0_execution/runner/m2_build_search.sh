#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=${RUN_ROOT:?RUN_ROOT is required}
DATASET_ROOT=${DATASET_ROOT:?DATASET_ROOT is required}
HARNESS_ROOT=${HARNESS_ROOT:?HARNESS_ROOT is required}

test -f "$RUN_ROOT/results/m0/M0_PASS"
test -f "$RUN_ROOT/results/m1/M1_PASS"
test ! -f "$RUN_ROOT/state/STOP_BEFORE_NEXT_STAGE"

BUILD="$RUN_ROOT/build/PipeANN-clean"
INPUT="$RUN_ROOT/input/m2_smoke"
INDEX_DIR="$RUN_ROOT/index/m2_smoke"
RESULT="$RUN_ROOT/results/m2"
PREFIX="$INDEX_DIR/sift1m_all_role0"
mkdir -p "$INPUT" "$INDEX_DIR" "$RESULT"

python3 "$HARNESS_ROOT/runner/m2_prepare_smoke.py" \
  --data "$DATASET_ROOT/full.bin" \
  --query "$DATASET_ROOT/query.bin" \
  --index-prefix "$PREFIX" \
  --output-dir "$INPUT"

sha256sum "$INPUT"/* > "$RESULT/generated_input_sha256.txt"

"$BUILD/tests/build_disk_index_filtered" \
  float "$DATASET_ROOT/full.bin" "$PREFIX" \
  64 64 96 32 8 8 l2 pq \
  label_spmat "$INPUT/base_all_role0.spmat"

sha256sum "$PREFIX"* > "$RESULT/index_sha256.txt"

"$BUILD/tests/search_disk_index_filtered" \
  float "$PREFIX" 1 32 \
  "$INPUT/query_16.bin" "$INPUT/groundtruth_16.bin" \
  10 l2 pq "$INPUT/filter_all_role0.json" 0 10 20 40 \
  > "$RESULT/search_stdout.txt" 2> "$RESULT/search_stderr.txt"

grep -q 'Recall@10' "$RESULT/search_stdout.txt"
grep -q 'Loaded filter from' "$RESULT/search_stderr.txt"

du -sb "$INPUT" "$INDEX_DIR" "$RESULT" > "$RESULT/space_breakdown.txt"
df -B1 "$RUN_ROOT" > "$RESULT/df_after.txt"
echo PASS > "$RESULT/M2_PASS"
