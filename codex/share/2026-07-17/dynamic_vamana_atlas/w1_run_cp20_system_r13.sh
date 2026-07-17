#!/usr/bin/env bash
# Run one formal CP10->CP20 continuation from an R12 frozen clone.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_CP20_R13_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || {
  echo 'R13 authorization/global lock absent' >&2; exit 64;
}
(( EUID == 0 )) || { echo 'R13 system runner must run as root' >&2; exit 1; }
[[ $# == 6 ]] || { echo "usage: $0 SYSTEM BASE_INDEX FREEZE_EVIDENCE DRIVER QUERY_BINARY LS" >&2; exit 2; }

system=$1; base=$(realpath "$2"); freeze=$(realpath "$3"); driver=$(realpath "$4"); query_binary=$(realpath "$5"); ls_csv=$6
[[ $system == DGAI || $system == OdinANN ]] || exit 2
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
r02=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas
run=pilot3_sift10m_w1_cp20_trajectory_r13; attempt=trajectory-cp20-13
work="$root/formal/$run/$system/$attempt"
result="$root/results/$run/$system/$attempt"
input="$root/results/$run/inputs/cp10_to_cp20"
dataset="$root/datasets/sift10m"; trajectory="$dataset/w1_trajectory"
full="$dataset/full_10m.bin"; query="$dataset/query.bin"
gt="$root/groundtruth/sift10m/w1_trajectory/cp20/gt_cp20"
before_active="$trajectory/cp10/active_cp10.tags.bin"
after_active="$trajectory/cp20/active_cp20.tags.bin"
trace="$input/delta_cp10_to_cp20.bin"; delta_manifest="$input/delta_manifest.json"
local_bin="$input/delta_visibility_probes.bin"; local_spec="$input/delta_visibility_probes.json"
combined_bin="$input/combined_visibility_probes.bin"; combined_spec="$input/combined_visibility_probes.json"
global_spec="$trajectory/cp20/visibility_probes.json"
artifact="$old/artifact_rebuild_manifest.json"; evidence="$new/w1_cp20_evidence_r13.py"
device=${ATLAS_NVME_MAJMIN:-259:10}; system_lower=${system,,}

expected_base=$(python3 - "$freeze" "$system" <<'PY'
import json,sys
from pathlib import Path
d=json.load(open(sys.argv[1]))
if d.get('status')!='pass' or d.get('system')!=sys.argv[2] or d.get('checkpoint')!='cp10':
 raise SystemExit('R12 freeze evidence mismatch')
print(Path(d['root_realpath']).resolve())
PY
)
[[ $base == "$expected_base" && ! -e $work && ! -e $result ]] || { echo 'R13 base/target capability mismatch' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'R13 root is not project NVMe' >&2; exit 1; }
for file in "$driver" "$query_binary" "$full" "$query" "$gt" "$before_active" "$after_active" "$trace" "$delta_manifest" "$local_bin" "$local_spec" "$combined_bin" "$combined_spec" "$global_spec"; do
  [[ -f $file ]] || { echo "missing R13 input: $file" >&2; exit 1; }
done

install -d -o ubuntu -g ubuntu "$(dirname "$work")" "$(dirname "$result")"
export W1_FORMAL_PATH_AUTHORIZED=1 W1_CLONE_PREFLIGHT_ONLY=0 W1_MUTABLE_CLONE_OWNER=ubuntu
export W1_ALLOWED_CLONE_TARGET="$work" W1_ALLOWED_CLONE_SYSTEM="$system"
export W1_ALLOWED_CLONE_RUN="$run" W1_ALLOWED_CLONE_ATTEMPT="$attempt"
export ATLAS_W1_MUTABLE_CHAT="$r02"
"$old/w1_clone_base.sh" "$system" "$base" "$work"
install -d -m 0700 -o ubuntu -g ubuntu "$result" "$result/stages" "$result/queries" "$result/checkpoints"

python3 "$old/w1_file_manifest.py" --root "$base" --output "$result/base_content_after_clone.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$result/base_mode_after_clone.tsv"
cmp -s "$work/base_content_before.tsv" "$result/base_content_after_clone.tsv" || { echo 'R12 frozen base content changed during clone' >&2; exit 1; }
cmp -s "$work/base_mode_before.tsv" "$result/base_mode_after_clone.tsv" || { echo 'R12 frozen base mode changed during clone' >&2; exit 1; }

stage="$result/stages/cp20"; canary="$stage/input_canary"
install -d -m 0700 -o ubuntu -g ubuntu "$stage" "$canary"
touch "$canary/canary.log"; chown ubuntu:ubuntu "$canary/canary.log"; chmod 0600 "$canary/canary.log"
canary_unit="dv-w1-cp20-r13-${system_lower}-input-canary"
systemd-run --wait --collect --pipe --unit "$canary_unit" --uid ubuntu --property=Type=exec \
  --property="InaccessiblePaths=$trajectory/master_replacements_1600k.bin" \
  --property="InaccessiblePaths=$trajectory/cp10/replace_cp10.bin" \
  --property="InaccessiblePaths=$trajectory/cp20/replace_cp20.bin" \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
  python3 "$new/w1_input_canary.py" --allowed "$trace" \
    --denied "$trajectory/master_replacements_1600k.bin" \
    --denied "$trajectory/cp10/replace_cp10.bin" --denied "$trajectory/cp20/replace_cp20.bin" \
    --output "$canary/canary.json" >>"$canary/canary.log" 2>&1
chmod 0444 "$canary/canary.json" "$canary/canary.log"

libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
resource="$result/cp20_stage_resources.json"; primer="$result/cp20_stage_io_primer.json"
unit="dv-w1-cp20-r13-${system_lower}-update"
systemd-run --wait --collect --pipe --unit "$unit" --uid ubuntu --property=Type=exec \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
  --property=IOAccounting=yes --property=MemoryMax=32G --property=LimitCORE=0 --property=RuntimeMaxSec=5400 \
  --property="InaccessiblePaths=$trajectory/master_replacements_1600k.bin" \
  --property="InaccessiblePaths=$trajectory/cp10/replace_cp10.bin" \
  --property="InaccessiblePaths=$trajectory/cp20/replace_cp20.bin" \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH="$libs" \
    W1_CUMULATIVE_STAGE_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 W1_ALLOWED_CLONE_TARGET="$work" \
    W1_CUMULATIVE_RESULT_ROOT="$result" ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device" \
  numactl --physcpubind=0-23 --membind=0 timeout --signal=TERM --kill-after=30s 75m \
  python3 "$new/w1_stage_io_primer.py" --index-root "$work/index" --device "$device" \
    --primer-report "$primer" --resources "$resource" --resource-probe "$old/resource_probe.py" --space-root "$work/index" -- \
  "$new/w1_cp20_stage_worker_r13.sh" --mode formal --system "$system" --stage cp20 \
    --attempt-dir "$work" --full-corpus "$full" --driver "$driver" --trace "$trace" \
    --delta-manifest "$delta_manifest" --expected-count 800000 --delta-start 800000 \
    --forbidden-paths "$trajectory/master_replacements_1600k.bin,$trajectory/cp10/replace_cp10.bin,$trajectory/cp20/replace_cp20.bin" \
    --expected-before-tags "$before_active" --expected-after-tags "$after_active" \
    --combined-probes "$combined_bin" --combined-probe-spec "$combined_spec" \
    --local-probe-spec "$local_spec" --global-probe-spec "$global_spec" \
    --result-dir "$stage" --expected-scope "$unit.service" --old-tools "$old" --new-tools "$new" \
    >>"$result/cp20_controller.log" 2>&1
[[ -f $stage/STAGE_WORKER_OK ]] || { echo 'R13 stage worker marker absent' >&2; exit 1; }

read -r before_bytes after_bytes < <(python3 - "$resource" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); samples=d['samples']
last=next(x['index_space'] for x in reversed(samples) if x.get('index_space'))
print(d['space_before']['apparent_bytes'],last['apparent_bytes'])
PY
)
python3 "$old/w1_collect_canary.py" --system "$system" --markers "$stage/markers.jsonl" \
  --resources "$resource" --active-audit "$stage/active_audit.json" --probe "$stage/fresh_probe.json" \
  --logical-replacements 800000 --logical-payload-bytes $((800000 * 128 * 4)) \
  --index-before-bytes "$before_bytes" --index-after-bytes "$after_bytes" --device "$device" \
  --output "$stage/legacy_canary.json"
stage_args=(runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" stage-evidence
  --mode formal --system "$system" --checkpoint cp20 --attempt-dir "$work" --index-root "$work/index"
  --stage-result "$stage" --stage-resources "$resource" --trace "$trace" --delta-manifest "$delta_manifest"
  --expected-active "$after_active" --local-probe-spec "$local_spec" --global-probe-spec "$global_spec"
  --combined-probe-spec "$combined_spec" --fresh-result "$stage/fresh.bin" --controller-log "$result/cp20_controller.log"
  --input-capability-canary "$canary/canary.json" --device "$device" --output "$stage/stage_evidence.json")
[[ $system == OdinANN ]] && stage_args+=(--online-result "$stage/online.bin")
"${stage_args[@]}"

checkpoint="$result/checkpoints/cp20"; qdir="$result/queries/cp20"
install -d -o ubuntu -g ubuntu "$checkpoint" "$qdir"
python3 "$old/w1_file_manifest.py" --root "$work/index" --output "$checkpoint/cp20_state_content_manifest.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$work/index" --output "$checkpoint/cp20_state_mode_manifest.tsv"
IFS=, read -r -a l_values <<<"$ls_csv"
for l in "${l_values[@]}"; do
  for rep in 1 2 3; do
    stem="$qdir/cp20_L${l}_r${rep}"; qunit="dv-w1-cum-r03-r13-${system_lower}-l${l}-r${rep}"
    W1_CP10_R03_CUMULATIVE_AUTHORIZED=1 "$new/w1_run_query_scope.sh" --unit "$qunit" --system "$system" \
      --index-root "$work/index" --query-binary "$query_binary" --query "$query" --gt "$gt" \
      --active-tags "$after_active" --stem "$stem" --l-value "$l" --memory-max 24G \
      --resource-probe "$old/resource_probe.py" --query-worker "$old/w1_query_worker.sh" --device "$device"
  done
done
io_engine=aio; [[ $system == OdinANN ]] && io_engine=uring
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" query-gate \
  --mode formal --system "$system" --checkpoint cp20 --result-dir "$qdir" --prefix cp20 \
  --binary "$query_binary" --driver "$driver" --artifact-manifest "$artifact" \
  --index-content-manifest "$checkpoint/cp20_state_content_manifest.tsv" --query "$query" --gt "$gt" \
  --active-tags "$after_active" --ls "$ls_csv" --repeats 1,2,3 --threads 1 --io-engine "$io_engine" \
  --device "$device" --expected-nq 10000 --expected-k 10 --expected-active-count 8000000 \
  --output "$qdir/query_gate.json"
python3 "$old/w1_file_manifest.py" --root "$work/index" --output "$result/index_content_after_query.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$work/index" --output "$result/index_mode_after_query.tsv"
cmp -s "$checkpoint/cp20_state_content_manifest.tsv" "$result/index_content_after_query.tsv" || { echo 'CP20 query changed index content' >&2; exit 1; }
cmp -s "$checkpoint/cp20_state_mode_manifest.tsv" "$result/index_mode_after_query.tsv" || { echo 'CP20 query changed index mode' >&2; exit 1; }

runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" checkpoint \
  --mode formal --system "$system" --checkpoint cp20 --attempt-dir "$work" --index-root "$work/index" \
  --stage-evidence "$stage/stage_evidence.json" --query-gate "$qdir/query_gate.json" \
  --state-content-manifest "$checkpoint/cp20_state_content_manifest.tsv" \
  --state-mode-manifest "$checkpoint/cp20_state_mode_manifest.tsv" \
  --base-content-manifest "$work/base_content_before.tsv" --base-mode-manifest "$work/base_mode_before.tsv" \
  --output-dir "$checkpoint"
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" freeze --mode formal --system "$system" \
  --attempt-dir "$work" --index-root "$work/index" --owner ubuntu \
  --checkpoint-evidence "$checkpoint/cp20_checkpoint_evidence.json" --output-dir "$checkpoint"
[[ -f $work/IMMUTABLE_TRAJECTORY_CP20_OK && -f $checkpoint/cp20_freeze_evidence.json ]] || { echo 'R13 freeze evidence absent' >&2; exit 1; }
touch "$result/CP20_TRAJECTORY_OK"
