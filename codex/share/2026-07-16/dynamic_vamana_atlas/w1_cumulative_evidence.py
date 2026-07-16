#!/usr/bin/env python3
"""Fail-closed cumulative W1 query, freeze, and checkpoint evidence gates.

The three public subcommands deliberately keep policy separate from execution:

* ``query-gate`` validates already-produced query artifacts and binds them to
  exact binary/index/input identities.
* ``freeze`` snapshots a private mutable clone, freezes it to 0555/0444, then
  proves that its owner can no longer write files or create directory entries.
* ``stage-evidence`` consolidates one raw update stage into a single contract.
* ``checkpoint`` binds a checkpoint state, update-worker identity, active-tag
  audit, and query gates into a cumulative CP01/CP05 evidence record.

All evidence outputs are create-only and all tree walks refuse symlinks,
hard-linked regular files, and special files.
"""
from __future__ import annotations

import argparse
import csv
import errno
import hashlib
import json
import math
import os
import pwd
import re
import secrets
import stat
import statistics
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np


DENIAL_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}
FATAL_LOG = re.compile(
    r"fatal|assert(?:ion)?(?: failed)?|EBADF|negative CQE|I/O error|"
    r"\bEIO\b|segmentation fault|core dumped|std::bad_alloc|out of memory|"
    r"\boom(?:[_-](?:kill|group[_-]kill))?\b|"
    r"killed process",
    re.IGNORECASE,
)
MODE_FIELDS = (
    "relative_path", "type", "uid", "gid", "mode_octal", "inode", "link_count"
)
METRIC_FIELDS = (
    "qps", "mean_latency_us", "p50_latency_us", "p95_latency_us",
    "p99_latency_us", "mean_ios", "recall_at_10_percent",
)


