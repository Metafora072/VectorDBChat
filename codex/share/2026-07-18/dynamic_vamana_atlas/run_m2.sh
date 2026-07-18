#!/usr/bin/env bash
set -euo pipefail
[[ ${M2_NEIGHBOR_REPAIR_AUTHORIZED:-0} == 1 ]] || { echo 'M2 controller authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'M2 controller must execute as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
run=pilot3_sift10m_neighbor_repair_m2_r01; result_root="$root/results/$run"; formal_root="$root/formal/$run"
build="$root/build/neighbor-repair-m2-v1-r01"; m1="$root/results/pilot3_sift10m_write_attribution_m1_scale_r01/scale_summary.json"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || exit 1
for path in "$build/M2_BUILD_OK" "$build/build_manifest.json" "$m1"; do [[ -f $path ]] || { echo "missing M2 prerequisite: $path" >&2; exit 1; }; done
[[ ! -e $formal_root && ! -e $result_root ]] || { echo 'refusing M2 tree reuse' >&2; exit 1; }
python3 - "$m1" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); assert d['status']=='complete' and len(d['points'])==8
assert {(r['system'],r['size']) for r in d['points']} == {(s,n) for s in ('DGAI','OdinANN') for n in (50000,100000,200000,400000)}
PY
available=$(df -PB1 "$root" | awk 'NR==2{print $4}'); (( available >= 100000000000 )) || { echo 'M2 requires 100GB project-NVMe headroom' >&2; exit 1; }
if systemctl list-units --all --no-legend 'dv-m2-*' | rg -q .; then echo 'stale M2 unit' >&2; exit 1; fi
mkdir -p "$result_root"; exec 9>"$root/.neighbor_repair_m2.lock"; flock -n 9 || exit 1
export M2_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
for size in 50000 400000; do
  bash "$chat/m2_run_one.sh" DGAI "$size"
  bash "$chat/m2_run_one.sh" OdinANN "$size"
done
python3 "$chat/m2_finalize.py" --root "$root" --result-root "$result_root" --formal-root "$formal_root" --build-manifest "$build/build_manifest.json" --m1-summary "$m1" --free-before "$available"
echo "$result_root/m2_summary.json"
