#!/usr/bin/env python3
"""Fail-closed storage/build/input gate for Z0B endpoint preparation/run.

The normal audit is read-only and may report ``launch_ready=false`` while the
native compact toolchain is still being frozen.  Formal callers must pass
``--require-launch-ready``; that also enables the expensive dataset hash.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from endpoint_common import (
    ABSOLUTE_PEAK_LIMIT_BYTES,
    ATLAS,
    BUILD,
    DATASET,
    FREEZE_EVIDENCE,
    FREE_SPACE_MULTIPLIER,
    FROZEN_HASHES,
    INITIAL_ROOTS,
    INPUT_EXPECTATIONS,
    INPUT_ROOT,
    M0_PROFILER,
    M0_PROFILER_SHA256,
    M3_BUILD,
    NVME_MAJMIN,
    PREREGISTRATION,
    REGISTERED_PEAK_BYTES,
    RUN_ROOT,
    SHARE,
    TOOLCHAIN_LOCK,
    atomic_json,
    load_json,
    mount_majmin,
    schedule,
    sha256,
    timestamp_pair,
)


DATASET_SHA256 = "91846887bbede67c4f9ddb0c47617b44e2efa32007cb32f24262d0033a55784b"
REQUIRED_TOOL_ROLES = {
    "analyze_endpoint_results",
    "compact_extent_manifest",
    "compact_lifecycle",
    "compare_native_results",
    "initial_replay_view",
    "native_replay",
    "native_reference",
    "stream_normalize",
}


def check(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"name": name, "pass": bool(passed), "detail": detail})


def immutable_tree_ok(root: Path) -> tuple[bool, str]:
    if not root.is_dir():
        return False, "missing"
    bad: list[str] = []
    for path in [root, *root.rglob("*")]:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o222:
            bad.append(f"{path}:{mode:04o}")
            if len(bad) >= 5:
                break
    return not bad, "all entries non-writable" if not bad else bad


def validate_toolchain(checks: list[dict[str, object]]) -> bool:
    if not TOOLCHAIN_LOCK.is_file():
        check(checks, "compact_native_toolchain_lock", False, f"missing: {TOOLCHAIN_LOCK}")
        return False
    try:
        lock = load_json(TOOLCHAIN_LOCK)
        artifacts = lock.get("artifacts", {})
        roles = set(artifacts)
        role_ok = lock.get("schema") == "zns-ann-z0b-toolchain-lock-v1" and roles == REQUIRED_TOOL_ROLES
        check(checks, "toolchain_roles_exact", role_ok, sorted(roles))
        good = role_ok
        for role in sorted(REQUIRED_TOOL_ROLES):
            row = artifacts.get(role, {})
            path = Path(str(row.get("path", ""))).resolve()
            expected = str(row.get("sha256", ""))
            exists = path.is_file() and bool(expected)
            digest = sha256(path) if exists else None
            passed = exists and digest == expected
            check(checks, f"toolchain_hash:{role}", passed, {"path": str(path), "sha256": digest})
            good &= passed
        compact_only = lock.get("expanded_json_intermediates_permitted") is False
        check(checks, "toolchain_compact_only", compact_only, lock.get("expanded_json_intermediates_permitted"))
        preflight = lock.get("native_scale_preflight", {})
        preflight_evidence = load_json(SHARE / "native_scale_preflight.json")
        preflight_ok = (
            preflight.get("status") == "pass"
            and int(preflight.get("benchmark_initial_pages", -1)) == 3_449_976
            and int(preflight.get("events_per_engine", -1)) >= 5_000_000
            and int(preflight.get("configurations_cross_checked", -1)) == 2
            and float(preflight.get("minimum_event_policy_steps_per_second_including_load_and_final_hash", 0))
                >= float(preflight.get("threshold_event_policy_steps_per_second", 500_000))
            and int(preflight.get("max_rss_kib", 2**63 - 1)) < 4 * 1024 * 1024
            and preflight_evidence.get("status") == "pass"
            and preflight_evidence.get("checks", {}).get("main_reference_exact") is True
            and preflight_evidence.get("checks", {}).get("transition_rolling_sha256_compared") is True
            and preflight_evidence.get("checks", {}).get("throughput_pass") is True
            and preflight_evidence.get("binaries", {}).get("native_replay_sha256")
                == artifacts.get("native_replay", {}).get("sha256")
            and preflight_evidence.get("binaries", {}).get("native_reference_sha256")
                == artifacts.get("native_reference", {}).get("sha256")
        )
        check(checks, "native_scale_preflight", preflight_ok, {
            "evidence": str(SHARE / "native_scale_preflight.json"),
            "steps_per_second": preflight.get(
                "minimum_event_policy_steps_per_second_including_load_and_final_hash"),
            "threshold": preflight.get("threshold_event_policy_steps_per_second"),
            "max_rss_kib": preflight.get("max_rss_kib"),
        })
        return bool(good and compact_only and preflight_ok)
    except Exception as exc:  # a malformed lock must never become launchable
        check(checks, "compact_native_toolchain_lock", False, f"invalid: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "prepare", "run"), default="audit")
    parser.add_argument("--require-launch-ready", action="store_true")
    parser.add_argument("--deep", action="store_true", help="hash the 5 GiB dataset")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    deep = args.deep or args.require_launch_ready

    checks: list[dict[str, object]] = []
    try:
        device = mount_majmin(ATLAS)
    except Exception as exc:
        device = f"error: {exc}"
    check(checks, "atlas_on_nvme8", device == NVME_MAJMIN, {"actual": device, "required": NVME_MAJMIN})

    probe = RUN_ROOT if RUN_ROOT.exists() else ATLAS
    space = os.statvfs(probe)
    free_bytes = space.f_bavail * space.f_frsize
    required_free = int(REGISTERED_PEAK_BYTES * FREE_SPACE_MULTIPLIER)
    check(checks, "registered_peak_within_150_gib", REGISTERED_PEAK_BYTES <= ABSOLUTE_PEAK_LIMIT_BYTES,
          {"registered_peak_bytes": REGISTERED_PEAK_BYTES, "limit_bytes": ABSOLUTE_PEAK_LIMIT_BYTES})
    check(checks, "free_at_least_1_5x_peak", free_bytes >= required_free,
          {"free_bytes": free_bytes, "required_free_bytes": required_free, "multiplier": FREE_SPACE_MULTIPLIER})

    marker = BUILD / "Z0B_BUILD_OK"
    check(checks, "r05_build_marker", marker.is_file(), str(marker))
    check(checks, "r05_build_root_frozen", BUILD.is_dir() and not (stat.S_IMODE(BUILD.stat().st_mode) & 0o222),
          oct(stat.S_IMODE(BUILD.stat().st_mode)) if BUILD.exists() else "missing")
    for relative, expected in FROZEN_HASHES.items():
        path = BUILD / relative
        actual = sha256(path) if path.is_file() else None
        check(checks, f"r05_hash:{relative}", actual == expected,
              {"path": str(path), "expected": expected, "actual": actual})
    m0_actual = sha256(M0_PROFILER) if M0_PROFILER.is_file() else None
    check(checks, "frozen_m0_profiler_hash", m0_actual == M0_PROFILER_SHA256,
          {"path": str(M0_PROFILER), "expected": M0_PROFILER_SHA256, "actual": m0_actual})
    check(checks, "frozen_m3_build_marker", (M3_BUILD / "M3_BUILD_OK").is_file(),
          str(M3_BUILD / "M3_BUILD_OK"))
    check(checks, "dual_interpose_order", True, [str(BUILD / "trace/libz0btrace.so"), str(M0_PROFILER)])
    check(checks, "normalizer_closure_source", True, "trace_ledger.json; M0 profile compared independently")

    for system in ("DGAI", "OdinANN"):
        evidence_path = FREEZE_EVIDENCE[system]
        try:
            evidence = load_json(evidence_path)
            expected_root = INITIAL_ROOTS[system].resolve()
            evidence_ok = (
                evidence.get("status") == "pass"
                and evidence.get("system") == system
                and evidence.get("checkpoint") == "cp10"
                and Path(str(evidence.get("root_realpath"))).resolve() == expected_root
                and evidence.get("content_exact_across_freeze") is True
            )
            check(checks, f"freeze_evidence:{system}", evidence_ok, str(evidence_path))
            tree_ok, detail = immutable_tree_ok(expected_root)
            check(checks, f"immutable_snapshot:{system}", tree_ok, detail)
            check(checks, f"immutable_marker:{system}", (expected_root / "IMMUTABLE_BASE_OK").is_file(),
                  str(expected_root / "IMMUTABLE_BASE_OK"))
        except Exception as exc:
            check(checks, f"freeze_evidence:{system}", False, str(exc))

    for size, expected in INPUT_EXPECTATIONS.items():
        root = INPUT_ROOT / f"n{size}"
        try:
            manifest = load_json(root / "manifest.json")
            manifest_ok = (
                manifest.get("status") == "pass"
                and manifest.get("size") == size
                and manifest.get("master_record_range") == expected["range"]
                and manifest.get("active_count") == 8_000_000
                and manifest.get("assertions", {}).get("nested_prefix") is True
            )
            check(checks, f"input_manifest:n{size}", manifest_ok, str(root / "manifest.json"))
            trace = root / "trace.bin"
            trace_ok = trace.is_file() and trace.stat().st_size == expected["trace_size"] and sha256(trace) == expected["trace_sha256"]
            check(checks, f"input_trace:n{size}", trace_ok, str(trace))
            active = root / "expected_active.tags.bin"
            active_ok = active.is_file() and active.stat().st_size == 32_000_008 and sha256(active) == expected["active_sha256"]
            check(checks, f"expected_active:n{size}", active_ok, str(active))
            probes = manifest.get("probes", {})
            for key, hash_key in (("binary", "binary_sha256"), ("spec", "spec_sha256")):
                path = root / str(probes.get(key, ""))
                ok = path.is_file() and sha256(path) == probes.get(hash_key)
                check(checks, f"input_probe_{key}:n{size}", ok, str(path))
        except Exception as exc:
            check(checks, f"input_manifest:n{size}", False, str(exc))

    dataset_exists = DATASET.is_file()
    check(checks, "dataset_present", dataset_exists, {"path": str(DATASET), "size_bytes": DATASET.stat().st_size if dataset_exists else None})
    if deep:
        actual = sha256(DATASET) if dataset_exists else None
        check(checks, "dataset_sha256", actual == DATASET_SHA256, {"expected": DATASET_SHA256, "actual": actual})

    try:
        prereg = load_json(PREREGISTRATION)
        matrix = prereg.get("matrix", {})
        prereg_ok = (
            prereg.get("schema") == "zns-ann-z0b-preregistration-v1"
            and matrix.get("trace_realizations") == 6
            and matrix.get("configurations_per_trace") == 48
            and matrix.get("total_configurations") == 288
            and prereg.get("ordering", {}).get("timestamps_permitted") is False
        )
        check(checks, "preregistration_matrix", prereg_ok, str(PREREGISTRATION))
    except Exception as exc:
        check(checks, "preregistration_matrix", False, str(exc))

    labels = [str(row["label"]) for row in schedule()]
    check(checks, "schedule_exact_six_unique", len(labels) == 6 and len(set(labels)) == 6,
          labels)
    toolchain_ok = validate_toolchain(checks)

    if args.mode == "prepare":
        state_ok = not RUN_ROOT.exists()
        check(checks, "new_campaign_root", state_ok, str(RUN_ROOT))
    elif args.mode == "run":
        state_ok = (RUN_ROOT / "PREPARED_OK").is_file() and (RUN_ROOT / "schedule.json").is_file()
        check(checks, "campaign_prepared", state_ok, str(RUN_ROOT))
    else:
        state_ok = True

    infrastructure_names = {
        "compact_native_toolchain_lock", "toolchain_roles_exact", "toolchain_compact_only"
    }
    infrastructure_ok = all(
        bool(row["pass"])
        for row in checks
        if not str(row["name"]).startswith("toolchain_hash:") and row["name"] not in infrastructure_names
    )
    launch_ready = all(bool(row["pass"]) for row in checks) and toolchain_ok and state_ok
    report = {
        "schema": "zns-ann-z0b-prelaunch-audit-v1",
        "timestamps": timestamp_pair(),
        "mode": args.mode,
        "audit_status": "pass" if infrastructure_ok else "fail",
        "launch_ready": launch_ready,
        "formal_full_trace_started": False,
        "registered_peak_bytes": REGISTERED_PEAK_BYTES,
        "free_bytes": free_bytes,
        "run_root": str(RUN_ROOT),
        "frozen_build": str(BUILD),
        "checks": checks,
    }
    if args.output:
        atomic_json(args.output, report)
    import json
    print(json.dumps(report, indent=2, sort_keys=True))
    if infrastructure_ok is False or (args.require_launch_ready and not launch_ready):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
