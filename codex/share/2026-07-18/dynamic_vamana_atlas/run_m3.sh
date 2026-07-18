#!/usr/bin/env bash
set -euo pipefail
[[ ${M3_WRITE_SUPERSESSION_AUTHORIZED:-0} == 1 ]] || { echo 'M3 controller authorization absent' >&2; exit 64; }; (( EUID == 0 )) || exit 1
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}; device=${ATLAS_NVME_MAJMIN:-259:10}; chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
run=pilot3_sift10m_write_supersession_m3_r01; result_root="$root/results/$run"; formal_root="$root/formal/$run"; build="$root/build/write-supersession-m3-v1-r01"; m2="$root/results/pilot3_sift10m_neighbor_repair_m2_r01/m2_summary.json"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" && -f $build/M3_BUILD_OK && -f $m2 && ! -e $formal_root && ! -e $result_root ]] || exit 1
available=$(df -PB1 "$root" | awk 'NR==2{print $4}'); (( available >= 100000000000 )) || { echo 'M3 requires 100GB project-NVMe headroom' >&2; exit 1; }
if systemctl list-units --all --no-legend 'dv-m3-*' | rg -q .; then echo 'stale M3 unit' >&2; exit 1; fi
mkdir -p "$result_root"; exec 9>"$root/.write_supersession_m3.lock"; flock -n 9 || exit 1; export M3_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
python3 "$chat/m3_comparability_audit.py" --root "$root" --output "$result_root/comparability_audit.json"
for size in 50000 400000; do for system in DGAI OdinANN; do bash "$chat/m3_run_one.sh" "$system" "$size"; done; done
python3 "$chat/m3_finalize.py" --root "$root" --result-root "$result_root" --formal-root "$formal_root" --build-manifest "$build/build_manifest.json" --m2-summary "$m2" --comparability "$result_root/comparability_audit.json" --free-before "$available"
