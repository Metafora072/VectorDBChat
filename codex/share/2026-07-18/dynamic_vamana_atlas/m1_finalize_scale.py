#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import time
from pathlib import Path


SIZES = (50_000, 100_000, 200_000, 400_000)
PHASES = ("load", "insert_neighbor_repair", "delete", "metadata", "visibility", "publish_save", "other")
FILE_CLASSES = ("graph_vector_combined", "vector_pq", "tags_metadata", "shadow_files", "unknown")
ROLES = ("target_only", "target_neighbor_shared_page", "neighbor_repair_only")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def space(path: Path) -> dict[str, int]:
    rows = [item.stat() for item in path.rglob("*") if item.is_file()]
    return {"files": len(rows), "apparent_bytes": sum(row.st_size for row in rows), "allocated_bytes": sum(row.st_blocks * 512 for row in rows)}


def bucket_stats(rows: list[dict]) -> dict[str, int | float | str]:
    requested = sum(int(row["requested_bytes"]) for row in rows)
    requests = sum(int(row["request_touches"]) for row in rows)
    unique = sum(int(row["unique_4k_pages"]) for row in rows)
    touches = sum(int(row["page_write_touches"]) for row in rows)
    return {
        "requested_bytes": requested,
        "request_touch_count": requests,
        "bucket_unique_4k_page_sum": unique,
        "page_touch_count": touches,
        "page_rewrite_factor": touches / unique if unique else 0.0,
        "unique_page_semantics": "sum of profiler bucket-level unique pages",
    }


def file_class(row: dict) -> str:
    if "shadow" in Path(row["path"]).name:
        return "shadow_files"
    component = row["component"]
    if component in ("graph", "graph_vector_combined"):
        return "graph_vector_combined"
    if component == "vector":
        return "vector_pq"
    if component == "metadata":
        return "tags_metadata"
    return "unknown"


def point(system: str, size: int, summary_path: Path, input_manifest: Path, run: str, attempt: str, profiler_sha: str, anchor: bool) -> dict:
    summary = load(summary_path)
    inputs = load(input_manifest)
    assert summary["status"] == "pass" and summary["system"] == system and summary["size"] == size
    assert summary["trace_range"] == [800_000, 800_000 + size]
    assert inputs["status"] == "pass" and inputs["size"] == size and inputs["master_record_range"] == [800_000, 800_000 + size]
    assert all(summary["gates"].values())
    app = summary["application_writes"]
    buckets = app["buckets"]
    phase = {name: bucket_stats([row for row in buckets if row["phase"] == name]) for name in PHASES}
    raw_components = sorted({row["component"] for row in buckets} | {"unknown/other"})
    components = {name: bucket_stats([row for row in buckets if row["component"] == name]) for name in raw_components}
    classes = {name: bucket_stats([row for row in buckets if file_class(row) == name]) for name in FILE_CLASSES}
    role_names = {"insert_target": "target_only", "insert_target_neighbor_shared_page": "target_neighbor_shared_page", "neighbor_repair": "neighbor_repair_only"}
    roles = {name: {"requested_bytes": 0, "unique_4k_pages": 0, "page_touch_count": 0, "page_rewrite_factor": 0.0} for name in ROLES}
    for row in app["logical_roles"]:
        name = role_names[row["role"]]
        roles[name] = {
            "requested_bytes": int(row["requested_bytes"]),
            "unique_4k_pages": int(row["unique_4k_pages"]),
            "page_touch_count": int(row["page_write_touches"]),
            "page_rewrite_factor": float(row["page_rewrite_factor"]),
        }
    load_bytes = phase["load"]["requested_bytes"]
    physical = int(app["physical_total_bytes"])
    return {
        "system": system,
        "size": size,
        "run": run,
        "attempt": attempt,
        "accepted_100k_anchor": anchor,
        "summary": str(summary_path),
        "summary_sha256": sha256(summary_path),
        "input_manifest": str(input_manifest),
        "input_manifest_sha256": sha256(input_manifest),
        "profiler_sha256": profiler_sha,
        "application_physical_bytes": physical,
        "recurring_update_window_bytes": physical - int(load_bytes),
        "async_bytes": int(app["async"]["requested_bytes"]),
        "posix_copy_bytes": int(app["posix"]["requested_bytes"]),
        "application_request_count": int(app["async"]["request_count"]) + int(app["posix"]["request_count"]),
        "device_write_bytes": int(summary["device_delta"]["wbytes"]),
        "bytes_per_replacement": physical / size,
        "recurring_bytes_per_replacement": (physical - int(load_bytes)) / size,
        "phase": phase,
        "raw_component": components,
        "physical_file_class": classes,
        "logical_role": roles,
        "wall_time": summary["wall_time"],
        "peak_rss_kb": summary["peak_rss_kb"],
        "correctness": summary["correctness"],
    }


