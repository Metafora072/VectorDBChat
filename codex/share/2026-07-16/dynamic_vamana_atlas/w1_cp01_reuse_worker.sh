#!/usr/bin/env bash
# Revalidate the frozen trace and audit CP01 without modifying the preserved directory.
set -euo pipefail
[[ ${W1_RECOVERY_AUTHORIZED:-0} == 1 && $# == 4 ]] || { echo "usage: $0 ROOT PARENT_EXECUTION OUTPUT_DIR OLD_CHAT" >&2; exit 64; }
root=$(realpath "$1"); parent=$(realpath "$2"); out=$(realpath -m "$3"); old=$(realpath "$4")
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cp01="$root/datasets/sift10m/w1_cp01"
mkdir -p "$out"
python3 "$old/w1_validate_cp01_trace.py" --initial-active-tags "$root/datasets/sift10m/active_cp00.tags.bin" --work-dir "$cp01" --output "$out/trace_revalidation.json"
python3 "$new/w1_cp01_reuse_audit.py" --root "$root" --cp01 "$cp01" --parent-execution "$parent" \
  --trace-revalidation "$out/trace_revalidation.json" --output "$out/cp01_reuse_validation.json"
