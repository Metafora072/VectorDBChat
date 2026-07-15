#!/usr/bin/env bash
# Authorized 1M/16-op infrastructure test.  Formal SIFT10M paths are rejected.
set -euo pipefail
[[ ${W1_MICRO_AUTHORIZED:-0} == 1 ]] || { echo 'micro-canary not authorized' >&2; exit 64; }
[[ $# == 1 && ( $1 == DGAI || $1 == OdinANN ) ]] || { echo "usage: $0 DGAI|OdinANN" >&2; exit 2; }
system=$1; root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); dataset="$root/datasets/sift1m"; attempt=${W1_MICRO_ATTEMPT:-attempt-01}; run="$root/formal/pilot3_w1_micro/$system/$attempt"; prep="$root/tmp/pilot3_w1_micro/$attempt"; lock="$root/locks/pilot3_w1_micro.lock"
mkdir -p "$(dirname "$lock")"; exec 9>"$lock"; flock -n 9 || { echo 'another W1 micro task holds the global lock' >&2; exit 1; }
[[ ! -e "$run" && ! -e "$prep" ]] || { echo 'micro attempt/prep already exists; refusing reuse' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN) == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'not experiment NVMe' >&2; exit 1; }
free=$(df -PB1 "$root" | awk 'NR==2{print $4}'); (( free >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
python3 "$chat/w1_micro_prepare.py" --authorized --dataset "$dataset" --output "$prep"
case "$system" in DGAI) base="$root/index/atlas1m/DGAI/sift1m";; OdinANN) base="$root/index/atlas1m/OdinANN/sift1m";; esac
mkdir -p "$(dirname "$run")"; tmp="${run}.partial.$$"; trap 'rm -rf "$tmp"' EXIT; mkdir "$tmp"; find "$base" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"$tmp/base_before.tsv"; cp -a --reflink=auto "$base/." "$tmp/index"; find "$base" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"$tmp/base_after_clone.tsv"; cmp -s "$tmp/base_before.tsv" "$tmp/base_after_clone.tsv" || { echo 'base changed during clone' >&2; exit 1; }; mv "$tmp" "$run"; trap - EXIT
"$chat/resource_probe.py" --output "$run/resources.json" --interval-ms 25 --space-root "$run" -- "$chat/w1_micro_worker.sh" "$system" "$run" "$dataset" "$prep" "$chat"
"$chat/w1_dump_active_tags.py" --tags "$run/index/index_disk.index.tags" --expected "$prep/active.tags.bin" --expected-count 800000 --output "$run/active_audit.json"
"$chat/w1_visibility_probe.py" --probes "$prep/probes.json" --result-tags "$run/fresh.bin" --active-tags "$prep/active.tags.bin" --output "$run/fresh_probe.json"
if [[ "$system" == OdinANN ]]; then "$chat/w1_visibility_probe.py" --probes "$prep/probes.json" --result-tags "$run/online.bin" --active-tags "$prep/active.tags.bin" --output "$run/online_probe.json"; fi
find "$base" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"$run/base_after_attempt.tsv"; cmp -s "$run/base_before.tsv" "$run/base_after_attempt.tsv" || { echo 'immutable base changed during micro canary' >&2; exit 1; }
before_bytes=$(du -sb "$base" | awk '{print $1}'); after_bytes=$(du -sb "$run/index" | awk '{print $1}')
"$chat/w1_collect_canary.py" --system "$system" --markers "$run/markers.jsonl" --resources "$run/resources.json" --active-audit "$run/active_audit.json" --probe "$run/fresh_probe.json" --logical-replacements 16 --logical-payload-bytes $((16 * 128 * 4)) --index-before-bytes "$before_bytes" --index-after-bytes "$after_bytes" --output "$run/collection.json"
touch "$run/MICRO_CANARY_OK"
