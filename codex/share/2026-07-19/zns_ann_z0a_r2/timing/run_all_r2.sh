#!/usr/bin/env bash
set -euo pipefail
[[ ${Z0A_R2_RUN_AUTHORIZED:-0} == 1 ]] || { echo 'Z0A-R2 authorization absent' >&2; exit 64; }
atlas=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
root=${Z0A_R2_RUN_ROOT:-$atlas/z0a_r2_final_closure_0719}
runner=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_one_r2.sh
[[ -f $root/PREPARED_OK && ! -e $root/ALL_RUNS_OK ]] || { echo 'root unprepared or already complete' >&2; exit 65; }
du -s -B1 "$root" > "$root/evidence/space_before_runs.txt"
total=$(python3 - "$root/schedule.json" <<'PY'
import json,sys
print(len(json.load(open(sys.argv[1]))['runs']))
PY
)
completed=0
while IFS= read -r label; do
  result=$root/results/$label
  if [[ -f $result/Z0A_R2_RUN_OK ]]; then
    completed=$((completed+1))
    continue
  fi
  free=$(df -PB1 "$root" | awk 'NR==2{print $4}')
  (( free > 8589934592 )) || { echo '8 GiB runtime free-space guard failed' >&2; exit 69; }
  "$runner" "$label"
  completed=$((completed+1))
  printf '%s/%s %s\n' "$completed" "$total" "$label" | tee -a "$root/evidence/progress.log"
done < <(python3 - "$root/schedule.json" <<'PY'
import json,sys
for row in json.load(open(sys.argv[1]))['runs']:
    print(row['label'])
PY
)
[[ $(find "$root/results" -mindepth 2 -maxdepth 2 -name Z0A_R2_RUN_OK | wc -l) -eq $total ]]
du -s -B1 "$root" > "$root/evidence/space_after_runs.txt"
touch "$root/ALL_RUNS_OK"
echo "$root"
