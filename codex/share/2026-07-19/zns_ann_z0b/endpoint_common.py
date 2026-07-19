#!/usr/bin/env python3
"""Frozen constants and small helpers for the Z0B endpoint campaign.

This module is deliberately data-only.  It does not authorize preparation or
execution, and importing it has no filesystem side effects.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


GIB = 1024**3
ATLAS = Path(os.environ.get(
    "ATLAS_ROOT", "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas"
)).resolve()
SHARE = Path(__file__).resolve().parent
RUN_ROOT = Path(os.environ.get(
    "Z0B_ENDPOINT_ROOT", str(ATLAS / "z0b_sequence_endpoint_reclaim_0719")
)).resolve()
BUILD = (ATLAS / "build/zns-ann-z0b-endpoint-v1-r05").resolve()
M3_BUILD = (ATLAS / "build/write-supersession-m3-v1-r01").resolve()
M0_PROFILER = M3_BUILD / "lib/libm0write.so"
M0_PROFILER_SHA256 = "b06d9800644c870b78f9e4f72437b922b7c8cab4845fcf122f1794bf58816d3e"
PREREGISTRATION = SHARE / "preregistration.json"
TOOLCHAIN_LOCK = SHARE / "endpoint_toolchain_lock.json"
NVME_MAJMIN = "259:10"

# The corrected 64-byte normalized ABI yields a 128.360 GiB guarded peak.
# The frozen registration rounds that upward to 129 GiB.
REGISTERED_PEAK_BYTES = 129 * GIB
ABSOLUTE_PEAK_LIMIT_BYTES = 150 * GIB
FREE_SPACE_MULTIPLIER = 1.5

FROZEN_HASHES = {
    "trace/libz0btrace.so": "03d4556d12033fc961b26e301738cb57c8f7616d6e2b62864ab464fea0be3c1d",
    "systems/DGAI/w1_canary": "2138e07ca1fa157f5559e545294234bdf7bbf9eee58a488201ebac32cf34993c",
    "systems/OdinANN/w1_canary": "7f2696ff96f78a52d5481409aeaaf4333a856933f90791d5aa9646164b622a91",
}

INPUT_ROOT = ATLAS / "results/pilot3_sift10m_write_attribution_m1_scale_r01/inputs"
DATASET = ATLAS / "datasets/sift10m/full_10m.bin"
FREEZE_RESULT = ATLAS / "results/pilot3_sift10m_w1_cp10_trajectory_r12"
INITIAL_ROOTS = {
    system: ATLAS / (
        "formal/pilot3_sift10m_w1_cp10_trajectory_r12/"
        f"{system}/trajectory-cp10-12/index"
    )
    for system in ("DGAI", "OdinANN")
}
FREEZE_EVIDENCE = {
    system: FREEZE_RESULT / (
        f"{system}/trajectory-cp10-12/checkpoints/cp10/cp10_freeze_evidence.json"
    )
    for system in ("DGAI", "OdinANN")
}

INPUT_EXPECTATIONS = {
    50000: {
        "trace_sha256": "a49d9aa98ec5e0df65f1bc5405bd0cf729688364534326f746d922b31950442a",
        "trace_size": 400004,
        "active_sha256": "0cadb566de0cab5ba00af7ea2f4ead46df76f6869d15ff74363b219419facfd5",
        "range": [800000, 850000],
    },
    400000: {
        "trace_sha256": "aeaab2edce1854e36004d6bef57cd0aee9cb8ff079a45df65845921f69596228",
        "trace_size": 3200004,
        "active_sha256": "b0dda4d811bab6b80121b621ae6b1ce4f8f180e60737217c879ed72e346cc4b9",
        "range": [800000, 1200000],
    },
}

# Capacities are fixed before any endpoint observation.  They exceed the M3
# observations (118,207 and 16,219,270 requests) while keeping the buffer in
# the registered memory/space envelope.  A dropped record is always fatal.
TRACE_CAPACITY = {"DGAI": 262_144, "OdinANN": 20_000_000}

UUID_NAMESPACE = uuid.UUID("9aec653e-53dd-5e11-bd0a-83c80f7d3ca4")


def schedule() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for system, size, stem in (("DGAI", 50000, "dgai-50k"), ("OdinANN", 400000, "odinann-400k")):
        for realization in range(1, 4):
            label = f"{stem}-r{realization}"
            rows.append({
                "label": label,
                "system": system,
                "input_size": size,
                "realization": realization,
                "run_uuid": str(uuid.uuid5(UUID_NAMESPACE, label)),
                "trace_capacity": TRACE_CAPACITY[system],
                "initial_root": str(INITIAL_ROOTS[system]),
                "input_root": str(INPUT_ROOT / f"n{size}"),
            })
    return rows


def timestamp_pair() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {
        "utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "utc_plus_8": now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
    }


def sha256(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def mount_majmin(path: Path) -> str:
    result = subprocess.run(
        ["findmnt", "-rn", "-T", str(path), "-o", "MAJ:MIN"],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
    return rows[0] if rows else ""


def allocated_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    result = subprocess.run(
        ["du", "-s", "-B1", str(path)], check=True, text=True, capture_output=True
    )
    return int(result.stdout.split()[0])


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def atomic_json(path: Path, value: object, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def schedule_document() -> dict[str, object]:
    return {
        "schema": "zns-ann-z0b-endpoint-schedule-v1",
        "frozen_build": str(BUILD),
        "independent_full_traces": 3,
        "reuse_permitted": False,
        "failure_policy": "stop-entire-campaign-on-first-failure; no retry",
        "order": "DGAI50K r1-r3, then OdinANN400K r1-r3",
        "runs": schedule(),
    }


def locked_tool(role: str) -> Path:
    """Return a hash-checked tool from the formal lock."""
    lock = load_json(TOOLCHAIN_LOCK)
    row = lock.get("artifacts", {}).get(role)
    if not isinstance(row, dict):
        raise RuntimeError(f"tool role is not locked: {role}")
    path = Path(str(row.get("path", ""))).resolve()
    expected = str(row.get("sha256", ""))
    if not path.is_file() or not expected or sha256(path) != expected:
        raise RuntimeError(f"tool role hash mismatch: {role}: {path}")
    return path


def tool_command(path: Path) -> list[str]:
    return ["python3", str(path)] if path.suffix == ".py" else [str(path)]
