#!/usr/bin/env bash
# Execute one fixed-policy dynamic-system query and preserve the returned IDs.
set -euo pipefail
[[ $# == 9 ]] || { echo "usage: $0 SYSTEM BINARY PREFIX QUERY GT IDS LOG L ACTIVE_TAGS" >&2; exit 2; }
system=$1; binary=$2; prefix=$3; query=$4; gt=$5; ids=$6; log=$7; l=$8; active=$9
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$(dirname "$ids")"
case "$system" in
  DGAI) ATLAS_RESULT_IDS_PATH="$ids" ATLAS_QUERY_METRICS_PATH="${ids%.result_ids.bin}.metrics.json" "$binary" float "$prefix" 1 16 "$query" "$gt" 10 l2 2 0 23 "$l" >"$log" 2>&1 ;;
  OdinANN) ATLAS_RESULT_IDS_PATH="$ids" ATLAS_QUERY_METRICS_PATH="${ids%.result_ids.bin}.metrics.json" "$binary" float "$prefix" 1 16 "$query" "$gt" 10 l2 pq 2 0 "$l" >"$log" 2>&1 ;;
  *) echo "unknown system: $system" >&2; exit 2 ;;
esac
python3 "$chat/validate_query_result.py" --result "$ids" --active-tags "$active" --query "$query" --log "$log" --output "${ids%.result_ids.bin}.validation.json"
