#!/usr/bin/env bash
# Shared updater plus fresh-process visibility worker, always sampled as one process tree.
set -euo pipefail
[[ $# == 8 ]] || { echo "usage: $0 SYSTEM DRIVER DATA PREFIX TRACE PROBES MARKERS FRESH_RESULT" >&2; exit 2; }
system=$1; driver=$2; data=$3; prefix=$4; trace=$5; probes=$6; markers=$7; fresh=$8
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
case "$system" in
 DGAI) ATLAS_W1_MARKERS="$markers" "$driver" run "$data" "$prefix" "$trace";;
 OdinANN) ATLAS_W1_MARKERS="$markers" "$driver" run "$data" "$prefix" "$trace" "$probes" "$(dirname "$fresh")/online.bin";;
 *) exit 2;;
esac
python3 "$chat/w1_marker.py" --output "$markers" --name fresh_process_probe_begin
"$driver" probe "$prefix" "$probes" "$fresh"
python3 "$chat/w1_marker.py" --output "$markers" --name fresh_process_visibility_verified
