#!/usr/bin/env bash
set -euo pipefail

[[ ${M0_WRITE_ATTRIBUTION_AUTHORIZED:-0} == 1 ]] || { echo 'M0 controller authorization absent' >&2; exit 64; }
(( EUID == 0 )) || { echo 'M0 controller must execute as root' >&2; exit 1; }
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
run=pilot3_sift10m_write_attribution_m0
result_root="$root/results/$run"
formal_root="$root/formal/$run"
input_root="$result_root/inputs"
source_trace="$root/results/pilot3_sift10m_w1_cp20_trajectory_r13/inputs/cp10_to_cp20/delta_cp10_to_cp20.bin"
before_active="$root/datasets/sift10m/w1_trajectory/cp10/active_cp10.tags.bin"
full="$root/datasets/sift10m/full_10m.bin"

[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || { echo 'M0 controller root is not project NVMe' >&2; exit 1; }
[[ -f $root/build/write-attribution-m0-v3/M0_BUILD_OK ]] || { echo 'M0 instrumented build absent' >&2; exit 1; }
[[ ! -e $formal_root && ! -e $result_root ]] || { echo 'refusing to reuse M0 controller tree' >&2; exit 1; }
available=$(df -PB1 "$root" | awk 'NR==2{print $4}')
(( available >= 250000000000 )) || { echo 'M0 requires at least 250GB project-NVMe headroom' >&2; exit 1; }
if systemctl list-units --all --no-legend 'dv-m0-*' | rg -q .; then echo 'stale M0 systemd unit exists' >&2; exit 1; fi

mkdir -p "$result_root"
exec 9>"$root/.write_attribution_m0.lock"
flock -n 9 || { echo 'M0 global lock busy' >&2; exit 1; }
export M0_GLOBAL_LOCK_HELD=1 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device"

prepare() {
  local size=$1
  python3 "$chat/m0_prepare.py" --size "$size" --source-trace "$source_trace" \
    --before-active "$before_active" --full-corpus "$full" --output-dir "$input_root/n${size}"
}
run_one() {
  local system=$1 size=$2
  "$chat/m0_run_one.sh" "$system" "$size"
}

prepare 100000
run_one DGAI 100000
run_one OdinANN 100000
python3 - "$result_root" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for system in ('DGAI','OdinANN'):
 p=root/system/'m0-n100000-01/summary.json'; d=json.load(open(p))
 if d.get('status')!='pass' or d.get('application_writes',{}).get('coverage',0)<0.90:
  raise SystemExit(f'100K pilot gate failed: {system}')
PY

for size in 50000 200000 400000; do
  prepare "$size"
  run_one OdinANN "$size"
done

python3 - "$result_root" "$formal_root" "$available" <<'PY'
import hashlib,json,shutil,sys,time
from pathlib import Path
result,formal,free_before=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3])
runs=[]
for system,size in [('DGAI',100000),('OdinANN',50000),('OdinANN',100000),('OdinANN',200000),('OdinANN',400000)]:
 p=result/system/f'm0-n{size}-01/summary.json'; d=json.load(open(p))
 if d.get('status')!='pass': raise SystemExit(f'non-pass summary: {p}')
 runs.append({'system':system,'size':size,'summary':str(p),'summary_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'coverage':d['application_writes']['coverage'],'device_wbytes':d['device_delta'].get('wbytes',0)})
def space(path):
 apparent=allocated=files=0
 for p in path.rglob('*'):
  if p.is_file():
   st=p.stat(); apparent+=st.st_size; allocated+=st.st_blocks*512; files+=1
 return {'files':files,'apparent_bytes':apparent,'allocated_bytes':allocated}
manifest={'schema':'dynamic-vamana-write-attribution-m0-controller-v1','status':'complete','runs':runs,
          'result_space':space(result),'formal_space':space(formal),'free_space_before':free_before,
          'free_space_after':shutil.disk_usage(result).free,'completed_unix_ns':time.time_ns()}
(result/'controller_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(result/'M0_COMPLETE').touch()
PY
echo "$result_root/controller_manifest.json"
