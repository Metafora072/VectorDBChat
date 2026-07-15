#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB
DATA="$ROOT/data/VectorDB"
POINT="$ROOT/chat/codex/share/run_concurrent_query_update_p0_point.sh"
SOURCE="$DATA/indexes/insert_cost_scale_substage/sift-128-euclidean/R64_900k_source"
WORK="$DATA/p0_interference/work/dgai_formal"
OUT="$DATA/p0_interference/formal"
ODIN_INDEX="$DATA/oracle_gate/index/odin_sift900k/index"
DURATION=10

mkdir -p "$WORK" "$OUT"
DQ=(400 1000 1800)
OQ=(900 2400 4000)
DU=(2 5 10)
OU=(20 80 140)

run_dgai() {
  local q="$1" u="$2" rep="$3"
  local run="$OUT/dgai_q${q}_u${u}_rep${rep}"
  if [ -s "$run/exit_status" ] && [ "$(cat "$run/exit_status")" = 0 ]; then return; fi
  if [ "$u" != 0 ]; then cp -a "$SOURCE"/. "$WORK"/; fi
  local prefix="$WORK/index"
  if [ "$u" = 0 ]; then prefix="$DATA/p0_interference/work/dgai_queryonly/index"; fi
  "$POINT" DGAI "$run" "$prefix" "$q" "$u" 8 1 "$DURATION"
}

run_odin() {
  local q="$1" u="$2" rep="$3"
  local run="$OUT/odin_q${q}_u${u}_rep${rep}"
  if [ -s "$run/exit_status" ] && [ "$(cat "$run/exit_status")" = 0 ]; then return; fi
  "$POINT" OdinANN "$run" "$ODIN_INDEX" "$q" "$u" 8 1 "$DURATION"
}

for rep in 0 1 2; do
  for qi in 0 1 2; do
    # Rotate update order across repetitions to reduce order bias.
    for offset in 0 1 2 3; do
      ui=$(((offset + rep) % 4))
      if [ "$ui" = 0 ]; then du=0; ou=0; else du="${DU[$((ui - 1))]}"; ou="${OU[$((ui - 1))]}"; fi
      run_dgai "${DQ[$qi]}" "$du" "$rep"
      run_odin "${OQ[$qi]}" "$ou" "$rep"
    done
  done
  for ui in 0 1 2; do
    run_dgai 0 "${DU[$ui]}" "$rep"
    run_odin 0 "${OU[$ui]}" "$rep"
  done
done
