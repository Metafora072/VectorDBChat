#!/usr/bin/env bash
set -euo pipefail
[[ ${M2_NEIGHBOR_REPAIR_AUTHORIZED:-0} == 1 && ${M2_GLOBAL_LOCK_HELD:-0} == 1 ]] || { echo 'M2 authorization/global lock absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'M2 runner must execute as root' >&2; exit 1; }
[[ $# == 2 && ( $1 == DGAI || $1 == OdinANN ) && ( $2 == 50000 || $2 == 400000 ) ]] || { echo 'usage: m2_run_one.sh DGAI|OdinANN 50000|400000' >&2; exit 2; }
system=$1; size=$2
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
chat17=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-17/dynamic_vamana_atlas
old=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas
r02=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas
run=pilot3_sift10m_neighbor_repair_m2_r01; attempt="m2-n${size}-01"
work="$root/formal/$run/$system/$attempt"; result="$root/results/$run/$system/$attempt"
input="$root/results/pilot3_sift10m_write_attribution_m1_scale_r01/inputs/n${size}"
build="$root/build/neighbor-repair-m2-v1-r01"; driver="$build/install/$system/w1_canary"; canonical="$root/build/w1-canonical-v6/install/$system/w1_canary"
full="$root/datasets/sift10m/full_10m.bin"; prefix="$work/index/index"; trace="$input/trace.bin"; expected="$input/expected_active.tags.bin"; probes="$input/probes.bin"; probe_spec="$input/probes.json"
freeze="$root/results/pilot3_sift10m_w1_cp10_trajectory_r12/$system/trajectory-cp10-12/checkpoints/cp10/cp10_freeze_evidence.json"; system_lower=${system,,}
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || exit 1
for path in "$build/M2_BUILD_OK" "$build/build_manifest.json" "$driver" "$canonical" "$full" "$trace" "$expected" "$probes" "$probe_spec" "$freeze"; do
  [[ -f $path ]] || { echo "missing M2 input: $path" >&2; exit 1; }
done
[[ ! -e $work && ! -e $result ]] || { echo "refusing M2 attempt reuse: $system/$attempt" >&2; exit 1; }
python3 - "$input/manifest.json" "$size" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); n=int(sys.argv[2])
assert d['status']=='pass' and d['size']==n and d['master_record_range']==[800000,800000+n]
assert d['active_count']==8000000 and d['assertions']['nested_prefix'] is True
PY
base=$(python3 - "$freeze" "$system" <<'PY'
import json,sys
from pathlib import Path
d=json.load(open(sys.argv[1])); assert d['status']=='pass' and d['system']==sys.argv[2] and d['checkpoint']=='cp10'
print(Path(d['root_realpath']).resolve())
PY
)
[[ -d $base && -f $base/IMMUTABLE_BASE_OK ]] || exit 1
export W1_FORMAL_PATH_AUTHORIZED=1 W1_CLONE_PREFLIGHT_ONLY=0 W1_MUTABLE_CLONE_OWNER=ubuntu W1_ALLOWED_CLONE_TARGET="$work" W1_ALLOWED_CLONE_SYSTEM="$system" W1_ALLOWED_CLONE_RUN="$run" W1_ALLOWED_CLONE_ATTEMPT="$attempt" ATLAS_W1_MUTABLE_CHAT="$r02" ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
"$old/w1_clone_base.sh" "$system" "$base" "$work"
install -d -m 0700 -o ubuntu -g ubuntu "$result"; install -m 0600 -o ubuntu -g ubuntu /dev/null "$result/controller.log"
profile="$result/app_write_profile_v5.json"; logical="$result/neighbor_repair_logical.json"; markers="$result/markers.jsonl"; resources="$result/resources.json"; primer="$result/io_primer.json"; online="$result/online.bin"
libs="$build/lib:$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
driver_args=(env LD_PRELOAD="$build/lib/libm0write.so" ATLAS_W1_MARKERS="$markers" ATLAS_M0_INDEX_ROOT="$work/index" ATLAS_M0_PROFILE_OUTPUT="$profile" ATLAS_M2_LOGICAL_OUTPUT="$logical" "$driver" run "$full" "$prefix" "$trace")
online_args=()
if [[ $system == OdinANN ]]; then driver_args+=("$probes" "$online"); fi
unit="dv-m2-r01-${system_lower}-n${size}-01"
systemd-run --wait --collect --pipe --unit "$unit" --uid ubuntu --property=Type=exec --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes --property=IOAccounting=yes --property=MemoryMax=40G --property=LimitCORE=0 --property=RuntimeMaxSec=7200 env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/home/ubuntu OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 LD_LIBRARY_PATH="$libs" numactl --physcpubind=0-23 --membind=0 python3 "$chat17/w1_stage_io_primer.py" --index-root "$work/index" --device "$device" --primer-report "$primer" --resources "$resources" --resource-probe "$old/resource_probe.py" --space-root "$work/index" -- "${driver_args[@]}" >>"$result/controller.log" 2>&1
for path in "$profile" "$logical" "$markers" "$resources" "$primer"; do [[ -s $path ]] || { echo "missing M2 evidence: $path" >&2; exit 1; }; done
python3 "$old/w1_dump_active_tags.py" --tags "${prefix}_disk.index.tags" --expected "$expected" --expected-count 8000000 --output "$result/active_audit.json"
LD_LIBRARY_PATH="$libs" "$canonical" probe "$prefix" "$probes" "$result/fresh.bin" >>"$result/controller.log" 2>&1
python3 "$old/w1_visibility_probe.py" --probes "$probe_spec" --result-tags "$result/fresh.bin" --active-tags "$expected" --output "$result/fresh_probe.json"
if [[ $system == OdinANN ]]; then
  python3 "$old/w1_visibility_probe.py" --probes "$probe_spec" --result-tags "$online" --active-tags "$expected" --output "$result/online_probe.json"
  online_args=(--online-probe "$result/online_probe.json")
fi
python3 "$old/w1_file_manifest.py" --root "$base" --output "$result/base_content_after.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$result/base_mode_after.tsv"
cmp -s "$work/base_content_before.tsv" "$result/base_content_after.tsv" || exit 1
cmp -s "$work/base_mode_before.tsv" "$result/base_mode_after.tsv" || exit 1
python3 "$old/w1_file_manifest.py" --root "$work/index" --output "$result/index_content_after.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$work/index" --output "$result/index_mode_after.tsv"
python3 "$chat17/m0_validate_v4.py" --system "$system" --size "$size" --input-manifest "$input/manifest.json" --build-manifest "$build/build_manifest.json" --profile "$profile" --resources "$resources" --markers "$markers" --active-audit "$result/active_audit.json" --fresh-probe "$result/fresh_probe.json" "${online_args[@]}" --base-before "$work/base_content_before.tsv" --base-after "$result/base_content_after.tsv" --mode-before "$work/base_mode_before.tsv" --mode-after "$result/base_mode_after.tsv" --index-before "$work/clone_content_after.tsv" --index-after "$result/index_content_after.tsv" --device "$device" --output "$result/physical_summary.json"
python3 "$chat/m2_validate.py" --system "$system" --size "$size" --physical-summary "$result/physical_summary.json" --logical-profile "$logical" --output "$result/m2_summary.json"
touch "$result/M2_RUN_OK"; chmod -R a-w "$result"; echo "$result/m2_summary.json"
