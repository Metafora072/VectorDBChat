#!/usr/bin/env python3
"""Fail-closed R03 continuation preflight; never recomputes CP01 or GT."""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, struct, subprocess
from pathlib import Path
import numpy as np

EXPECTED_GT_SHA = "4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"
EXPECTED_VALIDATION_SHA = "b44b50e7950ff95a2b6c9a64070bf30dbf4d55faea01981d3d8a072e9495e49f"
EXPECTED_REPORT_SHA = "2722fad04592fc8adf9c43407ef2098b8f4afe6886e77f681e36f331898fae38"
EXPECTED_GT_MANIFEST_SHA = "d022051fbccb09b753f479f7444b381180dd3fc4957a250896572ba4923f357d"

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): h.update(block)
    return h.hexdigest()

def tree_from_artifacts(root: Path, artifacts: dict) -> dict:
    h = hashlib.sha256(); total = 0
    for name in sorted(artifacts):
        row = artifacts[name]; h.update(f"{name}\t{row['size_bytes']}\t{row['sha256']}\n".encode()); total += row["size_bytes"]
    return {"realpath": str(root.resolve()), "manifest_sha256": h.hexdigest(), "file_count": len(artifacts), "total_bytes": total}

def tree_manifest(root: Path) -> dict:
    h = hashlib.sha256(); count = total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix(); size = path.stat().st_size
        h.update(f"{rel}\t{size}\t{sha(path)}\n".encode()); count += 1; total += size
    return {"realpath": str(root.resolve()), "manifest_sha256": h.hexdigest(), "file_count": count, "total_bytes": total}

