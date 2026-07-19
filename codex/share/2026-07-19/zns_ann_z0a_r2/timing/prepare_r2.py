#!/usr/bin/env python3
"""Pre-register the balanced R2 schedule and pre-create every timed clone."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import random
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARE = HERE.parent
OLD = SHARE.parent / "zns_ann_z0a"
ATLAS = Path(os.environ.get("ATLAS_ROOT", "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas"))
ROOT = Path(os.environ.get("Z0A_R2_RUN_ROOT", str(ATLAS / "z0a_r2_final_closure_0719")))
SEED = 20260719
MODES = ("native", "shim", "full")
SYSTEMS = ("DGAI", "OdinANN")
NAMESPACE = uuid.UUID("e05b42e0-0ad9-475f-a33a-0e41005cb521")


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def clone(source: Path, target: Path) -> None:
    run("cp", "-a", "--reflink=auto", str(source), str(target))


def main() -> int:
    if os.environ.get("Z0A_R2_PREPARE_AUTHORIZED") != "1":
        raise RuntimeError("Z0A-R2 prepare authorization absent")
    if ROOT.exists() or not ATLAS.is_dir():
        raise RuntimeError(f"refusing reused/missing root: {ROOT}")
    stat = subprocess.check_output(["findmnt", "-rn", "-T", str(ATLAS), "-o", "MAJ:MIN"], text=True).splitlines()[0]
    if stat != "259:10":
        raise RuntimeError(f"project root is not NVMe 259:10: {stat}")
    free = shutil.disk_usage(ATLAS).free
    required = 16 * 1024**3
    if free < required:
        raise RuntimeError(f"free-space guard failed: free={free}, required={required}")
    (ROOT / "work").mkdir(parents=True)
    (ROOT / "results").mkdir()
    (ROOT / "evidence").mkdir()

    permutations = list(itertools.permutations(MODES)) * 2
    random.Random(SEED).shuffle(permutations)
    runs: list[dict[str, object]] = []
    for system in SYSTEMS:
        for position, mode in enumerate(MODES, 1):
            label = f"{system.lower()}-warmup-p{position}-{mode}"
            runs.append({"system": system, "warmup": True, "triplet": 0, "position": position, "mode": mode, "label": label})
        for triplet, order in enumerate(permutations, 1):
            for position, mode in enumerate(order, 1):
                label = f"{system.lower()}-t{triplet:02d}-p{position}-{mode}"
                runs.append({"system": system, "warmup": False, "triplet": triplet, "position": position, "mode": mode, "label": label})
    for row in runs:
        row["run_uuid"] = str(uuid.uuid5(NAMESPACE, str(row["label"])))
    schedule = {
        "schema": "zns-ann-z0a-r2-preregistered-schedule-v1",
        "seed": SEED,
        "formal_triplets_per_system": 12,
        "bootstrap_resamples": 100000,
        "cpu_binding": "0-27,56-59",
        "numa_node": 0,
        "warmup_in_analysis": False,
        "runs": runs,
    }
    schedule_bytes = (json.dumps(schedule, indent=2, sort_keys=True) + "\n").encode()
    schedule["schedule_sha256_without_self_hash"] = hashlib.sha256(schedule_bytes).hexdigest()
    (ROOT / "schedule.json").write_text(json.dumps(schedule, indent=2, sort_keys=True) + "\n")
    (ROOT / ".z0a-r2-owned").write_text("zns-ann-z0a-r2-owned-v1\n")

    for index, row in enumerate(runs, 1):
        label = str(row["label"])
        system = str(row["system"])
        work = ROOT / "work" / label
        result = ROOT / "results" / label
        work.mkdir()
        result.mkdir()
        index_root = work / "index"
        clone(ATLAS / "index" / "sanity" / system, index_root)
        for path in index_root.glob("sift10k_*"):
            path.rename(path.with_name(path.name.replace("sift10k_", "index_", 1)))
        for path in index_root.rglob("*"):
            if path.is_file():
                path.chmod(path.stat().st_mode | 0o200)
        clone(index_root, work / "initial_snapshot")
        (work / ".z0a-r2-owned").write_text("zns-ann-z0a-r2-owned-v1\n")
        (result / ".z0a-r2-owned").write_text("zns-ann-z0a-r2-owned-v1\n")
        manifest = result / "initial_live.jsonl"
        run(sys.executable, str(OLD / "initial_manifest.py"), "--system", system, "--run-id", str(row["run_uuid"]),
            "--clone-root", str(index_root), "--output", str(manifest), "--z0a-root", str(ROOT))
        run(sys.executable, str(OLD / "runner" / "manifest_to_registry.py"), "--manifest", str(manifest),
            "--output", str(result / "object_registry.tsv"))
        if row["mode"] == "full":
            run(sys.executable, str(SHARE / "canonical_pack.py"), "--manifest", str(manifest),
                "--snapshot-root", str(work / "initial_snapshot"), "--config", str(SHARE / "short_closure_config.json"),
                "--image", str(result / "initial_zns_image.bin"), "--physical-map", str(result / "initial_physical_map.jsonl"),
                "--summary", str(result / "initial_packing_summary.json"))
        print(f"prepared {index}/{len(runs)} {label}", flush=True)
    (ROOT / "PREPARED_OK").touch()
    print(json.dumps({"status": "pass", "root": str(ROOT), "runs": len(runs), "free_before": free, "guard_bytes": required}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
