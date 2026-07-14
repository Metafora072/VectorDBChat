#!/usr/bin/env bash
# Lightweight P0 runtime proof for cgroup, CPU affinity, NUMA policy and NVMe.
set -euo pipefail

SYSTEM=RuntimeCanary
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/f0_common.sh"

RUN_ROOT="$ROOT/formal/$RUN_NAME/canary/$ATTEMPT"
RESULT_DIR="$ROOT/results/$RUN_NAME/canary/$ATTEMPT"
MANIFEST_DIR="$ROOT/manifests/$RUN_NAME/canary/$ATTEMPT"
TMP_WORK="$ROOT/tmp/$RUN_NAME/canary/$ATTEMPT"
CANARY_PAYLOAD="$RESULT_DIR/payload.json"
CANARY_FILE="$RUN_ROOT/nvme-canary.bin"

for path in "$ROOT" "$RUN_ROOT" "$RESULT_DIR" "$MANIFEST_DIR" "$TMP_WORK"; do
  require_nvme_path "$path"
done
mkdir -p "$RUN_ROOT" "$RESULT_DIR" "$MANIFEST_DIR" "$TMP_WORK"
check_numa_binding
write_environment_manifest
assert_fresh_attempt
enable_error_trap

run_scoped canary 60 "$RUN_ROOT" "$RESULT_DIR/resources.json" \
  python3 "$CHAT/formal/f0_runtime_canary_payload.py" --output "$CANARY_PAYLOAD" \
  --nvme-file "$CANARY_FILE" --hold-seconds 3

unit=$(<"$RESULT_DIR/canary_systemd_unit.txt")
python3 - "$RESULT_DIR/resources.json" "$CANARY_PAYLOAD" "$CANARY_FILE" "$(id -u)" \
  "${ATLAS_NVME_MAJMIN:-259:10}" "$unit" "$CPUSET" "$NUMA_NODE" "$RESULT_DIR/canary_validation.json" <<'PY'
import json, sys
from pathlib import Path

resources, payload_path, nvme_file, uid, device, unit, cpuset, numa_node, output = map(str, sys.argv[1:])
report = json.loads(Path(resources).read_text())
payload = json.loads(Path(payload_path).read_text())
samples = report.get("samples", [])
if not samples:
    raise ValueError("resource probe produced no samples")
cg = report.get("cgroup_path") or ""
if not cg.endswith(".scope") or unit not in cg or "session" in cg:
    raise ValueError(f"not an independent transient scope: {cg}")
if not any(sample.get("cgroup_memory_current") is not None and sample.get("cgroup_memory_peak") is not None for sample in samples):
    raise ValueError("cgroup memory counters are unavailable")
if not any(any(row.get("device") == device for row in sample.get("cgroup_io_stat", [])) for sample in samples):
    raise ValueError(f"cgroup io.stat lacks expected NVMe device {device}")
if payload.get("uid") != int(uid) or Path(nvme_file).stat().st_uid != int(uid):
    raise ValueError("payload command or NVMe output is not owned by the operator")
def expand(spec):
    result = set()
    for part in spec.split(','):
        if '-' in part:
            left, right = map(int, part.split('-', 1)); result.update(range(left, right + 1))
        else:
            result.add(int(part))
    return result
if set(payload.get("cpu_affinity", [])) != expand(cpuset):
    raise ValueError(f"unexpected effective CPU affinity: {payload.get('cpu_affinity')}")
show = payload.get("numactl_show", "")
if f"membind: {numa_node}" not in show:
    raise ValueError(f"NUMA membind did not take effect: {show}")
Path(output).write_text(json.dumps({
    "schema": "dynamic-vamana-f0-runtime-canary-validation-v1",
    "passed": True,
    "systemd_unit": unit,
    "cgroup_path": cg,
    "uid": payload["uid"],
    "cpu_affinity": payload["cpu_affinity"],
    "numactl_show": show,
    "expected_nvme_device": device,
    "output_owner_uid": Path(nvme_file).stat().st_uid,
}, indent=2) + "\n")
PY

# --collect should release the transient scope. A surviving unit is evidence of
# an incomplete cleanup, not a reason to continue toward P1.
if sudo -n systemctl show "$unit" --property=LoadState --value 2>/dev/null | grep -qx loaded; then
  fail "transient scope was not collected: $unit"
fi
touch "$RESULT_DIR/F0_OK"
write_state complete passed
notify_owner "Dynamic Vamana cgroup/NUMA canary complete" "result=$RESULT_DIR unit=$unit"
note "runtime canary passed: $unit"
