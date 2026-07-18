#!/usr/bin/env bash
set -euo pipefail
[[ ${M1_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]] || { echo 'M1 controller authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'M1 controller must execute as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; device=${ATLAS_NVME_MAJMIN:-259:10}
chat18=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); chat17=/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-17/dynamic_vamana_atlas
run=pilot3_sift10m_write_attribution_m1_scale_r01; result_root="$root/results/$run"; formal_root="$root/formal/$run"; input_root="$result_root/inputs"
build="$root/build/write-attribution-m1-v5-r01"; closure="$root/results/pilot3_sift10m_write_attribution_m0_r04/closure_manifest.json"
source_trace="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/inputs/cp10_to_cp20/delta_cp10_to_cp20.bin"; before_active="$root/datasets/sift10m/w1_trajectory/cp10/active_cp10.tags.bin"; full="$root/datasets/sift10m/full_10m.bin"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || exit 1
for path in "$build/M1_V5_BUILD_OK" "$build/build_manifest.json" "$closure" "$source_trace" "$before_active" "$full"; do [[ -f $path ]] || { echo "missing M1 prerequisite: $path" >&2; exit 1; }; done
[[ ! -e $formal_root && ! -e $result_root ]] || { echo 'refusing M1 tree reuse' >&2; exit 1; }
python3 - "$closure" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));assert d['status']=='complete' and d['scale_matrix_started'] is False
assert {(x['system'],x['attempt']) for x in d['anchors']}=={('DGAI','m0-n100000-03'),('OdinANN','m0-n100000-04')}
PY
available=$(df -PB1 "$root" | awk 'NR==2{print $4}'); (( available >= 150000000000 )) || { echo 'M1 requires 150GB project-NVMe headroom' >&2; exit 1; }
if systemctl list-units --all --no-legend 'dv-m[01]-*' | rg -q .; then echo 'stale M0/M1 unit' >&2; exit 1; fi
mkdir -p "$result_root"; exec 9>"$root/.write_attribution_m1.lock"; flock -n 9 || exit 1
export M1_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
for size in 50000 200000 400000; do
  python3 "$chat17/m0_prepare.py" --size "$size" --source-trace "$source_trace" --before-active "$before_active" --full-corpus "$full" --output-dir "$input_root/n${size}"
  chown -R nobody:nogroup "$input_root/n${size}"
done
for size in 50000 200000 400000; do
  bash "$chat18/m1_run_one.sh" DGAI "$size"
  bash "$chat18/m1_run_one.sh" OdinANN "$size"
done
python3 "$chat18/m1_finalize_scale.py" --root "$root" --result-root "$result_root" --formal-root "$formal_root" --build-manifest "$build/build_manifest.json" --closure "$closure" --free-before "$available"
echo "$result_root/scale_summary.json"
