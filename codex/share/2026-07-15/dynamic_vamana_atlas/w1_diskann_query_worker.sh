#!/usr/bin/env bash
set -euo pipefail
[[ $# == 7 ]] || { echo "usage: $0 BINARY PREFIX QUERY GT RESULT_PREFIX L LOG" >&2; exit 2; }
binary=$1; prefix=$2; query=$3; gt=$4; result=$5; l=$6; log=$7
"$binary" --data_type float --dist_fn l2 --index_path_prefix "$prefix" --result_path "$result" \
  --query_file "$query" --gt_file "$gt" -K 10 -L "$l" -T 1 -W 4 >"$log" 2>&1