class GateError(RuntimeError):
    """A fail-closed evidence-gate error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read JSON evidence {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON evidence is not an object: {path}")
    return value


def write_new_bytes(path: Path, payload: bytes) -> None:
    """Atomically create an evidence file, refusing an existing destination."""
    require(not path.exists(), f"evidence overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.partial.{os.getpid()}.{secrets.token_hex(6)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.close(descriptor)
        descriptor = -1
        # Recheck immediately before replace: os.replace itself is atomic but
        # would otherwise overwrite a concurrently-created evidence file.
        require(not path.exists(), f"concurrent evidence overwrite refused: {path}")
        os.link(temporary, path)
        os.unlink(temporary)
        # The root controller writes into capability directories owned by the
        # experiment owner; inherit that directory ownership so a subsequent
        # owner-UID freeze can read the checkpoint it must bind.
        if os.geteuid() == 0:
            parent_info = path.parent.stat()
            os.chown(path, parent_info.st_uid, parent_info.st_gid)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    write_new_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def canonical_path(path: Path, *, regular: bool = False, directory: bool = False) -> Path:
    require(not path.is_symlink(), f"symlink path refused: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise GateError(f"missing/unresolvable path {path}: {exc}") from exc
    if regular:
        require(resolved.is_file(), f"regular file required: {resolved}")
    if directory:
        require(resolved.is_dir(), f"directory required: {resolved}")
    return resolved


def under(path: Path, root: Path) -> bool:
    candidate = path.resolve(strict=False)
    return candidate == root or root in candidate.parents


def tree_objects(root_arg: Path) -> tuple[Path, list[Path], list[Path]]:
    root = canonical_path(root_arg, directory=True)
    directories: list[Path] = []
    files: list[Path] = []

    def visit(path: Path) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise GateError(f"symlink refused in evidence tree: {path}")
        if stat.S_ISDIR(info.st_mode):
            directories.append(path)
            with os.scandir(path) as entries:
                children = sorted((Path(entry.path) for entry in entries), key=lambda row: row.name)
            for child in children:
                visit(child)
        elif stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1, f"hard-link risk refused: {path} nlink={info.st_nlink}")
            files.append(path)
        else:
            raise GateError(f"unsupported tree object refused: {path}")

    visit(root)
    return root, directories, files


def content_rows(root: Path, files: Iterable[Path]) -> list[tuple[str, int, str]]:
    return [(path.relative_to(root).as_posix(), path.stat().st_size, sha256(path)) for path in files]


def content_payload(rows: Iterable[tuple[str, int, str]]) -> bytes:
    return "".join(f"{relative}\t{size}\t{digest}\n" for relative, size, digest in rows).encode()


def mode_rows(root: Path, directories: Iterable[Path], files: Iterable[Path]) -> list[dict[str, str]]:
    objects = list(directories) + list(files)
    objects.sort(key=lambda path: ("." if path == root else path.relative_to(root).as_posix()))
    rows: list[dict[str, str]] = []
    for path in objects:
        info = path.lstat()
        rows.append({
            "relative_path": "." if path == root else path.relative_to(root).as_posix(),
            "type": "directory" if stat.S_ISDIR(info.st_mode) else "regular",
            "uid": str(info.st_uid),
            "gid": str(info.st_gid),
            "mode_octal": f"{stat.S_IMODE(info.st_mode):04o}",
            "inode": str(info.st_ino),
            "link_count": str(info.st_nlink),
        })
    return rows


def mode_payload(rows: Iterable[dict[str, str]]) -> bytes:
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=MODE_FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def all_finite(value: Any, location: str = "metrics") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        require(math.isfinite(float(value)), f"non-finite numeric value at {location}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            all_finite(child, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            all_finite(child, f"{location}.{key}")


def memory_event_total(resource: dict[str, Any], key: str) -> int:
    total = 0
    final = resource.get("cgroup_memory_events_final", {})
    if isinstance(final, dict):
        total += int(final.get(key, 0))
    for sample in resource.get("samples", []):
        if isinstance(sample, dict):
            events = sample.get("cgroup_memory_events", {})
            if isinstance(events, dict):
                total += int(events.get(key, 0))
    return total


def device_row(sample: dict[str, Any], device: str) -> dict[str, Any]:
    matches = [row for row in sample.get("cgroup_io_stat", []) if row.get("device") == device]
    require(len(matches) == 1, f"expected exactly one cgroup io row for device {device}")
    return matches[0]


def resource_read_delta(resource: dict[str, Any], device: str) -> tuple[int, int]:
    samples = resource.get("samples", [])
    require(isinstance(samples, list) and len(samples) >= 2, "resource evidence needs >=2 samples")
    first, last = device_row(samples[0], device), device_row(samples[-1], device)
    rbytes = int(last.get("rbytes", -1)) - int(first.get("rbytes", -1))
    rios = int(last.get("rios", -1)) - int(first.get("rios", -1))
    require(rbytes > 0, f"no positive real device read-byte delta on {device}")
    require(rios > 0, f"no positive real device read-I/O delta on {device}")
    return rbytes, rios


def resource_write_delta(resource: dict[str, Any], device: str) -> tuple[int, int]:
    samples = resource.get("samples", [])
    require(isinstance(samples, list) and len(samples) >= 2, "resource evidence needs >=2 samples")
    first, last = device_row(samples[0], device), device_row(samples[-1], device)
    wbytes = int(last.get("wbytes", -1)) - int(first.get("wbytes", -1))
    wios = int(last.get("wios", -1)) - int(first.get("wios", -1))
    require(wbytes > 0 and wios > 0, f"no positive real device write delta on {device}")
    return wbytes, wios


def parse_csv_ints(value: str, label: str) -> list[int]:
    try:
        result = [int(part) for part in value.split(",") if part]
    except ValueError as exc:
        raise GateError(f"invalid {label}: {value}") from exc
    require(result and len(result) == len(set(result)), f"{label} must be nonempty and unique")
    return result


def artifact_identity(path: Path) -> dict[str, Any]:
    resolved = canonical_path(path, regular=True)
    return {"realpath": str(resolved), "size_bytes": resolved.stat().st_size, "sha256": sha256(resolved)}


def query_gate(args: argparse.Namespace) -> dict[str, Any]:
    result_dir = canonical_path(args.result_dir, directory=True)
    binary = artifact_identity(args.binary)
    driver = artifact_identity(args.driver) if args.driver else None
    artifact_manifest = artifact_identity(args.artifact_manifest)
    artifact = json_load(args.artifact_manifest)
    frozen_system = artifact.get("systems", {}).get(args.system, {})
    require(binary["sha256"] == frozen_system.get("binary_sha256", {}).get("search_disk_index"),
            "query binary differs from frozen artifact manifest")
    if driver is not None:
        require(driver["sha256"] == frozen_system.get("binary_sha256", {}).get("w1_canary"),
                "driver differs from frozen artifact manifest")
    if frozen_system.get("io_engine") is not None:
        require(args.io_engine == frozen_system["io_engine"], "I/O engine differs from frozen artifact manifest")
    index_manifest = artifact_identity(args.index_content_manifest)
    query = artifact_identity(args.query)
    gt = artifact_identity(args.gt)
    active_tags = artifact_identity(args.active_tags)
    if args.mode == "formal":
        expected_query = artifact.get("formal_inputs", {}).get("query", {}).get("sha256")
        require(query["sha256"] == expected_query, "formal query differs from frozen artifact manifest")
    with Path(query["realpath"]).open("rb") as stream:
        query_header = stream.read(8)
    require(len(query_header) == 8, "query input header is truncated")
    query_count, query_dimensions = struct.unpack("<II", query_header)
    require(query_count > 0 and query_dimensions > 0, "query input has invalid shape")
    expected_nq = args.expected_nq if args.expected_nq is not None else query_count
    require(expected_nq == query_count, "expected result rows differ from query input rows")
    if args.mode == "formal":
        require(expected_nq == 10_000, "formal identity-v2 requires 10,000 query rows")
    ls_values = parse_csv_ints(args.ls, "Ls")
    repeats = parse_csv_ints(args.repeats, "repeats")

    tags_path = Path(active_tags["realpath"])
    require(tags_path.stat().st_size >= 8, "active-tag file lacks header")
    with tags_path.open("rb") as stream:
        header = stream.read(8)
    tag_count, tag_dim = struct.unpack("<II", header)
    require(tag_dim == 1, f"active-tag dimension must be 1, got {tag_dim}")
    require(tags_path.stat().st_size == 8 + tag_count * 4, "active-tag file size/header mismatch")
    if args.expected_active_count is not None:
        require(tag_count == args.expected_active_count, "active-tag count differs from expected checkpoint")
    tags = np.memmap(tags_path, dtype="<u4", mode="r", offset=8, shape=(tag_count,))
    require(tag_count > 0, "active-tag set is empty")
    unique_tags = np.unique(np.asarray(tags))
    require(len(unique_tags) == tag_count, "active-tag file contains duplicates")
    require(int(unique_tags[-1]) < np.iinfo(np.uint32).max, "active-tag set contains sentinel")

    points: list[dict[str, Any]] = []
    ids_by_l: dict[int, list[np.ndarray]] = {value: [] for value in ls_values}
    for search_l in ls_values:
        for repeat in repeats:
            prefix = f"{args.prefix}_" if args.prefix else ""
            stem = result_dir / f"{prefix}L{search_l}_r{repeat}"
            paths = {
                "metrics": Path(f"{stem}.metrics.json"),
                "validation": Path(f"{stem}.validation.json"),
                "resources": Path(f"{stem}.resources.json"),
                "log": Path(f"{stem}.log"),
                "result_ids": Path(f"{stem}.result_ids.bin"),
            }
            for label, path in paths.items():
                canonical_path(path, regular=True)
                require(path.stat().st_size > 0, f"empty {label} artifact: {path}")

            metrics = json_load(paths["metrics"])
            validation = json_load(paths["validation"])
            resource = json_load(paths["resources"])
            log_text = paths["log"].read_text(errors="replace")
            raw = paths["result_ids"].read_bytes()
            require(len(raw) >= 8, f"result header truncated: {paths['result_ids']}")
            nq, k = struct.unpack("<II", raw[:8])
            require((nq, k) == (expected_nq, args.expected_k),
                    f"result shape is {(nq, k)}, expected {(expected_nq, args.expected_k)}")
            require(k == 10, f"identity-v2 requires top10, got k={k}")
            require(len(raw) == 8 + nq * k * 4, "result byte length/header mismatch")
            ids = np.frombuffer(raw, dtype="<u4", offset=8).reshape(nq, k)
            require(not bool(np.any(ids == np.uint32(0xFFFFFFFF))), "result contains uint32 sentinel")
            sorted_ids = np.sort(ids, axis=1)
            require(not bool(np.any(sorted_ids[:, 1:] == sorted_ids[:, :-1])),
                    "one or more top10 rows contain duplicate IDs")
            flat_ids = ids.reshape(-1)
            positions = np.searchsorted(unique_tags, flat_ids)
            in_range = positions < len(unique_tags)
            require(bool(np.all(in_range)), "result contains ID outside active-tag domain")
            require(bool(np.all(unique_tags[positions] == flat_ids)), "result contains inactive ID")

            for field in METRIC_FIELDS:
                require(field in metrics, f"required metric missing: {field}")
                require(math.isfinite(float(metrics[field])), f"required metric non-finite: {field}")
            all_finite(metrics)
            require(validation.get("query_count") == nq, "validation query_count mismatch")
            require(validation.get("k") == k, "validation k mismatch")
            require(validation.get("all_result_ids_active") is True, "validation reports inactive IDs")
            require(int(validation.get("invalid_or_inactive_ids", -1)) == 0,
                    "validation invalid/inactive count is nonzero")
            recall = float(validation.get("recall_at_10_normalized", float("nan")))
            require(math.isfinite(recall) and 0.0 <= recall <= 1.0, "validation recall is invalid")

            require(resource.get("returncode") == 0, "query process returncode is nonzero")
            space_root = canonical_path(Path(resource.get("space_root", "")), directory=True)
            rbytes, rios = resource_read_delta(resource, args.device)
            oom = {key: memory_event_total(resource, key) for key in ("oom", "oom_kill", "oom_group_kill")}
            require(all(value == 0 for value in oom.values()), f"query resource evidence contains OOM events: {oom}")
            require(not FATAL_LOG.search(log_text), "fatal/assert/I/O/OOM signature found in query log")
            actual_l = [int(value) for value in re.findall(
                r"(?:^|\s)(\d+)\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?",
                log_text, re.MULTILINE,
            )]
            require(search_l in actual_l, f"query log does not prove requested L={search_l}")

            point = {
                "L": search_l,
                "repeat": repeat,
                "recall_at_10": float(metrics["recall_at_10_percent"]) / 100.0,
                "qps": float(metrics["qps"]),
                "p99_latency_us": float(metrics["p99_latency_us"]),
                "device_read_bytes": rbytes,
                "device_read_ios": rios,
                "oom_events": oom,
                "index_root_realpath": str(space_root),
                "artifacts": {label: artifact_identity(path) for label, path in paths.items()},
            }
            points.append(point)
            ids_by_l[search_l].append(ids.copy())

    repeat_diagnostics: list[dict[str, Any]] = []
    for search_l in ls_values:
        arrays = ids_by_l[search_l]
        pairs: list[dict[str, Any]] = []
        for left in range(len(arrays)):
            for right in range(left + 1, len(arrays)):
                exact = float(np.mean(np.all(arrays[left] == arrays[right], axis=1)))
                intersections = np.sum(
                    np.any(arrays[left][:, :, None] == arrays[right][:, None, :], axis=2), axis=1
                )
                pairs.append({
                    "repeats": [repeats[left], repeats[right]],
                    "top10_exact_row_rate": exact,
                    "top10_set_overlap": float(np.mean(intersections / 10.0)),
                })
        l_points = [point for point in points if point["L"] == search_l]
        repeat_diagnostics.append({
            "L": search_l,
            "recall_median": statistics.median(point["recall_at_10"] for point in l_points),
            "qps_median": statistics.median(point["qps"] for point in l_points),
            "p99_latency_us_median": statistics.median(point["p99_latency_us"] for point in l_points),
            "pairwise": pairs,
        })

    index_roots = {point["index_root_realpath"] for point in points}
    require(len(index_roots) == 1, "query repeats did not use one exact index root")
    index_root = next(iter(index_roots))
    report = {
        "schema": "dynamic-vamana-w1-query-identity-v2",
        "status": "pass",
        "system": args.system,
        "mode": args.mode,
        "checkpoint": args.checkpoint.lower(),
        "prefix": args.prefix,
        "generated_unix_ns": time.time_ns(),
        "identities": {
            "query_binary": binary,
            "driver": driver,
            "artifact_manifest": artifact_manifest,
            "index_root_realpath": index_root,
            "index_content_manifest": index_manifest,
            "query": query,
            "ground_truth": gt,
            "active_tags": active_tags,
            "active_tag_count": tag_count,
            "threads": args.threads,
            "io_engine": args.io_engine,
            "device": args.device,
        },
        "expected_result_shape": [expected_nq, args.expected_k],
        "points": points,
        "repeat_diagnostics": repeat_diagnostics,
        "recall_is_diagnostic_only": True,
        "recall_threshold_applied": False,
    }
    write_new_json(args.output, report)
    return report


def private_policy(rows: Iterable[dict[str, str]], uid: int, gid: int) -> None:
    for row in rows:
        require((row["uid"], row["gid"]) == (str(uid), str(gid)),
                f"pre-freeze owner mismatch: {row}")
        mode = int(row["mode_octal"], 8)
        require(mode & stat.S_IWUSR, f"pre-freeze object is not owner-writable: {row}")
        require(not mode & (stat.S_IWGRP | stat.S_IWOTH),
                f"pre-freeze object is group/other-writable: {row}")
        if row["type"] == "directory":
            require(mode & stat.S_IXUSR, f"pre-freeze directory is not owner-searchable: {row}")
        if row["type"] == "regular":
            require(row["link_count"] == "1", f"pre-freeze hard-link risk: {row}")


def frozen_policy(rows: Iterable[dict[str, str]], uid: int, gid: int) -> None:
    for row in rows:
        mode = "0555" if row["type"] == "directory" else "0444"
        require((row["uid"], row["gid"], row["mode_octal"]) == (str(uid), str(gid), mode),
                f"post-freeze immutable policy mismatch: {row}")
        if row["type"] == "regular":
            require(row["link_count"] == "1", f"post-freeze hard-link risk: {row}")


def deny_file_write(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        require(exc.errno in DENIAL_ERRNOS, f"unexpected file-denial errno for {path}: {exc}")
    else:
        os.close(descriptor)
        raise GateError(f"frozen regular file unexpectedly owner-writable: {path}")


def deny_directory_create(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    name = f".w1-frozen-denial-{os.getpid()}-{secrets.token_hex(8)}"
    created = False
    try:
        try:
            descriptor = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600, dir_fd=directory_fd,
            )
            os.close(descriptor)
            created = True
        except OSError as exc:
            require(exc.errno in DENIAL_ERRNOS, f"unexpected directory-denial errno for {path}: {exc}")
        else:
            raise GateError(f"frozen directory unexpectedly allows owner create: {path}")
    finally:
        if created:
            try:
                os.unlink(name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def freeze(args: argparse.Namespace) -> dict[str, Any]:
    account = pwd.getpwnam(args.owner)
    require(os.geteuid() == account.pw_uid and os.getegid() == account.pw_gid,
            "freeze/denial audit must run as the configured owner uid/gid")
    attempt = canonical_path(args.attempt_dir, directory=True)
    root, directories, files = tree_objects(args.index_root)
    require(root.parent == attempt, "frozen index must be the direct attempt/index tree")
    output_dir = canonical_path(args.output_dir, directory=True)
    checkpoint_evidence, checkpoint_artifact = require_pass_json(
        args.checkpoint_evidence, "CP05 checkpoint evidence"
    )
    require(checkpoint_evidence.get("checkpoint") == "cp05", "freeze requires CP05 checkpoint evidence")
    require(checkpoint_evidence.get("system") == args.system, "freeze/checkpoint system mismatch")
    require(checkpoint_evidence.get("mode") == args.mode, "freeze/checkpoint mode mismatch")
    require(Path(checkpoint_evidence["index_root_realpath"]).resolve(strict=True) == root,
            "freeze/checkpoint index identity mismatch")
    args.content_before = output_dir / "cp05_freeze_content_before.tsv"
    args.mode_before = output_dir / "cp05_freeze_mode_before.tsv"
    args.content_after = output_dir / "cp05_freeze_content_after.tsv"
    args.mode_after = output_dir / "cp05_freeze_mode_after.tsv"
    args.marker = attempt / "IMMUTABLE_TRAJECTORY_CP05_OK"
    args.output = output_dir / "cp05_freeze_evidence.json"
    outputs = [args.content_before, args.mode_before, args.content_after,
               args.mode_after, args.marker, args.output]
    for output in outputs:
        require(not under(output, root), f"freeze evidence must be outside frozen tree: {output}")
        require(not output.exists(), f"freeze evidence overwrite refused: {output}")

    before_content_rows = content_rows(root, files)
    before_content = content_payload(before_content_rows)
    before_modes_rows = mode_rows(root, directories, files)
    before_modes = mode_payload(before_modes_rows)
    private_policy(before_modes_rows, account.pw_uid, account.pw_gid)
    write_new_bytes(args.content_before, before_content)
    write_new_bytes(args.mode_before, before_modes)
    require(checkpoint_evidence["state_content_manifest"]["sha256"] == sha256(args.content_before),
            "index content changed between CP05 checkpoint and freeze")
    require(checkpoint_evidence["state_mode_manifest"]["sha256"] == sha256(args.mode_before),
            "index mode changed between CP05 checkpoint and freeze")

    started = time.monotonic_ns()
    for path in files:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fchmod(descriptor, 0o444)
        finally:
            os.close(descriptor)
    for path in reversed(directories):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fchmod(descriptor, 0o555)
        finally:
            os.close(descriptor)

    post_root, post_directories, post_files = tree_objects(root)
    require(post_root == root, "clone root identity changed during freeze")
    after_content_rows = content_rows(root, post_files)
    after_content = content_payload(after_content_rows)
    after_modes_rows = mode_rows(root, post_directories, post_files)
    after_modes = mode_payload(after_modes_rows)
    require(before_content == after_content, "clone content changed during chmod freeze")
    frozen_policy(after_modes_rows, account.pw_uid, account.pw_gid)
    write_new_bytes(args.content_after, after_content)
    write_new_bytes(args.mode_after, after_modes)

    for path in post_files:
        deny_file_write(path)
    for path in post_directories:
        deny_directory_create(path)
    completed = time.monotonic_ns()

    marker_payload = b"IMMUTABLE_TRAJECTORY_CP05_OK\n"
    write_new_bytes(args.marker, marker_payload)
    report = {
        "schema": "dynamic-vamana-w1-cp05-freeze-v1",
        "status": "pass",
        "system": args.system,
        "mode": args.mode,
        "checkpoint": "cp05",
        "attempt_realpath": str(attempt),
        "root_realpath": str(root),
        "owner": args.owner,
        "owner_uid": account.pw_uid,
        "owner_gid": account.pw_gid,
        "directory_mode": "0555",
        "regular_file_mode": "0444",
        "directories": len(post_directories),
        "regular_files": len(post_files),
        "owner_file_write_denials": len(post_files),
        "owner_directory_create_denials": len(post_directories),
        "content_exact_across_freeze": True,
        "checkpoint_evidence": checkpoint_artifact,
        "freeze_started_monotonic_ns": started,
        "freeze_completed_monotonic_ns": completed,
        "elapsed_seconds": (completed - started) / 1e9,
        "evidence": {
            "content_before": artifact_identity(args.content_before),
            "mode_before": artifact_identity(args.mode_before),
            "content_after": artifact_identity(args.content_after),
            "mode_after": artifact_identity(args.mode_after),
            "immutable_marker": artifact_identity(args.marker),
        },
    }
    write_new_json(args.output, report)
    return report


def require_pass_json(path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    value = json_load(path)
    status_pass = value.get("status") == "pass"
    valid_pass = value.get("valid") is True and value.get("expected_exact_match", True) is True
    require(status_pass or valid_pass, f"{label} does not carry a pass/valid verdict: {path}")
    return value, artifact_identity(path)


def stage_evidence(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_name = args.checkpoint.lower()
    attempt = canonical_path(args.attempt_dir, directory=True)
    index_root = canonical_path(args.index_root, directory=True)
    require(index_root.parent == attempt, "stage index must be direct attempt/index")
    stage_result = canonical_path(args.stage_result, directory=True)
    worker_path = stage_result / "worker_identity.json"
    worker, _ = require_pass_json(worker_path, "stage worker identity")
    require(worker.get("mode") == args.mode and worker.get("system") == args.system,
            "stage worker mode/system mismatch")
    require(str(worker.get("checkpoint", "")).lower() == checkpoint_name,
            "stage worker checkpoint mismatch")
    require(Path(worker["attempt_realpath"]).resolve(strict=True) == attempt,
            "stage worker attempt mismatch")
    require(Path(worker["clone_realpath"]).resolve(strict=True) == index_root,
            "stage worker index mismatch")
    worker_binary = canonical_path(Path(worker["worker_binary_realpath"]), regular=True)
    require(sha256(worker_binary) == worker["worker_binary_sha256"],
            "stage worker executable/script hash mismatch")
    trace = canonical_path(args.trace, regular=True)
    require(Path(worker["delta_realpath"]).resolve(strict=True) == trace,
            "stage worker trace path mismatch")
    require(worker["delta_sha256"] == sha256(trace), "stage worker trace hash mismatch")
    controller_log = canonical_path(args.controller_log, regular=True)
    controller_text = controller_log.read_text(errors="replace")
    require(not FATAL_LOG.search(controller_text),
            "fatal/assert/I/O/OOM signature found in stage controller log")
    capability_path = canonical_path(args.input_capability_canary, regular=True)
    capability = json_load(capability_path)
    require(capability.get("schema") == "dynamic-vamana-w1-inaccessible-input-canary-v1",
            "input-capability canary schema mismatch")
    require(capability.get("status") == "pass", "input-capability canary status is not pass")
    require(Path(capability.get("allowed_delta", "")).resolve(strict=True) == trace,
            "input-capability canary did not allow the current stage trace")
    denied = capability.get("denied")
    require(isinstance(denied, list) and denied, "input-capability canary denied set is empty")
    denied_realpaths: set[str] = set()
    for row in denied:
        require(isinstance(row, dict) and row.get("open_refused") is True,
                f"input-capability canary lacks open refusal: {row}")
        require(int(row.get("errno", -1)) in (errno.EACCES, errno.EPERM),
                f"input-capability canary has unexpected denial errno: {row}")
        denied_path = canonical_path(Path(row.get("path", "")), regular=True)
        require(denied_path != trace, "input-capability canary denied the current stage trace")
        require(str(denied_path) not in denied_realpaths, "input-capability canary repeats a denied path")
        denied_realpaths.add(str(denied_path))
    intervals = {
        "replay": {"cp01": (0, 16), "cp05": (16, 64)},
        "formal": {"cp01": (0, 80_000), "cp05": (80_000, 320_000)},
    }
    expected_interval = intervals[args.mode][checkpoint_name]
    actual_interval = (int(worker.get("delta_start", -1)), int(worker.get("delta_count", -1)))
    require(actual_interval == expected_interval, "stage worker delta interval mismatch")

    resources = json_load(args.stage_resources)
    require(resources.get("returncode") == 0, "stage process returncode is nonzero")
    if "root_pid" in resources:
        require(int(resources["root_pid"]) == int(worker["worker_pid"]),
                "stage resource root_pid differs from worker identity")
    oom = {key: memory_event_total(resources, key) for key in ("oom", "oom_kill", "oom_group_kill")}
    require(all(value == 0 for value in oom.values()), f"stage resource evidence contains OOM: {oom}")
    write_bytes, write_ios = resource_write_delta(resources, args.device)
    require((stage_result / "STAGE_WORKER_OK").is_file(), "stage completion marker absent")

    marker_path = stage_result / "markers.jsonl"
    marker_rows: list[dict[str, Any]] = []
    for number, line in enumerate(marker_path.read_text().splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GateError(f"invalid marker JSON at line {number}: {exc}") from exc
        require(isinstance(row.get("marker"), str) and isinstance(row.get("monotonic_ns"), int),
                f"invalid marker row at line {number}")
        marker_rows.append(row)
    common_prefix = ["clone_ready", "index_loaded", "ingest_begin", "ingest_end"]
    online_names = (["online_visibility_probe_begin", "online_visibility_verified"]
                    if args.system == "OdinANN" else ["online_visibility_unsupported"])
    expected_markers = common_prefix + online_names + [
        "publish_begin", "publish_end", "fresh_process_probe_begin",
        "fresh_process_visibility_verified",
    ]
    marker_names = [row["marker"] for row in marker_rows]
    require(marker_names == expected_markers,
            f"stage marker set/order mismatch: {marker_names} != {expected_markers}")
    marker_ns = [int(row["monotonic_ns"]) for row in marker_rows]
    require(all(left < right for left, right in zip(marker_ns, marker_ns[1:])),
            "stage marker timestamps are not strictly increasing")
    if args.system == "DGAI":
        require(marker_rows[4].get("reason") == "requires_final_merge_and_reload",
                "DGAI online-unsupported reason mismatch")
    markers = {row["marker"]: int(row["monotonic_ns"]) for row in marker_rows}
    interval_ms = resources.get("sampling_interval_ms")
    require(isinstance(interval_ms, int) and interval_ms > 0, "invalid resource sampling interval")
    io_samples: list[tuple[int, dict[str, Any]]] = []
    for sample in resources.get("samples", []):
        if not isinstance(sample.get("monotonic_ns"), int):
            continue
        matches = [row for row in sample.get("cgroup_io_stat", []) if row.get("device") == args.device]
        require(len(matches) <= 1, "duplicate device row in one stage resource sample")
        if matches:
            io_samples.append((int(sample["monotonic_ns"]), matches[0]))
    io_samples.sort(key=lambda row: row[0])
    require(len(io_samples) >= 2, "stage has fewer than two target-device samples")

    def account(begin: int, end: int) -> dict[str, Any]:
        left = next((row for row in reversed(io_samples) if row[0] <= begin), None)
        right = next((row for row in io_samples if row[0] >= end), None)
        require(left is not None and right is not None and right[0] > left[0],
                "stage phase lacks distinct bracketing I/O samples")
        counters = {
            key: int(right[1].get(key, 0)) - int(left[1].get(key, 0))
            for key in ("rbytes", "wbytes", "rios", "wios")
        }
        require(all(value >= 0 for value in counters.values()), "stage device counter decreased")
        left_skew, right_skew = begin - left[0], right[0] - end
        interval_ns = interval_ms * 1_000_000
        require(left_skew <= 2 * interval_ns and right_skew <= 2 * interval_ns,
                "stage phase bracket skew exceeds two sampling periods")
        return {
            "begin_marker_ns": begin, "end_marker_ns": end,
            "left_sample_ns": left[0], "right_sample_ns": right[0],
            "left_skew_ns": left_skew, "right_skew_ns": right_skew,
            "sampling_interval_ms": interval_ms,
            "resolution": ("resolved" if end - begin >= interval_ns
                           else "bracketed_below_sampling_interval"),
            "wall_seconds": (end - begin) / 1e9,
            **counters,
            **{f"{key}_per_replacement": value / actual_interval[1]
               for key, value in counters.items()},
        }

    phases: dict[str, Any] = {
        "trace_load": account(markers["index_loaded"], markers["ingest_begin"]),
        "ingest": account(markers["ingest_begin"], markers["ingest_end"]),
        "publish": account(markers["publish_begin"], markers["publish_end"]),
        "fresh": account(markers["fresh_process_probe_begin"], markers["fresh_process_visibility_verified"]),
        "end_to_end": account(markers["ingest_begin"], markers["fresh_process_visibility_verified"]),
    }
    phases["online"] = (account(markers["online_visibility_probe_begin"],
                                        markers["online_visibility_verified"])
                                if args.system == "OdinANN" else {
                                    "supported": False,
                                    "marker_ns": markers["online_visibility_unsupported"],
                                    "reason": "requires_final_merge_and_reload",
                                })
    space_before = resources.get("space_before")
    space_after = next((sample.get("index_space") for sample in reversed(resources.get("samples", []))
                        if isinstance(sample.get("index_space"), dict)), None)
    require(isinstance(space_before, dict) and isinstance(space_after, dict),
            "stage lacks before/final index-space accounting")
    for field in ("files", "apparent_bytes", "allocated_bytes"):
        require(isinstance(space_before.get(field), int) and isinstance(space_after.get(field), int),
                f"stage space accounting lacks integer {field}")

    raw_artifacts = {
        "trace": args.trace,
        "delta_manifest": args.delta_manifest,
        "expected_active": args.expected_active,
        "runtime_active_audit": stage_result / "active_audit.json",
        "pre_stage_active_audit": stage_result / "pre_stage_active_audit.json",
        "local_probe_spec": args.local_probe_spec,
        "global_probe_spec": args.global_probe_spec,
        "combined_probe_spec": args.combined_probe_spec,
        "fresh_result": args.fresh_result,
        "fresh_probe": stage_result / "fresh_probe.json",
        "worker_identity": worker_path,
        "stage_resources": args.stage_resources,
        "markers": marker_path,
        "controller_log": controller_log,
        "input_capability_canary": capability_path,
        "stage_marker": stage_result / "STAGE_WORKER_OK",
    }
    if args.system == "OdinANN":
        require(args.online_result is not None, "OdinANN stage lacks online result")
        raw_artifacts["online_result"] = args.online_result
        raw_artifacts["online_probe"] = stage_result / "online_probe.json"
    artifacts = {name: artifact_identity(path) for name, path in raw_artifacts.items()}
    for name in ("runtime_active_audit", "pre_stage_active_audit", "fresh_probe"):
        require_pass_json(Path(artifacts[name]["realpath"]), name)
    if args.system == "OdinANN":
        require_pass_json(Path(artifacts["online_probe"]["realpath"]), "online probe")
    active_payload = json_load(Path(artifacts["runtime_active_audit"]["realpath"]))
    fresh_payload = json_load(Path(artifacts["fresh_probe"]["realpath"]))
    online_payload = (json_load(Path(artifacts["online_probe"]["realpath"]))
                      if args.system == "OdinANN" else None)
    cgroup_peak = max((int(sample.get("cgroup_memory_peak") or 0)
                       for sample in resources.get("samples", [])), default=0)

    report = {
        "schema": "dynamic-vamana-w1-cumulative-stage-evidence-v1", "status": "pass",
        "mode": args.mode, "system": args.system, "checkpoint": checkpoint_name,
        "attempt_realpath": str(attempt), "index_root_realpath": str(index_root),
        "delta_start": actual_interval[0], "delta_count": actual_interval[1],
        "worker_identity": worker,
        "resources": {"returncode": 0, "oom_events": oom, "device": args.device,
                      "elapsed_seconds": float(resources.get("elapsed_seconds", 0.0)),
                      "device_write_bytes": write_bytes, "device_write_ios": write_ios,
                      "peak_process_tree_rss_bytes": int(resources.get("peak_process_tree_rss_kb", 0)) * 1024,
                      "cgroup_memory_peak_bytes": cgroup_peak},
        "marker_sequence": marker_names,
        "marker_timestamps": markers,
        "phases": phases,
        "space": {
            "before": space_before, "after": space_after,
            "apparent_growth_bytes": int(space_after["apparent_bytes"]) - int(space_before["apparent_bytes"]),
            "allocated_growth_bytes": int(space_after["allocated_bytes"]) - int(space_before["allocated_bytes"]),
            "apparent_bytes_per_replacement":
                (int(space_after["apparent_bytes"]) - int(space_before["apparent_bytes"])) / actual_interval[1],
            "allocated_bytes_per_replacement":
                (int(space_after["allocated_bytes"]) - int(space_before["allocated_bytes"])) / actual_interval[1],
        },
        "active_audit": active_payload, "fresh_probe": fresh_payload, "online_probe": online_payload,
        "input_capability": {
            "allowed_delta_realpath": str(trace),
            "denied_count": len(denied),
            "all_denied_open_refused": True,
        },
        "artifacts": artifacts,
    }
    write_new_json(args.output, report)
    return report


def validate_identity_record(record: dict[str, Any], label: str) -> dict[str, Any]:
    require(isinstance(record, dict), f"{label} identity is not an object")
    for field in ("realpath", "sha256"):
        require(field in record, f"{label} identity lacks {field}")
    actual = artifact_identity(Path(record["realpath"]))
    require(actual["sha256"] == record["sha256"], f"{label} live hash mismatch")
    if "size_bytes" in record:
        require(actual["size_bytes"] == int(record["size_bytes"]), f"{label} live size mismatch")
    return actual


def validate_checkpoint_modes(path: Path) -> None:
    try:
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except OSError as exc:
        raise GateError(f"cannot read checkpoint mode manifest {path}: {exc}") from exc
    require(rows, "checkpoint mode manifest is empty")
    require(set(MODE_FIELDS).issubset(rows[0]), "checkpoint mode manifest schema mismatch")
    owners = {(row["uid"], row["gid"]) for row in rows}
    require(len(owners) == 1, "checkpoint mutable tree has mixed ownership")
    for row in rows:
        require(row["type"] in ("directory", "regular"), f"unsupported mode-manifest type: {row}")
        mode = int(row["mode_octal"], 8)
        require(mode & stat.S_IWUSR, f"checkpoint tree is not owner-writable: {row}")
        require(not mode & (stat.S_IWGRP | stat.S_IWOTH),
                f"checkpoint tree is group/other-writable: {row}")
        if row["type"] == "directory":
            require(mode & stat.S_IXUSR, f"checkpoint directory is not owner-searchable: {row}")
        if row["type"] == "regular":
            require(row["link_count"] == "1", f"checkpoint hard-link risk: {row}")


def checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_name = args.checkpoint.lower()
    attempt = canonical_path(args.attempt_dir, directory=True)
    index_root = canonical_path(args.index_root, directory=True)
    require(index_root.parent == attempt, "checkpoint index must be direct attempt/index")
    output_dir = canonical_path(args.output_dir, directory=True)
    stage, stage_artifact = require_pass_json(args.stage_evidence, "stage evidence")
    require(stage.get("schema") == "dynamic-vamana-w1-cumulative-stage-evidence-v1",
            "wrong cumulative stage-evidence schema")
    for field, expected in (("mode", args.mode), ("system", args.system),
                            ("checkpoint", checkpoint_name)):
        require(str(stage.get(field, "")).lower() == str(expected).lower(),
                f"stage evidence {field} mismatch")
    require(Path(stage["attempt_realpath"]).resolve(strict=True) == attempt,
            "stage evidence attempt mismatch")
    require(Path(stage["index_root_realpath"]).resolve(strict=True) == index_root,
            "stage evidence index mismatch")
    intervals = {
        "replay": {"cp01": (0, 16), "cp05": (16, 64)},
        "formal": {"cp01": (0, 80_000), "cp05": (80_000, 320_000)},
    }
    actual_interval = (int(stage.get("delta_start", -1)), int(stage.get("delta_count", -1)))
    require(actual_interval == intervals[args.mode][checkpoint_name],
            f"stage delta interval {actual_interval} violates {args.mode}/{checkpoint_name}")
    worker = stage.get("worker_identity", {})
    require(isinstance(worker, dict) and int(worker.get("worker_pid", -1)) > 1,
            "stage worker identity/PID absent")
    require(worker.get("mode") == args.mode and worker.get("system") == args.system and
            str(worker.get("checkpoint", "")).lower() == checkpoint_name,
            "stage worker mode/system/checkpoint mismatch")
    require(Path(worker["attempt_realpath"]).resolve(strict=True) == attempt,
            "stage worker did not use exact attempt")
    require(Path(worker["clone_realpath"]).resolve(strict=True) == index_root,
            "stage worker did not use exact index clone")
    require((int(worker.get("delta_start", -1)), int(worker.get("delta_count", -1))) == actual_interval,
            "stage report/worker delta intervals differ")
    require(int(worker.get("incremental_replacements", -1)) == actual_interval[1],
            "stage worker replacement count mismatch")
    resources = stage.get("resources", {})
    require(resources.get("returncode") == 0, "stage resource returncode is nonzero")
    oom = resources.get("oom_events", {})
    require(isinstance(oom, dict) and all(int(oom.get(key, -1)) == 0
            for key in ("oom", "oom_kill", "oom_group_kill")), "stage evidence contains OOM")
    require(int(resources.get("peak_process_tree_rss_bytes", -1)) >= 0 and
            int(resources.get("cgroup_memory_peak_bytes", -1)) >= 0,
            "stage peak-memory evidence absent")
    expected_markers = ["clone_ready", "index_loaded", "ingest_begin", "ingest_end"] + (
        ["online_visibility_probe_begin", "online_visibility_verified"]
        if args.system == "OdinANN" else ["online_visibility_unsupported"]
    ) + ["publish_begin", "publish_end", "fresh_process_probe_begin",
         "fresh_process_visibility_verified"]
    require(stage.get("marker_sequence") == expected_markers,
            "checkpoint stage marker set/order mismatch")
    phases = stage.get("phases", {})
    require(set(phases) == {"trace_load", "ingest", "online", "publish", "fresh", "end_to_end"},
            "checkpoint stage phase set mismatch")
    for phase_name in ("trace_load", "ingest", "publish", "fresh", "end_to_end"):
        phase = phases[phase_name]
        require(float(phase.get("wall_seconds", -1)) >= 0, f"{phase_name} wall time absent")
        for counter in ("rbytes", "wbytes", "rios", "wios"):
            require(int(phase.get(counter, -1)) >= 0, f"{phase_name} {counter} absent")
            require(math.isfinite(float(phase.get(f"{counter}_per_replacement", float("nan")))),
                    f"{phase_name} normalized {counter} absent")
    if args.system == "OdinANN":
        for counter in ("rbytes", "wbytes", "rios", "wios"):
            require(int(phases["online"].get(counter, -1)) >= 0,
                    f"online {counter} absent")
    else:
        require(phases["online"].get("supported") is False and
                phases["online"].get("reason") == "requires_final_merge_and_reload",
                "DGAI online unsupported evidence mismatch")
    space = stage.get("space", {})
    for side in ("before", "after"):
        for field in ("files", "apparent_bytes", "allocated_bytes"):
            require(int(space.get(side, {}).get(field, -1)) >= 0,
                    f"stage space {side}/{field} absent")
    artifacts = stage.get("artifacts", {})
    required_artifacts = ("trace", "delta_manifest", "expected_active", "runtime_active_audit",
                          "local_probe_spec", "global_probe_spec", "combined_probe_spec",
                          "fresh_result", "fresh_probe", "markers", "worker_identity",
                          "controller_log", "input_capability_canary")
    live_stage_artifacts = {name: validate_identity_record(artifacts.get(name), f"stage {name}")
                            for name in required_artifacts}
    if args.system == "OdinANN":
        live_stage_artifacts["online_result"] = validate_identity_record(
            artifacts.get("online_result"), "stage online_result"
        )
        live_stage_artifacts["online_probe"] = validate_identity_record(
            artifacts.get("online_probe"), "stage online_probe"
        )
    active, _ = require_pass_json(Path(live_stage_artifacts["runtime_active_audit"]["realpath"]),
                                  "runtime active-tag audit")

    query, query_artifact = require_pass_json(args.query_gate, "query gate")
    require(query.get("schema") == "dynamic-vamana-w1-query-identity-v2", "wrong query-gate schema")
    require(query.get("mode") == args.mode and query.get("system") == args.system,
            "query-gate mode/system mismatch")
    require(str(query.get("checkpoint", "")).lower() == checkpoint_name, "query-gate checkpoint mismatch")
    require(Path(query["identities"]["index_root_realpath"]).resolve(strict=True) == index_root,
            "query-gate index identity mismatch")

    content = artifact_identity(args.state_content_manifest)
    mode = artifact_identity(args.state_mode_manifest)
    base_content = artifact_identity(args.base_content_manifest)
    base_mode = artifact_identity(args.base_mode_manifest)
    require(content["size_bytes"] > 0, "empty checkpoint content manifest")
    require(mode["size_bytes"] > 0, "empty checkpoint mode manifest")
    validate_checkpoint_modes(Path(mode["realpath"]))
    require(query["identities"]["index_content_manifest"]["sha256"] == content["sha256"],
            "query-gate index manifest is not checkpoint state manifest")
    require(query["identities"]["active_tags"]["sha256"] ==
            live_stage_artifacts["expected_active"]["sha256"],
            "query-gate active tags differ from stage expected-active artifact")
    require(int(query["identities"]["active_tag_count"]) == int(active["active_tag_count"]),
            "query-gate/runtime-audit active counts differ")

    previous_artifact = None
    if checkpoint_name == "cp05":
        previous_path = output_dir.parent / "cp01" / "cp01_checkpoint_evidence.json"
        previous, previous_artifact = require_pass_json(previous_path, "previous CP01 evidence")
        require(previous.get("schema") == "dynamic-vamana-w1-cumulative-checkpoint-v1",
                "previous evidence schema mismatch")
        require(previous.get("checkpoint") == "cp01", "CP05 previous evidence is not CP01")
        require(previous.get("mode") == args.mode and previous.get("system") == args.system,
                "CP01/CP05 mode/system mismatch")
        require(Path(previous["attempt_realpath"]).resolve(strict=True) == attempt,
                "CP01/CP05 did not use the same clone")
        previous_pid = int(previous["worker_identity"]["worker_pid"])
        require(previous_pid != int(worker["worker_pid"]),
                "CP01 and CP05 must use distinct worker processes")
    active_output = output_dir / f"{checkpoint_name}_active_audit.json"
    active_report = {
        "schema": "dynamic-vamana-w1-cumulative-active-audit-v1", "status": "pass",
        "mode": args.mode, "system": args.system, "checkpoint": checkpoint_name,
        "expected_active": live_stage_artifacts["expected_active"],
        "runtime_active_audit": live_stage_artifacts["runtime_active_audit"],
        "active_tag_count": active.get("active_tag_count"),
    }
    write_new_json(active_output, active_report)
    summary_output = output_dir / f"{checkpoint_name}_query_summary.tsv"
    summary_rows = [
        "checkpoint\tsystem\tL\trepeat\trecall_at_10\tqps\tp99_latency_us\tdevice_read_bytes\tdevice_read_ios\n"
    ]
    summary_rows.extend(
        f"{checkpoint_name}\t{args.system}\t{point['L']}\t{point['repeat']}\t"
        f"{point['recall_at_10']:.12g}\t{point['qps']:.12g}\t{point['p99_latency_us']:.12g}\t"
        f"{point['device_read_bytes']}\t{point['device_read_ios']}\n"
        for point in query["points"]
    )
    write_new_bytes(summary_output, "".join(summary_rows).encode())
    output = output_dir / f"{checkpoint_name}_checkpoint_evidence.json"
    report = {
        "schema": "dynamic-vamana-w1-cumulative-checkpoint-v1",
        "status": "pass",
        "mode": args.mode,
        "system": args.system,
        "checkpoint": checkpoint_name,
        "attempt_realpath": str(attempt),
        "index_root_realpath": str(index_root),
        "generated_unix_ns": time.time_ns(),
        "delta_interval": {"start": actual_interval[0], "count": actual_interval[1]},
        "worker_identity": worker,
        "stage_evidence": stage_artifact,
        "stage_artifacts": live_stage_artifacts,
        "state_content_manifest": content,
        "state_mode_manifest": mode,
        "base_content_manifest": base_content,
        "base_mode_manifest": base_mode,
        "active_audit": artifact_identity(active_output),
        "active_tag_count": active.get("active_tag_count"),
        "query_gate": query_artifact,
        "query_summary": artifact_identity(summary_output),
        "previous_checkpoint_evidence": previous_artifact,
        "same_clone_as_previous": checkpoint_name == "cp05",
        "distinct_worker_from_previous": checkpoint_name == "cp05",
    }
    write_new_json(output, report)
    return report


def make_bin(path: Path, rows: np.ndarray) -> None:
    write_new_bytes(path, struct.pack("<II", *rows.shape) + rows.astype("<u4").tobytes())


def self_test(args: argparse.Namespace) -> dict[str, Any]:
    scratch_parent = args.scratch.resolve(strict=False)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="w1-cumulative-self-test-", dir=scratch_parent))
    attempt = root / "attempt"
    attempt.mkdir(mode=0o700)
    private = attempt / "index"
    private.mkdir(mode=0o700)
    (private / "index.bin").write_bytes(b"index-state")
    os.chmod(private / "index.bin", 0o600)
    evidence = root / "evidence"
    evidence.mkdir()

    # Exercise the real identity-v2 parsers using the same binary/result and
    # JSON schemas as a formal query, only at a tiny row count.
    results = root / "results"
    results.mkdir()
    binary = root / "search_disk_index"
    binary.write_bytes(b"synthetic-query-binary")
    query_input = root / "query.bin"
    query_input.write_bytes(struct.pack("<II", 2, 1) + np.asarray([0.0, 1.0], dtype="<f4").tobytes())
    ground_truth = root / "gt.bin"
    ground_truth.write_bytes(b"synthetic-ground-truth")
    active_tags = root / "active.tags"
    active_values = np.arange(32, dtype="<u4")
    active_tags.write_bytes(struct.pack("<II", len(active_values), 1) + active_values.tobytes())
    index_manifest = evidence / "index.content.tsv"
    index_manifest.write_text(f"index.bin\t11\t{sha256(private / 'index.bin')}\n")
    frozen_artifact = evidence / "artifact_manifest.json"
    frozen_artifact.write_text(json.dumps({
        "systems": {"DGAI": {"binary_sha256": {"search_disk_index": sha256(binary)},
                               "io_engine": "io_uring"}},
        "formal_inputs": {"query": {"sha256": sha256(query_input)}},
    }))
    result_ids = np.array([
        list(range(10)), list(range(10, 20)),
    ], dtype="<u4")
    stem = results / "self_cp01_L8_r1"
    make_bin(Path(f"{stem}.result_ids.bin"), result_ids)
    Path(f"{stem}.metrics.json").write_text(json.dumps({
        "qps": 100.0, "mean_latency_us": 10.0, "p50_latency_us": 9.0,
        "p95_latency_us": 12.0, "p99_latency_us": 13.0, "mean_ios": 2.0,
        "recall_at_10_percent": 100.0,
    }))
    Path(f"{stem}.validation.json").write_text(json.dumps({
        "query_count": 2, "k": 10, "all_result_ids_active": True,
        "invalid_or_inactive_ids": 0, "recall_at_10_normalized": 1.0,
    }))
    Path(f"{stem}.resources.json").write_text(json.dumps({
        "returncode": 0,
        "space_root": str(private),
        "cgroup_memory_events_final": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0},
        "samples": [
            {"cgroup_memory_events": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0},
             "cgroup_io_stat": [{"device": "1:2", "rbytes": 0, "rios": 0}]},
            {"cgroup_memory_events": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0},
             "cgroup_io_stat": [{"device": "1:2", "rbytes": 4096, "rios": 1}]},
        ],
    }))
    Path(f"{stem}.log").write_text("Ls I/O Width QPS AvgLat(us)\n 8 16 100.0 10.0\n")
    query_args = argparse.Namespace(
        mode="replay", system="DGAI", checkpoint="cp01", result_dir=results, prefix="self_cp01",
        binary=binary, driver=None, artifact_manifest=frozen_artifact,
        index_content_manifest=index_manifest,
        query=query_input, gt=ground_truth, active_tags=active_tags, ls="8", repeats="1",
        threads=1, io_engine="io_uring", device="1:2", expected_nq=2,
        expected_k=10, expected_active_count=32, output=evidence / "query_gate.json",
    )
    query_report = query_gate(query_args)
    require(query_report["status"] == "pass", "query-gate positive self-test failed")

    # Bind the query to a synthetic replay CP01 stage-evidence contract.
    runtime_active = evidence / "runtime_active_audit.json"
    runtime_active.write_text(json.dumps({
        "schema": "self-test-active", "valid": True, "expected_exact_match": True,
        "active_tag_count": 32,
    }))
    stage_files: dict[str, Path] = {
        "trace": evidence / "delta.bin", "delta_manifest": evidence / "delta.json",
        "expected_active": active_tags, "runtime_active_audit": runtime_active,
        "local_probe_spec": evidence / "local.json", "global_probe_spec": evidence / "global.json",
        "combined_probe_spec": evidence / "combined.json", "fresh_result": evidence / "fresh.bin",
        "fresh_probe": evidence / "fresh_probe.json",
        "markers": evidence / "markers.jsonl",
        "worker_identity": evidence / "worker_identity.json",
        "controller_log": evidence / "controller.log",
        "input_capability_canary": evidence / "input_capability_canary.json",
    }
    for name, path in stage_files.items():
        if not path.exists():
            path.write_bytes(f"self-test-{name}".encode())
    stage_files["fresh_probe"].write_text(json.dumps({"valid": True}))
    synthetic_worker = {"mode": "replay", "system": "DGAI", "checkpoint": "cp01",
                        "worker_pid": os.getpid(), "attempt_realpath": str(attempt.resolve()),
                        "clone_realpath": str(private.resolve()), "delta_start": 0, "delta_count": 16,
                        "incremental_replacements": 16}
    stage_files["worker_identity"].write_text(json.dumps(synthetic_worker))
    stage_files["controller_log"].write_text("synthetic stage completed cleanly\n")
    stage_files["input_capability_canary"].write_text(json.dumps({
        "schema": "dynamic-vamana-w1-inaccessible-input-canary-v1",
        "status": "pass", "allowed_delta": str(stage_files["trace"].resolve()),
        "denied": [{"path": str(stage_files["delta_manifest"].resolve()),
                    "open_refused": True, "errno": errno.EACCES}],
    }))
    synthetic_markers = ["clone_ready", "index_loaded", "ingest_begin", "ingest_end",
                         "online_visibility_unsupported", "publish_begin", "publish_end",
                         "fresh_process_probe_begin", "fresh_process_visibility_verified"]
    stage_files["markers"].write_text("".join(json.dumps({
        "marker": name, "monotonic_ns": (index + 1) * 1_000_000,
        **({"reason": "requires_final_merge_and_reload"}
           if name == "online_visibility_unsupported" else {}),
    }) + "\n" for index, name in enumerate(synthetic_markers)))
    synthetic_phase = {
        "begin_marker_ns": 1, "end_marker_ns": 2, "left_sample_ns": 0,
        "right_sample_ns": 3, "wall_seconds": 1e-9, "resolution": "resolved",
        **{key: 0 for key in ("rbytes", "wbytes", "rios", "wios")},
        **{f"{key}_per_replacement": 0.0 for key in ("rbytes", "wbytes", "rios", "wios")},
    }
    stage_evidence = evidence / "stage_evidence.json"
    stage_evidence.write_text(json.dumps({
        "schema": "dynamic-vamana-w1-cumulative-stage-evidence-v1", "status": "pass",
        "mode": "replay", "system": "DGAI", "checkpoint": "cp01",
        "attempt_realpath": str(attempt.resolve()), "index_root_realpath": str(private.resolve()),
        "delta_start": 0, "delta_count": 16,
        "worker_identity": synthetic_worker,
        "resources": {"returncode": 0, "peak_process_tree_rss_bytes": 0,
                      "cgroup_memory_peak_bytes": 0,
                      "oom_events": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0}},
        "marker_sequence": synthetic_markers,
        "phases": {"trace_load": synthetic_phase, "ingest": synthetic_phase,
                   "online": {"supported": False, "reason": "requires_final_merge_and_reload"},
                   "publish": synthetic_phase, "fresh": synthetic_phase,
                   "end_to_end": synthetic_phase},
        "space": {"before": {"files": 1, "apparent_bytes": 11, "allocated_bytes": 4096},
                  "after": {"files": 1, "apparent_bytes": 11, "allocated_bytes": 4096}},
        "artifacts": {name: artifact_identity(path) for name, path in stage_files.items()},
    }))
    mode_manifest = evidence / "cp01_state_mode_manifest.tsv"
    _, self_dirs, self_files = tree_objects(private)
    mode_manifest.write_bytes(mode_payload(mode_rows(private, self_dirs, self_files)))
    checkpoint_dir = root / "checkpoints" / "cp01"
    checkpoint_dir.mkdir(parents=True)
    checkpoint_args = argparse.Namespace(
        mode="replay", system="DGAI", checkpoint="cp01", attempt_dir=attempt,
        index_root=private, stage_evidence=stage_evidence, query_gate=evidence / "query_gate.json",
        state_content_manifest=index_manifest, state_mode_manifest=mode_manifest,
        base_content_manifest=index_manifest, base_mode_manifest=mode_manifest, output_dir=checkpoint_dir,
    )
    checkpoint_report = checkpoint(checkpoint_args)
    require(checkpoint_report["status"] == "pass", "checkpoint positive self-test failed")

    fake_checkpoint = evidence / "cp05_checkpoint_evidence.json"
    fake_checkpoint.write_text(json.dumps({
        "schema": "dynamic-vamana-w1-cumulative-checkpoint-v1", "status": "pass",
        "mode": "replay", "system": "DGAI", "checkpoint": "cp05",
        "index_root_realpath": str(private.resolve()),
        "state_content_manifest": artifact_identity(index_manifest),
        "state_mode_manifest": artifact_identity(mode_manifest),
    }))
    freeze_args = argparse.Namespace(
        mode="replay", system="DGAI", attempt_dir=attempt, index_root=private,
        owner=pwd.getpwuid(os.geteuid()).pw_name, checkpoint_evidence=fake_checkpoint,
        output_dir=evidence,
    )
    frozen = freeze(freeze_args)
    require(frozen["status"] == "pass", "freeze self-test failed")

    # Negative structural tests are performed on separate mutable trees.
    hard_tree = root / "hard"
    hard_tree.mkdir()
    (hard_tree / "a").write_bytes(b"x")
    os.link(hard_tree / "a", hard_tree / "b")
    try:
        tree_objects(hard_tree)
    except GateError:
        hard_link_refused = True
    else:
        hard_link_refused = False
    require(hard_link_refused, "hard-link negative self-test did not fail closed")

    link_tree = root / "link"
    link_tree.mkdir()
    (link_tree / "target").write_bytes(b"x")
    (link_tree / "alias").symlink_to("target")
    try:
        tree_objects(link_tree)
    except GateError:
        symlink_refused = True
    else:
        symlink_refused = False
    require(symlink_refused, "symlink negative self-test did not fail closed")

    report = {
        "schema": "dynamic-vamana-w1-cumulative-evidence-self-test-v1",
        "status": "pass",
        "query_gate_positive": True,
        "checkpoint_positive": True,
        "freeze_positive": True,
        "hard_link_refused": hard_link_refused,
        "symlink_refused": symlink_refused,
        "scratch_realpath": str(root),
    }
    write_new_json(args.output, report)
    return report


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    sub = top.add_subparsers(dest="command", required=True)

    query = sub.add_parser("query-gate", help="validate identity-v2 query evidence")
    query.add_argument("--mode", choices=("replay", "formal"), required=True)
    query.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    query.add_argument("--checkpoint", choices=("cp00", "cp01", "cp05"), required=True)
    query.add_argument("--result-dir", type=Path, required=True)
    query.add_argument("--prefix", default="", help="optional artifact prefix before L<value>_r<repeat>")
    query.add_argument("--binary", type=Path, required=True)
    query.add_argument("--driver", type=Path, required=True)
    query.add_argument("--artifact-manifest", type=Path, required=True)
    query.add_argument("--index-content-manifest", type=Path, required=True)
    query.add_argument("--query", type=Path, required=True)
    query.add_argument("--gt", type=Path, required=True)
    query.add_argument("--active-tags", type=Path, required=True)
    query.add_argument("--ls", required=True)
    query.add_argument("--repeats", default="1,2,3")
    query.add_argument("--threads", type=int, default=1)
    query.add_argument("--io-engine", required=True)
    query.add_argument("--device", required=True)
    query.add_argument("--expected-nq", type=int)
    query.add_argument("--expected-k", type=int, default=10)
    query.add_argument("--expected-active-count", type=int)
    query.add_argument("--output", type=Path, required=True)

    freeze_parser = sub.add_parser("freeze", help="freeze CP05 clone and prove owner denials")
    freeze_parser.add_argument("--mode", choices=("replay", "formal"), required=True)
    freeze_parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    freeze_parser.add_argument("--attempt-dir", type=Path, required=True)
    freeze_parser.add_argument("--index-root", type=Path, required=True)
    freeze_parser.add_argument("--owner", required=True)
    freeze_parser.add_argument("--checkpoint-evidence", type=Path, required=True)
    freeze_parser.add_argument("--output-dir", type=Path, required=True)

    stage_parser = sub.add_parser("stage-evidence", help="consolidate one completed update stage")
    stage_parser.add_argument("--mode", choices=("replay", "formal"), required=True)
    stage_parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    stage_parser.add_argument("--checkpoint", choices=("cp01", "cp05"), required=True)
    stage_parser.add_argument("--attempt-dir", type=Path, required=True)
    stage_parser.add_argument("--index-root", type=Path, required=True)
    stage_parser.add_argument("--stage-result", type=Path, required=True)
    stage_parser.add_argument("--stage-resources", type=Path, required=True)
    stage_parser.add_argument("--controller-log", type=Path, required=True)
    stage_parser.add_argument("--input-capability-canary", type=Path, required=True)
    stage_parser.add_argument("--trace", type=Path, required=True)
    stage_parser.add_argument("--delta-manifest", type=Path, required=True)
    stage_parser.add_argument("--expected-active", type=Path, required=True)
    stage_parser.add_argument("--local-probe-spec", type=Path, required=True)
    stage_parser.add_argument("--global-probe-spec", type=Path, required=True)
    stage_parser.add_argument("--combined-probe-spec", type=Path, required=True)
    stage_parser.add_argument("--fresh-result", type=Path, required=True)
    stage_parser.add_argument("--online-result", type=Path)
    stage_parser.add_argument("--device", required=True)
    stage_parser.add_argument("--output", type=Path, required=True)

    checkpoint_parser = sub.add_parser("checkpoint", help="bind CP01/CP05 cumulative evidence")
    checkpoint_parser.add_argument("--mode", choices=("replay", "formal"), required=True)
    checkpoint_parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    checkpoint_parser.add_argument("--checkpoint", choices=("cp01", "cp05"), required=True)
    checkpoint_parser.add_argument("--attempt-dir", type=Path, required=True)
    checkpoint_parser.add_argument("--index-root", type=Path, required=True)
    checkpoint_parser.add_argument("--stage-evidence", type=Path, required=True)
    checkpoint_parser.add_argument("--query-gate", type=Path, required=True)
    checkpoint_parser.add_argument("--state-content-manifest", type=Path, required=True)
    checkpoint_parser.add_argument("--state-mode-manifest", type=Path, required=True)
    checkpoint_parser.add_argument("--base-content-manifest", type=Path, required=True)
    checkpoint_parser.add_argument("--base-mode-manifest", type=Path, required=True)
    checkpoint_parser.add_argument("--output-dir", type=Path, required=True)

    test = sub.add_parser("self-test", help="run positive freeze and negative tree-safety tests")
    test.add_argument("--scratch", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)
    return top


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "query-gate":
            require(args.threads == 1, "formal identity-v2 query gate requires one query thread")
            require((args.expected_nq is None or args.expected_nq > 0) and args.expected_k > 0,
                    "invalid expected result shape")
            query_gate(args)
        elif args.command == "freeze":
            freeze(args)
        elif args.command == "stage-evidence":
            stage_evidence(args)
        elif args.command == "checkpoint":
            checkpoint(args)
        else:
            self_test(args)
    except GateError as exc:
        raise SystemExit(f"w1 cumulative evidence gate failed: {exc}") from exc


if __name__ == "__main__":
    main()
