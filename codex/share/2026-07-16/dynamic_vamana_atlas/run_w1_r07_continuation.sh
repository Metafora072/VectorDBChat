#!/usr/bin/env bash
# R07: freeze R06 OdinANN, validate the loader, and run DiskANN stale control only.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${W1_R07_AUTHORIZED:-0} == 1 ]] || { echo 'W1 R07 continuation gate absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'R07 launcher must run as root' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
run=pilot3_sift10m_w1_r07; stale=stale-cp00-07
result="$root/results/$run"; formal="$root/formal/$run"
cp01="$root/datasets/sift10m/w1_cp01"; gt="$root/groundtruth/sift10m/w1_r02/gt_cp01"
query="$root/datasets/sift10m/query.bin"; artifact="$old/artifact_rebuild_manifest.json"
binary="$root/build/DiskANN/apps/search_disk_index"
disk_base="$root/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
runtime_lib="$root/build/gperftools-install/lib"
runtime_manifest="$result/preflight/diskann_runtime_manifest.json"
loader_scratch="$root/tmp/${run}_loader_tests"
manifest="$result/execution_manifest.json"; phase=initializing
partial_report="$new/../dynamic_vamana_w1_r06_odinann_partial_results_0716.md"
final_report="$new/../dynamic_vamana_w1_composed_one_percent_canary_r07_results_0716.md"
controller_log=${ATLAS_CONTROLLER_LOG_PATH:-}

notify() {
  [[ ${ATLAS_NOTIFY_EMAIL:-1} == 1 ]] || return 0
  "$old/formal/notify_owner.sh" "$1" "$2" || true
}

on_exit() {
  local rc=$?
  if (( rc != 0 )); then
    python3 "$new/w1_mark_recovery_stopped.py" --manifest "$manifest" --phase "$phase" --exit-code "$rc" || true
    if [[ -f $result/preflight/execution_preflight.json && ! -e $result/preflight/preservation_after_stop.json ]]; then
      python3 "$new/w1_r03_assert_reused_inputs.py" --run-label R07 --preflight "$result/preflight/execution_preflight.json" \
        --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_after_stop.json" || true
    fi
    if [[ -d $result && ! -e $final_report ]]; then
      python3 "$new/w1_write_r03_stop_report.py" --run-label R07 --result "$result" --phase "$phase" \
        --exit-code "$rc" --output "$final_report" || true
    fi
    notify "Dynamic Vamana W1 R07 $phase failed" "exit=$rc; fail-closed stop, no retry and no dynamic-system rerun"
  fi
}
trap on_exit EXIT

