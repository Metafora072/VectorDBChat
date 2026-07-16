#!/usr/bin/env python3
"""Validate the DiskANN CP00-vs-CP01 stale-static negative control."""
from __future__ import annotations

import argparse, hashlib, json, math, re, struct
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def io_value(sample: dict, device: str) -> int:
    return next((int(row.get("rbytes", 0)) for row in sample.get("cgroup_io_stat", []) if row.get("device") == device), 0)


EXPECTED_GT_SHA = "4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"


def metrics(log: str, expected_l: int) -> dict:
    lines = log.splitlines()
    header = next((i for i, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("missing Recall@10")
    for line in lines[header + 1:]:
        fields = line.split()
        if fields and fields[0].isdigit():
            if len(fields) != 9 or int(fields[0]) != expected_l:
                raise ValueError(f"actual L/table shape mismatch: {fields}")
            values = list(map(float, fields[2:]))
            if not all(math.isfinite(value) for value in values):
                raise ValueError("non-finite query metric")
            recall = values[-1] / 100.0
            if not 0 <= recall <= 1:
                raise ValueError("Recall outside [0,1]")
            return {"actual_L": int(fields[0]), "beamwidth": int(fields[1]), "qps": values[0],
                    "mean_latency_us": values[1], "reported_tail_latency_us": values[2],
                    "reported_tail_percentile": 99.9, "mean_ios": values[3],
                    "mean_io_latency_us": values[4], "cpu_seconds": values[5], "recall_at_10": recall}
    raise ValueError("non-finite/unparseable Recall@10")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--result-dir", type=Path, required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--base-manifest", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--artifact-manifest", type=Path, required=True)
    p.add_argument("--runtime-manifest", type=Path, required=True)
    p.add_argument("--runtime-environment", type=Path, required=True)
    p.add_argument("--device", default="259:10")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    artifact = json.loads(a.artifact_manifest.read_text())
    frozen = artifact["systems"]["DiskANN"]
    identities = {name: {"realpath": str(path.resolve()), "sha256": sha(path)} for name, path in {
        "query_binary": a.binary, "cp00_index_manifest": a.base_manifest,
        "query": a.query, "cp01_groundtruth": a.gt}.items()}
    if identities["query_binary"]["sha256"] != frozen["binary_sha256"]["search_disk_index"]:
        raise SystemExit("DiskANN binary hash mismatch")
    if identities["cp00_index_manifest"]["sha256"] != frozen["formal_base"]["manifest_sha256"]:
        raise SystemExit("DiskANN CP00 manifest identity mismatch")
    if identities["query"]["sha256"] != artifact["formal_inputs"]["query"]["sha256"]:
        raise SystemExit("DiskANN query identity mismatch")
    if identities["cp01_groundtruth"]["sha256"] != EXPECTED_GT_SHA:
        raise SystemExit("checkpoint-1 GT identity mismatch")
    after_manifest = a.result_dir / "cp00_index_manifest_after.tsv"
    if not after_manifest.is_file() or after_manifest.read_bytes() != a.base_manifest.read_bytes():
        raise SystemExit("DiskANN immutable base changed")
    runtime = json.loads(a.runtime_manifest.read_text())
    environment = json.loads(a.runtime_environment.read_text())
    if runtime.get("status") != "pass" or runtime.get("not_found_dependencies") != []:
        raise SystemExit("DiskANN runtime manifest invalid")
    if runtime["binary"]["sha256"] != identities["query_binary"]["sha256"]:
        raise SystemExit("DiskANN runtime/binary mismatch")
    if environment.get("status") != "pass" or environment.get("uid") != 1000 or environment.get("gid") != 1000:
        raise SystemExit("DiskANN runtime environment identity mismatch")
    if environment.get("ld_library_path") != runtime.get("runtime_library_path"):
        raise SystemExit("DiskANN runtime path mismatch")
    if (environment.get("expected_scope") != "dv-w1-r07-diskann-stale.scope"
            or environment.get("affinity", {}).get("Cpus_allowed_list") != "0-23"
            or environment.get("membind_node") != 0
            or not any("dv-w1-r07-diskann-stale.scope" in row for row in environment.get("cgroup", []))):
        raise SystemExit("DiskANN formal scope/CPU/NUMA identity mismatch")
    points = []
    query_n, _ = struct.unpack("<II", a.query.open("rb").read(8))
    for l in (29, 53):
        for repetition in (1, 2, 3):
            stem = a.result_dir / f"L{l}_r{repetition}"
            result = Path(f"{stem}_{l}_idx_uint32.bin")
            n, k = struct.unpack("<II", result.open("rb").read(8))
            if (n, k) != (query_n, 10) or result.stat().st_size != 8 + n * k * 4:
                raise SystemExit(f"invalid stale result shape L={l} r={repetition}")
            log = stem.with_suffix(".log").read_text(errors="replace")
            if not re.search(r"Search parameters:\s*#threads:\s*1", log) or re.search(r"fatal|assert(?:ion)?|I/O error|input/output error|out of memory|oom|segmentation fault", log, re.I):
                raise SystemExit(f"fatal/I/O/OOM stale query log L={l} r={repetition}")
            resources = json.loads(stem.with_suffix(".resources.json").read_text())
            events = resources.get("cgroup_memory_events_final", {})
            samples = resources.get("samples", [])
            reads = io_value(samples[-1], a.device) - io_value(samples[0], a.device) if samples else 0
            if resources.get("returncode") != 0 or reads <= 0 or any(int(events.get(x, 0)) for x in ("oom", "oom_kill", "oom_group_kill")):
                raise SystemExit(f"invalid stale resource evidence L={l} r={repetition}")
            point_metrics = metrics(log, l)
            points.append({"L": l, "Tq": 1, "repetition": repetition, **point_metrics,
                           "nvme_read_bytes": reads, "result_shape": [n, k],
                           "result_ids_sha256": sha(result),
                           "resources": str(stem.with_suffix('.resources.json').resolve())})
    report = {"schema": "dynamic-vamana-w1-stale-control-v1", "status": "pass",
              "classification": "stale-static negative control", "rank_with_update_throughput": False,
              "deleted_cp01_tags_allowed": True, "identities": identities,
              "runtime_manifest": {"realpath": str(a.runtime_manifest.resolve()), "sha256": sha(a.runtime_manifest)},
              "runtime_environment": {"realpath": str(a.runtime_environment.resolve()), "sha256": sha(a.runtime_environment)},
              "immutable_base_after_sha256": sha(after_manifest), "points": points}
    a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