def fit(points: list[dict], getter, unit: str) -> dict:
    xs = [float(row["size"]) for row in points]
    ys = [float(getter(row)) for row in points]
    xmean = sum(xs) / len(xs); ymean = sum(ys) / len(ys)
    denominator = sum((x - xmean) ** 2 for x in xs)
    slope = sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys)) / denominator
    intercept = ymean - slope * xmean
    rows = []
    signs = []
    for x, actual in zip(xs, ys):
        predicted = intercept + slope * x
        residual = actual - predicted
        signs.append("positive" if residual > 0 else "negative" if residual < 0 else "zero")
        rows.append({
            "size": int(x),
            "actual": actual,
            "predicted": predicted,
            "absolute_residual": abs(residual),
            "signed_residual": residual,
            "relative_residual": abs(residual) / abs(actual) if actual else None,
            "actual_per_replacement": actual / x,
        })
    return {"unit": unit, "intercept": intercept, "slope_per_replacement": slope, "points": rows, "residual_sign_pattern": signs}


def trace_parts(path: Path) -> tuple[bytes, bytes]:
    payload = path.read_bytes(); count = struct.unpack_from("<I", payload)[0]
    assert len(payload) == 4 + 8 * count
    return payload[4:4 + 4 * count], payload[4 + 4 * count:]


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--result-root", type=Path, required=True)
parser.add_argument("--formal-root", type=Path, required=True)
parser.add_argument("--build-manifest", type=Path, required=True)
parser.add_argument("--closure", type=Path, required=True)
parser.add_argument("--free-before", type=int, required=True)
args = parser.parse_args()

closure = load(args.closure); build = load(args.build_manifest)
assert closure["status"] == "complete" and closure["scale_matrix_started"] is False
assert build["status"] == "pass" and build["scope"] == "m1-matched-size-dual-system"
anchor_by_system = {row["system"]: row for row in closure["anchors"]}
assert set(anchor_by_system) == {"DGAI", "OdinANN"}

points = []
input_paths = {
    50_000: args.result_root / "inputs/n50000",
    100_000: args.root / "results/pilot3_sift10m_write_attribution_m0_r03/inputs/n100000",
    200_000: args.result_root / "inputs/n200000",
    400_000: args.result_root / "inputs/n400000",
}
anchor_locations = {
    "DGAI": (args.root / "results/pilot3_sift10m_write_attribution_m0_r03/DGAI/m0-n100000-03/summary.json", "pilot3_sift10m_write_attribution_m0_r03", "m0-n100000-03"),
    "OdinANN": (args.root / "results/pilot3_sift10m_write_attribution_m0_r04/OdinANN/m0-n100000-04/summary.json", "pilot3_sift10m_write_attribution_m0_r04", "m0-n100000-04"),
}
for system in ("DGAI", "OdinANN"):
    for size in SIZES:
        if size == 100_000:
            summary_path, run, attempt = anchor_locations[system]
            profiler_sha = anchor_by_system[system]["profiler_sha256"]
            anchor = True
        else:
            run = "pilot3_sift10m_write_attribution_m1_scale_r01"; attempt = f"m1-n{size}-01"
            result = args.result_root / system / attempt
            assert (result / "M1_V5_RUN_OK").exists()
            summary_path = result / "summary.json"; profiler_sha = build["profiler_sha256"]; anchor = False
        points.append(point(system, size, summary_path, input_paths[size] / "manifest.json", run, attempt, profiler_sha, anchor))

