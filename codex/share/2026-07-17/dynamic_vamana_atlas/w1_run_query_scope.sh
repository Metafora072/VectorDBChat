#!/usr/bin/env bash
# The only authorized launcher for W1 static/replay/formal query scopes.
set -euo pipefail
[[ ${W1_CP05_R03_CUMULATIVE_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || {
  echo 'R03 query-scope authorization/global lock absent' >&2; exit 64;
}
(( EUID == 0 )) || { echo 'R03 query-scope launcher requires root' >&2; exit 1; }

usage() {
  echo 'usage: w1_run_query_scope.sh --unit NAME --system DGAI|OdinANN --index-root DIR --query-binary FILE --query FILE --gt FILE --active-tags FILE --stem PATH --l-value N --memory-max SIZE --resource-probe FILE --query-worker FILE --device MAJ:MIN' >&2
  exit 64
}
declare -A arg=()
while (($#)); do
  case $1 in
    --unit|--system|--index-root|--query-binary|--query|--gt|--active-tags|--stem|--l-value|--memory-max|--resource-probe|--query-worker|--device)
      (($# >= 2)) || usage; arg[${1#--}]=$2; shift 2 ;;
    *) usage ;;
  esac
done
for key in unit system index-root query-binary query gt active-tags stem l-value memory-max resource-probe query-worker device; do
  [[ -n ${arg[$key]:-} ]] || usage
done
[[ ${arg[system]} == DGAI || ${arg[system]} == OdinANN ]] || usage
[[ ${arg[unit]} =~ ^dv-w1-(cum-r03|cp05-r03-fixture)-[a-z0-9-]+$ ]] || { echo 'query scope unit identity rejected' >&2; exit 1; }
[[ ${arg[l-value]} =~ ^[1-9][0-9]*$ ]] || usage
[[ ${arg[memory-max]} =~ ^(8G|16G|24G)$ ]] || { echo 'query scope memory capability rejected' >&2; exit 1; }

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[[ ${arg[index-root]} == /* && ! -L ${arg[index-root]} && ${arg[index-root]} == "$(realpath "${arg[index-root]}")" ]] || {
  echo 'query index root capability is not an exact canonical path' >&2; exit 1;
}
index_root=$(realpath "${arg[index-root]}")
[[ -d $index_root ]] || { echo 'query index root is not exact' >&2; exit 1; }
[[ -f $index_root/index_disk.index && ! -L $index_root/index_disk.index ]] || { echo 'exact primer target absent/unsafe' >&2; exit 1; }
for key in query-binary query gt active-tags resource-probe query-worker; do
  [[ ${arg[$key]} == /* && ! -L ${arg[$key]} && ${arg[$key]} == "$(realpath "${arg[$key]}")" ]] || {
    echo "query capability input is not exact: $key" >&2; exit 1;
  }
  arg[$key]=$(realpath "${arg[$key]}"); [[ -f ${arg[$key]} ]] || { echo "query capability input unsafe: $key" >&2; exit 1; }
done
[[ -x ${arg[query-binary]} && -x ${arg[query-worker]} ]] || { echo 'query executable capability rejected' >&2; exit 1; }
stem=$(realpath -m "${arg[stem]}"); parent=$(dirname "$stem")
[[ -d $parent && $parent == "$(realpath "$parent")" && $(basename "$stem") =~ ^[A-Za-z0-9_.-]+$ ]] || { echo 'query output stem capability rejected' >&2; exit 1; }
primer="$stem.io_primer.json"; resources="$stem.resources.json"; ids="$stem.result_ids.bin"; log="$stem.log"
for output in "$primer" "$resources" "$ids" "$log" "$stem.metrics.json" "$stem.validation.json"; do
  [[ ! -e $output && ! -L $output ]] || { echo "query output reuse refused: $output" >&2; exit 1; }
done
[[ $(findmnt -rn -T "$index_root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${arg[device]}" ]] || { echo 'query index is not on expected device' >&2; exit 1; }

libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
systemd-run --scope --collect --unit "${arg[unit]}" --uid ubuntu \
  --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
  --property=IOAccounting=yes --property="MemoryMax=${arg[memory-max]}" --property=RuntimeMaxSec=1200 \
  env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH="$libs" \
    OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="${arg[device]}" \
  prlimit --core=0:0 -- numactl --physcpubind=0-23 --membind=0 \
    python3 "$new/w1_query_io_primer.py" --index-root "$index_root" --device "${arg[device]}" \
      --primer-report "$primer" --resources "$resources" --resource-probe "${arg[resource-probe]}" \
      --query-worker "${arg[query-worker]}" --system "${arg[system]}" --query-binary "${arg[query-binary]}" \
      --query "${arg[query]}" --gt "${arg[gt]}" --result-ids "$ids" --log "$log" \
      --l-value "${arg[l-value]}" --active-tags "${arg[active-tags]}"
[[ -s $primer && -s $resources && -s $ids && -s $log && -s $stem.metrics.json && -s $stem.validation.json ]] || {
  echo 'query scope completed without all expected artifacts' >&2; exit 1;
}
