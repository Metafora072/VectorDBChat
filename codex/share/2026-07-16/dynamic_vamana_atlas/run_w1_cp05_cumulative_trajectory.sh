#!/usr/bin/env bash
# Fail-closed CP00->CP01->CP05 cumulative replay and formal execution.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ulimit -c 0
[[ ${W1_CP05_CUMULATIVE_AUTHORIZED:-0} == 1 ]] || { echo 'CP05 cumulative authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'CP05 cumulative launcher must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
artifact="$old/artifact_rebuild_manifest.json"
run=pilot3_sift10m_w1_cp05_trajectory
result="$root/results/$run"; formal="$root/formal/$run"
replay_run=pilot3_w1_cp05_trajectory_replay; replay_formal="$root/formal/$replay_run"
dataset="$root/datasets/sift10m"; trajectory="$dataset/w1_trajectory"; cp01="$dataset/w1_cp01"
delta="$trajectory/execution_deltas"; replay_inputs="$result/replay/inputs"
tmp="$root/tmp/$run"
report="$new/../dynamic_vamana_w1_cp05_cumulative_trajectory_results_0716.md"
manifest="$result/execution_manifest.json"; preflight="$result/preflight/execution_preflight.json"
canonical="$root/build/w1-canonical-v6/install"
runtime="$root/results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json"
query="$dataset/query.bin"; full="$dataset/full_10m.bin"
cp00gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"
cp01gt="$root/groundtruth/sift10m/w1_r02/gt_cp01"
cp05gt="$root/groundtruth/sift10m/w1_trajectory/cp05/gt_cp05"
phase=initializing; attempt_armed=0

notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$old/formal/notify_owner.sh" "$1" "$2" || true
}

stop_transient_units() {
  local unit
  while read -r unit; do
    [[ -n $unit ]] && systemctl stop "$unit" >/dev/null 2>&1 || true
  done < <(systemctl list-units --all --plain --no-legend 'dv-w1-cum-*' 'dv-w1-cp05-*' 2>/dev/null | awk '{print $1}')
}

on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    stop_transient_units
    if (( attempt_armed == 1 )) && [[ -f $manifest ]]; then
      python3 "$new/w1_cumulative_execution_manifest.py" stop --manifest "$manifest" \
        --phase "$phase" --exit-code "$rc" || true
      if [[ -f $preflight && ! -e $result/preflight/preservation_after_stop.json ]]; then
        python3 "$new/w1_cumulative_preservation.py" --preflight "$preflight" \
          --output "$result/preflight/preservation_after_stop.json" || true
      fi
    fi
    notify "Dynamic Vamana CP05 cumulative $phase failed" \
      "exit=$rc phase=$phase; fail-closed, no retry/continuation and CP10/CP20 remain HOLD"
  fi
}
trap on_exit EXIT

mkdir -p "$root/locks" "$tmp"
chmod 0770 "$tmp"; chown ubuntu:ubuntu "$tmp"
export TMPDIR="$tmp" TMP="$tmp" TEMP="$tmp"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global flock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$
if systemctl list-units --all --plain --no-legend 'dv-w1-cum-*' 'dv-w1-cp05-*' 2>/dev/null | awk 'NF{bad=1} END{exit !bad}'; then
  echo 'stale CP05 cumulative transient unit exists' >&2; exit 1
fi

phase=trajectory_input_preflight
python3 "$new/w1_cumulative_preflight.py" --root "$root" --artifact-manifest "$artifact" \
  --result-root "$result" --formal-root "$formal" --replay-formal-root "$replay_formal" \
  --delta-root "$delta" --report "$report" --output "$preflight"
python3 "$new/w1_cumulative_execution_manifest.py" activate --manifest "$manifest" \
  --preflight "$preflight" --phase evidence_self_test
attempt_armed=1

phase=evidence_self_test
install -d -o ubuntu -g ubuntu "$tmp/evidence-self-test-parent"
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$new/w1_cumulative_evidence.py" self-test \
  --scratch "$tmp/evidence-self-test-parent/scratch" --output "$tmp/evidence-self-test-parent/result.json"
install -m 0444 "$tmp/evidence-self-test-parent/result.json" "$result/preflight/evidence_self_test.json"
chmod -R u+rwx "$tmp/evidence-self-test-parent"; rm -rf "$tmp/evidence-self-test-parent"

phase=derive_and_freeze_execution_deltas
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cumulative_prepare.py" --mode formal --dataset "$dataset" \
  --trajectory "$trajectory" --cp01 "$cp01" --output "$delta"
python3 "$new/w1_cumulative_prepare.py" --mode replay --dataset "$root/datasets/sift1m" \
  --output "$replay_inputs"
python3 "$old/w1_file_manifest.py" --root "$delta" --output "$result/preflight/execution_deltas_before.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$delta" --output "$result/preflight/execution_deltas_mode_before.tsv"
python3 "$old/w1_file_manifest.py" --root "$replay_inputs" --output "$result/preflight/replay_inputs_before.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$replay_inputs" --output "$result/preflight/replay_inputs_mode_before.tsv"

