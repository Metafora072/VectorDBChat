#!/usr/bin/env python3
"""Create machine-readable P2-B summaries and required audit figures."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

SYSTEMS = ("DiskANN", "DGAI", "OdinANN")


def read_points(root: Path) -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text())) for p in sorted(root.glob("*/tq*/L*/r*/point.json"))]


def median(rows: list[dict], key: str):
    values = [r[key] for r in rows if r.get(key) is not None]
    return statistics.median(values) if values else None


def write_tsv(path: Path, rows: list[dict]) -> None:
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter="\t", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--result-root", type=Path, required=True)
    p.add_argument("--coarse-tsv", type=Path, required=True)
    args = p.parse_args()
    root = args.result_root
    selected = json.loads((root / "selected_refinement.json").read_text())["points"]
    refinement = read_points(root / "refinement")
    tq16 = read_points(root / "tq16")
    if any(row.get("valid") is not True for _, row in refinement + tq16):
        raise SystemExit("invalid P2-B raw point")
    raw_rows = []
    for stage, entries in (("refinement", refinement), ("tq16", tq16)):
        for path, row in entries:
            raw_rows.append({"stage": stage, "raw_path": str(path), **row})
    write_tsv(root / "refinement_raw.tsv", [r for r in raw_rows if r["stage"] == "refinement"])
    write_tsv(root / "tq1_raw_runs.tsv", [r for r in raw_rows if r["stage"] == "refinement"])
    write_tsv(root / "tq16_raw_runs.tsv", [r for r in raw_rows if r["stage"] == "tq16"])
    index = {(row["system"], int(row["query_threads"]), int(row["L"])): [] for _, row in refinement + tq16}
    for _, row in refinement + tq16: index[(row["system"], int(row["query_threads"]), int(row["L"]))].append(row)
    summary = []
    for target, choices in sorted(selected.items(), key=lambda x: float(x[0])):
        for system in SYSTEMS:
            choice = choices[system]
            if choice.get("action") != "selected": continue
            for tq in (1, 16):
                rows = index[(system, tq, int(choice["L"]))]
                if len(rows) < 3 or (tq == 16 and len(rows) != 3):
                    raise SystemExit(f"invalid repeat count: {system}/{target}/Tq{tq} has {len(rows)} rows")
                summary.append({"target_floor": float(target), "system": system, "query_threads": tq,
                                "selected_L": int(choice["L"]), "repeat_count": len(rows),
                                "median_recall_at_10": median(rows, "recall_at_10"),
                                "minimum_recall_at_10": min(r["recall_at_10"] for r in rows),
                                "maximum_recall_at_10": max(r["recall_at_10"] for r in rows),
                                "driver_qps_median": median(rows, "driver_reported_qps"),
                                "external_qps_median": median(rows, "external_qps"),
                                "p99_latency_us_median": median(rows, "p99_latency_us") or median(rows, "p999_latency_us"),
                                "mean_latency_us_median": median(rows, "mean_latency_us"),
                                "mean_ios_median": median(rows, "mean_ios"),
                                "mean_io_us_median": median(rows, "mean_io_us"),
                                "device_read_bytes_median": median(rows, "device_read_bytes_delta"),
                                "peak_rss_kb_median": median(rows, "peak_process_tree_rss_kb"),
                                "cgroup_memory_peak_median": median(rows, "cgroup_memory_peak"),
                                "process_wall_seconds_median": median(rows, "process_wall_seconds"),
                                "index_load_seconds_median": median(rows, "index_load_seconds"),
                                "warmup_seconds_median": median(rows, "warmup_seconds"),
                                "timed_search_envelope_seconds_median": median(rows, "timed_search_envelope_seconds")})
    write_tsv(root / "selected_matched_points.tsv", [r for r in summary if r["query_threads"] == 1])
    write_tsv(root / "matched_recall_summary.tsv", summary)
    write_tsv(root / "timing_scope.tsv", [{k:v for k,v in r.items() if "qps" in k or "seconds" in k or k in ("target_floor","system","query_threads","selected_L")} for r in summary])
    write_tsv(root / "resource_summary.tsv", [{k:v for k,v in r.items() if "memory" in k or "rss" in k or "bytes" in k or k in ("target_floor","system","query_threads","selected_L","mean_ios_median")} for r in summary])
    figures = root / "figures"; figures.mkdir(exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        (figures / "FIGURES_SKIPPED_NO_MATPLOTLIB").write_text("matplotlib unavailable\n"); return
    colors = {"DiskANN":"#1f77b4", "DGAI":"#ff7f0e", "OdinANN":"#2ca02c"}
    coarse = list(csv.DictReader(args.coarse_tsv.open(), delimiter="\t"))
    def curve(metric, name, ylabel):
        plt.figure(figsize=(6,4))
        for s in SYSTEMS:
            rows=[r for r in coarse if r["system"]==s]
            values = [r.get(metric) or r.get("p999_latency_us") for r in rows]
            plt.plot([float(r["recall_at_10"]) for r in rows],[float(v) for v in values],"o-",label=s,color=colors[s])
        plt.xlabel("actual median Recall@10"); plt.ylabel(ylabel); plt.legend(); plt.tight_layout(); plt.savefig(figures/name,dpi=180); plt.close()
    curve("external_qps","recall_qps_curve.png","external QPS")
    curve("p99_latency_us","recall_p99_curve.png","P99 latency (us)")
    curve("mean_ios","recall_mean_io_curve.png","mean I/Os")
    def bars(metric, name, ylabel, tq):
        rows=[r for r in summary if r["query_threads"]==tq]; targets=sorted({r["target_floor"] for r in rows}); width=.24
        plt.figure(figsize=(8,4))
        for i,s in enumerate(SYSTEMS):
            vals=[next(r[metric] for r in rows if r["target_floor"]==t and r["system"]==s) for t in targets]
            plt.bar([j+(i-1)*width for j in range(len(targets))],vals,width,label=s,color=colors[s])
        plt.xticks(range(len(targets)),targets); plt.xlabel("Recall floor"); plt.ylabel(ylabel); plt.legend(); plt.tight_layout(); plt.savefig(figures/name,dpi=180); plt.close()
    bars("driver_qps_median","matched_qps_tq1.png","driver QPS",1); bars("driver_qps_median","matched_qps_tq16.png","driver QPS",16)
    bars("p99_latency_us_median","matched_p99.png","P99 latency (us)",1); bars("mean_ios_median","matched_mean_io.png","mean I/Os",1)
    bars("peak_rss_kb_median","serving_dram.png","peak RSS (KB)",1)
    plt.figure(figsize=(6,4)); rows=[r for r in summary if r["query_threads"]==1]
    for s in SYSTEMS:
        q=[r for r in rows if r["system"]==s]; plt.scatter([r["driver_qps_median"] for r in q],[r["external_qps_median"] for r in q],label=s,color=colors[s])
    plt.xlabel("driver QPS"); plt.ylabel("external QPS"); plt.legend(); plt.tight_layout(); plt.savefig(figures/"timing_reconciliation.png",dpi=180); plt.close()
    bars("selected_L","selected_l.png","selected L",1)


if __name__ == "__main__": main()