mkdir -p "$root/locks"
exec 9>"$root/locks/pilot3_w1_global.lock"
flock -n 9 || { echo 'another W1 path owns the global lock' >&2; exit 1; }
export W1_GLOBAL_LOCK_HELD=1 W1_GLOBAL_LOCK_FD=9 W1_CONTROLLER_PID=$$
if [[ -z ${W1_ALLOWED_SESSION:-} ]]; then W1_ALLOWED_SESSION=$(tmux display-message -p '#S' 2>/dev/null || true); fi
export W1_ALLOWED_SESSION
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == ${ATLAS_NVME_MAJMIN:-259:10} ]] || { echo 'experiment root not on project NVMe' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2{print $4}') >= 150000000000 )) || { echo 'free-space guard failed' >&2; exit 1; }
for path in "$result" "$formal" "$loader_scratch" "$final_report"; do
  [[ ! -e $path ]] || { echo "fresh R07 target exists: $path" >&2; exit 1; }
done

phase=process_identity_regressions
python3 "$new/w1_process_identity.py" test-fixtures --root "$root" --artifact-manifest "$artifact" \
  --output "$result/preflight/process_identity_tests.json"

phase=freeze_r06_odinann
python3 "$new/w1_r07_freeze_r06_odin.py" --root "$root" --artifact-manifest "$artifact" \
  --output-json "$result/preflight/r06_odinann_freeze.json" \
  --output-tsv "$result/preflight/r06_odinann_evidence_manifest.tsv" \
  --report "$partial_report" --expected-report "$partial_report"

phase=runtime_manifest
python3 "$new/w1_diskann_runtime_manifest.py" --root "$root" --binary "$binary" \
  --runtime-lib-dir "$runtime_lib" --output "$runtime_manifest"
chown -R ubuntu:ubuntu "$result"

phase=loader_regressions
systemd-run --scope --collect --unit dv-w1-r07-loader-tests --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 ATLAS_NVME_MAJMIN=${ATLAS_NVME_MAJMIN:-259:10} \
  numactl --physcpubind=0-23 --membind=0 python3 "$new/w1_diskann_loader_tests.py" \
    --root "$root" --manifest "$runtime_manifest" --binary "$binary" --base-dir "$disk_base" \
    --query "$query" --gt "$gt" --old-tools "$old" --scratch "$loader_scratch" \
    --output "$result/preflight/diskann_loader_tests.json"

phase=continuation_preflight
python3 "$new/w1_r07_continuation_preflight.py" --root "$root" --artifact-manifest "$artifact" \
  --process-tests "$result/preflight/process_identity_tests.json" \
  --odin-freeze "$result/preflight/r06_odinann_freeze.json" \
  --odin-freeze-tsv "$result/preflight/r06_odinann_evidence_manifest.tsv" \
  --runtime-manifest "$runtime_manifest" --loader-tests "$result/preflight/diskann_loader_tests.json" \
  --output "$result/preflight/execution_preflight.json"
if [[ -n $controller_log && -f $controller_log ]]; then ln -s "$controller_log" "$result/formal_controller.log"; fi

phase=freeze_base_manifest
mkdir -p "$result/preflight/base_before"
python3 "$old/w1_file_manifest.py" --root "$disk_base" --output "$result/preflight/base_before/DiskANN.content.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$disk_base" --output "$result/preflight/base_before/DiskANN.mode.tsv"
python3 "$new/w1_r07_execution_manifest.py" --root "$root" --preflight "$result/preflight/execution_preflight.json" \
  --runtime-manifest "$runtime_manifest" --loader-tests "$result/preflight/diskann_loader_tests.json" --output "$manifest"
chown -R ubuntu:ubuntu "$result"
notify 'Dynamic Vamana W1 R07 started' 'R06 Odin frozen; DiskANN runtime manifest, loader regressions and continuation preflight passed'

phase=diskann_stale_static_control
install -d -o ubuntu -g ubuntu "$result/DiskANN"
systemd-run --scope --collect --unit dv-w1-r07-diskann-stale --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
    W1_SIFT10M_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN=${ATLAS_NVME_MAJMIN:-259:10} \
  numactl --physcpubind=0-23 --membind=0 "$old/w1_diskann_stale_control.sh" \
    "$query" "$gt" "$result/DiskANN/$stale" "$artifact" "$runtime_manifest"

phase=final_base_audit
mkdir -p "$result/preflight/base_after"
python3 "$old/w1_file_manifest.py" --root "$disk_base" --output "$result/preflight/base_after/DiskANN.content.tsv"
python3 "$new/w1_mode_manifest.py" write --root "$disk_base" --output "$result/preflight/base_after/DiskANN.mode.tsv"
cmp -s "$result/preflight/base_before/DiskANN.content.tsv" "$result/preflight/base_after/DiskANN.content.tsv" || { echo 'DiskANN base content changed' >&2; exit 1; }
cmp -s "$result/preflight/base_before/DiskANN.mode.tsv" "$result/preflight/base_after/DiskANN.mode.tsv" || { echo 'DiskANN base mode changed' >&2; exit 1; }
python3 - "$result/preflight/base_final_audit.json" "$result/preflight/base_before" "$result/preflight/base_after" <<'PY'
import hashlib,json,sys
from pathlib import Path
out,before,after=map(Path,sys.argv[1:])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows={kind:{'before_sha256':sha(before/f'DiskANN.{kind}.tsv'),'after_sha256':sha(after/f'DiskANN.{kind}.tsv'),
            'exact':(before/f'DiskANN.{kind}.tsv').read_bytes()==(after/f'DiskANN.{kind}.tsv').read_bytes()}
      for kind in ('content','mode')}
report={'schema':'dynamic-vamana-w1-r07-final-base-audit-v1','status':'pass' if all(x['exact'] for x in rows.values()) else 'fail','DiskANN':rows}
out.write_text(json.dumps(report,indent=2)+'\n')
if report['status']!='pass': raise SystemExit('R07 final base audit failed')
PY

phase=final_report
python3 "$new/w1_r03_assert_reused_inputs.py" --run-label R07 --preflight "$result/preflight/execution_preflight.json" \
  --cp01 "$cp01" --gt "$gt" --output "$result/preflight/preservation_final.json"
python3 "$new/w1_r07_finalize_composed.py" --root "$root" --output "$final_report"
touch "$result/FORMAL_W1_COMPLETE"
notify 'Dynamic Vamana W1 R07 complete' 'Composed W1 1% result complete; stopped before higher churn'
phase=complete