runner="$new/w1_run_cumulative_trajectory.sh"
evidence="$new/w1_cumulative_evidence.py"

run_replay_system() {
  local system=$1 base driver query_binary ls io
  if [[ $system == DGAI ]]; then
    base="$root/index/atlas1m/DGAI/sift1m"; driver="$canonical/DGAI/w1_canary"
    query_binary="$canonical/DGAI/search_disk_index"; ls=64,128; io=pread
  else
    base="$root/index/atlas1m/OdinANN/sift1m"; driver="$canonical/OdinANN/w1_canary"
    query_binary="$canonical/OdinANN/search_disk_index"; ls=29,46; io=uring
  fi
  local first="$replay_inputs/cp00_to_cp16" second="$replay_inputs/cp16_to_cp80"
  W1_CUMULATIVE_AUTHORIZED=1 "$runner" --mode replay --system "$system" \
    --run-name "$replay_run" --attempt sequential-cp80-01 --base-index "$base" \
    --dataset-dir "$root/datasets/sift1m" --full-corpus "$root/datasets/sift1m/full_1m.bin" \
    --driver "$driver" --query-binary "$query_binary" --artifact-manifest "$artifact" \
    --cp00-query "$replay_inputs/query_36.bin" --cp00-gt "$replay_inputs/gt_cp00_36" \
    --cp00-active "$root/datasets/sift1m/active_cp00.tags.bin" \
    --cp01-trace "$first/delta_cp00_to_cp16.bin" --cp01-delta-manifest "$first/delta_manifest.json" --cp01-count 16 \
    --cp01-query "$replay_inputs/query_36.bin" --cp01-gt "$replay_inputs/gt_cp16_36" \
    --cp01-active "$first/expected_active.tags.bin" \
    --cp01-local-probes "$first/delta_visibility_probes.bin" --cp01-local-probe-spec "$first/delta_visibility_probes.json" \
    --cp01-global-probes "$first/checkpoint_visibility_probes.bin" --cp01-global-probe-spec "$first/checkpoint_visibility_probes.json" \
    --cp01-combined-probes "$first/combined_visibility_probes.bin" --cp01-combined-probe-spec "$first/combined_visibility_probes.json" \
    --cp01-inaccessible "$root/datasets/sift1m/smoke_replace_new_trace.bin,$second/delta_cp16_to_cp80.bin" \
    --cp05-trace "$second/delta_cp16_to_cp80.bin" --cp05-delta-manifest "$second/delta_manifest.json" --cp05-count 64 \
    --cp05-query "$replay_inputs/query_36.bin" --cp05-gt "$replay_inputs/gt_cp80_36" \
    --cp05-active "$second/expected_active.tags.bin" \
    --cp05-local-probes "$second/delta_visibility_probes.bin" --cp05-local-probe-spec "$second/delta_visibility_probes.json" \
    --cp05-global-probes "$second/checkpoint_visibility_probes.bin" --cp05-global-probe-spec "$second/checkpoint_visibility_probes.json" \
    --cp05-combined-probes "$second/combined_visibility_probes.bin" --cp05-combined-probe-spec "$second/combined_visibility_probes.json" \
    --cp05-inaccessible "$root/datasets/sift1m/smoke_replace_new_trace.bin,$first/delta_cp00_to_cp16.bin" \
    --ls "$ls" --io-engine "$io" --old-tools "$old" --new-tools "$new" --evidence-tool "$evidence"
}

