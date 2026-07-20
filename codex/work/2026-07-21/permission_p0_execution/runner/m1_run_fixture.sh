#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=${RUN_ROOT:?RUN_ROOT is required}
HARNESS_ROOT=${HARNESS_ROOT:?HARNESS_ROOT is required}

test -f "$RUN_ROOT/results/m0/M0_PASS"
test ! -f "$RUN_ROOT/state/STOP_BEFORE_NEXT_STAGE"

RESULT="$RUN_ROOT/results/m1"
mkdir -p "$RESULT"

(
  cd "$HARNESS_ROOT/m1_fixture"
  python3 -B -m unittest -v test_g0_fixture.py
) > "$RESULT/unittest_stdout.txt" 2> "$RESULT/unittest_stderr.txt"

python3 -B "$HARNESS_ROOT/m1_fixture/g0_fixture.py" --pretty \
  > "$RESULT/g0_six_cases.json"

python3 - "$RESULT/g0_six_cases.json" <<'PY'
import json
import sys

cases = json.load(open(sys.argv[1], encoding="utf-8"))
assert len(cases) == 6
assert {(x["strategy"], x["approximate_state"]) for x in cases} == {
    (strategy, state)
    for strategy in ("IN_FILTER", "PRE_FILTER", "POST_FILTER")
    for state in ("fresh", "stale")
}
assert all(x["termination_reason"] == "l_search_satisfied_after_exact_allow" for x in cases)
PY

sha256sum \
  "$HARNESS_ROOT/m1_fixture/g0_fixture.py" \
  "$HARNESS_ROOT/m1_fixture/test_g0_fixture.py" \
  "$RESULT/g0_six_cases.json" > "$RESULT/sha256.txt"
echo PASS > "$RESULT/M1_PASS"
