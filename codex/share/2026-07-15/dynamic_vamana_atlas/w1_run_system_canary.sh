#!/usr/bin/env bash
# Shared W1 state machine.  Micro and formal modes differ only in supplied artifacts and repeat count.
set -euo pipefail
[[ ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'formal-path gate not granted' >&2; exit 64; }
[[ ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || { echo 'global W1 lock is not held' >&2; exit 64; }

usage() { echo "usage: $0 --system S --mode micro|formal --dataset-dir D --full-corpus F --base-index B --trace T --expected-active-tags A --probe-queries P --probe-spec J --cp0-query Q0 --cp0-gt G0 --cp1-query Q1 --cp1-gt G1 --attempt-dir W --result-dir R --replacements N --pre-ls L --post-ls L --driver X --query-binary X --artifact-manifest M" >&2; exit 2; }
declare -A v=()
while (($#)); do
  case "$1" in
    --system|--mode|--dataset-dir|--full-corpus|--base-index|--trace|--expected-active-tags|--probe-queries|--probe-spec|--cp0-query|--cp0-gt|--cp1-query|--cp1-gt|--attempt-dir|--result-dir|--replacements|--pre-ls|--post-ls|--driver|--query-binary|--artifact-manifest) v[${1#--}]=$2; shift 2;;
    *) usage;;
  esac
done
for k in system mode dataset-dir full-corpus base-index trace expected-active-tags probe-queries probe-spec cp0-query cp0-gt cp1-query cp1-gt attempt-dir result-dir replacements pre-ls post-ls driver query-binary artifact-manifest; do [[ -n ${v[$k]:-} ]] || usage; done
[[ ${v[system]} == DGAI || ${v[system]} == OdinANN ]] || usage
[[ ${v[mode]} == micro || ${v[mode]} == formal ]] || usage

chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
nvme=${ATLAS_NVME_MAJMIN:-259:10}
work=$(realpath -m "${v[attempt-dir]}"); result=$(realpath -m "${v[result-dir]}")
base=$(realpath "${v[base-index]}")
[[ ! -e "$work" && ! -e "$result" ]] || { echo 'attempt/result reuse refused' >&2; exit 1; }
mkdir -p "$(dirname "$work")" "$(dirname "$result")"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$nvme" && $(findmnt -rn -T "$(dirname "$work")" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$nvme" && $(findmnt -rn -T "$base" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$nvme" ]] || { echo 'root/base/attempt not on experiment NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
[[ -x ${v[driver]} && -x ${v[query-binary]} ]] || { echo 'missing frozen driver/query binary' >&2; exit 1; }
for f in "${v[full-corpus]}" "${v[trace]}" "${v[expected-active-tags]}" "${v[probe-queries]}" "${v[probe-spec]}" "${v[cp0-query]}" "${v[cp0-gt]}" "${v[cp1-query]}" "${v[cp1-gt]}" "${v[artifact-manifest]}"; do [[ -f "$f" ]] || { echo "missing required artifact: $f" >&2; exit 1; }; done
python3 "$chat/w1_verify_artifacts.py" --manifest "${v[artifact-manifest]}" --system "${v[system]}" --driver "${v[driver]}" --query-binary "${v[query-binary]}" >/dev/null
"$chat/w1_clone_base.sh" "${v[system]}" "$base" "$work"
mkdir -p "$result"
prefix="$work/index/index"; markers="$result/markers.jsonl"
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8

query_point() {
  local phase=$1 query=$2 gt=$3 active=$4 l=$5 rep=$6
  local out="$result/${phase}_L${l}_r${rep}"
  local ids="$out.result_ids.bin" log="$out.log"
  "$chat/resource_probe.py" --output "$out.resources.json" --interval-ms 25 --space-root "$work/index" -- \
    "$chat/w1_query_worker.sh" "${v[system]}" "${v[query-binary]}" "$prefix" "$query" "$gt" "$ids" "$log" "$l" "$active"
}

# Both the automated replay and formal execution exercise the exact three-run
# pre-update gate.  Post-update points use the same repeat count.
repeats=3
IFS=, read -r -a pre_ls <<<"${v[pre-ls]}"; IFS=, read -r -a post_ls <<<"${v[post-ls]}"
for l in "${pre_ls[@]}"; do for ((r=1;r<=repeats;r++)); do query_point pre_cp00 "${v[cp0-query]}" "${v[cp0-gt]}" "$work/index/index_disk.index.tags" "$l" "$r"; done; done
python3 "$chat/w1_preupdate_gate.py" --system "${v[system]}" --mode "${v[mode]}" --result-dir "$result" \
  --binary "${v[query-binary]}" --index-manifest "$work/base_before.tsv" --query "${v[cp0-query]}" \
  --gt "${v[cp0-gt]}" --active-tags "$work/index/index_disk.index.tags" --ls "${v[pre-ls]}" \
  --device "$nvme" --output "$result/preupdate_gate.json"

data_file=$(realpath "${v[full-corpus]}")
python3 - "$work/attempt_artifacts.json" "$data_file" "${v[trace]}" "${v[expected-active-tags]}" "${v[probe-queries]}" "${v[probe-spec]}" <<'PY'
import hashlib,json,sys
from pathlib import Path
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
out=Path(sys.argv[1]); names=('full_corpus','trace','expected_active_tags','probe_queries','probe_spec')
paths=[Path(x).resolve() for x in sys.argv[2:]]
out.write_text(json.dumps({'schema':'dynamic-vamana-w1-attempt-artifacts-v1','artifacts':{n:{'realpath':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)} for n,p in zip(names,paths)}},indent=2)+'\n')
PY
"$chat/resource_probe.py" --output "$result/resources.json" --interval-ms 25 --space-root "$work" --space-interval-seconds 1 -- \
  "$chat/w1_system_worker.sh" "${v[system]}" "${v[driver]}" "$data_file" "$prefix" "${v[trace]}" "${v[probe-queries]}" "$markers" "$result/fresh.bin"
"$chat/w1_dump_active_tags.py" --tags "$work/index/index_disk.index.tags" --expected "${v[expected-active-tags]}" --expected-count "$(python3 -c 'import struct,sys; print(struct.unpack("<I",open(sys.argv[1],"rb").read(4))[0])' "${v[expected-active-tags]}")" --output "$result/active_audit.json"
"$chat/w1_visibility_probe.py" --probes "${v[probe-spec]}" --result-tags "$result/fresh.bin" --active-tags "${v[expected-active-tags]}" --output "$result/fresh_probe.json"
if [[ ${v[system]} == OdinANN ]]; then "$chat/w1_visibility_probe.py" --probes "${v[probe-spec]}" --result-tags "$result/online.bin" --active-tags "${v[expected-active-tags]}" --output "$result/online_probe.json"; fi
for l in "${post_ls[@]}"; do for ((r=1;r<=repeats;r++)); do query_point post_cp01 "${v[cp1-query]}" "${v[cp1-gt]}" "${v[expected-active-tags]}" "$l" "$r"; done; done
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$result/base_after_attempt.tsv"
cmp -s "$work/base_before.tsv" "$result/base_after_attempt.tsv" || { echo 'immutable base changed during attempt' >&2; exit 1; }
before=$(du -sb "$base" | awk '{print $1}'); after=$(du -sb "$work/index" | awk '{print $1}')
"$chat/w1_collect_canary.py" --system "${v[system]}" --markers "$markers" --resources "$result/resources.json" --active-audit "$result/active_audit.json" --probe "$result/fresh_probe.json" --logical-replacements "${v[replacements]}" --logical-payload-bytes "$(( ${v[replacements]} * 128 * 4 ))" --index-before-bytes "$before" --index-after-bytes "$after" --output "$result/canary.json"
touch "$result/FORMAL_W1_CANARY_OK"
