#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 8 ]; then
  echo "usage: $0 <system> <run_dir> <index_prefix> <query_qps> <update_qps> <qthreads> <uthreads> <duration>" >&2
  exit 2
fi

SYSTEM="$1"
RUN_DIR="$2"
INDEX_PREFIX="$3"
QUERY_QPS="$4"
UPDATE_QPS="$5"
QTHREADS="$6"
UTHREADS="$7"
DURATION="$8"
ROOT=/home/ubuntu/pz/VectorDB
DATA_ROOT="$ROOT/data/VectorDB"
mkdir -p "$RUN_DIR"

if [ "$SYSTEM" = "DGAI" ]; then
  BIN="$DATA_ROOT/p0_interference/build/DGAI/tests/vectordb_p0_open_loop"
  EXTRA=(--strategy 1 --search_mode 3)
else
  BIN="$DATA_ROOT/oracle_gate/build/PipeANN/tests/vectordb_p0_open_loop"
  EXTRA=()
fi

iostat -x -d -t nvme8n1 1 >"$RUN_DIR/iostat.txt" 2>&1 &
IOSTAT_PID=$!

taskset -c 0-27 "$BIN" \
  --index "$INDEX_PREFIX" \
  --data "$DATA_ROOT/datasets/real/sift-128-euclidean/full.bin" \
  --query "$DATA_ROOT/datasets/real/sift-128-euclidean/query.bin" \
  --truth "$DATA_ROOT/datasets/real/sift-128-euclidean/groundtruth.bin" \
  --output "$RUN_DIR" --run_id "$(basename "$RUN_DIR")" \
  --query_qps "$QUERY_QPS" --update_qps "$UPDATE_QPS" \
  --query_threads "$QTHREADS" --update_threads "$UTHREADS" \
  --warmup_sec 3 --duration_sec "$DURATION" --base_npts 900000 \
  --L 160 --R 64 --beam 4 "${EXTRA[@]}" >"$RUN_DIR/harness.log" 2>&1 &
HARNESS_PID=$!

pidstat -h -u -r -d -w -p "$HARNESS_PID" 1 >"$RUN_DIR/pidstat.txt" 2>&1 &
PIDSTAT_PID=$!
python3 "$ROOT/chat/codex/share/p0_wchan_monitor.py" "$HARNESS_PID" >"$RUN_DIR/wchan.csv" 2>"$RUN_DIR/wchan.err" &
WCHAN_PID=$!

set +e
wait "$HARNESS_PID"
STATUS=$?
set -e
kill "$IOSTAT_PID" "$PIDSTAT_PID" "$WCHAN_PID" 2>/dev/null || true
wait "$IOSTAT_PID" "$PIDSTAT_PID" "$WCHAN_PID" 2>/dev/null || true
echo "$STATUS" >"$RUN_DIR/exit_status"
exit "$STATUS"
