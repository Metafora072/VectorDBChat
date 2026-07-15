#!/usr/bin/env bash
# W1 DGAI execution entrypoint; intentionally inert until separately authorized.
set -euo pipefail
[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing DGAI update' >&2; exit 64; }
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; run=${W1_RUN_NAME:-pilot3_sift10m_w1}; attempt=${W1_ATTEMPT:-dgai-01}
work="$root/formal/$run/DGAI/$attempt"; result="$root/results/$run/DGAI/$attempt"; cp01="$root/datasets/sift10m/w1_cp01"; driver="$root/build/DGAI/tests/w1_canary"
[[ -x "$driver" && -f "$cp01/replace_cp01_80k.bin" && -f "$cp01/trace_validation.json" ]] || { echo 'missing reviewed DGAI W1 artifact or prepared CP01 inputs' >&2; exit 1; }
"$chat/w1_clone_base.sh" DGAI "$work"
mkdir -p "$result"; "$chat/resource_probe.py" --output "$result/resources.json" --interval-ms 100 --space-root "$work" -- \
  env ATLAS_TRACE_BIN="$cp01/replace_cp01_80k.bin" ATLAS_W1_MARKERS="$result/markers.jsonl" ATLAS_W1_PROBES="$cp01/visibility_probes.bin" \
  "$driver" float "$root/datasets/sift10m/full_10m.bin" 75 "$work/index/index" "$root/datasets/sift10m/query.bin" "$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00" 10 16 1 0 2 23
"$chat/w1_dump_active_tags.py" --tags "$work/index/index_disk.index.tags" --expected "$cp01/active_cp01.tags.bin" --output "$result/active_audit.json"
"$chat/w1_visibility_probe.py" --probes "$cp01/visibility_probes.json" --result-tags "$result/probe_result_tags.bin" --active-tags "$cp01/active_cp01.tags.bin" --output "$result/visibility_probe.json"
before=$(awk -F'\t' '{s+=$2} END{print s+0}' "$work/base_before.tsv"); after=$(du -sb "$work/index" | awk '{print $1}')
"$chat/w1_collect_canary.py" --system DGAI --markers "$result/markers.jsonl" --resources "$result/resources.json" --active-audit "$result/active_audit.json" --probe "$result/visibility_probe.json" --logical-payload-bytes 40960000 --index-before-bytes "$before" --index-after-bytes "$after" --output "$result/canary.json"
