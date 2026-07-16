#!/usr/bin/env python3
"""Validate the R02 immutable replay-base CP00 static-load smoke.

The runner creates this exact layout beneath ``--smoke-root``::

  DGAI/
    base_content_before.tsv  base_mode_before.tsv
    base_content_after.tsv   base_mode_after.tsv
    L64.{cache_evict.json,metrics.json,validation.json,resources.json,log,result_ids.bin}
    L128.{cache_evict.json,metrics.json,validation.json,resources.json,log,result_ids.bin}
  OdinANN/
    ... same manifests ...
    L29.*  L46.*

The validator independently enforces 36x10 shape, active IDs, finite metrics,
Recall, NVMe reads and OOM/fatal signatures from these raw artifacts.  It also
binds the before/after manifests to the published immutable replay base.  It
never runs a query.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import struct
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-r02-static-load-smoke-v1"
SYSTEMS = {"DGAI": (64, 128), "OdinANN": (29, 46)}
METRIC_FIELDS = ("qps", "mean_latency_us", "p99_latency_us", "mean_ios", "recall_at_10_percent")
FATAL = re.compile(r"fatal|assert(?:ion)?(?: failed)?|I/O error|segmentation fault|core dumped|std::bad_alloc|out of memory|oom-kill|killed process", re.I)


def fail(message: str) -> None:
    raise ValueError(message)


def require(value: bool, message: str) -> None:
    if not value:
        fail(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    info = path.stat()
    return {"realpath": str(path), "size_bytes": info.st_size, "sha256": sha256(path),
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
            "device": info.st_dev, "inode": info.st_ino}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"output overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush(); os.fsync(stream.fileno())


def evict_cache(args: argparse.Namespace) -> None:
    """Evict only this immutable tree; device I/O later proves effectiveness."""
    require(os.geteuid() == 0, "cache eviction requires root")
    root = args.index_root.resolve(strict=True)
    root_info = root.lstat()
    require(stat.S_ISDIR(root_info.st_mode) and stat.S_IMODE(root_info.st_mode) == 0o555,
            "cache eviction root is not an immutable 0555 directory")
    actual_device = f"{os.major(root_info.st_dev)}:{os.minor(root_info.st_dev)}"
    require(actual_device == args.device, f"cache eviction device mismatch: {actual_device}")
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in sorted(dirnames):
            item = base / name; info = item.lstat()
            require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o555,
                    f"non-immutable directory in cache eviction tree: {item}")
        for name in sorted(filenames):
            item = base / name; info = item.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o444,
                    f"unsafe file in cache eviction tree: {item}")
            files.append(item)
    def snapshot(path: Path) -> tuple[int, ...]:
        info = path.lstat()
        return (info.st_dev, info.st_ino, info.st_size, info.st_uid, info.st_gid,
                stat.S_IMODE(info.st_mode), info.st_nlink, info.st_mtime_ns)
    before = {path: snapshot(path) for path in files}; total = 0
    for path in files:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            require((info.st_dev, info.st_ino) == before[path][:2],
                    f"cache eviction file identity raced: {path}")
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            total += info.st_size
        finally:
            os.close(fd)
    require(all(snapshot(path) == expected for path, expected in before.items()),
            "immutable tree metadata changed during cache eviction")
    write_new(args.output, {
        "schema": "dynamic-vamana-w1-per-file-cache-eviction-v1", "status": "pass",
        "root_realpath": str(root), "device": actual_device,
        "advice": "POSIX_FADV_DONTNEED", "regular_file_count": len(files),
        "total_file_bytes": total, "content_or_mode_modified": False,
        "proof_boundary": "subsequent cgroup device-read delta"})


def all_finite(value: Any, label: str = "metrics") -> None:
    if isinstance(value, dict):
        for key, item in value.items(): all_finite(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value): all_finite(item, f"{label}[{index}]")
    elif isinstance(value, float):
        require(math.isfinite(value), f"non-finite {label}")


def memory_events(resource: dict[str, Any]) -> dict[str, int]:
    totals = {key: 0 for key in ("oom", "oom_kill", "oom_group_kill")}
    final = resource.get("cgroup_memory_events_final", {})
    if isinstance(final, dict):
        for key in totals: totals[key] += int(final.get(key, 0))
    for row in resource.get("samples", []):
        events = row.get("cgroup_memory_events", {})
        if isinstance(events, dict):
            for key in totals: totals[key] += int(events.get(key, 0))
    return totals


def nvme_read_delta(resource: dict[str, Any], device: str) -> tuple[int, int]:
    samples = resource.get("samples", [])
    require(len(samples) >= 2, "resource evidence lacks bracketing samples")
    def row(sample: dict[str, Any]) -> dict[str, int]:
        match = next((item for item in sample.get("cgroup_io_stat", []) if item.get("device") == device), None)
        require(match is not None, f"resource evidence lacks device {device}")
        return {"rbytes": int(match.get("rbytes", 0)), "rios": int(match.get("rios", 0))}
    before, after = row(samples[0]), row(samples[-1])
    require(after["rbytes"] >= before["rbytes"] and after["rios"] >= before["rios"], "I/O counters decreased")
    return after["rbytes"] - before["rbytes"], after["rios"] - before["rios"]


def validate_result_ids(raw: bytes, active_set: set[int]) -> tuple[int, int]:
    require(len(raw) >= 8, "result header truncated")
    nq, k = struct.unpack("<II", raw[:8])
    require((nq, k) == (36, 10), "smoke result shape is not 36x10")
    require(len(raw) == 8 + nq * k * 4, "result byte length mismatch")
    ids = struct.unpack(f"<{nq*k}I", raw[8:])
    require(0xFFFFFFFF not in ids and all(value in active_set for value in ids),
            "inactive/sentinel result ID")
    require(all(len(set(ids[row*10:(row+1)*10])) == 10 for row in range(36)),
            "duplicate top10 row")
    return nq, k


def verify_base_manifest(base_dir: Path, system: str) -> tuple[dict[str, Any], Path]:
    base_dir = base_dir.resolve(strict=True)
    manifest_path = base_dir / "immutable_replay_base_manifest.json"
    manifest = load(manifest_path)
    require(manifest.get("status") == "pass", f"{system} immutable manifest is not PASS")
    require(manifest.get("system") == system, f"{system} immutable manifest system mismatch")
    require(manifest.get("schema") == "dynamic-vamana-w1-immutable-replay-base-v1",
            f"{system} immutable manifest schema mismatch")
    immutable_entry = manifest.get("immutable_base", {})
    immutable = Path(immutable_entry.get("realpath", "")).resolve(strict=True)
    require(immutable == (base_dir / "index").resolve(strict=True),
            f"{system} immutable base realpath mismatch")
    for filename in ("base_content.tsv", "base_mode.tsv", "source_content_before.tsv",
                     "source_content_after.tsv", "source_mode_before.tsv", "source_mode_after.tsv",
                     "write_denial_audit.json", "IMMUTABLE_REPLAY_BASE_OK"):
        require((base_dir / filename).is_file(), f"{system} immutable evidence missing: {filename}")
    expected_content_sha = immutable_entry.get("content", {}).get("sha256") or manifest.get("content_manifest_sha256")
    expected_mode_sha = immutable_entry.get("mode", {}).get("sha256") or manifest.get("mode_manifest_sha256")
    require(sha256(base_dir / "base_content.tsv") == expected_content_sha,
            f"{system} immutable content manifest anchor mismatch")
    require(sha256(base_dir / "base_mode.tsv") == expected_mode_sha,
            f"{system} immutable mode manifest anchor mismatch")
    denial = load(base_dir / "write_denial_audit.json")
    require(denial.get("status") == "pass", f"{system} write-denial audit not PASS")
    return manifest, immutable


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(strict=True)
    artifact = args.artifact_manifest.resolve(strict=True)
    replay_input = args.replay_input_root.resolve(strict=True)
    smoke_root = args.smoke_root.resolve(strict=True)
    bases = args.immutable_base_root.resolve(strict=True)
    query = replay_input / "query_36.bin"; gt = replay_input / "gt_cp00_36"
    active = args.cp00_active.resolve(strict=True)
    for path in (query, gt, active, artifact):
        require(path.is_file(), f"static-smoke input missing: {path}")
    with active.open("rb") as stream:
        active_header = stream.read(8)
        require(len(active_header) == 8, "active-tag header truncated")
        active_count, active_dim = struct.unpack("<II", active_header)
        require(active_dim == 1 and active.stat().st_size == 8 + active_count * 4,
                "active-tag shape invalid")
        active_values = struct.unpack(f"<{active_count}I", stream.read(active_count * 4))
    active_set = set(active_values)
    require(len(active_set) == active_count and 0xFFFFFFFF not in active_set, "active tags duplicate/sentinel")
    systems: dict[str, Any] = {}
    for system, expected_ls in SYSTEMS.items():
        base_dir = bases / system / "cp00"
        manifest, immutable = verify_base_manifest(base_dir, system)
        system_root = smoke_root / system
        require(system_root.resolve(strict=True) == (smoke_root / system).resolve(strict=True),
                f"{system} smoke root unavailable")
        before_content = system_root / "base_content_before.tsv"
        before_mode = system_root / "base_mode_before.tsv"
        after_content = system_root / "base_content_after.tsv"
        after_mode = system_root / "base_mode_after.tsv"
        for path in (before_content, before_mode, after_content, after_mode):
            require(path.is_file(), f"{system} smoke base evidence missing: {path.name}")
        require(before_content.read_bytes() == (base_dir / "base_content.tsv").read_bytes()
                == after_content.read_bytes(), f"{system} base content changed across smoke")
        require(before_mode.read_bytes() == (base_dir / "base_mode.tsv").read_bytes()
                == after_mode.read_bytes(), f"{system} base mode changed across smoke")

        points = []
        for l_value in expected_ls:
            # The canonical runner uses the identity-v2-compatible long stem;
            # the short stem remains accepted for the documented raw layout.
            long_stem = system_root / f"cp00_L{l_value}_r1"
            short_stem = system_root / f"L{l_value}"
            stem = long_stem if Path(f"{long_stem}.metrics.json").is_file() else short_stem
            paths = {name: Path(f"{stem}.{suffix}") for name, suffix in {
                "metrics": "metrics.json", "validation": "validation.json", "resources": "resources.json",
                "log": "log", "result_ids": "result_ids.bin", "cache_eviction": "cache_evict.json"}.items()}
            for name, path in paths.items():
                require(path.is_file() and path.stat().st_size > 0, f"{system} L{l_value} {name} missing")
            metrics, validation, resource = load(paths["metrics"]), load(paths["validation"]), load(paths["resources"])
            cache_eviction = load(paths["cache_eviction"])
            require(cache_eviction.get("schema") == "dynamic-vamana-w1-per-file-cache-eviction-v1"
                    and cache_eviction.get("status") == "pass"
                    and Path(cache_eviction.get("root_realpath", "")).resolve(strict=True) == immutable
                    and cache_eviction.get("device") == args.device
                    and cache_eviction.get("advice") == "POSIX_FADV_DONTNEED"
                    and cache_eviction.get("content_or_mode_modified") is False,
                    f"{system} L{l_value} cache-eviction evidence invalid")
            all_finite(metrics)
            require(all(field in metrics and math.isfinite(float(metrics[field])) for field in METRIC_FIELDS),
                    f"{system} L{l_value} metric missing/non-finite")
            require(resource.get("returncode") == 0, f"{system} L{l_value} process failed")
            require(Path(resource.get("space_root", "")).resolve(strict=True) == immutable,
                    f"{system} L{l_value} resource index root mismatch")
            rbytes, rios = nvme_read_delta(resource, args.device)
            require(rbytes > 0, f"{system} L{l_value} lacks NVMe reads")
            oom = memory_events(resource); require(not any(oom.values()), f"{system} L{l_value} OOM evidence")
            log_text = paths["log"].read_text(errors="replace")
            require(not FATAL.search(log_text), f"{system} L{l_value} fatal log signature")
            require(re.search(rf"(?:^|\s){l_value}\s+\d", log_text, re.M) is not None,
                    f"{system} query log does not prove requested L={l_value}")
            nq, k = validate_result_ids(paths["result_ids"].read_bytes(), active_set)
            recall = float(validation.get("recall_at_10_normalized", float("nan")))
            require(validation.get("query_count") == 36 and validation.get("k") == 10
                    and validation.get("all_result_ids_active") is True
                    and int(validation.get("invalid_or_inactive_ids", -1)) == 0
                    and math.isfinite(recall) and 0 <= recall <= 1,
                    f"{system} L{l_value} validation failed")
            points.append({"L": l_value, "repeat": 1, "recall_at_10": recall,
                "qps": float(metrics["qps"]), "p99_latency_us": float(metrics["p99_latency_us"]),
                "mean_ios": float(metrics["mean_ios"]), "device_read_bytes": rbytes,
                "device_read_ios": rios, "oom_events": oom,
                "artifacts": {name: identity(path) for name, path in paths.items()}})
        systems[system] = {"status": "pass", "L": list(expected_ls), "result_shape": [36, 10],
            "immutable_base_manifest": identity(base_dir / "immutable_replay_base_manifest.json"),
            "immutable_base_realpath": str(immutable),
            "base_content_before": identity(before_content), "base_content_after": identity(after_content),
            "base_mode_before": identity(before_mode), "base_mode_after": identity(after_mode),
            "points": points, "recall_threshold_applied": False}
    result = {"schema": SCHEMA, "status": "pass", "root_realpath": str(root),
        "replay_input_root": str(replay_input), "immutable_base_root": str(bases),
        "expected_shape": [36, 10], "device": args.device, "systems": systems}
    write_new(args.output, result)
    return result


def self_test(args: argparse.Namespace) -> None:
    # Unit-test the fail-closed primitives without pretending to execute I/O.
    with tempfile.TemporaryDirectory(dir=args.scratch) as directory:
        root = Path(directory); sample = root / "sample"; sample.write_text("x")
        row = identity(sample)
        require(row["sha256"] == hashlib.sha256(b"x").hexdigest(), "identity self-test failed")
        bad = root / "bad.json"; bad.write_text("[]")
        failed = False
        try: load(bad)
        except ValueError: failed = True
        require(failed, "non-object JSON negative test did not fail")
        active = set(range(10))
        good_raw = struct.pack("<II", 36, 10) + struct.pack("<360I", *(list(range(10)) * 36))
        require(validate_result_ids(good_raw, active) == (36, 10), "36x10 positive fixture failed")
        duplicate = struct.pack("<II", 36, 10) + struct.pack("<360I", *([0] * 10 + list(range(10)) * 35))
        duplicate_failed = False
        try: validate_result_ids(duplicate, active)
        except ValueError: duplicate_failed = True
        sentinel = bytearray(good_raw); struct.pack_into("<I", sentinel, 8, 0xFFFFFFFF)
        sentinel_failed = False
        try: validate_result_ids(bytes(sentinel), active)
        except ValueError: sentinel_failed = True
        finite_failed = False
        try: all_finite({"x": float("nan")})
        except ValueError: finite_failed = True
        require(duplicate_failed and sentinel_failed and finite_failed,
                "static-smoke duplicate/sentinel/nonfinite negatives failed")
        result = {"schema": "dynamic-vamana-w1-cp05-r02-static-smoke-self-test-v1",
                  "status": "pass", "identity_positive": True, "shape_36x10_positive": True,
                  "non_object_negative": True, "duplicate_top10_negative": duplicate_failed,
                  "sentinel_negative": sentinel_failed, "nonfinite_negative": finite_failed}
    write_new(args.output, result)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    sub = top.add_subparsers(dest="command", required=True)
    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--root", type=Path, required=True)
    validate_p.add_argument("--artifact-manifest", type=Path, required=True)
    validate_p.add_argument("--immutable-base-root", type=Path, required=True)
    validate_p.add_argument("--replay-input-root", type=Path, required=True)
    validate_p.add_argument("--smoke-root", type=Path, required=True)
    validate_p.add_argument("--cp00-active", type=Path, required=True)
    validate_p.add_argument("--evidence-tool", type=Path,
                            help="accepted for runner interface compatibility; raw evidence is revalidated here")
    validate_p.add_argument("--device", default="259:10")
    validate_p.add_argument("--output", type=Path, required=True)
    test = sub.add_parser("self-test")
    test.add_argument("--scratch", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)
    evict = sub.add_parser("evict-cache")
    evict.add_argument("--index-root", type=Path, required=True)
    evict.add_argument("--device", default="259:10")
    evict.add_argument("--output", type=Path, required=True)
    return top


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "self-test": self_test(args)
        elif args.command == "evict-cache": evict_cache(args)
        else: validate(args)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
