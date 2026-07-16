#!/usr/bin/env python3
"""Freeze and independently validate the accepted R06 OdinANN attempt."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import re
import statistics
import struct
from pathlib import Path

import numpy as np

GT_SHA = "4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"
MARKERS = ["clone_ready", "index_loaded", "ingest_begin", "ingest_end",
           "online_visibility_probe_begin", "online_visibility_verified", "publish_begin", "publish_end",
           "fresh_process_probe_begin", "fresh_process_visibility_verified"]
ERROR_RE = re.compile(r"fatal|assert(?:ion)?|EBADF|negative CQE|I/O error|input/output error|out of memory|segmentation fault", re.I)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def io_delta(resource: dict, device: str = "259:10") -> int:
    samples = resource.get("samples", [])
    def value(sample: dict) -> int:
        return next((int(row.get("rbytes", 0)) for row in sample.get("cgroup_io_stat", [])
                     if row.get("device") == device), 0)
    return value(samples[-1]) - value(samples[0]) if samples else 0


def query_rows(attempt: Path, active_masks: dict[str, np.ndarray]) -> list[dict]:
    rows = []
    for metric_path in sorted(attempt.glob("*_L*_r*.metrics.json")):
        match = re.fullmatch(r"(pre_cp00|post_cp01)_L(\d+)_r(\d+)\.metrics\.json", metric_path.name)
        if not match:
            continue
        phase, l_raw, repetition_raw = match.groups()
        l, repetition = int(l_raw), int(repetition_raw)
        stem = metric_path.with_name(metric_path.name.removesuffix(".metrics.json"))
        path = lambda suffix: Path(str(stem) + suffix)
        metric = load(metric_path)
        validation = load(path(".validation.json"))
        resource = load(path(".resources.json"))
        log = path(".log").read_text(errors="replace")
        result_path = path(".result_ids.bin")
        raw = result_path.read_bytes()
        nq, k = struct.unpack("<II", raw[:8])
        if (nq, k) != (10_000, 10) or len(raw) != 8 + nq * k * 4:
            raise SystemExit(f"query result shape mismatch: {result_path}")
        ids = np.frombuffer(raw, dtype="<u4", offset=8)
        active_mask = active_masks[phase]
        if int(ids.max()) >= active_mask.size or not active_mask[np.asarray(ids, dtype=np.int64)].all():
            raise SystemExit(f"query result contains inactive ID: {result_path}")
        required = ("qps", "mean_latency_us", "p50_latency_us", "p95_latency_us", "p99_latency_us", "mean_ios", "recall_at_10_percent")
        if not all(math.isfinite(float(metric[key])) for key in required):
            raise SystemExit(f"non-finite query metric: {metric_path}")
        recall = float(metric["recall_at_10_percent"]) / 100.0
        if not 0 <= recall <= 1 or validation.get("all_result_ids_active") is not True:
            raise SystemExit(f"query validation failed: {metric_path}")
        events = resource.get("cgroup_memory_events_final", {})
        if resource.get("returncode") != 0 or io_delta(resource) <= 0 or any(int(events.get(key, 0)) for key in ("oom", "oom_kill", "oom_group_kill")):
            raise SystemExit(f"query resource evidence failed: {metric_path}")
        if ERROR_RE.search(log):
            raise SystemExit(f"query log contains error: {metric_path}")
        rows.append({"phase": phase, "L": l, "repetition": repetition, "recall_at_10": recall,
                     "qps": float(metric["qps"]), "p99_latency_us": float(metric["p99_latency_us"]),
                     "mean_ios": float(metric["mean_ios"]), "nvme_read_bytes": io_delta(resource),
                     "result_ids_sha256": sha(result_path)})
    if len(rows) != 12:
        raise SystemExit(f"expected 12 Odin query points, got {len(rows)}")
    for phase in ("pre_cp00", "post_cp01"):
        for l in (29, 46):
            if len([row for row in rows if row["phase"] == phase and row["L"] == l]) != 3:
                raise SystemExit(f"query repetition set incomplete: {phase} L={l}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-tsv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-report", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    result = root / "results/pilot3_sift10m_w1_r06"
    attempt = result / "OdinANN/cp01-06"
    clone = root / "formal/pilot3_sift10m_w1_r06/OdinANN/cp01-06"
    for path in (args.output_json, args.output_tsv):
        if path.exists():
            raise SystemExit(f"freeze output overwrite refused: {path}")
    execution = load(result / "execution_manifest.json")
    if (execution.get("status"), execution.get("stopped_phase"), execution.get("exit_code")) != ("stopped_failed", "diskann_stale_static_control", 127):
        raise SystemExit("R06 is not the accepted DiskANN loader stop")
    if not (attempt / "FORMAL_W1_CANARY_OK").is_file():
        raise SystemExit("R06 Odin success marker absent")
    gate = load(attempt / "preupdate_gate.json")
    if gate.get("schema") != "dynamic-vamana-w1-preupdate-identity-v2" or gate.get("status") != "pass":
        raise SystemExit("R06 Odin identity-v2 gate invalid")
    artifact = load(args.artifact_manifest)
    odin = artifact["systems"]["OdinANN"]
    identities = gate["identities"]
    if (identities.get("query_binary_sha256") != odin["binary_sha256"]["search_disk_index"]
            or identities.get("driver_sha256") != odin["binary_sha256"]["w1_canary"]
            or identities.get("io_engine") != "uring" or identities.get("device") != "259:10"):
        raise SystemExit("R06 Odin canonical io_uring identity mismatch")
    marker_names = [json.loads(line)["marker"] for line in (attempt / "markers.jsonl").read_text().splitlines() if line]
    if marker_names != MARKERS:
        raise SystemExit(f"R06 Odin marker sequence mismatch: {marker_names}")
    active = load(attempt / "active_audit.json")
    online = load(attempt / "online_probe.json")
    fresh = load(attempt / "fresh_probe.json")
    if not (active.get("valid") is True and active.get("expected_exact_match") is True
            and active.get("active_tag_count") == 8_000_000 and active.get("duplicate_count") == 0):
        raise SystemExit("R06 Odin active set audit invalid")
    for name, probe in (("online", online), ("fresh", fresh)):
        rows = probe.get("rows", [])
        if probe.get("valid") is not True or len(rows) != 18 or not all(row.get("passed") for row in rows):
            raise SystemExit(f"R06 Odin {name} probes invalid")
    active_masks = {}
    for phase, tag_path in (("pre_cp00", root / "datasets/sift10m/active_cp00.tags.bin"),
                            ("post_cp01", root / "datasets/sift10m/w1_cp01/active_cp01.tags.bin")):
        ntag, dim = struct.unpack("<II", tag_path.read_bytes()[:8])
        tags = np.memmap(tag_path, dtype="<u4", mode="r", offset=8, shape=(ntag,))
        if (ntag, dim) != (8_000_000, 1):
            raise SystemExit(f"{phase} active-tag shape mismatch")
        mask = np.zeros(int(tags.max()) + 1, dtype=np.bool_)
        mask[np.asarray(tags, dtype=np.int64)] = True
        active_masks[phase] = mask
    queries = query_rows(attempt, active_masks)
    resource = load(attempt / "resources.json")
    events = resource.get("cgroup_memory_events_final", {})
    if resource.get("returncode") != 0 or any(int(events.get(key, 0)) for key in ("oom", "oom_kill", "oom_group_kill")):
        raise SystemExit("R06 Odin update resource evidence invalid")
    canary = load(attempt / "canary.json")
    if (canary.get("schema") != "dynamic-vamana-w1-canary-collection-v3"
            or canary.get("online_visibility_supported") is not True):
        raise SystemExit("R06 Odin canary evidence invalid")
    base_audit = load(attempt / "base_immutability.json")
    if base_audit.get("status") != "pass" or base_audit.get("content_exact") is not True or base_audit.get("mode_exact") is not True:
        raise SystemExit("R06 Odin immutable-base audit invalid")
    clone_manifest = load(clone / "clone_manifest.json")
    if (clone_manifest.get("schema") != "dynamic-vamana-w1-clone-v3"
            or clone_manifest.get("base_content_manifest_sha256") != clone_manifest.get("clone_content_manifest_sha256")):
        raise SystemExit("R06 Odin clone-v3 evidence invalid")
    preservation = load(result / "preflight/preservation_after_stop.json")
    if preservation.get("status") != "pass" or preservation.get("r02_gt_sha256") != GT_SHA:
        raise SystemExit("R06 CP01/GT preservation invalid")
    if sha(root / "groundtruth/sift10m/w1_r02/gt_cp01") != GT_SHA:
        raise SystemExit("R02 GT identity mismatch")
    if ERROR_RE.search("\n".join(path.read_text(errors="replace") for path in attempt.glob("*.log"))):
        raise SystemExit("R06 Odin log corpus contains fatal evidence")
    evidence = []
    for path in sorted(item for item in attempt.rglob("*") if item.is_file()):
        evidence.append((path.relative_to(attempt).as_posix(), path.stat().st_size, sha(path)))
    tsv = "relative_path\tsize_bytes\tsha256\n" + "".join(f"{name}\t{size}\t{digest}\n" for name, size, digest in evidence)
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.output_tsv.write_text(tsv)
    phase_io = canary["phase_device_accounting"]
    payload = 80_000 * 128 * 4
    stats = {
        "ingestion_seconds": canary["ingestion_seconds"],
        "ingestion_ops_s": canary["ingestion_throughput_ops_s"],
        "online_visibility_seconds": canary["online_visibility_seconds"],
        "online_visible_ops_s": canary["online_visible_throughput_ops_s"],
        "fresh_visibility_seconds": canary["restart_visibility_seconds"],
        "fresh_visible_ops_s": canary["restart_visible_throughput_ops_s"],
        "phase_device_accounting": phase_io,
        "logical_insert_payload_bytes": payload,
        "ingest_write_per_payload": phase_io["ingest_device_delta"]["wbytes"] / payload,
        "publish_write_per_payload": phase_io["publish_device_delta"]["wbytes"] / payload,
        "end_to_end_write_per_payload": phase_io["end_to_end_device_delta"]["wbytes"] / payload,
        "persistent_index_growth_bytes": canary["persistent_index_growth_bytes"],
        "persistent_growth_per_payload": canary["persistent_index_growth_bytes"] / payload,
        "update_elapsed_seconds": resource["elapsed_seconds"],
        "peak_process_tree_rss_bytes": int(resource.get("peak_process_tree_rss_kb", 0)) * 1024,
        "cgroup_memory_peak_bytes": max([int(row.get("cgroup_memory_peak") or 0) for row in resource.get("samples", [])] or [0]),
        "clone": {"wall_seconds": clone_manifest["clone_wall_seconds"],
                  "apparent_bytes": clone_manifest["clone_space"]["apparent_bytes"],
                  "allocated_bytes": clone_manifest["clone_space"]["allocated_bytes"],
                  "device_delta": clone_manifest["clone_device_delta"],
                  "normalization_seconds": clone_manifest["normalization_elapsed_seconds"],
                  "normalization_metadata_operations": clone_manifest["normalization_metadata_operations"]},
    }
    freeze = {"schema": "dynamic-vamana-w1-r06-odinann-freeze-v1", "status": "pass",
              "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "source_run": "pilot3_sift10m_w1_r06", "attempt": "OdinANN/cp01-06",
              "gt_sha256": GT_SHA, "markers": marker_names, "identity_gate_sha256": sha(attempt / "preupdate_gate.json"),
              "query_runs": queries, "statistics": stats,
              "online_probes_passed": 18, "fresh_probes_passed": 18,
              "base_immutability": base_audit, "clone_manifest_sha256": sha(clone / "clone_manifest.json"),
              "preservation_sha256": sha(result / "preflight/preservation_after_stop.json"),
              "evidence_manifest": {"file_count": len(evidence), "sha256": sha(args.output_tsv)}}
    args.output_json.write_text(json.dumps(freeze, indent=2) + "\n")
    table = []
    for phase in ("pre_cp00", "post_cp01"):
        for l in (29, 46):
            group = [row for row in queries if row["phase"] == phase and row["L"] == l]
            table.append(f"| {phase} | {l} | " + " / ".join(f"{row['recall_at_10']:.5f}" for row in group)
                         + " | " + " / ".join(f"{row['qps']:.2f}" for row in group)
                         + " | " + " / ".join(f"{row['p99_latency_us']:.1f}" for row in group)
                         + " | " + " / ".join(f"{row['mean_ios']:.2f}" for row in group) + " |")
    ingest, publish, end = (phase_io["ingest_device_delta"], phase_io["publish_device_delta"], phase_io["end_to_end_device_delta"])
    clone_stats = stats["clone"]
    lines = ["# Dynamic Vamana W1 R06 OdinANN Partial Results", "",
             "R06 OdinANN `cp01-06` 是独立有效的 W1 1% system-level canary。R06 后续 DiskANN loader stop 不使该 attempt 失效；R07 不重跑 OdinANN。", "",
             "## Update、可见性与资源", "",
             f"- ingestion：`{stats['ingestion_seconds']:.6f} s / {stats['ingestion_ops_s']:.3f} ops/s`。",
             f"- online visibility：`{stats['online_visibility_seconds']:.6f} s / {stats['online_visible_ops_s']:.3f} ops/s`。",
             f"- fresh-process visibility：`{stats['fresh_visibility_seconds']:.6f} s / {stats['fresh_visible_ops_s']:.3f} ops/s`。",
             f"- ingest NVMe R/W：`{ingest['rbytes']}/{ingest['wbytes']} B`；publish R/W：`{publish['rbytes']}/{publish['wbytes']} B`；end-to-end R/W：`{end['rbytes']}/{end['wbytes']} B`。",
             f"- 40,960,000 B inserted payload 对应 ingest/publish/end-to-end write ratio：`{stats['ingest_write_per_payload']:.3f}x / {stats['publish_write_per_payload']:.3f}x / {stats['end_to_end_write_per_payload']:.3f}x`。",
             f"- persistent growth：`{stats['persistent_index_growth_bytes']} B`，即 payload 的 `{stats['persistent_growth_per_payload']:.3f}x`。",
             f"- update probe wall / peak RSS / cgroup peak：`{stats['update_elapsed_seconds']:.3f} s / {stats['peak_process_tree_rss_bytes']} B / {stats['cgroup_memory_peak_bytes']} B`。",
             f"- mutable clone wall：`{clone_stats['wall_seconds']:.3f} s`，apparent/allocated：`{clone_stats['apparent_bytes']}/{clone_stats['allocated_bytes']} B`，clone NVMe R/W：`{clone_stats['device_delta'].get('rbytes', 0)}/{clone_stats['device_delta'].get('wbytes', 0)} B`。",
             f"- permission normalization：`{clone_stats['normalization_seconds']:.6f} s`，`{clone_stats['normalization_metadata_operations']}` 次 metadata operation。", "",
             "## Pre/Post query raw values", "",
             "| Phase | L | Recall@10 r1/r2/r3 | QPS r1/r2/r3 | P99(us) r1/r2/r3 | Mean I/O r1/r2/r3 |",
             "|---|---:|---|---|---|---|", *table, "",
             "Identity-v2、active set exact、18/18 online probes、18/18 fresh probes、12 次 query resource/ID audit、clone-v3、immutable-base content/mode 与停止后的 CP01/R02 GT preservation 均通过。全部正式 result evidence 的 size/SHA256 位于 R07 `preflight/r06_odinann_evidence_manifest.tsv`。", ""]
    content = "\n".join(lines)
    if args.expected_report and args.expected_report.read_text() != content:
        raise SystemExit("committed Odin partial report differs from regenerated content")
    if args.report.exists() and args.report.read_text() != content:
        raise SystemExit("Odin partial report content mismatch")
    if not args.report.exists():
        args.report.write_text(content)


if __name__ == "__main__":
    main()