def header(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream: raw = stream.read(8)
    if len(raw) != 8: raise SystemExit(f"short binary header: {path}")
    return struct.unpack("<II", raw)

def ancestors() -> set[int]:
    out: set[int] = set(); pid = os.getpid()
    while pid > 1:
        out.add(pid)
        try: pid = int(Path(f"/proc/{pid}/stat").read_text().split()[3])
        except (FileNotFoundError, ValueError, IndexError): break
    return out

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--artifact-manifest", type=Path, required=True); p.add_argument("--gt-report", type=Path, required=True)
    p.add_argument("--output", type=Path); p.add_argument("--runtime-canary-passed", action="store_true")
    p.add_argument("--dry-run", action="store_true"); a = p.parse_args()
    root = a.root.resolve(); run = "pilot3_sift10m_w1_r03"
    result = root / f"results/{run}"; formal = root / f"formal/{run}"
    if result.exists() or formal.exists() or (a.output is not None and a.output.exists()): raise SystemExit("R03 target reuse refused")
    if not a.dry_run and (a.output is None or a.output.parent.parent.resolve() != result):
        raise SystemExit("R03 preflight output must be under the fresh result root")

    r01_path = root / "results/pilot3_sift10m_w1/execution_manifest.json"
    r02_path = root / "results/pilot3_sift10m_w1_r02/execution_manifest.json"
    r01 = json.loads(r01_path.read_text()); r02 = json.loads(r02_path.read_text())
    if r01.get("status") != "stopped_failed" or r01.get("stopped_phase") not in ("gt_validation", "gt_cp01_validation"):
        raise SystemExit("R01 is not the accepted GT-validation stop")
    if (r02.get("status"), r02.get("stopped_phase"), r02.get("exit_code")) != ("stopped_failed", "DGAI_canary", 2):
        raise SystemExit("R02 is not the accepted DGAI pre-clone stop")
    r02_result = root / "results/pilot3_sift10m_w1_r02"; r02_formal = root / "formal/pilot3_sift10m_w1_r02"
    allowed_r02_result_top = {"DGAI", "GT_RECOVERY_OK", "execution_manifest.json", "formal_controller.log",
                              "preflight", "preparation", "regressions"}
    if {path.name for path in r02_result.iterdir()} != allowed_r02_result_top:
        raise SystemExit("R02 result root contains an unreported top-level artifact")
    if {path.name for path in r02_formal.iterdir()} != {"DGAI"}:
        raise SystemExit("R02 formal root contains an unreported artifact")
    forbidden = [r02_result / "FORMAL_W1_COMPLETE", r02_result / "OdinANN", r02_result / "DiskANN",
                 r02_formal / "OdinANN", r02_formal / "DiskANN"]
    if any(path.exists() for path in forbidden): raise SystemExit("R02 contains a forbidden later-stage artifact")
    for parent in (r02_result / "DGAI", r02_formal / "DGAI"):
        if not parent.is_dir() or any(parent.iterdir()): raise SystemExit(f"R02 DGAI parent is absent or non-empty: {parent}")
    if any(r02_result.glob("**/FORMAL_W1_CANARY_OK")) or any(r02_result.glob("**/DISKANN_STALE_CONTROL_OK")):
        raise SystemExit("R02 contains an unexpected success marker")

    gt_dir = root / "groundtruth/sift10m/w1_r02"; gt = gt_dir / "gt_cp01"
    validation_path = gt_dir / "gt_cp01_validation.json"; gt_manifest_path = gt_dir / "gt_cp01_manifest.json"
    if sha(gt) != EXPECTED_GT_SHA or sha(validation_path) != EXPECTED_VALIDATION_SHA or sha(gt_manifest_path) != EXPECTED_GT_MANIFEST_SHA:
        raise SystemExit("R02 recovered GT/validation/manifest identity mismatch")
    if sha(a.gt_report) != EXPECTED_REPORT_SHA or EXPECTED_GT_SHA not in a.gt_report.read_text():
        raise SystemExit("R02 GT report identity/content mismatch")
    nq, k = header(gt)
    if (nq, k) != (10_000, 100) or gt.stat().st_size != 8 + nq * k * 8: raise SystemExit("R02 GT shape/size mismatch")
    ids = np.memmap(gt, dtype="<u4", mode="r", offset=8, shape=(nq, k))
    dists = np.memmap(gt, dtype="<f4", mode="r", offset=8 + nq * k * 4, shape=(nq, k))
    cp01_dir = root / "datasets/sift10m/w1_cp01"; tags_path = cp01_dir / "active_cp01.tags.bin"
    nt, td = header(tags_path); tags = np.memmap(tags_path, dtype="<u4", mode="r", offset=8, shape=(nt,))
    if (nt, td) != (8_000_000, 1): raise SystemExit("CP01 active-tag shape mismatch")
    if np.unique(tags).size != nt or int(np.count_nonzero(tags == 0)) != 1:
        raise SystemExit("CP01 active tags are not unique with one legal tag 0")
    active_map = np.zeros(max(int(tags.max()), int(ids.max())) + 1, dtype=np.bool_); active_map[np.asarray(tags, dtype=np.int64)] = True
    if not active_map[np.asarray(ids, dtype=np.int64)].all(): raise SystemExit("R02 GT contains inactive/deleted tags")
    if not np.isfinite(dists).all() or np.any(dists[:, 1:] < dists[:, :-1]) or 0 not in set(map(int, ids[7150])):
        raise SystemExit("R02 GT finite/monotonic/tag-zero validation failed")
    validation = json.loads(validation_path.read_text()); audits = validation.get("checkpoints", [{}])[0].get("independent_bruteforce_audits", [])
    gt_manifest = json.loads(gt_manifest_path.read_text())
    if len(audits) != 36 or gt_manifest.get("truthset_sha256") != EXPECTED_GT_SHA or gt_manifest.get("validation_sha256") != EXPECTED_VALIDATION_SHA:
        raise SystemExit("R02 validation/manifest content mismatch")

    reuse_path = r02_result / "preflight/cp01_reuse_validation.json"; reuse = json.loads(reuse_path.read_text())
    if reuse.get("status") != "pass" or reuse.get("full_vector_tag_mapping_exact") is not True: raise SystemExit("R02 CP01 reuse evidence invalid")
    actual_cp01_names = {path.relative_to(cp01_dir).as_posix() for path in cp01_dir.rglob("*") if path.is_file()}
    if actual_cp01_names != set(reuse["artifacts"]): raise SystemExit("CP01 directory gained/lost an artifact after R02")
    current_artifacts = {}
    for name, expected in reuse["artifacts"].items():
        path = cp01_dir / name; stat = path.stat()
        row = {"size_bytes": stat.st_size, "sha256": sha(path), "mtime_ns": stat.st_mtime_ns}
        if row != expected: raise SystemExit(f"CP01 preservation mismatch: {name}")
        current_artifacts[name] = row
    r02_preflight = json.loads((r02_result / "preflight/execution_preflight.json").read_text())
    if tree_from_artifacts(cp01_dir, current_artifacts) != r02_preflight["preserved_cp01"]:
        raise SystemExit("CP01 directory manifest differs from R02 preflight")
    raw = (cp01_dir / "replace_cp01_80k.bin").read_bytes(); count = struct.unpack("<I", raw[:4])[0]
    if len(raw) != 4 + count * 8: raise SystemExit("current CP01 trace layout invalid")
    deletes = np.frombuffer(raw, dtype="<u4", offset=4, count=count); inserts = np.frombuffer(raw, dtype="<u4", offset=4 + count * 4, count=count)
    n0, d0 = header(root / "datasets/sift10m/active_cp00.tags.bin")
    initial = np.memmap(root / "datasets/sift10m/active_cp00.tags.bin", dtype="<u4", mode="r", offset=8, shape=(n0,))
    expected_tags = np.sort(np.concatenate((initial[~np.isin(initial, deletes)], inserts))).astype("<u4", copy=False)
    trace_manifest = json.loads((cp01_dir / "replace_cp01_manifest.json").read_text())
    old_trace_validation = json.loads((cp01_dir / "trace_validation.json").read_text())
    trace_valid = (count == 80_000 and d0 == 1 and np.unique(deletes).size == count and np.unique(inserts).size == count
                   and np.intersect1d(deletes, inserts).size == 0 and np.all(np.isin(deletes, initial))
                   and not np.any(np.isin(inserts, initial)) and np.array_equal(expected_tags, np.asarray(tags))
                   and old_trace_validation.get("valid") is True
                   and trace_manifest.get("binary_trace_sha256") == current_artifacts["replace_cp01_80k.bin"]["sha256"]
                   and trace_manifest.get("expected_cp01_active_set_sha256") == current_artifacts["active_cp01.tags.bin"]["sha256"])
    if not trace_valid: raise SystemExit("current CP01 trace validation failed")
    rng = np.random.default_rng(20260716)
    rows = np.unique(np.concatenate((np.asarray([0], dtype=np.int64), rng.choice(nt, size=1024, replace=False)))).astype(np.int64)
    if rows.size != 1025: raise SystemExit("R03 fixed CP01 sample cardinality changed")
    na, ad = header(cp01_dir / "active_cp01.bin"); nc, dim = header(root / "datasets/sift10m/full_10m.bin")
    active = np.memmap(cp01_dir / "active_cp01.bin", dtype="<f4", mode="r", offset=8, shape=(na, ad))
    corpus = np.memmap(root / "datasets/sift10m/full_10m.bin", dtype="<f4", mode="r", offset=8, shape=(nc, dim))
    for lo in range(0, rows.size, 128):
        selected = rows[lo:lo + 128]
        if not np.array_equal(np.asarray(active[selected]), np.asarray(corpus[np.asarray(tags[selected], dtype=np.int64)])):
            raise SystemExit("R03 fixed 1025-row CP01 sample mismatch")

    artifact = json.loads(a.artifact_manifest.read_text()); artifact_sha = sha(a.artifact_manifest)
    if artifact_sha != r01["artifact_manifest"]["sha256"] or artifact_sha != r02_preflight["artifact_manifest_parent_anchor_sha256"]:
        raise SystemExit("artifact manifest is not anchored to R01/R02")
    bases = {"DGAI": root / "formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index",
             "OdinANN": root / "formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index",
             "DiskANN": root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"}
    base_checks = {}
    for system, path in bases.items():
        check = tree_manifest(path); expected = artifact["systems"][system]["formal_base"]
        if not (path / "IMMUTABLE_BASE_OK").is_file() or check["manifest_sha256"] != expected["manifest_sha256"]: raise SystemExit(f"base mismatch: {system}")
        base_checks[system] = check
    inputs = {"full_corpus": root / "datasets/sift10m/full_10m.bin", "query": root / "datasets/sift10m/query.bin",
              "gt_cp00": root / "groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00",
              "diskann_query": root / "build/DiskANN/apps/search_disk_index"}
    input_checks = {name: {"realpath": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha(path)} for name, path in inputs.items()}
    for name in ("full_corpus", "query", "gt_cp00"):
        if input_checks[name]["sha256"] != artifact["formal_inputs"][name]["sha256"]: raise SystemExit(f"input mismatch: {name}")
    if input_checks["diskann_query"]["sha256"] != artifact["systems"]["DiskANN"]["binary_sha256"]["search_disk_index"]: raise SystemExit("DiskANN query mismatch")
    verifier = a.artifact_manifest.parent / "w1_verify_artifacts.py"; artifact_verification = {}
    for system in ("DGAI", "OdinANN"):
        entry = artifact["systems"][system]["canonical_install"]
        run = subprocess.run(["python3", str(verifier), "--manifest", str(a.artifact_manifest), "--system", system,
                              "--driver", entry["w1_canary"], "--query-binary", entry["search_disk_index"]], check=True, text=True, capture_output=True)
        artifact_verification[system] = json.loads(run.stdout)

    device = subprocess.run(["findmnt", "-rn", "-T", str(root), "-o", "MAJ:MIN"], check=True, text=True, capture_output=True).stdout.splitlines()[0]
    free = shutil.disk_usage(root).free
    if device != os.environ.get("ATLAS_NVME_MAJMIN", "259:10") or free < 150_000_000_000 or not a.runtime_canary_passed:
        raise SystemExit("R03 device/capacity/runtime gate failed")
    if os.environ.get("W1_GLOBAL_LOCK_HELD") != "1": raise SystemExit("R03 global lock marker absent")
    allowed = os.environ.get("W1_ALLOWED_SESSION", "")
    sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"], text=True, capture_output=True).stdout.splitlines()
    stale_sessions = [name for name in sessions if "w1" in name.lower() and name != allowed]
    scopes = subprocess.run(["systemctl", "list-units", "--type=scope", "--state=running", "--no-legend", "--plain"], text=True, capture_output=True).stdout.splitlines()
    stale_scopes = [line.strip() for line in scopes if "dv-w1" in line.lower()]
    lineage = ancestors(); pattern = re.compile(r"w1_canary|w1_run_system_canary|w1_diskann_stale_control|w1_gt_recovery_worker")
    stale_processes = []
    for row in subprocess.run(["ps", "-eo", "pid=,args="], check=True, text=True, capture_output=True).stdout.splitlines():
        fields = row.strip().split(maxsplit=1)
        if len(fields) == 2 and int(fields[0]) not in lineage and pattern.search(fields[1]): stale_processes.append(row.strip())
    if stale_sessions or stale_scopes or stale_processes: raise SystemExit(f"legacy W1 state: {stale_sessions}, {stale_scopes}, {stale_processes}")

    report = {"schema": "dynamic-vamana-w1-r03-continuation-preflight-v1", "status": "pass", "read_only_inputs": True,
              "continuation_parent_r01": "pilot3_sift10m_w1", "continuation_parent_r02": "pilot3_sift10m_w1_r02",
              "r01": {"manifest_sha256": sha(r01_path), "actual_stopped_phase": r01["stopped_phase"]},
              "r02": {"manifest_sha256": sha(r02_path), "stopped_phase": r02["stopped_phase"], "exit_code": 2,
                       "no_system_attempts": True},
              "r02_gt_reused": True, "r02_gt_sha256": EXPECTED_GT_SHA, "gt_shape": [nq, k], "gt_finite": True,
              "gt_monotonic": True, "gt_ids_active": True, "query7150_has_tag_zero": True,
              "gt_validation_sha256": EXPECTED_VALIDATION_SHA, "gt_report_sha256": EXPECTED_REPORT_SHA,
              "cp01_reused": True, "cp01_artifacts": current_artifacts, "cp01_trace_revalidated": True,
              "cp01_sample_seed": 20260716, "cp01_sample_rows": 1025, "cp01_sample_exact": True,
              "clone_allowlist_mode": "exact_target_capability", "formal_bases": base_checks, "formal_inputs": input_checks,
              "artifact_manifest_sha256": artifact_sha, "artifact_verification": artifact_verification,
              "experiment_device": device, "free_bytes": free, "global_lock_held": True,
              "new_targets_absent_before_preflight": {"result": str(result), "formal": str(formal)},
              "stale_execution_checks": {"allowed_session": allowed, "other_w1_sessions": stale_sessions,
                                           "running_w1_scopes": stale_scopes, "running_w1_workers": stale_processes}}
    if a.dry_run:
        print(json.dumps({"status": report["status"], "dry_run": True, "r02_gt_sha256": report["r02_gt_sha256"],
                          "cp01_sample_rows": report["cp01_sample_rows"], "free_bytes": report["free_bytes"]}))
    else:
        assert a.output is not None
        a.output.parent.mkdir(parents=True, exist_ok=False); a.output.write_text(json.dumps(report, indent=2) + "\n")

if __name__ == "__main__": main()
