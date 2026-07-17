#!/usr/bin/env bash
set -euo pipefail
[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]]||exit 64;((EUID==0))||exit 1
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas};device=${ATLAS_NVME_MAJMIN:-259:10};chat=$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd);run=pilot3_sift10m_write_attribution_m0_r03;result="$root/results/$run";formal="$root/formal/$run";input="$result/inputs/n100000"
[[ $(findmnt -rn -T "$root" -o MAJ:MIN|awk 'NR==1{print;exit}') == "$device" ]]||exit 1;[[ -f $root/build/write-attribution-m0-v4-r02/M0_V4_BUILD_OK && -f $input/manifest.json ]]||exit 1;[[ ! -e $formal && ! -e $result/DGAI && ! -e $result/OdinANN && ! -e $result/controller_manifest.json ]]||{ echo 'not an input-only R03 stop' >&2;exit 1;}
python3 - "$input/manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));assert d['status']=='pass' and d['size']==100000 and d['master_record_range']==[800000,900000] and d['active_count']==8000000
PY
if systemctl list-units --all --no-legend 'dv-m0-*'|rg -q .;then echo 'stale M0 unit' >&2;exit 1;fi
available=$(df -PB1 "$root"|awk 'NR==2{print $4}');((available>=100000000000))||exit 1;exec 9>"$root/.write_attribution_m0.lock";flock -n 9||exit 1;export M0_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"
bash "$chat/m0_run_one_v4.sh" DGAI
bash "$chat/m0_run_one_v4.sh" OdinANN
python3 - "$result" "$formal" "$available" <<'PY'
import hashlib,json,shutil,sys,time
from pathlib import Path
r,f,free=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]);runs=[]
for s in ('DGAI','OdinANN'):
 p=r/s/'m0-n100000-03/summary.json';d=json.load(open(p));assert d['status']=='pass';runs.append({'system':s,'size':100000,'summary':str(p),'summary_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'classification_coverage':d['application_writes']['classification_coverage'],'application_bytes':d['application_writes']['physical_total_bytes'],'device_wbytes':d['device_delta'].get('wbytes',0)})
def space(p):
 st=[x.stat() for x in p.rglob('*') if x.is_file()];return {'files':len(st),'apparent_bytes':sum(x.st_size for x in st),'allocated_bytes':sum(x.st_blocks*512 for x in st)}
m={'schema':'dynamic-vamana-write-attribution-m0-controller-v4','status':'complete','composition':'input-only-initial-plus-continuation','scope':'dual-system-100K-only','scale_matrix_started':False,'runs':runs,'result_space':space(r),'formal_space':space(f),'free_space_before_continuation':free,'free_space_after':shutil.disk_usage(r).free,'completed_unix_ns':time.time_ns()};(r/'controller_manifest.json').write_text(json.dumps(m,indent=2)+'\n');(r/'M0_V4_COMPLETE').touch()
PY
echo "$result/controller_manifest.json"
