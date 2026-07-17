#!/usr/bin/env bash
# Execute exactly one cumulative update delta against an already-published clone.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

usage() {
  cat >&2 <<'EOF'
usage: w1_cumulative_stage_worker.sh
  --mode replay|formal --system DGAI|OdinANN --stage cp01|cp05
  --attempt-dir DIR --full-corpus FILE --driver FILE --trace FILE
  --delta-manifest FILE --expected-count N --expected-before-tags FILE
  --delta-start N --forbidden-paths CSV
  --expected-after-tags FILE --combined-probes FILE --combined-probe-spec FILE
  --local-probe-spec FILE --global-probe-spec FILE
  --result-dir DIR --expected-scope UNIT.service --old-tools DIR --new-tools DIR

The caller must set W1_CUMULATIVE_STAGE_AUTHORIZED=1, W1_GLOBAL_LOCK_HELD=1,
W1_ALLOWED_CLONE_TARGET to ATTEMPT-DIR, and run this worker in EXPECTED-SCOPE.
EOF
  exit 2
}

declare -A arg=()
while (($#)); do
  case "$1" in
    --mode|--system|--stage|--attempt-dir|--full-corpus|--driver|--trace|--delta-manifest|--expected-count|--delta-start|--forbidden-paths|--expected-before-tags|--expected-after-tags|--combined-probes|--combined-probe-spec|--local-probe-spec|--global-probe-spec|--result-dir|--expected-scope|--old-tools|--new-tools)
      (($# >= 2)) || usage
      arg[${1#--}]=$2
      shift 2
      ;;
    *) usage ;;
  esac
done
for key in mode system stage attempt-dir full-corpus driver trace delta-manifest expected-count delta-start forbidden-paths expected-before-tags expected-after-tags combined-probes combined-probe-spec local-probe-spec global-probe-spec result-dir expected-scope old-tools new-tools; do
  [[ -n ${arg[$key]:-} ]] || usage
done

[[ ${W1_CUMULATIVE_STAGE_AUTHORIZED:-0} == 1 && ${W1_GLOBAL_LOCK_HELD:-0} == 1 ]] || {
  echo 'cumulative stage/global-lock capability absent' >&2; exit 64;
}
[[ ${arg[mode]} == replay || ${arg[mode]} == formal ]] || usage
[[ ${arg[system]} == DGAI || ${arg[system]} == OdinANN ]] || usage
[[ ${arg[stage]} == cp01 || ${arg[stage]} == cp05 ]] || usage
[[ ${arg[expected-count]} =~ ^[1-9][0-9]*$ ]] || usage
[[ ${arg[delta-start]} =~ ^[0-9]+$ ]] || usage
(( EUID == 1000 )) || { echo 'cumulative update worker must run as ubuntu' >&2; exit 1; }

attempt=$(realpath "${arg[attempt-dir]}")
allowed=$(realpath -m "${W1_ALLOWED_CLONE_TARGET:-/capability/absent}")
[[ $attempt == "$allowed" ]] || { echo 'stage worker clone capability mismatch' >&2; exit 1; }
prefix="$attempt/index/index"
[[ -d $attempt/index && -f ${prefix}_disk.index && -f ${prefix}_disk.index.tags ]] || {
  echo 'published clone/index is incomplete' >&2; exit 1;
}
result=$(realpath -m "${arg[result-dir]}")
allowed_result=$(realpath -m "${W1_CUMULATIVE_RESULT_ROOT:-/result/capability/absent}")
[[ $result == "$allowed_result/stages/${arg[stage]}" ]] || { echo 'stage result capability mismatch' >&2; exit 1; }
if [[ -e $result ]]; then
  [[ -d $result && -d $result/input_canary && ! -L $result/input_canary \
    && -f $result/input_canary/canary.json && -f $result/input_canary/canary.log ]] || {
    echo 'stage result lacks the exact R05 input-canary evidence' >&2; exit 1;
  }
  mapfile -t existing < <(find "$result" -mindepth 1 -maxdepth 2 -printf '%P\n' | sort)
  [[ ${existing[*]} == 'input_canary input_canary/canary.json input_canary/canary.log' ]] || {
    echo 'stage result contains state beyond the R05 input canary' >&2; exit 1;
  }
else
  echo 'stage result/input-canary directory absent' >&2; exit 1
fi

root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
device=${ATLAS_NVME_MAJMIN:-259:10}
for path in "$attempt" "$result"; do
  [[ $(findmnt -rn -T "$path" -o MAJ:MIN | awk 'NR==1{print;exit}') == "$device" ]] || {
    echo "stage path is not on project NVMe: $path" >&2; exit 1;
  }
done
scope=${arg[expected-scope]}
[[ $scope == *.service && $scope != */* ]] || usage
grep -Fq "/$scope" /proc/self/cgroup || { echo "worker is not in expected scope: $scope" >&2; exit 1; }

full=$(realpath "${arg[full-corpus]}")
driver=$(realpath "${arg[driver]}")
trace=$(realpath "${arg[trace]}")
delta_manifest=$(realpath "${arg[delta-manifest]}")
before_tags=$(realpath "${arg[expected-before-tags]}")
after_tags=$(realpath "${arg[expected-after-tags]}")
probes=$(realpath "${arg[combined-probes]}")
probe_spec=$(realpath "${arg[combined-probe-spec]}")
local_spec=$(realpath "${arg[local-probe-spec]}")
global_spec=$(realpath "${arg[global-probe-spec]}")
old=$(realpath "${arg[old-tools]}")
new=$(realpath "${arg[new-tools]}")
[[ -x $driver ]] || { echo 'driver is not executable' >&2; exit 1; }

# This precheck is intentionally inside the stage worker.  In particular, the
# cp05 worker proves that the persisted clone is still CP01 and that its input
# is the 320K (or replay 64-record) delta, never the cumulative prefix.
python3 - "$trace" "$delta_manifest" "${arg[expected-count]}" "${arg[delta-start]}" "$full" "$before_tags" "$after_tags" "$probes" "$probe_spec" "$local_spec" "$global_spec" "$result/worker_identity.json" "$scope" "${arg[mode]}" "${arg[system]}" "${arg[stage]}" "$attempt" "$new/w1_cumulative_stage_worker_r05.sh" "${arg[forbidden-paths]}" <<'PY'
import hashlib, json, os, stat, struct, sys, time
from pathlib import Path

(trace, manifest_path, count_text, start_text, full, before, after, probes, spec, local_spec, global_spec, output,
 scope, mode, system, stage, attempt, worker_binary, forbidden_csv) = sys.argv[1:]
paths = [Path(x) for x in (trace, manifest_path, full, before, after, probes, spec, local_spec, global_spec)]
count = int(count_text)
delta_start = int(start_text)
def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

opened = []
for path in paths:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit(f"non-regular stage input: {path}")
        opened.append({"realpath": str(path.resolve()), "device": info.st_dev,
                       "inode": info.st_ino, "size_bytes": info.st_size,
                       "sha256": sha(path) if info.st_size <= 128 * 1024 * 1024 else None,
                       "large_input_hash_bound_by_preflight": info.st_size > 128 * 1024 * 1024,
                       "opened_o_nofollow": True})
    finally:
        os.close(fd)

raw = Path(trace).read_bytes()
if len(raw) < 4 or struct.unpack_from("<I", raw)[0] != count or len(raw) != 4 + count * 8:
    raise SystemExit("stage trace count/layout mismatch")
manifest = json.loads(Path(manifest_path).read_text())
declared = next((manifest.get(k) for k in ("incremental_replacements", "replacement_count", "record_count", "operation_count")
                 if isinstance(manifest.get(k), int)), None)
if manifest.get("status", "pass") != "pass" or declared != count:
    raise SystemExit("delta manifest count/status mismatch")
if manifest.get("master_record_range") != [delta_start, delta_start + count]:
    raise SystemExit("delta manifest master record interval mismatch")
hashes = [manifest.get(k) for k in ("trace_sha256", "binary_trace_sha256", "delta_binary_sha256") if manifest.get(k)]
if isinstance(manifest.get("trace"), dict) and manifest["trace"].get("sha256"):
    hashes.append(manifest["trace"]["sha256"])
if not hashes or sha(trace) not in hashes:
    raise SystemExit("delta trace hash differs from manifest")
local_probe_identity = manifest.get("local_probes")
combined_probe_identity = manifest.get("combined_probes")
if not isinstance(local_probe_identity, dict):
    raise SystemExit("delta manifest lacks local probe identity")
if not isinstance(combined_probe_identity, dict):
    raise SystemExit("delta manifest lacks combined probe identity")
probe_hash_bindings = (
    ("local probe specification", local_probe_identity.get("json_sha256"), sha(local_spec)),
    ("combined probe binary", combined_probe_identity.get("binary_sha256"), sha(probes)),
    ("combined probe specification", combined_probe_identity.get("json_sha256"), sha(spec)),
    ("combined global source specification", combined_probe_identity.get("global_source_spec_sha256"), sha(global_spec)),
)
for label, declared_hash, observed_hash in probe_hash_bindings:
    if not isinstance(declared_hash, str) or declared_hash != observed_hash:
        raise SystemExit(f"{label} hash differs from delta manifest")
if stage == "cp05" and mode == "formal" and count != 320_000:
    raise SystemExit("formal CP05 worker must consume exactly the 320K delta")
if stage == "cp01" and mode == "formal" and count != 80_000:
    raise SystemExit("formal CP01 worker must consume exactly 80K")
if stage == "cp05" and ("400k" in Path(trace).name.lower() or "master" in Path(trace).name.lower()):
    raise SystemExit("CP05 worker refuses a cumulative/master trace pathname")

with Path(probes).open("rb") as stream:
    qn, qd = struct.unpack("<II", stream.read(8))
if qn != 36 or qd <= 0 or Path(probes).stat().st_size != 8 + qn * qd * 4:
    raise SystemExit("combined local/global probes must be 36 float32 rows")
payload = json.loads(Path(spec).read_text())
rows = payload.get("probes")
groups = payload.get("groups")
if not isinstance(rows, list) or len(rows) != 36 or not isinstance(groups, list) or len(groups) != 2:
    raise SystemExit("combined probe spec lacks 36 rows/local-global groups")
by_name = {group.get("name"): group for group in groups if isinstance(group, dict)}
if (by_name.get("local", {}).get("row_range") != [0, 18]
        or by_name.get("global", {}).get("row_range") != [18, 36]):
    raise SystemExit("combined probes must be local[0:18] then global[18:36]")
def semantic(row):
    return {key: row.get(key) for key in ("op_seq", "kind", "query_tag", "expected_tag", "forbidden_tag")}
local_rows = json.loads(Path(local_spec).read_text()).get("probes")
global_rows = json.loads(Path(global_spec).read_text()).get("probes")
if (not isinstance(local_rows, list) or not isinstance(global_rows, list)
        or len(local_rows) != 18 or len(global_rows) != 18
        or [semantic(x) for x in rows[:18]] != [semantic(x) for x in local_rows]
        or [semantic(x) for x in rows[18:]] != [semantic(x) for x in global_rows]):
    raise SystemExit("combined probes are not semantic local+global concatenation")

forbidden = []
for item in (x for x in forbidden_csv.split(",") if x):
    path = Path(item)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except PermissionError as exc:
        forbidden.append({"path": str(path), "open_refused": True, "errno": exc.errno})
    else:
        os.close(fd)
        raise SystemExit(f"scope failed to hide forbidden cumulative input: {path}")

worker_pid = os.getppid()
proc_stat = Path(f"/proc/{worker_pid}/stat").read_text().split()
cmdline = Path(f"/proc/{worker_pid}/cmdline").read_bytes().split(b"\0")
worker_path = Path(worker_binary).resolve(strict=True)
report = {"schema": "dynamic-vamana-w1-cumulative-stage-worker-identity-v1",
          "status": "pass", "mode": mode, "system": system, "stage": stage,
          "checkpoint": stage, "worker_pid": worker_pid, "worker_starttime_ticks": int(proc_stat[21]),
          "worker_argv": [x.decode(errors="surrogateescape") for x in cmdline if x],
          "worker_binary_realpath": str(worker_path), "worker_binary_sha256": sha(worker_path),
          "expected_scope": scope, "cgroup": Path("/proc/self/cgroup").read_text().splitlines(),
          "attempt_realpath": str(Path(attempt).resolve()), "clone_realpath": str((Path(attempt)/"index").resolve()),
          "prefix_realpath": str((Path(attempt)/"index/index").resolve()),
          "delta_realpath": str(Path(trace).resolve()), "delta_sha256": sha(trace),
          "delta_start": delta_start, "delta_count": count,
          "incremental_replacements": count, "primitive_mutations": 2 * count,
          "input_open_evidence": opened, "forbidden_input_open_evidence": forbidden,
          "recorded_unix_ns": time.time_ns()}
Path(output).write_text(json.dumps(report, indent=2) + "\n")
PY

python3 "$old/w1_dump_active_tags.py" --tags "${prefix}_disk.index.tags" --expected "$before_tags" \
  --expected-count "$(python3 -c 'import struct,sys; print(struct.unpack("<I",open(sys.argv[1],"rb").read(4))[0])' "$before_tags")" \
  --output "$result/pre_stage_active_audit.json"

markers="$result/markers.jsonl"
libs="$root/build/gperftools-install/lib:$root/build/openblas-install/lib:$root/build/jemalloc-install/lib"
export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 ATLAS_W1_MARKERS="$markers"

case "${arg[system]}" in
  DGAI)
    "$driver" run "$full" "$prefix" "$trace"
    ;;
  OdinANN)
    "$driver" run "$full" "$prefix" "$trace" "$probes" "$result/online.bin"
    ;;
esac
python3 "$old/w1_marker.py" --output "$markers" --name fresh_process_probe_begin
"$driver" probe "$prefix" "$probes" "$result/fresh.bin"
python3 "$old/w1_marker.py" --output "$markers" --name fresh_process_visibility_verified

python3 "$old/w1_dump_active_tags.py" --tags "${prefix}_disk.index.tags" --expected "$after_tags" \
  --expected-count "$(python3 -c 'import struct,sys; print(struct.unpack("<I",open(sys.argv[1],"rb").read(4))[0])' "$after_tags")" \
  --output "$result/active_audit.json"
python3 "$old/w1_visibility_probe.py" --probes "$probe_spec" --result-tags "$result/fresh.bin" \
  --active-tags "$after_tags" --output "$result/fresh_probe.json"
if [[ ${arg[system]} == OdinANN ]]; then
  python3 "$old/w1_visibility_probe.py" --probes "$probe_spec" --result-tags "$result/online.bin" \
    --active-tags "$after_tags" --output "$result/online_probe.json"
fi

touch "$result/STAGE_WORKER_OK"