run_formal_system() {
  local system=$1 base driver query_binary ls io
  if [[ $system == DGAI ]]; then
    base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"
    driver="$canonical/DGAI/w1_canary"; query_binary="$canonical/DGAI/search_disk_index"; ls=64,128; io=pread
  else
    base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"
    driver="$canonical/OdinANN/w1_canary"; query_binary="$canonical/OdinANN/search_disk_index"; ls=29,46; io=uring
  fi
  local first="$delta/cp00_to_cp01" second="$delta/cp01_to_cp05"
  W1_CUMULATIVE_AUTHORIZED=1 "$runner" --mode formal --system "$system" \
    --run-name "$run" --attempt trajectory-cp05-01 --base-index "$base" \
    --dataset-dir "$dataset" --full-corpus "$full" --driver "$driver" --query-binary "$query_binary" \
    --artifact-manifest "$artifact" --cp00-query "$query" --cp00-gt "$cp00gt" \
    --cp00-active "$dataset/active_cp00.tags.bin" \
    --cp01-trace "$first/delta_cp00_to_cp01.bin" --cp01-delta-manifest "$first/delta_manifest.json" --cp01-count 80000 \
    --cp01-query "$query" --cp01-gt "$cp01gt" --cp01-active "$cp01/active_cp01.tags.bin" \
    --cp01-local-probes "$first/delta_visibility_probes.bin" --cp01-local-probe-spec "$first/delta_visibility_probes.json" \
    --cp01-global-probes "$cp01/visibility_probes.bin" --cp01-global-probe-spec "$cp01/visibility_probes.json" \
    --cp01-combined-probes "$first/combined_visibility_probes.bin" --cp01-combined-probe-spec "$first/combined_visibility_probes.json" \
    --cp01-inaccessible "$trajectory/master_replacements_1600k.bin,$trajectory/cp05/replace_cp05.bin,$cp01/replace_cp01_80k.bin,$second/delta_cp01_to_cp05.bin" \
    --cp05-trace "$second/delta_cp01_to_cp05.bin" --cp05-delta-manifest "$second/delta_manifest.json" --cp05-count 320000 \
    --cp05-query "$query" --cp05-gt "$cp05gt" --cp05-active "$trajectory/cp05/active_cp05.tags.bin" \
    --cp05-local-probes "$second/delta_visibility_probes.bin" --cp05-local-probe-spec "$second/delta_visibility_probes.json" \
    --cp05-global-probes "$trajectory/cp05/visibility_probes.bin" --cp05-global-probe-spec "$trajectory/cp05/visibility_probes.json" \
    --cp05-combined-probes "$second/combined_visibility_probes.bin" --cp05-combined-probe-spec "$second/combined_visibility_probes.json" \
    --cp05-inaccessible "$trajectory/master_replacements_1600k.bin,$trajectory/cp05/replace_cp05.bin,$cp01/replace_cp01_80k.bin,$first/delta_cp00_to_cp01.bin" \
    --ls "$ls" --io-engine "$io" --old-tools "$old" --new-tools "$new" --evidence-tool "$evidence"
}

phase=replay_DGAI
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
run_replay_system DGAI
phase=replay_OdinANN
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
run_replay_system OdinANN

phase=formal_DGAI_cumulative
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
run_formal_system DGAI
python3 "$new/w1_cumulative_preservation.py" --preflight "$preflight" \
  --output "$result/preflight/preservation_after_DGAI.json"

phase=formal_OdinANN_cumulative
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
run_formal_system OdinANN
python3 "$new/w1_cumulative_preservation.py" --preflight "$preflight" \
  --output "$result/preflight/preservation_after_OdinANN.json"

phase=diskann_cp05_stale_control
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
install -d -o ubuntu -g ubuntu "$result/DiskANN"
disk_unit=dv-w1-cp05-diskann-stale
systemd-run --scope --collect --unit "$disk_unit" --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
  --property=IOAccounting=yes --property=MemoryMax=4G --property=RuntimeMaxSec=2700 \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
    W1_CP05_CUMULATIVE_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" \
    ATLAS_NVME_MAJMIN="${ATLAS_NVME_MAJMIN:-259:10}" W1_EXPECTED_SCOPE="$disk_unit.scope" \
  prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 \
    "$new/w1_run_diskann_cp05_stale.sh" "$query" "$cp05gt" \
      "$result/DiskANN/stale-cp05-01" "$artifact" "$runtime" "$preflight"

phase=final_preservation_audit
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cumulative_preservation.py" --preflight "$preflight" \
  --output "$result/preflight/preservation_final.json"
python3 "$old/w1_file_manifest.py" --root "$delta" --output "$result/preflight/execution_deltas_after.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$delta" --output "$result/preflight/execution_deltas_mode_after.tsv"
python3 "$old/w1_file_manifest.py" --root "$replay_inputs" --output "$result/preflight/replay_inputs_after.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$replay_inputs" --output "$result/preflight/replay_inputs_mode_after.tsv"
for name in execution_deltas replay_inputs; do
  cmp -s "$result/preflight/${name}_before.tsv" "$result/preflight/${name}_after.tsv" || { echo "$name content changed" >&2; exit 1; }
  cmp -s "$result/preflight/${name}_mode_before.tsv" "$result/preflight/${name}_mode_after.tsv" || { echo "$name mode changed" >&2; exit 1; }
done

phase=final_report
python3 "$new/w1_cumulative_execution_manifest.py" phase --manifest "$manifest" --phase "$phase"
python3 "$new/w1_cumulative_finalize.py" --root "$root" --result-root "$result" \
  --report "$report" --device "${ATLAS_NVME_MAJMIN:-259:10}"
python3 "$new/w1_cumulative_execution_manifest.py" complete --manifest "$manifest" \
  --summary "$result/trajectory_summary.json"
touch "$result/FORMAL_W1_CP05_CUMULATIVE_COMPLETE"
notify 'Dynamic Vamana W1 CP05 cumulative complete' \
  '1M replay, DGAI/OdinANN CP00->CP01->CP05, freeze and DiskANN stale CP05 all passed; CP10/CP20 remain HOLD'
phase=complete
