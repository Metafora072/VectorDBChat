#!/usr/bin/env python3
"""R08 identity-v2 validation for DiskANN CP00-index versus CP05-GT stale control."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import struct
from pathlib import Path
from typing import Any

import numpy as np


FATAL = re.compile(
    r"fatal|assert(?:ion)?|I/O error|input/output error|out of memory|oom|segmentation fault",
    re.I,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def standard_identity(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"identity target is not a regular file: {resolved}")
    info = resolved.stat()
    return {
        "realpath": str(resolved),
        "size_bytes": info.st_size,
        "sha256": sha256(resolved),
        "mtime_ns": info.st_mtime_ns,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def require_standard_identity(record: object, path: Path | None, label: str) -> dict[str, object]:
    if not isinstance(record, dict):
        raise ValueError(f"{label} accepted identity absent")
    required = {"realpath", "size_bytes", "sha256", "mtime_ns", "mode", "uid", "gid", "device", "inode"}
    if not required.issubset(record):
        raise ValueError(f"{label} accepted identity is incomplete")
    accepted_path = Path(str(record["realpath"])).resolve(strict=True)
    if path is not None and accepted_path != path.resolve(strict=True):
        raise ValueError(f"{label} accepted realpath mismatch")
    live = standard_identity(accepted_path)
    if any(record[key] != live[key] for key in required):
        raise ValueError(f"{label} accepted identity changed")
    return live


def runtime_sources(runtime: dict[str, Any]) -> dict[str, dict[str, object]]:
    sources: dict[str, dict[str, object]] = {}

    def add(row: object, role: str, name: str) -> None:
        if not isinstance(row, dict) or not isinstance(row.get("resolved_realpath"), str):
            raise ValueError(f"runtime manifest {role} row is invalid")
        path = str(Path(row["resolved_realpath"]).resolve(strict=True))
        entry = sources.setdefault(path, {"roles": set(), "names": set(), "sizes": set(), "hashes": set()})
        entry["roles"].add(role)  # type: ignore[union-attr]
        entry["names"].add(name)  # type: ignore[union-attr]
        if not isinstance(row.get("size_bytes"), int):
            raise ValueError(f"runtime manifest {role} size is invalid")
        entry["sizes"].add(int(row["size_bytes"]))  # type: ignore[union-attr]
        digest = row.get("sha256")
        if digest is not None:
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"runtime manifest {role} hash is invalid")
            entry["hashes"].add(digest)  # type: ignore[union-attr]

    interpreter = runtime.get("elf_interpreter")
    add(interpreter, "elf_interpreter", "elf_interpreter")
    direct = runtime.get("dependencies")
    transitive = runtime.get("transitive_loader_mappings")
    if not isinstance(direct, list) or not direct or not isinstance(transitive, list) or not transitive:
        raise ValueError("runtime manifest dependency sets are absent")
    for row in direct:
        add(row, "direct", str(row.get("name", "")) if isinstance(row, dict) else "")
    for row in transitive:
        add(row, "transitive", str(row.get("name", "")) if isinstance(row, dict) else "")
    return sources


def validate_dependency_lineage(runtime: dict[str, Any], accepted: object) -> list[dict[str, object]]:
    if not isinstance(accepted, list) or not accepted:
        raise ValueError("accepted DiskANN dependency lineage absent")
    sources = runtime_sources(runtime)
    observed: dict[str, dict[str, object]] = {}
    for row in accepted:
        if not isinstance(row, dict):
            raise ValueError("accepted DiskANN dependency row is invalid")
        required = {"name", "roles", "realpath", "size_bytes", "sha256",
                    "manifest_expected_size_bytes", "manifest_expected_sha256"}
        if not required.issubset(row):
            raise ValueError("accepted DiskANN dependency identity is incomplete")
        resolved = Path(str(row["realpath"])).resolve(strict=True)
        realpath = str(resolved)
        if realpath in observed:
            raise ValueError("accepted DiskANN dependency realpath is duplicated")
        if not resolved.is_file():
            raise ValueError(f"DiskANN dependency is not a regular file: {resolved}")
        info = resolved.stat()
        live_hash = sha256(resolved)
        if row["size_bytes"] != info.st_size or row["sha256"] != live_hash:
            raise ValueError(f"DiskANN dependency identity changed: {resolved}")
        roles = row["roles"]
        if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)):
            raise ValueError(f"DiskANN dependency roles invalid: {resolved}")
        observed[realpath] = {
            "name": row["name"], "names": row.get("names", [row["name"]]),
            "roles": roles, "realpath": realpath, "size_bytes": info.st_size, "sha256": live_hash,
            "manifest_expected_size_bytes": row["manifest_expected_size_bytes"],
            "manifest_expected_sha256": row["manifest_expected_sha256"],
        }
    if set(observed) != set(sources):
        raise ValueError("accepted DiskANN dependency path set differs from runtime manifest")
    for path, expected in sources.items():
        row = observed[path]
        if set(row["roles"]) != expected["roles"]:
            raise ValueError(f"DiskANN dependency role set differs from runtime manifest: {path}")
        if expected["sizes"] != {row["size_bytes"]}:
            raise ValueError(f"DiskANN dependency size differs from runtime manifest: {path}")
        expected_hashes = expected["hashes"]
        expected_manifest_hash = next(iter(expected_hashes)) if expected_hashes else None
        if row["manifest_expected_size_bytes"] != row["size_bytes"]:
            raise ValueError(f"DiskANN dependency expected-size binding mismatch: {path}")
        if row["manifest_expected_sha256"] != expected_manifest_hash:
            raise ValueError(f"DiskANN dependency expected-hash binding mismatch: {path}")
        names = row["names"]
        if not isinstance(names, list) or not expected["names"].issubset(set(names)):
            raise ValueError(f"DiskANN dependency aliases differ from runtime manifest: {path}")
    return [observed[path] for path in sorted(observed)]


def validate_accepted_lineage(args: argparse.Namespace, artifact: dict[str, Any]) -> dict[str, object]:
    preflight = json.loads(args.execution_preflight.read_text())
    if preflight.get("status") != "pass" or preflight.get("schema") != "dynamic-vamana-w1-cp05-cumulative-r08-preflight-v1":
        raise ValueError("CP05 R08 execution preflight is not accepted")
    lineage = preflight.get("diskann_lineage")
    if not isinstance(lineage, dict):
        raise ValueError("DiskANN accepted lineage absent from execution preflight")
    required = {"runtime_manifest", "loader_tests", "runtime_environment", "base_content_manifest",
                "base_mode_manifest", "base_root_realpath", "dependencies"}
    if not required.issubset(lineage):
        raise ValueError("DiskANN accepted lineage is incomplete")

    accepted_runtime = require_standard_identity(
        lineage["runtime_manifest"], args.runtime_manifest, "R08 runtime manifest"
    )
    accepted_loader = require_standard_identity(lineage["loader_tests"], None, "R08 loader tests")
    accepted_environment = require_standard_identity(
        lineage["runtime_environment"], None, "R08 runtime environment"
    )
    accepted_base_content = require_standard_identity(
        lineage["base_content_manifest"], None, "R08 base content manifest"
    )
    accepted_base_mode = require_standard_identity(
        lineage["base_mode_manifest"], None, "R08 base mode manifest"
    )
    base_root = args.base_root.resolve(strict=True)
    if not base_root.is_dir() or str(base_root) != lineage["base_root_realpath"]:
        raise ValueError("DiskANN accepted base root mismatch")
    if base_root != Path(artifact["systems"]["DiskANN"]["formal_base"]["realpath"]).resolve(strict=True):
        raise ValueError("DiskANN artifact/accepted base realpath mismatch")
    if args.base_manifest.read_bytes() != Path(str(accepted_base_content["realpath"])).read_bytes():
        raise ValueError("current DiskANN base content differs from accepted R07 lineage")
    if args.base_mode_manifest.read_bytes() != Path(str(accepted_base_mode["realpath"])).read_bytes():
        raise ValueError("current DiskANN base mode differs from accepted R07 lineage")

    runtime = json.loads(args.runtime_manifest.read_text())
    if (runtime.get("schema") != "dynamic-vamana-w1-diskann-runtime-manifest-v1"
            or runtime.get("status") != "pass" or runtime.get("not_found_dependencies") != []):
        raise ValueError("R08 runtime manifest verdict/schema invalid")
    dependencies = validate_dependency_lineage(runtime, lineage["dependencies"])

    loader = json.loads(Path(str(accepted_loader["realpath"])).read_text())
    accepted_env_payload = json.loads(Path(str(accepted_environment["realpath"])).read_text())
    if (loader.get("status") != "pass"
            or loader.get("runtime_manifest", {}).get("sha256") != accepted_runtime["sha256"]
            or loader.get("positive_loader", {}).get("all_direct_dependencies_exact") is not True
            or loader.get("positive_loader", {}).get("passed") is not True
            or loader.get("negative_loader", {}).get("passed") is not True
            or loader.get("query_smoke", {}).get("passed") is not True
            or loader.get("immutable_base", {}).get("exact") is not True):
        raise ValueError("accepted R07 loader tests do not carry the required pass evidence")
    if (accepted_env_payload.get("status") != "pass"
            or accepted_env_payload.get("runtime_manifest", {}).get("sha256") != accepted_runtime["sha256"]
            or accepted_env_payload.get("binary", {}).get("sha256") != sha256(args.binary)
            or accepted_env_payload.get("uid") != 1000 or accepted_env_payload.get("gid") != 1000
            or accepted_env_payload.get("affinity", {}).get("Cpus_allowed_list") != "0-23"
            or accepted_env_payload.get("membind_node") != 0):
        raise ValueError("accepted R07 runtime environment is invalid")

    preflight_binary = preflight.get("binaries", {}).get("DiskANN_search_disk_index")
    require_standard_identity(preflight_binary, args.binary, "preflight DiskANN binary")
    require_standard_identity(preflight.get("artifact_manifest"), args.artifact_manifest, "preflight artifact manifest")
    protected = preflight.get("protected_artifacts")
    if not isinstance(protected, dict):
        raise ValueError("preflight protected identities absent")
    require_standard_identity(protected.get("query"), args.query, "preflight formal query")
    require_standard_identity(protected.get("cp05_gt"), args.gt, "preflight CP05 GT")
    return {
        "execution_preflight": standard_identity(args.execution_preflight),
        "runtime_manifest": accepted_runtime,
        "loader_tests": accepted_loader,
        "accepted_runtime_environment": accepted_environment,
        "base_content_manifest": accepted_base_content,
        "base_mode_manifest": accepted_base_mode,
        "base_root_realpath": str(base_root),
        "dependencies": dependencies,
    }


def device_counter(sample: dict, device: str, key: str) -> int:
    return next(
        (int(row.get(key, 0)) for row in sample.get("cgroup_io_stat", []) if row.get("device") == device),
        0,
    )


def parse_metrics(log: str, expected_l: int) -> dict[str, float | int]:
    lines = log.splitlines()
    header = next((i for i, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("Recall@10 table absent")
    for line in lines[header + 1 :]:
        fields = line.split()
        if not fields or not fields[0].isdigit():
            continue
        if len(fields) != 9 or int(fields[0]) != expected_l:
            raise ValueError("actual L or metric-table shape mismatch")
        values = [float(value) for value in fields[2:]]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("non-finite DiskANN metric")
        recall = values[-1] / 100.0
        if not 0.0 <= recall <= 1.0:
            raise ValueError("Recall outside [0,1]")
        return {
            "actual_L": int(fields[0]),
            "beamwidth": int(fields[1]),
            "qps": values[0],
            "mean_latency_us": values[1],
            "reported_tail_latency_us": values[2],
            "reported_tail_percentile": 99.9,
            "mean_ios": values[3],
            "mean_io_latency_us": values[4],
            "cpu_seconds": values[5],
            "recall_at_10": recall,
        }
    raise ValueError("DiskANN metric row absent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--base-mode-manifest", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--execution-preflight", type=Path, required=True)
    parser.add_argument("--runtime-environment", type=Path, required=True)
    parser.add_argument("--expected-scope", required=True)
    parser.add_argument("--device", default="259:10")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    artifact = json.loads(args.artifact_manifest.read_text())
    frozen = artifact["systems"]["DiskANN"]
    if sha256(args.binary) != frozen["binary_sha256"]["search_disk_index"]:
        raise SystemExit("DiskANN query binary identity mismatch")
    if sha256(args.base_manifest) != frozen["formal_base"]["manifest_sha256"]:
        raise SystemExit("DiskANN CP00 base identity mismatch")
    if sha256(args.query) != artifact["formal_inputs"]["query"]["sha256"]:
        raise SystemExit("DiskANN formal query identity mismatch")
    try:
        accepted_lineage = validate_accepted_lineage(args, artifact)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"DiskANN accepted lineage validation failed: {exc}") from exc
    after_content = args.result_dir / "cp00_index_manifest_after.tsv"
    after_mode = args.result_dir / "cp00_index_mode_after.tsv"
    if after_content.read_bytes() != args.base_manifest.read_bytes():
        raise SystemExit("DiskANN CP00 base content changed")
    if after_mode.read_bytes() != args.base_mode_manifest.read_bytes():
        raise SystemExit("DiskANN CP00 base mode changed")

    runtime = json.loads(args.runtime_manifest.read_text())
    environment = json.loads(args.runtime_environment.read_text())
    if runtime.get("status") != "pass" or runtime.get("binary", {}).get("sha256") != sha256(args.binary):
        raise SystemExit("DiskANN frozen runtime manifest invalid")
    if (
        environment.get("status") != "pass"
        or environment.get("uid") != 1000
        or environment.get("gid") != 1000
        or environment.get("expected_scope") != args.expected_scope
        or environment.get("affinity", {}).get("Cpus_allowed_list") != "0-23"
        or environment.get("membind_node") != 0
        or not any(args.expected_scope in row for row in environment.get("cgroup", []))
        or environment.get("ld_library_path") != runtime.get("runtime_library_path")
    ):
        raise SystemExit("DiskANN runtime environment mismatch")

    with args.query.open("rb") as stream:
        query_count, query_dim = struct.unpack("<II", stream.read(8))
    points: list[dict[str, object]] = []
    for l_value in (29, 53):
        for repetition in (1, 2, 3):
            stem = args.result_dir / f"L{l_value}_r{repetition}"
            result = Path(f"{stem}_{l_value}_idx_uint32.bin")
            with result.open("rb") as stream:
                rows, width = struct.unpack("<II", stream.read(8))
            if (rows, width) != (query_count, 10) or result.stat().st_size != 8 + rows * width * 4:
                raise SystemExit(f"invalid result shape L={l_value} repetition={repetition}")
            ids = np.memmap(result, dtype="<u4", mode="r", offset=8, shape=(rows, width))
            if np.any(ids == np.iinfo(np.uint32).max):
                raise SystemExit("sentinel result ID present")
            if np.any(np.sort(ids, axis=1)[:, 1:] == np.sort(ids, axis=1)[:, :-1]):
                raise SystemExit("duplicate top-10 result ID present")
            log_path = stem.with_suffix(".log")
            log = log_path.read_text(errors="replace")
            if FATAL.search(log) or not re.search(r"Search parameters:\s*#threads:\s*1", log):
                raise SystemExit(f"fatal/log policy violation L={l_value} repetition={repetition}")
            resources_path = stem.with_suffix(".resources.json")
            resources = json.loads(resources_path.read_text())
            samples = resources.get("samples", [])
            reads = (
                device_counter(samples[-1], args.device, "rbytes")
                - device_counter(samples[0], args.device, "rbytes")
                if samples
                else 0
            )
            events = resources.get("cgroup_memory_events_final", {})
            if (
                resources.get("returncode") != 0
                or reads <= 0
                or any(int(events.get(name, 0)) for name in ("oom", "oom_kill", "oom_group_kill"))
            ):
                raise SystemExit(f"resource identity-v2 failed L={l_value} repetition={repetition}")
            points.append(
                {
                    "L": l_value,
                    "Tq": 1,
                    "repetition": repetition,
                    **parse_metrics(log, l_value),
                    "nvme_read_bytes": reads,
                    "result_shape": [rows, width],
                    "result_ids_sha256": sha256(result),
                    "result_top10_unique": True,
                    "sentinel_absent": True,
                    "resources_realpath": str(resources_path.resolve()),
                    "resources_sha256": sha256(resources_path),
                }
            )
    report = {
        "schema": "dynamic-vamana-w1-diskann-cp05-stale-r08-v1",
        "status": "pass",
        "classification": "stale-static negative control",
        "rank_with_update_throughput": False,
        "stale_result_ids_may_be_inactive_at_cp05": True,
        "query_shape": [query_count, query_dim],
        "identities": {
            "binary": {"realpath": str(args.binary.resolve()), "sha256": sha256(args.binary)},
            "cp00_index_manifest": {"realpath": str(args.base_manifest.resolve()), "sha256": sha256(args.base_manifest)},
            "query": {"realpath": str(args.query.resolve()), "sha256": sha256(args.query)},
            "cp05_gt": {"realpath": str(args.gt.resolve()), "sha256": sha256(args.gt)},
            "runtime_manifest": {"realpath": str(args.runtime_manifest.resolve()), "sha256": sha256(args.runtime_manifest)},
            "runtime_environment": {"realpath": str(args.runtime_environment.resolve()), "sha256": sha256(args.runtime_environment)},
            "accepted_r07_lineage": accepted_lineage,
        },
        "points": points,
        "cp00_base_content_preserved": True,
        "cp00_base_mode_preserved": True,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
