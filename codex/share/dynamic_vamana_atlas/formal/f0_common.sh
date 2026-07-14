#!/usr/bin/env bash
# Shared guarded launcher for the approved three-system SIFT10M F0 readiness.
# It is sourced by f0_{diskann,dgai,odinann}.sh; do not invoke directly.

set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m}
ATTEMPT=${F0_ATTEMPT:-attempt-01}
CPUSET=${ATLAS_CPUSET:-0-23}
NUMA_NODE=${ATLAS_NUMA_NODE:-0}
BUILD_THREADS=${ATLAS_BUILD_THREADS:-24}
QUERY_THREADS=${ATLAS_QUERY_THREADS:-8}
MIN_FREE_BYTES=${ATLAS_MIN_FREE_BYTES:-300000000000}
SYSTEM=${SYSTEM:?SYSTEM must be set before sourcing f0_common.sh}

DATASET="$ROOT/datasets/sift10m"
GT="$ROOT/groundtruth/sift10m/gt_cp00"
RUN_ROOT="$ROOT/formal/$RUN_NAME/f0/$SYSTEM/$ATTEMPT"
INDEX_DIR="$RUN_ROOT/index"
RESULT_DIR="$ROOT/results/$RUN_NAME/f0/$SYSTEM/$ATTEMPT"
MANIFEST_DIR="$ROOT/manifests/$RUN_NAME/f0/$SYSTEM/$ATTEMPT"
TMP_WORK="$ROOT/tmp/$RUN_NAME/f0/$SYSTEM/$ATTEMPT"
LIBS="$ROOT/build/gperftools-install/lib:$ROOT/build/openblas-install/lib:$ROOT/build/jemalloc-install/lib"

fail() { echo "f0_${SYSTEM,,}: $*" >&2; exit 1; }
note() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
require_file() { [[ -f "$1" ]] || fail "missing required file: $1"; }
require_executable() { [[ -x "$1" ]] || fail "missing executable: $1"; }

