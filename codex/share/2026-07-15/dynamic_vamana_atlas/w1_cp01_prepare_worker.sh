#!/usr/bin/env bash
# Ordered CP01 preparation: trace -> validation -> vector materialization.
set -euo pipefail
[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 ]] || { echo 'W1 execution gate absent' >&2; exit 64; }
[[ $# == 2 ]] || { echo "usage: $0 DATASET OUTPUT" >&2; exit 2; }
dataset=$1; out=$2
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
python3 "$chat/w1_prepare_cp01_trace.py" --authorized --dataset "$dataset" --output-dir "$out" --count 80000
python3 "$chat/w1_validate_cp01_trace.py" --initial-active-tags "$dataset/active_cp00.tags.bin" --work-dir "$out" --output "$out/trace_validation.json"
python3 "$chat/w1_materialize_cp01.py" --authorized --dataset "$dataset" --work-dir "$out"
