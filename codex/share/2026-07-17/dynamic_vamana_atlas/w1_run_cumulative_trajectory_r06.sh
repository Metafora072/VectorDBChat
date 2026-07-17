#!/usr/bin/env bash
# R06-only shared CP00 -> CP01 -> CP05 state machine for DGAI and OdinANN.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

usage() {
  cat >&2 <<'EOF'
usage: w1_run_cumulative_trajectory.sh
  --mode replay|formal --system DGAI|OdinANN --run-name NAME --attempt NAME
  --base-index DIR --dataset-dir DIR --full-corpus FILE
  --driver FILE --query-binary FILE --artifact-manifest FILE
  --cp00-query FILE --cp00-gt FILE --cp00-active FILE
  --cp01-trace FILE --cp01-delta-manifest FILE --cp01-count N
  --cp01-query FILE --cp01-gt FILE --cp01-active FILE
  --cp01-local-probes FILE --cp01-local-probe-spec FILE
  --cp01-global-probes FILE --cp01-global-probe-spec FILE
  --cp01-combined-probes FILE --cp01-combined-probe-spec FILE
  --cp01-inaccessible CSV
  --cp05-trace FILE --cp05-delta-manifest FILE --cp05-count N
  --cp05-query FILE --cp05-gt FILE --cp05-active FILE
  --cp05-local-probes FILE --cp05-local-probe-spec FILE
  --cp05-global-probes FILE --cp05-global-probe-spec FILE
  --cp05-combined-probes FILE --cp05-combined-probe-spec FILE
  --cp05-inaccessible CSV
  --ls CSV --io-engine NAME --old-tools DIR --new-tools DIR
  --evidence-tool FILE

Targets are derived, never accepted as free paths.  Replay evidence is nested
under the formal run's results/replay subtree as required by the gate.

w1_cumulative_evidence.py interface used here:
  query-gate  --mode --system --checkpoint --result-dir --prefix --binary
              --driver --artifact-manifest --index-content-manifest --query --gt --active-tags --ls
              --repeats --threads --io-engine --device --expected-nq
              --expected-k --expected-active-count --output
  stage-evidence --mode --system --checkpoint --attempt-dir --index-root
              --stage-result --stage-resources --trace --delta-manifest
              --expected-active --local-probe-spec --global-probe-spec
              --combined-probe-spec --fresh-result [--online-result]
              --controller-log --input-capability-canary --device --output
  checkpoint  --mode --system --checkpoint --attempt-dir --index-root
              --stage-evidence --query-gate --state-content-manifest
              --state-mode-manifest --base-content-manifest
              --base-mode-manifest --output-dir
  freeze      --mode --system --attempt-dir --index-root --owner
              --checkpoint-evidence --output-dir
EOF
  exit 2
}

