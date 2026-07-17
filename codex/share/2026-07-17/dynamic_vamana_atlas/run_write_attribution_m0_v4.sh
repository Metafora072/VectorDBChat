#!/usr/bin/env bash
set -euo pipefail
[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]]||{ echo 'M0 V4 controller authorization absent' >&2;exit 64;};(( EUID==0 ))||{ echo 'must run as root' >&2;exit 1;}
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas};device=${ATLAS_NVME_MAJMIN:-259:10};chat=$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd);run=pilot3_sift10m_write_attribution_m0_r03;result_root="$root/results/$run";formal_root="$root/formal/$run";input_root="$result_root/inputs";source_trace="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/inputs/cp10_to_cp20/delta_cp10_to_cp20.bin";before_active="$root/datasets/sift10m/w1_trajectory/cp10/active_cp10.tags.bin";full="$root/datasets/sift10m/full_10m.bin"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN|awk 'NR==1{print;exit}') == "$device" ]]||exit 1;[[ -f $root/build/write-attribution-m0-v4-r02/M0_V4_BUILD_OK ]]||exit 1;[[ ! -e $formal_root && ! -e $result_root ]]||{ echo 'refusing R03 tree reuse' >&2;exit 1;}
available=$(df -PB1 "$root"|awk 'NR==2{print $4}');((available>=100000000000))||{ echo 'requires 100GB NVMe headroom' >&2;exit 1;};if systemctl list-units --all --no-legend 'dv-m0-*'|rg -q .;then echo 'stale M0 unit' >&2;exit 1;fi
mkdir -p "$result_root";exec 9>"$root/.write_attribution_m0.lock";flock -n 9||exit 1;export M0_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
python3 "$chat/m0_prepare.py" --size 100000 --source-trace "$source_trace" --before-active "$before_active" --full-corpus "$full" --output-dir "$input_root/n100000"
"$chat/m0_run_one_v4.sh" DGAI
"$chat/m0_run_one_v4.sh" OdinANN
python3 - "$result_root" "$formal_root" "$available" <<'PY'
import hashlib,json,shutil,sys,time
from pathlib import Path
r,f,free=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]);runs=[]
for s in ('DGAI','OdinANN'):
 p=r/s/'m0-n100000-03/summary.json';d=json.load(open(p));assert d['status']=='pass';runs.append({'system':s,'size':100000,'summary':str(p),'summary_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'classification_coverage':d['application_writes']['classification_coverage'],'application_bytes':d['application_writes']['physical_total_bytes'],'device_wbytes':d['device_delta'].get('wbytes',0)})
def space(p):
 rows=[x.stat() for x in p.rglob('*') if x.is_file()];return {'files':len(rows),'apparent_bytes':sum(x.st_size for x in rows),'allocated_bytes':sum(x.st_blocks*512 for x in rows)}
m={'schema':'dynamic-vamana-write-attribution-m0-controller-v4','status':'complete','scope':'dual-system-100K-only','scale_matrix_started':False,'runs':runs,'result_space':space(r),'formal_space':space(f),'free_space_before':free,'free_space_after':shutil.disk_usage(r).free,'completed_unix_ns':time.time_ns()};(r/'controller_manifest.json').write_text(json.dumps(m,indent=2)+'\n');(r/'M0_V4_COMPLETE').touch()
PY
echo "$result_root/controller_manifest.json"