require_nvme_path() {
  local canonical probe source majmin
  canonical=$(realpath -m "$1")
  case "$canonical" in
    /home/ubuntu/pz/VectorDB/data|/home/ubuntu/pz/VectorDB/data/*) ;;
    *) fail "refusing path outside experiment NVMe: $1" ;;
  esac
  probe=$canonical
  while [[ ! -e "$probe" ]]; do probe=$(dirname "$probe"); done
  source=$(findmnt -rn -T "$probe" -o SOURCE | head -n1)
  majmin=$(findmnt -rn -T "$probe" -o MAJ:MIN | head -n1)
  [[ "$source" == "${ATLAS_NVME_SOURCE:-/dev/nvme8n1}" && "$majmin" == "${ATLAS_NVME_MAJMIN:-259:10}" ]] \
    || fail "path is not expected experiment NVMe: $canonical ($source $majmin)"
}

check_numa_binding() {
  command -v numactl >/dev/null || fail "numactl is required"
  local node_cpus
  node_cpus=$(cat "/sys/devices/system/node/node${NUMA_NODE}/cpulist" 2>/dev/null) \
    || fail "NUMA node ${NUMA_NODE} is absent"
  python3 - "$CPUSET" "$node_cpus" <<'PY'
import sys
def expand(spec):
    result = set()
    for part in spec.split(','):
        if '-' in part:
            left, right = map(int, part.split('-', 1)); result.update(range(left, right + 1))
        else:
            result.add(int(part))
    return result
requested, node = map(expand, sys.argv[1:])
if not requested or not requested <= node:
    raise SystemExit(f"CPUSET {sys.argv[1]} is not contained in node cpulist {sys.argv[2]}")
PY
}

check_paths() {
  for path in "$ROOT" "$DATASET" "$RUN_ROOT" "$RESULT_DIR" "$MANIFEST_DIR" "$TMP_WORK"; do
    require_nvme_path "$path"
  done
  [[ -d "$ROOT" ]] || fail "missing atlas root: $ROOT"
  local free
  free=$(df -PB1 "$ROOT" | awk 'NR==2 {print $4}')
  [[ "$free" =~ ^[0-9]+$ ]] || fail "cannot determine free space"
  (( free >= MIN_FREE_BYTES )) || fail "NVMe free bytes $free below guard $MIN_FREE_BYTES"
  require_file "$DATASET/DATA_PREPARED_OK"
  require_file "$ROOT/results/$RUN_NAME/data_validation/VALIDATED_CP00_OK"
  require_file "$DATASET/active_cp00.bin"
  require_file "$DATASET/active_cp00.tags.bin"
  require_file "$DATASET/query.bin"
  require_file "$GT"
  check_numa_binding
  mkdir -p "$RUN_ROOT" "$RESULT_DIR" "$MANIFEST_DIR" "$TMP_WORK"
  export TMPDIR="$TMP_WORK"
  require_nvme_path "$TMPDIR"
}

check_allowed_patch() {
  local repo=$1 expected_commit=$2 patch=$3 expected_sha=$4
  [[ "$(git -C "$repo" rev-parse HEAD)" == "$expected_commit" ]] || fail "unexpected commit in $repo"
  [[ "$(sha256sum "$patch" | awk '{print $1}')" == "$expected_sha" ]] || fail "patch hash mismatch: $patch"

  # Only paths enumerated by the checked-in compatibility patch may be dirty.
  local allowed changed
  while IFS= read -r changed; do
    [[ -z "$changed" ]] && continue
    allowed=0
    while IFS= read -r path; do
      [[ "$changed" == "$path" ]] && { allowed=1; break; }
    done < <(awk '$1 == "diff" && $2 == "--git" {sub(/^b\//, "", $4); print $4}' "$patch")
    (( allowed == 1 )) || fail "unexpected source modification in $repo: $changed"
  done < <(git -C "$repo" status --porcelain | sed -E 's/^...//')
  git -C "$repo" apply --check --reverse "$patch" \
    || fail "working tree does not exactly contain the allowed compatibility patch: $repo"
}

check_sources() {
  local disk_repo="$ROOT/src/DiskANN-cpp_main"
  local dgai_repo="$ROOT/src/DGAI-clean"
  local odin_repo="$ROOT/src/OdinANN-PipeANN"
  check_allowed_patch "$disk_repo" 78256bbab4685e1774e78d331e081a153be26823 \
    "$CHAT/patches/DiskANN_system_blas.patch" \
    1f3ef6b49df4293708be6988f73ea22c5a3e99d6fe0e7e03b2390ec42fd99354
  check_allowed_patch "$dgai_repo" a0179b876a4bd453336dc2893b46ae890f680555 \
    "$CHAT/patches/DGAI_mkl_cblas_compat.patch" \
    cc5a1d06a5902c0d8fcdbe24e1e2c2a770e3070b3c9ad5b426c6d54d00604319
  check_allowed_patch "$odin_repo" 9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b \
    "$CHAT/patches/OdinANN_system_uring_cblas.patch" \
    97af1345dd5ecb3e66e20597caf1aabfd8b4be52f2fcd56f6c11468f7eb41ee7
}

write_environment_manifest() {
  local output="$MANIFEST_DIR/environment.txt"
  [[ -f "$output" ]] && return 0
  {
    echo "schema=dynamic-vamana-f0-environment-v1"
    echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "system=$SYSTEM"
    echo "run_name=$RUN_NAME"
    echo "attempt=$ATTEMPT"
    echo "cpuset=$CPUSET"
    echo "numa_node=$NUMA_NODE"
    echo "build_threads=$BUILD_THREADS"
    echo "query_threads=$QUERY_THREADS"
    echo "atlas_root=$ROOT"
    echo "--- uname ---"; uname -a
    echo "--- lscpu ---"; lscpu
    echo "--- numactl ---"; numactl --hardware
    echo "--- requested NUMA policy ---"; echo "physcpubind=$CPUSET membind=$NUMA_NODE"
    echo "--- node cpulist ---"; cat "/sys/devices/system/node/node${NUMA_NODE}/cpulist"
    echo "--- mounts ---"; findmnt -T "$ROOT" -o TARGET,SOURCE,FSTYPE,OPTIONS
    echo "--- block devices ---"; lsblk -o NAME,MODEL,SERIAL,SIZE,ROTA,TYPE,MOUNTPOINTS
    echo "--- cpu governor ---"; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>&1 || true
    echo "--- THP ---"; cat /sys/kernel/mm/transparent_hugepage/enabled 2>&1 || true
    echo "--- commits ---"
    for repo in "$ROOT/src/DiskANN-cpp_main" "$ROOT/src/DGAI-clean" "$ROOT/src/OdinANN-PipeANN"; do
      printf '%s ' "$repo"; git -C "$repo" rev-parse HEAD
    done
  } >"$output"
}

write_state() {
  local phase=$1 status=$2 detail=${3:-}
  python3 - "$MANIFEST_DIR/state.json" "$SYSTEM" "$ATTEMPT" "$phase" "$status" "$detail" <<'PY'
import json, sys, time
from pathlib import Path
path, system, attempt, phase, status, detail = map(str, sys.argv[1:])
payload = {
    "schema": "dynamic-vamana-f0-state-v1",
    "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "system": system,
    "attempt": attempt,
    "phase": phase,
    "status": status,
    "detail": detail,
}
Path(path).write_text(json.dumps(payload, indent=2) + "\n")
PY
}

on_error() {
  local code=$?
  write_state "${CURRENT_PHASE:-preflight}" failed "exit=$code"
  printf 'FAILED exit=%s phase=%s utc=%s\n' "$code" "${CURRENT_PHASE:-preflight}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$RESULT_DIR/FAILED"
  notify_owner "Dynamic Vamana F0 failed: $SYSTEM/$ATTEMPT" \
    "phase=${CURRENT_PHASE:-preflight} exit=$code result=$RESULT_DIR"
  exit "$code"
}

enable_error_trap() { trap on_error ERR; }

notify_owner() {
  [[ "${ATLAS_NOTIFY_EMAIL:-1}" == 1 ]] || return 0
  "$CHAT/formal/notify_owner.sh" "$1" "$2" || note "MailSender notification failed; preserving primary result"
}

assert_fresh_attempt() {
  if [[ -f "$RESULT_DIR/F0_OK" ]]; then
    note "already complete: $SYSTEM/$ATTEMPT"
    exit 0
  fi
  if [[ -e "$RESULT_DIR/FAILED" ]]; then
    fail "attempt is marked failed; preserve evidence and set F0_ATTEMPT=attempt-02 for a clean retry"
  fi
}

run_scoped() {
  local phase=$1 timeout_seconds=$2 space_root=$3 output=$4
  shift 4
  local unit="dv-${RUN_NAME}-${SYSTEM}-${phase}-${ATTEMPT}-$$"
  local worker_threads=$BUILD_THREADS
  [[ "$phase" == query ]] && worker_threads=$QUERY_THREADS
  CURRENT_PHASE=$phase
  write_state "$phase" running
  printf '%s\n' "$unit" >"$RESULT_DIR/${phase}_systemd_unit.txt"
  # A root-managed transient scope is required because this host has no usable
  # unprivileged user bus. `sudo -n` intentionally fails fast if the operator
  # has not pre-authenticated/pre-provisioned the dedicated cgroup launcher.
  # --scope is synchronous by itself on this host; systemd rejects combining
  # it with --wait, so do not add that mutually exclusive option.
  sudo -n systemd-run --scope --quiet --collect --unit "$unit" --uid "$(id -u)" \
    --property="AllowedCPUs=$CPUSET" --property=MemoryAccounting=yes \
    --property=CPUAccounting=yes --property=IOAccounting=yes -- \
    timeout --signal=TERM --kill-after=120s "$timeout_seconds" \
    env TMPDIR="$TMP_WORK" LD_LIBRARY_PATH="$LIBS" \
      OPENBLAS_NUM_THREADS="$worker_threads" OMP_NUM_THREADS="$worker_threads" \
      numactl --physcpubind="$CPUSET" --membind="$NUMA_NODE" \
      "$CHAT/resource_probe.py" --output "$output" --interval-ms 100 \
      --space-root "$space_root" -- bash -c \
      'policy=$1; log=$2; shift 2; { taskset -pc $$; numactl --show; } >"$policy" 2>&1; exec "$@" >"$log" 2>&1' \
      bash "$RESULT_DIR/${phase}_effective_policy.txt" "$RESULT_DIR/${phase}.log" "$@"
  write_state "$phase" passed
}

make_immutable_base() {
  [[ -f "$INDEX_DIR/BUILD_OK" ]] || fail "cannot freeze an unbuilt index"
  touch "$INDEX_DIR/IMMUTABLE_BASE_OK"
  chmod -R a-w "$INDEX_DIR"
}

assert_query_recall() {
  local log=$1
  grep -q 'Recall@10' "$log" || fail "query output does not contain Recall@10"
  grep -Eq '^[[:space:]]*[0-9]+' "$log" || fail "query output contains no result row"
}

write_space_report() {
  python3 - "$INDEX_DIR" "$RESULT_DIR/index_space.json" <<'PY'
import json, os, sys
from pathlib import Path
root, output = map(Path, sys.argv[1:])
apparent = allocated = files = 0
for path in root.rglob('*'):
    if path.is_file():
        st = path.stat()
        apparent += st.st_size
        allocated += st.st_blocks * 512
        files += 1
output.write_text(json.dumps({"files": files, "apparent_bytes": apparent,
                              "allocated_bytes": allocated}, indent=2) + "\n")
PY
}