declare -A arg=()
while (($#)); do
  case "$1" in
    --mode|--system|--run-name|--attempt|--base-index|--dataset-dir|--full-corpus|--driver|--query-binary|--artifact-manifest|--cp00-query|--cp00-gt|--cp00-active|--cp01-trace|--cp01-delta-manifest|--cp01-count|--cp01-query|--cp01-gt|--cp01-active|--cp01-local-probes|--cp01-local-probe-spec|--cp01-global-probes|--cp01-global-probe-spec|--cp01-combined-probes|--cp01-combined-probe-spec|--cp01-inaccessible|--cp05-trace|--cp05-delta-manifest|--cp05-count|--cp05-query|--cp05-gt|--cp05-active|--cp05-local-probes|--cp05-local-probe-spec|--cp05-global-probes|--cp05-global-probe-spec|--cp05-combined-probes|--cp05-combined-probe-spec|--cp05-inaccessible|--ls|--io-engine|--old-tools|--new-tools|--evidence-tool)
      (($# >= 2)) || usage
      arg[${1#--}]=$2
      shift 2
      ;;
    *) usage ;;
  esac
done

required=(mode system run-name attempt base-index dataset-dir full-corpus driver query-binary artifact-manifest
  cp00-query cp00-gt cp00-active
  cp01-trace cp01-delta-manifest cp01-count cp01-query cp01-gt cp01-active
  cp01-local-probes cp01-local-probe-spec cp01-global-probes cp01-global-probe-spec cp01-combined-probes cp01-combined-probe-spec cp01-inaccessible
  cp05-trace cp05-delta-manifest cp05-count cp05-query cp05-gt cp05-active
  cp05-local-probes cp05-local-probe-spec cp05-global-probes cp05-global-probe-spec cp05-combined-probes cp05-combined-probe-spec cp05-inaccessible
  ls io-engine old-tools new-tools evidence-tool)
for key in "${required[@]}"; do [[ -n ${arg[$key]:-} ]] || usage; done

[[ ${W1_CP05_R06_CUMULATIVE_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || {
  echo 'R06 cumulative trajectory/global-lock capability absent' >&2; exit 64;
}
(( EUID == 0 )) || { echo 'cumulative runner must run as root' >&2; exit 1; }
[[ ${arg[mode]} == replay || ${arg[mode]} == formal ]] || usage
[[ ${arg[system]} == DGAI || ${arg[system]} == OdinANN ]] || usage
for component in run-name attempt; do
  [[ ${arg[$component]} != */* && ${arg[$component]} != . && ${arg[$component]} != .. ]] || usage
done
[[ ${arg[cp01-count]} =~ ^[1-9][0-9]*$ && ${arg[cp05-count]} =~ ^[1-9][0-9]*$ ]] || usage
if [[ ${arg[mode]} == formal ]]; then
  [[ ${arg[cp01-count]} == 80000 && ${arg[cp05-count]} == 320000 ]] || {
    echo 'formal cumulative counts must be 80K then 320K delta' >&2; exit 1;
  }
  [[ ${arg[run-name]} == pilot3_sift10m_w1_cp05_trajectory_r06 && ${arg[attempt]} == trajectory-cp05-06 ]] || {
    echo 'R06 formal run/attempt identity mismatch' >&2; exit 1;
  }
else
  [[ ${arg[cp01-count]} == 16 && ${arg[cp05-count]} == 64 ]] || {
    echo 'sequential replay counts must be 16 then 64 delta' >&2; exit 1;
  }
  [[ ${arg[run-name]} == pilot3_w1_cp05_trajectory_replay_r06 && ${arg[attempt]} == sequential-cp80-06 ]] || {
    echo 'R06 replay run/attempt identity mismatch' >&2; exit 1;
  }
fi

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
old=$(realpath "${arg[old-tools]}")
new=$(realpath "${arg[new-tools]}")
r02=${ATLAS_W1_R02_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas}
evidence=$(realpath "${arg[evidence-tool]}")
[[ -f $evidence && -x $new/w1_cumulative_stage_worker_r06.sh \
  && -x $new/w1_run_query_scope.sh && -x $new/w1_input_canary.py \
  && -x $new/w1_stage_io_primer.py ]] || {
  echo 'cumulative helper missing' >&2; exit 1;
}
base=$(realpath "${arg[base-index]}")
dataset=$(realpath "${arg[dataset-dir]}")
full=$(realpath "${arg[full-corpus]}")
driver=$(realpath "${arg[driver]}")
query_binary=$(realpath "${arg[query-binary]}")
artifact=$(realpath "${arg[artifact-manifest]}")
work=$(realpath -m "$root/formal/${arg[run-name]}/${arg[system]}/${arg[attempt]}")
if [[ ${arg[mode]} == formal ]]; then
  result=$(realpath -m "$root/results/pilot3_sift10m_w1_cp05_trajectory_r06/${arg[system]}/${arg[attempt]}")
else
  result=$(realpath -m "$root/results/pilot3_sift10m_w1_cp05_trajectory_r06/replay/${arg[system]}/${arg[attempt]}")
fi
expected_work="$root/formal/${arg[run-name]}/${arg[system]}/${arg[attempt]}"
if [[ ${arg[mode]} == formal ]]; then expected_result="$root/results/pilot3_sift10m_w1_cp05_trajectory_r06/${arg[system]}/${arg[attempt]}"
else expected_result="$root/results/pilot3_sift10m_w1_cp05_trajectory_r06/replay/${arg[system]}/${arg[attempt]}"; fi
[[ $work == "$expected_work" && $result == "$expected_result" ]] || { echo 'derived target has a symlink escape' >&2; exit 1; }
if [[ ${arg[mode]} == replay ]]; then
  expected_base="$root/formal/pilot3_w1_cp05_replay_bases_v1/${arg[system]}/cp00/index"
elif [[ ${arg[system]} == DGAI ]]; then
  expected_base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index"
else
  expected_base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index"
fi
[[ $base == "$expected_base" ]] || { echo "R06 base identity mismatch: $base" >&2; exit 1; }
[[ ! -e $work && ! -e $result ]] || { echo 'cumulative attempt/result reuse refused' >&2; exit 1; }
[[ -x $driver && -x $query_binary ]] || { echo 'driver/query binary is not executable' >&2; exit 1; }
[[ $(findmnt -rn -T "$root" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || {
  echo 'experiment root is not project NVMe' >&2; exit 1;
}

all_files=(full-corpus artifact-manifest cp00-query cp00-gt cp00-active
  cp01-trace cp01-delta-manifest cp01-query cp01-gt cp01-active cp01-local-probes cp01-local-probe-spec
  cp01-global-probes cp01-global-probe-spec cp01-combined-probes cp01-combined-probe-spec
  cp05-trace cp05-delta-manifest cp05-query cp05-gt cp05-active cp05-local-probes cp05-local-probe-spec
  cp05-global-probes cp05-global-probe-spec cp05-combined-probes cp05-combined-probe-spec)
for key in "${all_files[@]}"; do [[ -f ${arg[$key]} ]] || { echo "missing input: ${arg[$key]}" >&2; exit 1; }; done

install -d -o ubuntu -g ubuntu "$(dirname "$work")" "$(dirname "$result")"
export W1_FORMAL_PATH_AUTHORIZED=1 W1_CLONE_PREFLIGHT_ONLY=0 W1_MUTABLE_CLONE_OWNER=ubuntu
export W1_ALLOWED_CLONE_TARGET="$work" W1_ALLOWED_CLONE_SYSTEM="${arg[system]}"
export W1_ALLOWED_CLONE_RUN="${arg[run-name]}" W1_ALLOWED_CLONE_ATTEMPT="${arg[attempt]}"
export ATLAS_W1_MUTABLE_CHAT="$r02"
if [[ ${arg[mode]} == replay ]]; then
  clone_helper="$new/w1_clone_replay_base_r06.sh"
else
  clone_helper="$old/w1_clone_base.sh"
fi
"$clone_helper" "${arg[system]}" "$base" "$work"
[[ -d $work/index && -f $work/clone_manifest.json ]] || { echo 'initial clone did not publish' >&2; exit 1; }
install -d -m 0700 -o ubuntu -g ubuntu "$result"
install -d -m 0700 -o ubuntu -g ubuntu "$result/queries" "$result/stages" "$result/checkpoints"

libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
system_lower=${arg[system],,}
if [[ ${arg[mode]} == replay ]]; then
  stage_memory=8G; query_memory=8G
elif [[ ${arg[system]} == DGAI ]]; then
  stage_memory=32G; query_memory=24G
else
  stage_memory=32G; query_memory=16G
fi
IFS=, read -r -a query_ls <<<"${arg[ls]}"
for value in "${query_ls[@]}"; do [[ $value =~ ^[1-9][0-9]*$ ]] || usage; done
(( ${#query_ls[@]} >= 1 )) || usage

file_manifest() {
  python3 "$old/w1_file_manifest.py" --root "$1" --output "$2"
}
mode_manifest() {
  python3 "$r02/w1_mode_manifest.py" write --root "$1" --output "$2"
}
assert_base_exact() {
  local checkpoint=$1 out="$result/stages/$1"
  mkdir -p "$out"
  file_manifest "$base" "$out/base_content_after.tsv"
  mode_manifest "$base" "$out/base_mode_after.tsv"
  cmp -s "$work/base_content_before.tsv" "$out/base_content_after.tsv" || { echo "$checkpoint changed immutable base content" >&2; exit 1; }
  cmp -s "$work/base_mode_before.tsv" "$out/base_mode_after.tsv" || { echo "$checkpoint changed immutable base mode" >&2; exit 1; }
}

query_checkpoint() {
  local checkpoint=$1 query=$2 gt=$3 active=$4 index_manifest=$5
  local qdir="$result/queries/$checkpoint"
  install -d -o ubuntu -g ubuntu "$qdir"
  for l in "${query_ls[@]}"; do
    for repetition in 1 2 3; do
      local stem="$qdir/${checkpoint}_L${l}_r${repetition}"
      local unit="dv-w1-cum-r03-r06-${arg[mode]}-${system_lower}-${checkpoint}-l${l}-r${repetition}"
      W1_CP05_R03_CUMULATIVE_AUTHORIZED=1 "$new/w1_run_query_scope.sh" \
        --unit "$unit" --system "${arg[system]}" \
        --index-root "$work/index" --query-binary "$query_binary" --query "$query" --gt "$gt" \
        --active-tags "$active" --stem "$stem" --l-value "$l" --memory-max "$query_memory" \
        --resource-probe "$old/resource_probe.py" --query-worker "$old/w1_query_worker.sh" --device "$device"
    done
  done
  read -r query_n _ < <(python3 - "$query" <<'PY'
import struct,sys
print(*struct.unpack("<II",open(sys.argv[1],"rb").read(8)))
PY
)
  active_n=$(python3 -c 'import struct,sys; print(struct.unpack("<I",open(sys.argv[1],"rb").read(4))[0])' "$active")
  runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" query-gate \
    --mode "${arg[mode]}" --system "${arg[system]}" --checkpoint "$checkpoint" \
    --result-dir "$qdir" --prefix "$checkpoint" --binary "$query_binary" --driver "$driver" \
    --artifact-manifest "$artifact" --index-content-manifest "$index_manifest" --query "$query" --gt "$gt" --active-tags "$active" \
    --ls "${arg[ls]}" --repeats 1,2,3 --threads 1 --io-engine "${arg[io-engine]}" --device "$device" \
    --expected-nq "$query_n" --expected-k 10 --expected-active-count "$active_n" --output "$qdir/query_gate.json"
}

state_before_query() {
  local checkpoint=$1 dir="$result/checkpoints/$1"
  install -d -o ubuntu -g ubuntu "$dir"
  file_manifest "$work/index" "$dir/${checkpoint}_state_content_manifest.tsv"
  mode_manifest "$work/index" "$dir/${checkpoint}_state_mode_manifest.tsv"
}

assert_query_read_only() {
  local checkpoint=$1 dir="$result/checkpoints/$1" after="$result/stages/$1"
  mkdir -p "$after"
  file_manifest "$work/index" "$after/index_content_after_query.tsv"
  mode_manifest "$work/index" "$after/index_mode_after_query.tsv"
  cmp -s "$dir/${checkpoint}_state_content_manifest.tsv" "$after/index_content_after_query.tsv" || { echo "$checkpoint query changed index content" >&2; exit 1; }
  cmp -s "$dir/${checkpoint}_state_mode_manifest.tsv" "$after/index_mode_after_query.tsv" || { echo "$checkpoint query changed index mode" >&2; exit 1; }
}

stage_health_guard() {
  local threshold=$((64 * 1024 * 1024 * 1024))
  if [[ ${arg[mode]} == formal && ${arg[system]} == OdinANN ]]; then threshold=$((96 * 1024 * 1024 * 1024)); fi
  local free available
  free=$(df -PB1 "$root" | awk 'NR==2{print $4}')
  available=$(awk '/^MemAvailable:/{print $2*1024}' /proc/meminfo)
  (( free >= threshold )) || { echo "stage free-space guard failed: $free < $threshold" >&2; exit 1; }
  (( available >= 64 * 1024 * 1024 * 1024 )) || { echo "stage MemAvailable guard failed: $available" >&2; exit 1; }
}

inaccessible_canary() {
  local checkpoint=$1 allowed=$2 csv=$3
  local -a denied=() properties=()
  IFS=, read -r -a denied <<<"$csv"
  ((${#denied[@]} >= 1)) || { echo "$checkpoint inaccessible list is empty" >&2; exit 1; }
  local item canonical joined=
  for item in "${denied[@]}"; do
    canonical=$(realpath "$item")
    [[ $canonical != "$allowed" ]] || { echo "$checkpoint hides its own delta" >&2; exit 1; }
    denied[${#properties[@]}]=$canonical
    properties+=("--property=InaccessiblePaths=$canonical")
    joined+="${joined:+,}$canonical"
  done
  local canary_dir="$result/stages/$checkpoint/input_canary"
  local output="$canary_dir/canary.json" log="$canary_dir/canary.log"
  local unit="dv-w1-cum-r06-${arg[mode]}-${system_lower}-${checkpoint}-input-canary"
  install -d -m 0700 -o ubuntu -g ubuntu "$result/stages/$checkpoint" "$canary_dir"
  touch "$log"; chown ubuntu:ubuntu "$log"; chmod 0600 "$log"
  local -a canary_args=(python3 "$new/w1_input_canary.py" --allowed "$allowed" --output "$output")
  for item in "${denied[@]}"; do canary_args+=(--denied "$item"); done
  systemd-run --wait --collect --pipe --unit "$unit" --uid ubuntu --property=Type=exec \
    --property=AllowedCPUs=0 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
    --property=IOAccounting=yes --property=MemoryMax=256M --property=LimitCORE=0 --property=RuntimeMaxSec=60 \
    "${properties[@]}" \
    env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
      "${canary_args[@]}" >>"$log" 2>&1
  [[ -f $output ]] || { echo "$checkpoint inaccessible canary evidence absent" >&2; exit 1; }
  [[ ! -e $result/stages/$checkpoint/STAGE_WORKER_OK \
    && ! -e $result/stages/$checkpoint/markers.jsonl ]] || {
    echo "$checkpoint update marker exists before canary completion" >&2; exit 1;
  }
  chmod 0444 "$output" "$log"
  printf '%s' "$joined"
}

collect_stage() {
  local checkpoint=$1 count=$2 trace=$3 delta_manifest=$4 local_spec=$5 global_spec=$6 combined_spec=$7
  local stage_result="$result/stages/$checkpoint" resource="$result/${checkpoint}_stage_resources.json"
  local primer="$result/${checkpoint}_stage_io_primer.json"
  local before after
  read -r before after < <(python3 - "$resource" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); before=d["space_before"]["apparent_bytes"]
samples=d["samples"]; final=next((x.get("index_space") for x in reversed(samples) if x.get("index_space") is not None),None)
if final is None: raise SystemExit("stage resource lacks final space sample")
print(before,final["apparent_bytes"])
PY
)
  python3 "$old/w1_collect_canary.py" --system "${arg[system]}" --markers "$stage_result/markers.jsonl" \
    --resources "$resource" --active-audit "$stage_result/active_audit.json" --probe "$stage_result/fresh_probe.json" \
    --logical-replacements "$count" --logical-payload-bytes "$((count * 128 * 4))" \
    --index-before-bytes "$before" --index-after-bytes "$after" --device "$device" \
    --output "$stage_result/legacy_canary.json"
  python3 - "$result/${checkpoint}_controller.log" "$result/stages/$checkpoint/input_canary/canary.json" <<'PY'
import json,re,sys
log=open(sys.argv[1],errors='replace').read(); canary=json.load(open(sys.argv[2]))
if re.search(r'fatal|assert(?:ion)?(?: failed)?|EBADF|negative CQE|I/O error|segmentation fault|core dumped|std::bad_alloc|out of memory|oom-kill|killed process',log,re.I):
 raise SystemExit('fatal/assert/I/O/OOM signature in stage controller log')
if canary.get('status')!='pass' or not canary.get('denied') or not all(x.get('open_refused') for x in canary['denied']):
 raise SystemExit('stage inaccessible-input canary invalid')
PY
  local -a evidence_args=(runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" stage-evidence
    --mode "${arg[mode]}" --system "${arg[system]}"
    --checkpoint "$checkpoint" --attempt-dir "$work" --index-root "$work/index" --stage-result "$stage_result"
    --stage-resources "$resource" --trace "$trace" --delta-manifest "$delta_manifest"
    --expected-active "$([[ $checkpoint == cp01 ]] && realpath "${arg[cp01-active]}" || realpath "${arg[cp05-active]}")"
    --local-probe-spec "$local_spec" --global-probe-spec "$global_spec" --combined-probe-spec "$combined_spec"
    --fresh-result "$stage_result/fresh.bin" --controller-log "$result/${checkpoint}_controller.log"
    --input-capability-canary "$result/stages/$checkpoint/input_canary/canary.json"
    --device "$device" --output "$stage_result/stage_evidence.json")
  if [[ ${arg[system]} == OdinANN ]]; then evidence_args+=(--online-result "$stage_result/online.bin"); fi
  "${evidence_args[@]}"
}

run_stage() {
  local checkpoint=$1 before_active=$2 after_active=$3 trace=$4 delta_manifest=$5 count=$6
  local combined_probes=$7 combined_spec=$8
  local local_key="${checkpoint}-local-probe-spec" global_key="${checkpoint}-global-probe-spec"
  local local_spec global_spec
  local_spec=${arg[$local_key]}; global_spec=${arg[$global_key]}
  local stage_result="$result/stages/$checkpoint" resource="$result/${checkpoint}_stage_resources.json"
  local unit="dv-w1-cum-r06-${arg[mode]}-${system_lower}-${checkpoint}-update"
  local inaccessible_key="${checkpoint}-inaccessible" inaccessible_csv
  inaccessible_csv=${arg[$inaccessible_key]}
  [[ ! -e $stage_result && ! -e $resource && ! -e $primer ]] || { echo "$checkpoint stage freshness failed" >&2; exit 1; }
  stage_health_guard
  inaccessible_csv=$(inaccessible_canary "$checkpoint" "$trace" "$inaccessible_csv")
  local -a inaccessible_properties=()
  IFS=, read -r -a inaccessible_rows <<<"$inaccessible_csv"
  for item in "${inaccessible_rows[@]}"; do inaccessible_properties+=("--property=InaccessiblePaths=$item"); done
  systemd-run --wait --collect --pipe --unit "$unit" --uid ubuntu --property=Type=exec \
    --property=AllowedCPUs=0-23 --property=CPUAccounting=yes --property=MemoryAccounting=yes \
    --property=IOAccounting=yes --property="MemoryMax=$stage_memory" --property=LimitCORE=0 --property=RuntimeMaxSec=2700 \
    "${inaccessible_properties[@]}" \
    env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH="$libs" \
      W1_CUMULATIVE_STAGE_AUTHORIZED=1 W1_GLOBAL_LOCK_HELD=1 W1_ALLOWED_CLONE_TARGET="$work" \
      W1_CUMULATIVE_RESULT_ROOT="$result" \
      ATLAS_ROOT="$root" ATLAS_NVME_MAJMIN="$device" \
    numactl --physcpubind=0-23 --membind=0 \
      timeout --signal=TERM --kill-after=30s 45m \
      python3 "$new/w1_stage_io_primer.py" --index-root "$work/index" --device "$device" \
        --primer-report "$primer" --resources "$resource" --resource-probe "$old/resource_probe.py" \
        --space-root "$work/index" -- \
      "$new/w1_cumulative_stage_worker_r06.sh" --mode "${arg[mode]}" --system "${arg[system]}" --stage "$checkpoint" \
        --attempt-dir "$work" --full-corpus "$full" --driver "$driver" --trace "$trace" \
        --delta-manifest "$delta_manifest" --expected-count "$count" \
        --delta-start "$([[ $checkpoint == cp01 ]] && echo 0 || echo "${arg[cp01-count]}")" --forbidden-paths "$inaccessible_csv" \
        --expected-before-tags "$before_active" \
        --expected-after-tags "$after_active" --combined-probes "$combined_probes" --combined-probe-spec "$combined_spec" \
        --local-probe-spec "$local_spec" --global-probe-spec "$global_spec" \
        --result-dir "$stage_result" --expected-scope "$unit.service" --old-tools "$old" --new-tools "$new" \
        >>"$result/${checkpoint}_controller.log" 2>&1
  python3 - "$primer" "$resource" "$device" "$work/index/index_disk.index" "$unit.service" <<'PY'
import json,sys
from pathlib import Path
primer_path,resources_path,device,target,scope=map(Path,sys.argv[1:])
p=json.loads(primer_path.read_text()); r=json.loads(resources_path.read_text())
if (p.get("schema")!="dynamic-vamana-w1-stage-io-primer-v1" or p.get("status")!="pass"
    or p.get("bytes_read")!=4096 or not p.get("direct_io")
    or not p.get("resource_probe_started_after_primer")
    or not p.get("primer_excluded_from_stage_deltas")):
 raise SystemExit("stage I/O primer report invalid")
if Path(p.get("prime_file",{}).get("realpath","")).resolve()!=target.resolve():
 raise SystemExit("stage primer did not target the current private clone")
if not any(f"/{scope}" in row for row in p.get("cgroup",[])):
 raise SystemExit("stage primer was not executed in the update scope")
samples=r.get("samples",[])
if not samples:
 raise SystemExit("stage resource probe has no samples")
def row(sample):
 return next((x for x in sample.get("cgroup_io_stat",[]) if x.get("device")==str(device)),None)
first,final=row(samples[0]),row(samples[-1])
if first is None or final is None or first.get("rbytes",0)<4096:
 raise SystemExit("target device does not bracket the stage resource samples")
if any(final.get(k,0)<first.get(k,0) for k in ("rbytes","wbytes","rios","wios")):
 raise SystemExit("final target-device counters precede the primer baseline")
PY
  [[ -f $stage_result/STAGE_WORKER_OK ]] || { echo "$checkpoint worker marker absent" >&2; exit 1; }
}

checkpoint_evidence() {
  local checkpoint=$1 content_manifest=$2 mode_manifest=$3
  local checkpoint_dir="$result/checkpoints/$checkpoint" stage_result="$result/stages/$checkpoint"
  runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" checkpoint \
    --mode "${arg[mode]}" --system "${arg[system]}" --checkpoint "$checkpoint" \
    --attempt-dir "$work" --index-root "$work/index" --stage-evidence "$stage_result/stage_evidence.json" \
    --query-gate "$result/queries/$checkpoint/query_gate.json" --state-content-manifest "$content_manifest" \
    --state-mode-manifest "$mode_manifest" --base-content-manifest "$work/base_content_before.tsv" \
    --base-mode-manifest "$work/base_mode_before.tsv" --output-dir "$checkpoint_dir"
}

# The CP00 query is part of the same state machine in both replay and formal
# modes.  It is read-only and is audited before any delta is accepted.
state_before_query cp00
query_checkpoint cp00 "$(realpath "${arg[cp00-query]}")" "$(realpath "${arg[cp00-gt]}")" \
  "$(realpath "${arg[cp00-active]}")" "$result/checkpoints/cp00/cp00_state_content_manifest.tsv"
assert_query_read_only cp00

# Worker 1: CP00 -> CP01.  Worker 2 below is necessarily a new process and
# must reload this same published realpath after proving persisted CP01 tags.
run_stage cp01 "$(realpath "${arg[cp00-active]}")" "$(realpath "${arg[cp01-active]}")" \
  "$(realpath "${arg[cp01-trace]}")" "$(realpath "${arg[cp01-delta-manifest]}")" "${arg[cp01-count]}" \
  "$(realpath "${arg[cp01-combined-probes]}")" "$(realpath "${arg[cp01-combined-probe-spec]}")"
collect_stage cp01 "${arg[cp01-count]}" "$(realpath "${arg[cp01-trace]}")" "$(realpath "${arg[cp01-delta-manifest]}")" \
  "$(realpath "${arg[cp01-local-probe-spec]}")" "$(realpath "${arg[cp01-global-probe-spec]}")" \
  "$(realpath "${arg[cp01-combined-probe-spec]}")"
assert_base_exact cp01
state_before_query cp01
query_checkpoint cp01 "$(realpath "${arg[cp01-query]}")" "$(realpath "${arg[cp01-gt]}")" \
  "$(realpath "${arg[cp01-active]}")" "$result/checkpoints/cp01/cp01_state_content_manifest.tsv"
assert_query_read_only cp01
checkpoint_evidence cp01 "$result/checkpoints/cp01/cp01_state_content_manifest.tsv" \
  "$result/checkpoints/cp01/cp01_state_mode_manifest.tsv"
for file in cp01_state_content_manifest.tsv cp01_state_mode_manifest.tsv cp01_active_audit.json cp01_query_summary.tsv cp01_checkpoint_evidence.json; do
  [[ -f $result/checkpoints/cp01/$file ]] || { echo "CP01 evidence missing: $file" >&2; exit 1; }
  chmod a-w "$result/checkpoints/cp01/$file"
done

run_stage cp05 "$(realpath "${arg[cp01-active]}")" "$(realpath "${arg[cp05-active]}")" \
  "$(realpath "${arg[cp05-trace]}")" "$(realpath "${arg[cp05-delta-manifest]}")" "${arg[cp05-count]}" \
  "$(realpath "${arg[cp05-combined-probes]}")" "$(realpath "${arg[cp05-combined-probe-spec]}")"
collect_stage cp05 "${arg[cp05-count]}" "$(realpath "${arg[cp05-trace]}")" "$(realpath "${arg[cp05-delta-manifest]}")" \
  "$(realpath "${arg[cp05-local-probe-spec]}")" "$(realpath "${arg[cp05-global-probe-spec]}")" \
  "$(realpath "${arg[cp05-combined-probe-spec]}")"
assert_base_exact cp05
state_before_query cp05
query_checkpoint cp05 "$(realpath "${arg[cp05-query]}")" "$(realpath "${arg[cp05-gt]}")" \
  "$(realpath "${arg[cp05-active]}")" "$result/checkpoints/cp05/cp05_state_content_manifest.tsv"
assert_query_read_only cp05
checkpoint_evidence cp05 "$result/checkpoints/cp05/cp05_state_content_manifest.tsv" \
  "$result/checkpoints/cp05/cp05_state_mode_manifest.tsv"
runuser -u ubuntu -- env PYTHONDONTWRITEBYTECODE=1 python3 "$evidence" freeze --mode "${arg[mode]}" \
  --system "${arg[system]}" --attempt-dir "$work" --index-root "$work/index" --owner ubuntu \
  --checkpoint-evidence "$result/checkpoints/cp05/cp05_checkpoint_evidence.json" --output-dir "$result/checkpoints/cp05"
[[ -f $work/IMMUTABLE_TRAJECTORY_CP05_OK ]] || { echo 'final immutable marker absent' >&2; exit 1; }
assert_base_exact cp05_final
touch "$result/CUMULATIVE_TRAJECTORY_OK"