largest_delete, largest_insert = trace_parts(input_paths[400_000] / "trace.bin")
for size in SIZES[:-1]:
    deletes, inserts = trace_parts(input_paths[size] / "trace.bin")
    assert deletes == largest_delete[:4 * size] and inserts == largest_insert[:4 * size]

fits = {}
for system in ("DGAI", "OdinANN"):
    rows = [row for row in points if row["system"] == system]
    metrics = {
        "application_physical_bytes": (lambda row: row["application_physical_bytes"], "bytes"),
        "recurring_update_window_bytes": (lambda row: row["recurring_update_window_bytes"], "bytes"),
    }
    for phase in PHASES:
        metrics[f"phase.{phase}.bytes"] = (lambda row, name=phase: row["phase"][name]["requested_bytes"], "bytes")
        metrics[f"phase.{phase}.bucket_unique_4k_page_sum"] = (lambda row, name=phase: row["phase"][name]["bucket_unique_4k_page_sum"], "pages")
        metrics[f"phase.{phase}.page_touch_count"] = (lambda row, name=phase: row["phase"][name]["page_touch_count"], "page_touches")
    for category in FILE_CLASSES:
        metrics[f"physical_file_class.{category}.bytes"] = (lambda row, name=category: row["physical_file_class"][name]["requested_bytes"], "bytes")
    for role in ROLES:
        metrics[f"logical_role.{role}.bytes"] = (lambda row, name=role: row["logical_role"][name]["requested_bytes"], "bytes")
        metrics[f"logical_role.{role}.unique_4k_pages"] = (lambda row, name=role: row["logical_role"][name]["unique_4k_pages"], "pages")
    fits[system] = {name: fit(rows, getter, unit) for name, (getter, unit) in metrics.items()}

matched = []
for size in SIZES:
    dg = next(row for row in points if row["system"] == "DGAI" and row["size"] == size)
    od = next(row for row in points if row["system"] == "OdinANN" and row["size"] == size)
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    matched.append({
        "size": size,
        "odin_over_dgai": {
            "recurring_update_window_bytes": ratio(od["recurring_update_window_bytes"], dg["recurring_update_window_bytes"]),
            "insert_neighbor_repair_bytes": ratio(od["phase"]["insert_neighbor_repair"]["requested_bytes"], dg["phase"]["insert_neighbor_repair"]["requested_bytes"]),
            "publish_save_bytes": ratio(od["phase"]["publish_save"]["requested_bytes"], dg["phase"]["publish_save"]["requested_bytes"]),
            "insert_bucket_unique_4k_page_sum": ratio(od["phase"]["insert_neighbor_repair"]["bucket_unique_4k_page_sum"], dg["phase"]["insert_neighbor_repair"]["bucket_unique_4k_page_sum"]),
            "insert_page_rewrite_factor": ratio(od["phase"]["insert_neighbor_repair"]["page_rewrite_factor"], dg["phase"]["insert_neighbor_repair"]["page_rewrite_factor"]),
        },
    })

summary = {
    "schema": "dynamic-vamana-write-attribution-m1-scale-v1",
    "status": "complete",
    "scope": "DGAI-and-OdinANN-50K-100K-200K-400K-single-run-matched-size",
    "single_run_per_point": True,
    "new_system_or_optimization_started": False,
    "nested_prefix_verified": True,
    "m0_closure": {"path": str(args.closure), "sha256": sha256(args.closure)},
    "m1_build_manifest": {"path": str(args.build_manifest), "sha256": sha256(args.build_manifest), "profiler_sha256": build["profiler_sha256"]},
    "points": points,
    "descriptive_fixed_plus_marginal_fits": fits,
    "matched_size_ratios": matched,
    "fit_interpretation_policy": "Inspect actual, predicted, absolute/relative residuals and sign patterns; no R-squared-only or threshold-based linearity claim.",
    "result_space": space(args.result_root),
    "formal_space": space(args.formal_root),
    "free_space_before": args.free_before,
    "free_space_after": shutil.disk_usage(args.result_root).free,
    "completed_unix_ns": time.time_ns(),
}
assert all(math.isfinite(value["slope_per_replacement"]) for system in fits.values() for value in system.values())
output = args.result_root / "scale_summary.json"
output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
(args.result_root / "M1_SCALE_COMPLETE").touch()
print(output)
