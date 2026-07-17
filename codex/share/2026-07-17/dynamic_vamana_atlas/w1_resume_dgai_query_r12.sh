#!/usr/bin/env bash
# Resume only the never-started DGAI CP10 query/freeze after unit-name rejection.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_CP10_R12_CONTINUATION_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || exit 64
(( EUID == 0 )) || exit 1
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
r02=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas
result="$root/results/pilot3_sift10m_w1_cp10_trajectory_r12/DGAI/trajectory-cp10-12"
work="$root/formal/pilot3_sift10m_w1_cp10_trajectory_r12/DGAI/trajectory-cp10-12"
stage="$result/stages/cp10"; checkpoint="$result/checkpoints/cp10"; qdir="$result/queries/cp10"
manifest="$root/results/pilot3_sift10m_w1_cp10_trajectory_r12/execution_manifest.json"
dataset="$root/datasets/sift10m"; query="$dataset/query.bin"; active="$dataset/w1_trajectory/cp10/active_cp10.tags.bin"
gt="$root/groundtruth/sift10m/w1_trajectory/cp10/gt_cp10"; artifact="$old/artifact_rebuild_manifest.json"
driver="$root/build/w1-canonical-v6/install/DGAI/w1_canary"; binary="$root/build/w1-canonical-v6/install/DGAI/search_disk_index"
evidence="$new/w1_cp10_evidence_r12.py"; device=${ATLAS_NVME_MAJMIN:-259:10}
python3 - "$manifest" "$stage/stage_evidence.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2]))
if (m.get('status'),m.get('phase'),m.get('exit_code'))!=('stopped_failed','cp10_DGAI',1): raise SystemExit('R12 stop identity mismatch')
if s.get('status')!='pass' or (s.get('delta_start'),s.get('delta_count'))!=(400000,400000): raise SystemExit('DGAI stage not accepted')
PY
[[ -f $stage/STAGE_WORKER_OK && -f $checkpoint/cp10_state_content_manifest.tsv && -f $checkpoint/cp10_state_mode_manifest.tsv ]] || exit 1
[[ -d $qdir && -z $(find "$qdir" -mindepth 1 -maxdepth 1 -print -quit) ]] || { echo 'DGAI query outputs are not fresh' >&2; exit 1; }
python3 "$old/w1_file_manifest.py" --root "$work/index" --output "$result/pre_resume_content.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$work/index" --output "$result/pre_resume_mode.tsv"
cmp -s "$checkpoint/cp10_state_content_manifest.tsv" "$result/pre_resume_content.tsv" || { echo 'DGAI index changed after stage stop' >&2; exit 1; }
cmp -s "$checkpoint/cp10_state_mode_manifest.tsv" "$result/pre_resume_mode.tsv" || { echo 'DGAI modes changed after stage stop' >&2; exit 1; }
for l in 64 128; do for rep in 1 2 3; do
  stem="$qdir/cp10_L${l}_r${rep}"; unit="dv-w1-cum-r03-r12-dgai-l${l}-r${rep}"
  W1_CP05_R03_CUMULATIVE_AUTHORIZED=1 "$new/w1_run_query_scope.sh" --unit "$unit" --system DGAI \
    --index-root "$work/index" --query-binary "$binary" --query "$query" --gt "$gt" --active-tags "$active" \
    --stem "$stem" --l-value "$l" --memory-max 24G --resource-probe "$old/resource_probe.py" \
    --query-worker "$old/w1_query_worker.sh" --device "$device"
done; done
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" query-gate --mode formal --system DGAI \
  --checkpoint cp10 --result-dir "$qdir" --prefix cp10 --binary "$binary" --driver "$driver" --artifact-manifest "$artifact" \
  --index-content-manifest "$checkpoint/cp10_state_content_manifest.tsv" --query "$query" --gt "$gt" --active-tags "$active" \
  --ls 64,128 --repeats 1,2,3 --threads 1 --io-engine aio --device "$device" --expected-nq 10000 --expected-k 10 \
  --expected-active-count 8000000 --output "$qdir/query_gate.json"
python3 "$old/w1_file_manifest.py" --root "$work/index" --output "$result/index_content_after_query.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$work/index" --output "$result/index_mode_after_query.tsv"
cmp -s "$checkpoint/cp10_state_content_manifest.tsv" "$result/index_content_after_query.tsv" || exit 1
cmp -s "$checkpoint/cp10_state_mode_manifest.tsv" "$result/index_mode_after_query.tsv" || exit 1
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" checkpoint --mode formal --system DGAI --checkpoint cp10 \
  --attempt-dir "$work" --index-root "$work/index" --stage-evidence "$stage/stage_evidence.json" --query-gate "$qdir/query_gate.json" \
  --state-content-manifest "$checkpoint/cp10_state_content_manifest.tsv" --state-mode-manifest "$checkpoint/cp10_state_mode_manifest.tsv" \
  --base-content-manifest "$work/base_content_before.tsv" --base-mode-manifest "$work/base_mode_before.tsv" --output-dir "$checkpoint"
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" freeze --mode formal --system DGAI --attempt-dir "$work" \
  --index-root "$work/index" --owner ubuntu --checkpoint-evidence "$checkpoint/cp10_checkpoint_evidence.json" --output-dir "$checkpoint"
touch "$result/CP10_TRAJECTORY_OK"
