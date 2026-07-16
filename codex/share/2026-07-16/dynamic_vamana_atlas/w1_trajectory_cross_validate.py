#!/usr/bin/env python3
"""Cross-check every trajectory invariant after outputs are frozen read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np

from w1_trajectory_generate import CHECKPOINTS, read_tags, read_trace, sha


def resource_summary(path: Path, device: str, expected_scope: str,
                     expected_command: list[str], expected_space: Path) -> dict:
    report = json.loads(path.read_text()); samples = report.get("samples", [])
    if (report.get("schema") != "dynamic-vamana-w1-trajectory-resource-probe-v1"
            or len(samples) < 2 or report.get("io_device") != device
            or Path(report.get("space_root", "")).resolve() != expected_space.resolve()
            or report.get("command") != expected_command
            or report.get("target_device_present_raw_final") is not True
            or not str(report.get("cgroup_path", "")).endswith("/" + expected_scope)
            or not isinstance(report.get("space_before"), dict)
            or not isinstance(report.get("space_final"), dict)):
        raise SystemExit(f"invalid resource evidence envelope: {path}")
    def io(sample: dict) -> dict:
        rows = [row for row in sample.get("cgroup_io_stat", []) if row.get("device") == device]
        if len(rows) != 1 or any(key not in rows[0] for key in ("rbytes", "wbytes", "rios", "wios")):
            raise SystemExit(f"missing/ambiguous target-device sample: {path}")
        return rows[0]
    for sample in samples:
        if (not isinstance(sample.get("index_space"), dict)
                or not isinstance(sample.get("target_device_present_raw"), bool)):
            raise SystemExit(f"missing space sample: {path}")
    first, last = io(samples[0]), io(samples[-1])
    if (io({"cgroup_io_stat": report.get("cgroup_io_baseline", [])}) != first
            or io({"cgroup_io_stat": report.get("cgroup_io_final", [])}) != last):
        raise SystemExit(f"resource baseline/final mismatch: {path}")
    events = report.get("cgroup_memory_events_final", {})
    if (not all(key in events for key in ("oom", "oom_kill", "oom_group_kill"))
            or not isinstance(report.get("cgroup_memory_peak_final"), int)):
        raise SystemExit(f"incomplete cgroup memory evidence: {path}")
    before = report["space_before"]; after = report["space_final"]
    nvme_delta = {key: int(last[key]) - int(first[key]) for key in ("rbytes", "wbytes", "rios", "wios")}
    if any(value < 0 for value in nvme_delta.values()) or nvme_delta["wbytes"] <= 0:
        raise SystemExit(f"invalid/absent target-NVMe write accounting: {path}")
    return {"realpath": str(path.resolve()), "sha256": sha(path), "returncode": report.get("returncode"),
            "cgroup_path": report.get("cgroup_path"),
            "elapsed_seconds": report.get("elapsed_seconds"), "peak_process_tree_rss_bytes": int(report.get("peak_process_tree_rss_kb", 0)) * 1024,
            "cgroup_memory_peak_bytes": max([int(row.get("cgroup_memory_peak") or 0) for row in samples] or [0]),
            "memory_events_final": events,
            "command": report["command"], "space_root": report["space_root"], "sample_count": len(samples),
            "nvme_delta": nvme_delta,
            "space_delta": {"apparent_bytes": int(after.get("apparent_bytes", 0)) - int(before.get("apparent_bytes", 0)),
                            "allocated_bytes": int(after.get("allocated_bytes", 0)) - int(before.get("allocated_bytes", 0))}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--groundtruth", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="259:10")
    args = parser.parse_args()
    if args.output.exists(): raise SystemExit("trajectory validation overwrite refused")
    root, trajectory, groundtruth = args.root.resolve(), args.trajectory.resolve(), args.groundtruth.resolve()
    preflight = json.loads(args.preflight.read_text())
    if preflight.get("status") != "pass": raise SystemExit("trajectory preflight is not a pass")
    master_deletes, master_inserts = read_trace(trajectory / "master_replacements_1600k.bin")
    prefix = json.loads((trajectory / "cp01_prefix_validation.json").read_text())
    cp01_deletes, cp01_inserts = read_trace(root / "datasets/sift10m/w1_cp01/replace_cp01_80k.bin")
    if (prefix.get("status") != "pass" or not np.array_equal(cp01_deletes, master_deletes[:80_000])
            or not np.array_equal(cp01_inserts, master_inserts[:80_000])):
        raise SystemExit("historical CP01 prefix changed")
    previous_delete = set(cp01_deletes.tolist()); previous_insert = set(cp01_inserts.tolist())
    checkpoint_reports = {}; inode_owner: dict[tuple[int, int], str] = {}
    for path in sorted(item for item in trajectory.iterdir() if item.is_file() or item.is_symlink()):
        if path.is_symlink(): raise SystemExit(f"master trajectory symlink forbidden: {path}")
        st = path.stat(); key = (st.st_dev, st.st_ino)
        if st.st_nlink != 1 or st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise SystemExit(f"master trajectory artifact linked/writable: {path}")
        inode_owner[key] = str(path)
    for pct, count in CHECKPOINTS.items():
        name = f"cp{pct:02d}"; directory = trajectory / name; gt_dir = groundtruth / name
        deletes, inserts = read_trace(directory / f"replace_{name}.bin")
        if not np.array_equal(deletes, master_deletes[:count]) or not np.array_equal(inserts, master_inserts[:count]):
            raise SystemExit(f"{name} is not an exact master prefix")
        deleted, inserted = set(deletes.tolist()), set(inserts.tolist())
        if (not previous_delete < deleted or not previous_insert < inserted
                or len(deleted) != count or len(inserted) != count):
            raise SystemExit(f"{name} delete/insert nesting failed")
        previous_delete, previous_insert = deleted, inserted
        tags = read_tags(directory / f"active_{name}.tags.bin")
        mask = np.ones(8_000_000, dtype=np.bool_); mask[deletes] = False
        expected = np.sort(np.concatenate((np.flatnonzero(mask).astype("<u4"), inserts))).astype("<u4")
        if tags.size != 8_000_000 or not np.array_equal(tags, expected):
            raise SystemExit(f"{name} active set does not equal trace transition")
        spec = json.loads((directory / "visibility_probes.json").read_text()); positions = [j * (count - 1) // 8 for j in range(9)]
        if spec.get("positions") != positions:
            raise SystemExit(f"{name} probe positions invalid")
        if spec.get("probe_count") != 18 or len(spec.get("probes", [])) != 18:
            raise SystemExit(f"{name} probe count invalid")
        for index, (position, insert_probe, delete_probe) in enumerate(zip(positions, spec["probes"][::2], spec["probes"][1::2])):
            if (insert_probe != {"ordinal": 2 * index, "op_seq": position, "kind": "insert",
                                 "query_tag": int(inserts[position]), "expected_tag": int(inserts[position])}
                    or delete_probe != {"ordinal": 2 * index + 1, "op_seq": position, "kind": "delete",
                                        "query_tag": int(deletes[position]), "forbidden_tag": int(deletes[position])}):
                raise SystemExit(f"{name} probe/trace mismatch")
        manifest = json.loads((directory / "checkpoint_manifest.json").read_text())
        for artifact, identity in manifest["artifacts"].items():
            path = directory / artifact
            if path.stat().st_size != identity["size_bytes"] or sha(path) != identity["sha256"]:
                raise SystemExit(f"{name} checkpoint artifact identity mismatch: {artifact}")
        validation = json.loads((directory / "checkpoint_validation.json").read_text())
        gt_manifest = json.loads((gt_dir / "gt_manifest.json").read_text())
        gt_validation = json.loads((gt_dir / "gt_validation.json").read_text())
        if set(gt_manifest.get("artifacts", {})) != {"locations_top100.bin", "compute_groundtruth.log", f"gt_{name}", "gt_validation.json"}:
            raise SystemExit(f"{name} GT artifact set invalid")
        for artifact, identity in gt_manifest["artifacts"].items():
            path = gt_dir / artifact
            if path.stat().st_size != identity.get("size_bytes") or sha(path) != identity.get("sha256"):
                raise SystemExit(f"{name} GT artifact identity mismatch: {artifact}")
        formal = preflight["formal_inputs"]
        expected_sources = {
            "active_vectors_sha256": sha(directory / f"active_{name}.bin"),
            "active_tags_sha256": sha(directory / f"active_{name}.tags.bin"),
            "query_sha256": formal["query"]["sha256"],
            "compute_groundtruth_sha256": formal["compute_groundtruth"]["sha256"],
            "openblas_sha256": formal["openblas"]["sha256"],
            "preflight_sha256": sha(args.preflight),
        }
        if any(gt_manifest.get(key) != value for key, value in expected_sources.items()):
            raise SystemExit(f"{name} GT source/tool identity mismatch")
        for key in ("query", "compute_groundtruth", "openblas"):
            source = Path(formal[key]["realpath"])
            if source.stat().st_size != formal[key]["size_bytes"] or sha(source) != formal[key]["sha256"]:
                raise SystemExit(f"formal GT source changed during validation: {key}")
        gt_path = gt_dir / f"gt_{name}"
        nq, k = __import__("struct").unpack("<II", gt_path.open("rb").read(8))
        gt_ids = np.memmap(gt_path, dtype="<u4", mode="r", offset=8, shape=(nq, k))
        active_mask = np.zeros(10_000_000, dtype=np.bool_); active_mask[tags.astype(np.int64)] = True
        if (validation.get("status") != "pass" or gt_manifest.get("status") != "pass"
                or gt_validation.get("status") != "pass" or len(gt_validation.get("independent_bruteforce_audits", [])) != 36
                or not all(row.get("tie_aware_top100_exact") and row.get("canonical_top100_id_exact_match")
                           and row.get("position_distance_comparison_pass")
                           and row.get("raw_order_difference_only_equal_distance_ties")
                           for row in gt_validation.get("independent_bruteforce_audits", []))
                or not active_mask[np.asarray(gt_ids, dtype=np.int64)].all()):
            raise SystemExit(f"{name} checkpoint/GT validation invalid")
        for tree in (directory, gt_dir):
            for path in sorted(item for item in tree.rglob("*") if item.is_file() or item.is_symlink()):
                if path.is_symlink(): raise SystemExit(f"trajectory symlink forbidden: {path}")
                st = path.stat(); key = (st.st_dev, st.st_ino)
                if st.st_nlink != 1 or key in inode_owner:
                    raise SystemExit(f"shared/hardlinked trajectory artifact: {path} owner={inode_owner.get(key)}")
                if st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                    raise SystemExit(f"checkpoint artifact remains writable: {path}")
                inode_owner[key] = str(path)
        checkpoint_reports[name] = {"replacement_count": count, "active_cardinality": int(tags.size),
                                    "trace_sha256": sha(directory / f"replace_{name}.bin"),
                                    "trace_tsv_sha256": sha(directory / f"replace_{name}.tsv"),
                                    "active_tags_sha256": sha(directory / f"active_{name}.tags.bin"),
                                    "active_vectors_sha256": sha(directory / f"active_{name}.bin"),
                                    "probe_spec_sha256": sha(directory / "visibility_probes.json"),
                                    "probe_vectors_sha256": sha(directory / "visibility_probes.bin"),
                                    "checkpoint_manifest_sha256": sha(directory / "checkpoint_manifest.json"),
                                    "gt_sha256": sha(gt_path), "gt_manifest_sha256": sha(gt_dir / "gt_manifest.json"),
                                    "gt_validation_sha256": sha(gt_dir / "gt_validation.json"),
                                    "locations_gt_sha256": sha(gt_dir / "locations_top100.bin"),
                                    "compute_log_sha256": sha(gt_dir / "compute_groundtruth.log"),
                                    "audit_qids": gt_validation["audit_qids"], "audit_count": 36,
                                    "all_audits_canonical_tie_aware_exact": True,
                                    "tag_zero_active": gt_validation["tag_zero_active"]}
    expected_resources = ["master_trace"] + [f"cp{pct:02d}_{stage}" for pct in CHECKPOINTS for stage in ("derive", "materialize", "gt")]
    resources = {}
    for stage in expected_resources:
        path = args.resources / f"{stage}.resources.json"
        if not path.is_file(): raise SystemExit(f"missing stage resource evidence: {stage}")
        expected_scope = "dv-w1-trajectory-master.scope" if stage == "master_trace" else f"dv-w1-trajectory-{stage.replace('_', '-')}.scope"
        if stage == "master_trace":
            limit = "600"
            command = ["python3", str((Path(__file__).resolve().parent / "w1_trajectory_generate.py")),
                       "--dataset", str(root / "datasets/sift10m"), "--cp01", str(root / "datasets/sift10m/w1_cp01"),
                       "--output", str(trajectory)]
            space_root = trajectory
        else:
            cp, operation = stage.split("_", 1); pct = str(int(cp[2:])); cp_dir = trajectory / cp
            script = {"derive": "w1_trajectory_derive_checkpoint.py", "materialize": "w1_trajectory_materialize.py",
                      "gt": "w1_trajectory_gt.py"}[operation]
            if operation == "derive":
                limit = "600"
                command = ["python3", str(Path(__file__).resolve().parent / script), "--trajectory", str(trajectory), "--checkpoint", pct]
                space_root = cp_dir
            elif operation == "materialize":
                limit = "900"
                command = ["python3", str(Path(__file__).resolve().parent / script), "--dataset", str(root / "datasets/sift10m"),
                           "--checkpoint", pct, "--directory", str(cp_dir)]
                space_root = cp_dir
            else:
                limit = "1800"
                space_root = groundtruth / cp
                command = ["python3", str(Path(__file__).resolve().parent / script), "--root", str(root), "--checkpoint", pct,
                           "--checkpoint-dir", str(cp_dir), "--preflight", str(args.preflight.resolve()), "--output", str(space_root)]
        command = ["timeout", "--signal=TERM", "--kill-after=30", limit] + command
        resources[stage] = resource_summary(path, args.device, expected_scope, command, space_root)
        if (resources[stage]["returncode"] != 0 or any(int(resources[stage]["memory_events_final"].get(key, 0))
                                                        for key in ("oom", "oom_kill", "oom_group_kill"))
                or not str(resources[stage]["cgroup_path"]).endswith(expected_scope)):
            raise SystemExit(f"failed/OOM stage resource evidence: {stage}")
    report = {"schema": "dynamic-vamana-w1-trajectory-validation-v1", "status": "pass",
              "master_trace_sha256": sha(trajectory / "master_replacements_1600k.bin"),
              "master_trace_tsv_sha256": sha(trajectory / "master_replacements_1600k.tsv"),
              "master_trace_manifest_sha256": sha(trajectory / "master_trace_manifest.json"),
              "cp01_prefix_validation_sha256": sha(trajectory / "cp01_prefix_validation.json"),
              "checkpoint_prefix_exact": True, "delete_sets_strictly_nested": True,
              "insert_sets_strictly_nested": True, "active_sets_exact": True,
              "active_vector_row_tag_mapping_full_exact": True, "probe_specifications_exact": True,
              "groundtruth_active_only": True, "groundtruth_artifact_hashes_and_sources_exact": True,
              "checkpoint_artifacts_read_only_and_inode_disjoint": True,
              "checkpoints": checkpoint_reports, "resources": resources}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
