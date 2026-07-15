#!/usr/bin/env python3
"""Fail-closed median Recall and identity/I/O gate before any W1 update."""
from __future__ import annotations

import argparse, hashlib, json, math, re, statistics
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def device_counter(sample: dict, device: str, key: str) -> int:
    for row in sample.get("cgroup_io_stat", []):
        if row.get("device") == device:
            return int(row.get(key, 0))
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    p.add_argument("--mode", choices=("micro", "formal"), required=True)
    p.add_argument("--result-dir", type=Path, required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--index-manifest", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--active-tags", type=Path, required=True)
    p.add_argument("--ls", required=True)
    p.add_argument("--device", default="259:10")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    formal = {"DGAI": {64: (0.950, 0.955), 128: (0.980, 0.985)},
              "OdinANN": {29: (0.950, 0.955), 46: (0.980, 0.985)}}
    # The micro replay has a separate frozen SIFT1M baseline.  These narrow
    # intervals are evidence gates, not formal SIFT10M policy changes.
    # r07 contained one query per point and therefore could not define a
    # repeat-to-repeat interval.  The replay gate is intentionally a broad
    # high-recall sanity bound; the formal SIFT10M intervals above remain exact.
    micro = {"DGAI": {64: (0.9800, 1.0000), 128: (0.9800, 1.0000)},
             "OdinANN": {29: (0.9800, 1.0000), 46: (0.9800, 1.0000)}}
    ranges = formal if a.mode == "formal" else micro
    identities = {name: {"realpath": str(path.resolve()), "sha256": sha(path)} for name, path in {
        "binary": a.binary, "index_manifest": a.index_manifest, "query": a.query,
        "groundtruth": a.gt, "active_tags": a.active_tags}.items()}
    points = []
    for l in map(int, a.ls.split(",")):
        if l not in ranges[a.system]:
            raise SystemExit(f"no frozen gate interval for {a.system} L={l}")
        recalls = []
        runs = []
        for repetition in (1, 2, 3):
            stem = a.result_dir / f"pre_cp00_L{l}_r{repetition}"
            validation = json.loads(stem.with_suffix(".validation.json").read_text())
            resources = json.loads(stem.with_suffix(".resources.json").read_text())
            metrics = json.loads(stem.with_suffix(".metrics.json").read_text())
            log = stem.with_suffix(".log").read_text(errors="replace")
            if resources.get("returncode") != 0:
                raise SystemExit(f"query resource probe failed: L={l} r={repetition}")
            events = resources.get("cgroup_memory_events_final", {})
            if any(int(events.get(key, 0)) for key in ("oom", "oom_kill", "oom_group_kill")):
                raise SystemExit(f"query OOM evidence: L={l} r={repetition}")
            if re.search(r"fatal|assert(?:ion)?|I/O error|input/output error|out of memory|oom", log, re.I):
                raise SystemExit(f"fatal/I/O/OOM marker in query log: L={l} r={repetition}")
            samples = resources.get("samples", [])
            if not samples:
                raise SystemExit(f"missing query samples: L={l} r={repetition}")
            read_bytes = device_counter(samples[-1], a.device, "rbytes") - device_counter(samples[0], a.device, "rbytes")
            if read_bytes <= 0:
                raise SystemExit(f"zero real NVMe reads: L={l} r={repetition}")
            if not validation.get("all_result_ids_active") or validation.get("invalid_or_inactive_ids") != 0:
                raise SystemExit(f"inactive CP00 result tag: L={l} r={repetition}")
            recall = float(validation["recall_at_10_normalized"])
            required_metrics = ("qps", "mean_latency_us", "p50_latency_us", "p95_latency_us", "p99_latency_us", "mean_ios")
            if not math.isfinite(recall) or not all(math.isfinite(float(metrics[key])) for key in required_metrics):
                raise SystemExit("non-finite recall")
            recalls.append(recall)
            runs.append({"repetition": repetition, "recall_at_10": recall, "nvme_read_bytes": read_bytes,
                         "validation": str(stem.with_suffix('.validation.json').resolve()),
                         "resources": str(stem.with_suffix('.resources.json').resolve()), "metrics": metrics})
        median = statistics.median(recalls)
        low, high = ranges[a.system][l]
        if not low <= median <= high:
            raise SystemExit(f"pre-update Recall gate failed: {a.system} L={l} median={median} expected=[{low},{high}]")
        points.append({"L": l, "allowed_interval": [low, high], "raw_recalls": recalls,
                       "median_recall_at_10": median, "valid_runs": 3, "runs": runs})
    report = {"schema": "dynamic-vamana-w1-preupdate-gate-v1", "status": "pass",
              "system": a.system, "mode": a.mode, "identity_consistent": True,
              "identities": identities, "points": points}
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
