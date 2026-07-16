#!/usr/bin/env python3
"""Fail-closed preflight for the CP00->CP01->CP05 cumulative trajectory."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


EXPECTED_TRAJECTORY_VALIDATION_SHA256 = (
    "cb19e056eb19fbdac27a6d52b98757427c981f9f5d78dd710ad7246c3c4f7848"
)
EXPECTED_MASTER_BIN_SHA256 = (
    "039fdff996d26dc51ca3715f2a9b3b32a840feb6fb6aa49e3d3be838df357880"
)
EXPECTED_MASTER_TSV_SHA256 = (
    "925686659fd0db94e87bb25e4632bbb511e6a36dea6643ecc7db4a5390dd980d"
)
ACCEPTED_BASES = {
    "DGAI": {
        "content_sha256": "980ce1c3ed6eb5bef4a595c74dab641b5cd5da5a606786c753d3d00cd5ddcaa5",
        "mode_sha256": "d9c252ccb6deaeaec45515a6bf9c47bbe79bb93fe18ad98264fea73c6f55a56a",
        "source_run": "pilot3_sift10m_w1_r05",
    },
    "OdinANN": {
        "content_sha256": "50d5aacb142bf352c0fb63920cc85573fdced5dccf9d7c5dd16586442b3a0a4e",
        "mode_sha256": "32f2028de52702181e508a8041a756a3df4bf9221a2b03be1c459c37d3ff0040",
        "source_run": "pilot3_sift10m_w1_r06",
    },
    "DiskANN": {
        "content_sha256": "301f374cf8bd7037ef4506f7bcc228e504675e64d88a4729b83c185939c019bb",
        "mode_sha256": "0ade9f8550321e6024d31ca30c882e0990b720e7d1bfea14773316df5e00b6fc",
        "source_run": "pilot3_sift10m_w1_r07",
    },
}
R07_RUNTIME_MANIFEST_SHA256 = "c8fc63365d4fe388ba9b8b49fd9edee3b8b6c4a04574e5bcf0aa1e0ec67347d2"
R07_LOADER_TESTS_SHA256 = "916d7976666ab2fb237298bf913185f256b708b390c2ccb8a7e3131abbcc86e7"
R07_RUNTIME_ENVIRONMENT_SHA256 = "ed515b92d8a5495ba2ce87804c039b18ba8c5aa5220b78d161bc05384c46a756"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    stat = path.stat()
    return {
        "realpath": str(path),
        "size_bytes": stat.st_size,
        "sha256": sha256(path),
        "mtime_ns": stat.st_mtime_ns,
        "mode": stat.st_mode & 0o7777,
        "uid": stat.st_uid,
        "gid": stat.st_gid,
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_manifest(root: Path) -> bytes:
    root = root.resolve(strict=True)
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise SystemExit(f"base content manifest refuses symlink: {path}")
        rows.append(f"{path.relative_to(root)}\t{path.stat().st_size}\t{sha256(path)}")
    return (("\n".join(rows) + "\n") if rows else "").encode()


def mode_manifest(root: Path) -> bytes:
    root = root.resolve(strict=True)
    rows: list[dict[str, str]] = []

    def visit(path: Path, relative: str) -> None:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat.S_ISREG(info.st_mode):
            kind = "regular"
        else:
            raise SystemExit(f"unsupported base object: {path}")
        rows.append({"relative_path": relative, "type": kind, "uid": str(info.st_uid),
                     "gid": str(info.st_gid), "mode_octal": f"{stat.S_IMODE(info.st_mode):04o}",
                     "inode": str(info.st_ino), "link_count": str(info.st_nlink)})
        if kind == "directory":
            for name in sorted(entry.name for entry in os.scandir(path)):
                visit(path / name, name if relative == "." else f"{relative}/{name}")

    visit(root, ".")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream,
                            fieldnames=("relative_path", "type", "uid", "gid", "mode_octal", "inode", "link_count"),
                            delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def write_new(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise SystemExit(f"preflight evidence overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def mount_device(path: Path) -> str:
    current = path
    while not current.exists():
        current = current.parent
    result = subprocess.run(
        ["findmnt", "-rn", "-T", str(current), "-o", "MAJ:MIN"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines()[0]


def available_memory() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable absent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--replay-formal-root", type=Path, required=True)
    parser.add_argument("--delta-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    result_root = args.result_root.resolve(strict=False)
    formal_root = args.formal_root.resolve(strict=False)
    replay_root = args.replay_formal_root.resolve(strict=False)
    delta_root = args.delta_root.resolve(strict=False)
    output = args.output.resolve(strict=False)
    if output != result_root / "preflight/execution_preflight.json":
        raise SystemExit("preflight output is not capability-bound to result root")
    for path in (result_root, formal_root, replay_root, delta_root, args.report):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"fresh target already exists: {path}")
    output.parent.mkdir(parents=True, exist_ok=False)

    expected_device = os.environ.get("ATLAS_NVME_MAJMIN", "259:10")
    for path in (root, formal_root.parent, replay_root.parent, delta_root.parent):
        if mount_device(path) != expected_device:
            raise SystemExit(f"large-artifact path is not on project NVMe: {path}")
    free_bytes = shutil.disk_usage(root).free
    memory_bytes = available_memory()
    if free_bytes < 128 * 1024**3:
        raise SystemExit("128 GiB free-space launch guard failed")
    if memory_bytes < 64 * 1024**3:
        raise SystemExit("64 GiB MemAvailable launch guard failed")
    expected_tmp = (root / "tmp/pilot3_sift10m_w1_cp05_trajectory").resolve(strict=False)
    if os.environ.get("TMPDIR") != str(expected_tmp):
        raise SystemExit("TMPDIR is not capability-bound to project NVMe")
    if os.environ.get("W1_GLOBAL_LOCK_HELD") != "1":
        raise SystemExit("global W1 flock marker absent")

    prep_result = root / "results/pilot3_sift10m_w1_trajectory_prep"
    prep_execution = json.loads((prep_result / "execution_manifest.json").read_text())
    if prep_execution.get("status") != "complete" or not (
        prep_result / "FORMAL_TRAJECTORY_PREPARATION_COMPLETE"
    ).is_file():
        raise SystemExit("trajectory preparation is not complete")
    trajectory_validation = prep_result / "trajectory_validation.json"
    if sha256(trajectory_validation) != EXPECTED_TRAJECTORY_VALIDATION_SHA256:
        raise SystemExit("trajectory validation identity mismatch")

    trajectory = root / "datasets/sift10m/w1_trajectory"
    cp01 = root / "datasets/sift10m/w1_cp01"
    protected_paths = {
        "trajectory_validation": trajectory_validation,
        "trajectory_master_bin": trajectory / "master_replacements_1600k.bin",
        "trajectory_master_tsv": trajectory / "master_replacements_1600k.tsv",
        "trajectory_master_manifest": trajectory / "master_trace_manifest.json",
        "trajectory_cp01_prefix_validation": trajectory / "cp01_prefix_validation.json",
        "historical_cp01_trace_bin": cp01 / "replace_cp01_80k.bin",
        "historical_cp01_trace_tsv": cp01 / "replace_cp01_80k.tsv",
        "historical_cp01_active_tags": cp01 / "active_cp01.tags.bin",
        "historical_cp01_global_probes_bin": cp01 / "visibility_probes.bin",
        "historical_cp01_global_probes_json": cp01 / "visibility_probes.json",
        "cp05_prefix_bin": trajectory / "cp05/replace_cp05.bin",
        "cp05_prefix_tsv": trajectory / "cp05/replace_cp05.tsv",
        "cp05_active_tags": trajectory / "cp05/active_cp05.tags.bin",
        "cp05_global_probes_bin": trajectory / "cp05/visibility_probes.bin",
        "cp05_global_probes_json": trajectory / "cp05/visibility_probes.json",
        "full_corpus": root / "datasets/sift10m/full_10m.bin",
        "query": root / "datasets/sift10m/query.bin",
        "cp00_active_tags": root / "datasets/sift10m/active_cp00.tags.bin",
        "cp00_gt": root / "groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00",
        "cp01_gt": root / "groundtruth/sift10m/w1_r02/gt_cp01",
        "cp05_gt": root / "groundtruth/sift10m/w1_trajectory/cp05/gt_cp05",
        "accepted_DGAI_base_content_manifest": root / "results/pilot3_sift10m_w1_r05/preflight/base_before/DGAI.content.tsv",
        "accepted_DGAI_base_mode_manifest": root / "results/pilot3_sift10m_w1_r05/preflight/base_before/DGAI.mode.tsv",
        "accepted_OdinANN_base_content_manifest": root / "results/pilot3_sift10m_w1_r06/preflight/base_before/OdinANN.content.tsv",
        "accepted_OdinANN_base_mode_manifest": root / "results/pilot3_sift10m_w1_r06/preflight/base_before/OdinANN.mode.tsv",
        "accepted_DiskANN_base_content_manifest": root / "results/pilot3_sift10m_w1_r07/preflight/base_before/DiskANN.content.tsv",
        "accepted_DiskANN_base_mode_manifest": root / "results/pilot3_sift10m_w1_r07/preflight/base_before/DiskANN.mode.tsv",
        "r07_diskann_runtime_manifest": root / "results/pilot3_sift10m_w1_r07/preflight/diskann_runtime_manifest.json",
        "r07_diskann_loader_tests": root / "results/pilot3_sift10m_w1_r07/preflight/diskann_loader_tests.json",
        "r07_diskann_runtime_environment": root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07/runtime_environment.json",
    }
    # CP10/CP20 remain held, but are protected against accidental mutation.
    for checkpoint in ("cp10", "cp20"):
        for name in (
            f"replace_{checkpoint}.bin",
            f"replace_{checkpoint}.tsv",
            f"active_{checkpoint}.tags.bin",
            "visibility_probes.bin",
            "visibility_probes.json",
        ):
            protected_paths[f"held_{checkpoint}_{name}"] = trajectory / checkpoint / name

    protected = {name: identity(path) for name, path in protected_paths.items()}
    if protected["trajectory_master_bin"]["sha256"] != EXPECTED_MASTER_BIN_SHA256:
        raise SystemExit("master binary hash mismatch")
    if protected["trajectory_master_tsv"]["sha256"] != EXPECTED_MASTER_TSV_SHA256:
        raise SystemExit("master TSV hash mismatch")

    artifact = json.loads(args.artifact_manifest.read_text())
    dynamic_base_lineage: dict[str, dict[str, object]] = {}
    accepted_manifest_keys = {
        "DGAI": ("accepted_DGAI_base_content_manifest", "accepted_DGAI_base_mode_manifest"),
        "OdinANN": ("accepted_OdinANN_base_content_manifest", "accepted_OdinANN_base_mode_manifest"),
        "DiskANN": ("accepted_DiskANN_base_content_manifest", "accepted_DiskANN_base_mode_manifest"),
    }
    for system, anchors in ACCEPTED_BASES.items():
        entry = artifact["systems"][system]["formal_base"]
        base_root = Path(entry["realpath"]).resolve(strict=True)
        if str(base_root) != entry["realpath"]:
            raise SystemExit(f"{system} formal base realpath is not canonical")
        if entry["manifest_sha256"] != anchors["content_sha256"]:
            raise SystemExit(f"{system} artifact base content anchor mismatch")
        content_key, mode_key = accepted_manifest_keys[system]
        if protected[content_key]["sha256"] != anchors["content_sha256"]:
            raise SystemExit(f"{system} accepted content evidence anchor mismatch")
        if protected[mode_key]["sha256"] != anchors["mode_sha256"]:
            raise SystemExit(f"{system} accepted mode evidence anchor mismatch")
        live_content = content_manifest(base_root)
        live_mode = mode_manifest(base_root)
        if sha256_bytes(live_content) != anchors["content_sha256"]:
            raise SystemExit(f"{system} live CP00 base differs from accepted content")
        if sha256_bytes(live_mode) != anchors["mode_sha256"]:
            raise SystemExit(f"{system} live CP00 base differs from accepted ownership/mode/inode lineage")
        live_dir = output.parent / "live_bases"
        content_path = live_dir / f"{system}.content.tsv"
        mode_path = live_dir / f"{system}.mode.tsv"
        write_new(content_path, live_content)
        write_new(mode_path, live_mode)
        protected[f"live_{system}_base_content_manifest"] = identity(content_path)
        protected[f"live_{system}_base_mode_manifest"] = identity(mode_path)
        dynamic_base_lineage[system] = {
            "status": "pass", "source_run": anchors["source_run"],
            "base_root_realpath": str(base_root),
            "artifact_content_sha256": entry["manifest_sha256"],
            "accepted_content_manifest": protected[content_key],
            "accepted_mode_manifest": protected[mode_key],
            "live_content_manifest": protected[f"live_{system}_base_content_manifest"],
            "live_mode_manifest": protected[f"live_{system}_base_mode_manifest"],
            "content_exact": True, "mode_exact": True,
        }

    runtime_path = Path(protected["r07_diskann_runtime_manifest"]["realpath"])
    loader_path = Path(protected["r07_diskann_loader_tests"]["realpath"])
    environment_path = Path(protected["r07_diskann_runtime_environment"]["realpath"])
    if protected["r07_diskann_runtime_manifest"]["sha256"] != R07_RUNTIME_MANIFEST_SHA256:
        raise SystemExit("accepted R07 runtime manifest SHA mismatch")
    if protected["r07_diskann_loader_tests"]["sha256"] != R07_LOADER_TESTS_SHA256:
        raise SystemExit("accepted R07 loader tests SHA mismatch")
    if protected["r07_diskann_runtime_environment"]["sha256"] != R07_RUNTIME_ENVIRONMENT_SHA256:
        raise SystemExit("accepted R07 runtime environment SHA mismatch")
    runtime = json.loads(runtime_path.read_text())
    loader = json.loads(loader_path.read_text())
    environment = json.loads(environment_path.read_text())
    disk_binary = (root / "build/DiskANN/apps/search_disk_index").resolve(strict=True)
    protected["diskann_runtime_binary"] = identity(disk_binary)
    if (runtime.get("schema") != "dynamic-vamana-w1-diskann-runtime-manifest-v1"
            or runtime.get("status") != "pass" or runtime.get("not_found_dependencies") != []
            or runtime.get("binary", {}).get("realpath") != str(disk_binary)
            or runtime.get("binary", {}).get("sha256") != artifact["systems"]["DiskANN"]["binary_sha256"]["search_disk_index"]):
        raise SystemExit("R07 DiskANN runtime lineage schema/binary mismatch")
    if (loader.get("schema") != "dynamic-vamana-w1-r07-diskann-loader-tests-v1"
            or loader.get("status") != "pass"
            or loader.get("runtime_manifest", {}).get("sha256") != R07_RUNTIME_MANIFEST_SHA256
            or loader.get("positive_loader", {}).get("all_direct_dependencies_exact") is not True
            or loader.get("immutable_base", {}).get("before_sha256") != ACCEPTED_BASES["DiskANN"]["content_sha256"]
            or loader.get("immutable_base", {}).get("after_sha256") != ACCEPTED_BASES["DiskANN"]["content_sha256"]):
        raise SystemExit("R07 DiskANN loader-test lineage mismatch")
    if (environment.get("schema") != "dynamic-vamana-w1-diskann-runtime-environment-v1"
            or environment.get("status") != "pass"
            or environment.get("runtime_manifest", {}).get("sha256") != R07_RUNTIME_MANIFEST_SHA256
            or environment.get("binary", {}).get("sha256") != runtime["binary"]["sha256"]
            or environment.get("ld_library_path") != runtime.get("runtime_library_path")):
        raise SystemExit("R07 DiskANN accepted runtime environment lineage mismatch")

    dependency_rows: dict[str, dict[str, object]] = {}
    dependency_sources = [("elf_interpreter", runtime["elf_interpreter"])]
    dependency_sources.extend(("direct", row) for row in runtime.get("dependencies", []))
    dependency_sources.extend(("transitive", row) for row in runtime.get("transitive_loader_mappings", []))
    for role, row in dependency_sources:
        realpath = str(Path(row["resolved_realpath"]).resolve(strict=True))
        live = identity(Path(realpath))
        if live["realpath"] != realpath or live["size_bytes"] != row["size_bytes"]:
            raise SystemExit(f"DiskANN dependency realpath/size mismatch: {row.get('name', role)}")
        if row.get("sha256") is not None and live["sha256"] != row["sha256"]:
            raise SystemExit(f"DiskANN dependency SHA mismatch: {row.get('name', role)}")
        item = dependency_rows.setdefault(realpath, {
            "name": row.get("name", "elf_interpreter"), "names": set(), "roles": set(),
            "realpath": realpath, "size_bytes": live["size_bytes"], "sha256": live["sha256"],
            "manifest_expected_size_bytes": row["size_bytes"], "manifest_expected_sha256": row.get("sha256"),
        })
        item["names"].add(row.get("name", "elf_interpreter"))
        item["roles"].add(role)
    dependencies = []
    for index, (realpath, item) in enumerate(sorted(dependency_rows.items())):
        item["names"] = sorted(item["names"])
        item["roles"] = sorted(item["roles"])
        dependencies.append(item)
        protected[f"diskann_dependency_{index:02d}"] = identity(Path(realpath))

    diskann_lineage = {
        "schema": "dynamic-vamana-w1-cp05-diskann-lineage-v1", "status": "pass",
        "runtime_manifest": protected["r07_diskann_runtime_manifest"],
        "loader_tests": protected["r07_diskann_loader_tests"],
        "runtime_environment": protected["r07_diskann_runtime_environment"],
        "base_content_manifest": protected["accepted_DiskANN_base_content_manifest"],
        "base_mode_manifest": protected["accepted_DiskANN_base_mode_manifest"],
        "base_root_realpath": dynamic_base_lineage["DiskANN"]["base_root_realpath"],
        "live_base_content_manifest": dynamic_base_lineage["DiskANN"]["live_content_manifest"],
        "live_base_mode_manifest": dynamic_base_lineage["DiskANN"]["live_mode_manifest"],
        "binary": protected["diskann_runtime_binary"], "runtime_library_path": runtime["runtime_library_path"],
        "dt_needed": runtime["dt_needed"], "dependencies": dependencies,
        "accepted_anchor_sha256": {"runtime_manifest": R07_RUNTIME_MANIFEST_SHA256,
                                     "loader_tests": R07_LOADER_TESTS_SHA256,
                                     "runtime_environment": R07_RUNTIME_ENVIRONMENT_SHA256,
                                     "base_content": ACCEPTED_BASES["DiskANN"]["content_sha256"],
                                     "base_mode": ACCEPTED_BASES["DiskANN"]["mode_sha256"]},
    }
    formal_inputs = artifact.get("formal_inputs", {})
    expected_hashes = {
        "full_corpus": formal_inputs["full_corpus"]["sha256"],
        "query": formal_inputs["query"]["sha256"],
        "cp00_active_tags": formal_inputs["active_cp00_tags"]["sha256"],
    }
    for name, digest in expected_hashes.items():
        if protected[name]["sha256"] != digest:
            raise SystemExit(f"frozen formal input mismatch: {name}")

    canonical = root / "build/w1-canonical-v6/install"
    binaries = {
        f"{system}_{name}": identity(canonical / system / name)
        for system in ("DGAI", "OdinANN")
        for name in ("w1_canary", "search_disk_index")
    }
    diskann_binary = root / "build/DiskANN/apps/search_disk_index"
    binaries["DiskANN_search_disk_index"] = identity(diskann_binary)
    for system in ("DGAI", "OdinANN"):
        entry = artifact["systems"][system]
        for name in ("w1_canary", "search_disk_index"):
            if binaries[f"{system}_{name}"]["sha256"] != entry["binary_sha256"][name]:
                raise SystemExit(f"canonical binary hash mismatch: {system}/{name}")

    report = {
        "schema": "dynamic-vamana-w1-cp05-cumulative-preflight-v1",
        "status": "pass",
        "authorized_sequence": ["CP00", "CP01", "CP05"],
        "held_checkpoints": ["CP10", "CP20"],
        "fresh_targets": {
            "result_root": str(result_root),
            "formal_root": str(formal_root),
            "replay_formal_root": str(replay_root),
            "delta_root": str(delta_root),
            "report": str(args.report.resolve(strict=False)),
        },
        "experiment_device": expected_device,
        "free_bytes": free_bytes,
        "memory_available_bytes": memory_bytes,
        "space_budget_bytes": 64 * 1024**3,
        "launch_space_guard_bytes": 128 * 1024**3,
        "launch_memory_guard_bytes": 64 * 1024**3,
        "nominal_wall_minutes": [35, 50],
        "conservative_wall_minutes": [90, 120],
        "controller_hard_limit_hours": 3,
        "tmpdir": str(expected_tmp),
        "protected_artifacts": protected,
        "dynamic_base_lineage": dynamic_base_lineage,
        "diskann_lineage": diskann_lineage,
        "binaries": binaries,
        "artifact_manifest": identity(args.artifact_manifest),
        "trajectory_preparation_execution": identity(prep_result / "execution_manifest.json"),
        "trajectory_preparation_validation": identity(trajectory_validation),
        "negative_authorization": {
            "cp10_update": False,
            "cp20_update": False,
            "full_400k_on_cp01": False,
            "independent_cp05_clone": False,
            "diskann_rebuild": False,
            "mixed_workload": False,
            "w2_deep_gist": False,
        },
    }
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
