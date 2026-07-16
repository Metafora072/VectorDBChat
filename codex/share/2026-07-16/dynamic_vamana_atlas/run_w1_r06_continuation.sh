#!/usr/bin/env bash
# R06: compose frozen R05 DGAI with fresh OdinANN and DiskANN evidence.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_R06_AUTHORIZED:-0} == 1 ]] || { echo 'W1 R06 gate absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'R06 launcher must run as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
run=pilot3_sift10m_w1_r06; attempt=cp01-06; stale=stale-cp00-06; result="$root/results/$run"; formal="$root/formal/$run"
cp01="$root/datasets/sift10m/w1_cp01"; gt="$root/groundtruth/sift10m/w1_r02/gt_cp01"; artifact="$old/artifact_rebuild_manifest.json"
manifest="$result/execution_manifest.json"; phase=initializing; clone_scratch="$root/tmp/${run}_clone_tests"
partial_report="$new/../dynamic_vamana_w1_r05_dgai_partial_results_0716.md"; final_report="$new/../dynamic_vamana_w1_composed_one_percent_canary_r06_results_0716.md"
odin_base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"; dgai_base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"; disk_base="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
notify(){ [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0; "$old/formal/notify_owner.sh" "$1" "$2" || true; }
on_exit(){ rc=$?; if ((rc)); then python3 "$new/w1_mark_recovery_stopped.py" --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true; if [[ -f $result/preflight/execution_preflight.json && ! -e $result/preflight/preservation_after_stop.json ]]; then python3 "$new/w1_r03_assert_reused_inputs.py" --run-label R06 --preflight "$result/preflight/execution_preflight.json" --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_after_stop.json" || true; fi; [[ -d $result && ! -e $final_report ]] && python3 "$new/w1_write_r03_stop_report.py" --run-label R06 --result "$result" --phase "$phase" --exit-code "$rc" --output "$final_report" || true; notify "Dynamic Vamana W1 R06 $phase failed" "exit=$rc; fail closed"; fi; }
trap on_exit EXIT
mkdir -p "$root/locks"; exec 9>"$root/locks/pilot3_w1_global.lock"; flock -n 9 || { echo 'global W1 lock busy' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$; W1_ALLOWED_SESSION=${W1_ALLOWED_SESSION:-$(tmux display-message -p '#S' 2>/dev/null || true)}; export W1_ALLOWED_SESSION
[[ ! -e $result && ! -e $formal && ! -e $clone_scratch && ! -e $final_report ]] || { echo 'R06 freshness failed' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == ${ATLAS_NVME_MAJMIN:-259:10} ]] || exit 1
(( $(df -PB1 "$root"|awk 'NR==2{print $4}') >= 150000000000 )) || exit 1
phase=process_identity_regressions
python3 "$new/w1_process_identity.py" test-fixtures --root "$root" --artifact-manifest "$artifact" --output "$result/preflight/process_identity_tests.json"
phase=freeze_r05_dgai
python3 "$new/w1_r06_freeze_r05_dgai.py" --root "$root" --output-json "$result/preflight/r05_dgai_freeze.json" --output-tsv "$result/preflight/r05_dgai_evidence_manifest.tsv" --report "$partial_report" --expected-report "$partial_report"
phase=continuation_preflight
systemd-run --scope --collect --unit dv-w1-r06-runtime-canary --uid ubuntu --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes numactl --physcpubind=0 --membind=0 /usr/bin/true
python3 "$new/w1_r06_continuation_preflight.py" --root "$root" --artifact-manifest "$artifact" --process-tests "$result/preflight/process_identity_tests.json" --freeze "$result/preflight/r05_dgai_freeze.json" --freeze-tsv "$result/preflight/r05_dgai_evidence_manifest.tsv" --output "$result/preflight/execution_preflight.json" --runtime-canary-passed
phase=freeze_base_manifests
mkdir -p "$result/preflight/base_before"
for item in "OdinANN:$odin_base" "DiskANN:$disk_base"; do system=${item%%:*}; base=${item#*:}; python3 "$old/w1_file_manifest.py" --root "$base" --output "$result/preflight/base_before/$system.content.tsv"; python3 "$new/w1_mode_manifest.py" write --root "$base" --output "$result/preflight/base_before/$system.mode.tsv"; done
phase=clone_capability_tests
python3 "$new/w1_r04_clone_target_tests.py" --root "$root" --helper "$old/w1_clone_base.sh" --dgai-base "$dgai_base" --odin-base "$odin_base" --run "$run" --attempt "$attempt" --scratch "$clone_scratch" --output "$result/preflight/clone_target_tests.json"
phase=identity_gate_regressions
python3 "$new/w1_r06_identity_gate_tests.py" --root "$root" --gate "$new/w1_preupdate_identity_gate.py" --artifact "$artifact" --scratch "$root/tmp/${run}_identity_tests" --output "$result/preflight/identity_gate_tests.json"
python3 "$new/w1_r06_execution_manifest.py" --root "$root" --preflight "$result/preflight/execution_preflight.json" --clone-tests "$result/preflight/clone_target_tests.json" --identity-tests "$result/preflight/identity_gate_tests.json" --output "$manifest"
chown -R ubuntu:ubuntu "$result"; notify 'Dynamic Vamana W1 R06 started' 'R05 DGAI frozen; identity-v2 and continuation preflight passed'
dataset="$root/datasets/sift10m"; full="$dataset/full_10m.bin"; trace="$cp01/replace_cp01_80k.bin"; tags="$cp01/active_cp01.tags.bin"; probes="$cp01/visibility_probes.bin"; probe_spec="$cp01/visibility_probes.json"; query="$dataset/query.bin"; cp0gt="$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"; canonical="$root/build/w1-canonical-v6/install"
phase=OdinANN_canary
install -d -o ubuntu -g ubuntu "$formal/OdinANN" "$result/OdinANN"; target="$formal/OdinANN/$attempt"
systemd-run --scope --collect --unit dv-w1-r06-odinann-cp0106 --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
 env W1_FORMAL_PATH_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 W1_CLONE_PREFLIGHT_ONLY=0 W1_MUTABLE_CLONE_OWNER=ubuntu W1_ALLOWED_CLONE_TARGET="$target" W1_ALLOWED_CLONE_SYSTEM=OdinANN W1_ALLOWED_CLONE_RUN="$run" W1_ALLOWED_CLONE_ATTEMPT="$attempt" W1_PREUPDATE_GATE_POLICY=identity-v2 W1_IDENTITY_GATE_TOOL="$new/w1_preupdate_identity_gate.py" W1_IO_ENGINE=uring ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN=${ATLAS_NVME_MAJMIN:-259:10} \
 numactl --physcpubind=0-23 --membind=0 "$old/w1_run_system_canary.sh" --system OdinANN --mode formal --dataset-dir "$dataset" --full-corpus "$full" --base-index "$odin_base" --trace "$trace" --expected-active-tags "$tags" --probe-queries "$probes" --probe-spec "$probe_spec" --cp0-query "$query" --cp0-gt "$cp0gt" --cp1-query "$query" --cp1-gt "$gt" --attempt-dir "$target" --result-dir "$result/OdinANN/$attempt" --replacements 80000 --pre-ls 29,46 --post-ls 29,46 --driver "$canonical/OdinANN/w1_canary" --query-binary "$canonical/OdinANN/search_disk_index" --artifact-manifest "$artifact"
python3 "$new/w1_r05_assert_base_immutable.py" --system OdinANN --base "$odin_base" --attempt "$target" --output "$result/OdinANN/$attempt/base_immutability.json"
phase=diskann_stale_static_control
install -d -o ubuntu -g ubuntu "$result/DiskANN"
systemd-run --scope --collect --unit dv-w1-r06-diskann-stale --uid ubuntu --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes env W1_SIFT10M_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN=${ATLAS_NVME_MAJMIN:-259:10} numactl --physcpubind=0-23 --membind=0 "$old/w1_diskann_stale_control.sh" "$query" "$gt" "$result/DiskANN/$stale" "$artifact"
phase=final_base_audit
mkdir -p "$result/preflight/base_after"
for item in "OdinANN:$odin_base" "DiskANN:$disk_base"; do system=${item%%:*}; base=${item#*:}; python3 "$old/w1_file_manifest.py" --root "$base" --output "$result/preflight/base_after/$system.content.tsv"; python3 "$new/w1_mode_manifest.py" write --root "$base" --output "$result/preflight/base_after/$system.mode.tsv"; cmp -s "$result/preflight/base_before/$system.content.tsv" "$result/preflight/base_after/$system.content.tsv"; cmp -s "$result/preflight/base_before/$system.mode.tsv" "$result/preflight/base_after/$system.mode.tsv"; done
phase=final_report
python3 "$new/w1_r03_assert_reused_inputs.py" --run-label R06 --preflight "$result/preflight/execution_preflight.json" --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_final.json"
python3 "$new/w1_r06_finalize_composed.py" --root "$root" --output "$final_report"; touch "$result/FORMAL_W1_COMPLETE"; notify 'Dynamic Vamana W1 R06 complete' 'composed W1 1% canary result complete'; phase=complete
