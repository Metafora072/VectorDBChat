#!/usr/bin/env python3
"""Build the multi-attempt composed W1 1% result after R07 passes."""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import statistics
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def normalized_dynamic_queries(system: str, freeze: dict, attempt: Path) -> list[dict]:
    rows = []
    for source in freeze["query_runs"]:
        repetition = int(source.get("repetition", source.get("repeat")))
        metric_path = attempt / f"{source['phase']}_L{source['L']}_r{repetition}.metrics.json"
        metrics = load(metric_path)
        rows.append({"system": system, "phase": source["phase"], "L": int(source["L"]),
                     "repetition": repetition, "recall_at_10": float(source["recall_at_10"]),
                     "qps": float(source["qps"]), "p99_latency_us": float(source["p99_latency_us"]),
                     "mean_ios": float(source.get("mean_ios", metrics["mean_ios"])),
                     "nvme_read_bytes": int(source.get("nvme_read_bytes", source.get("read_bytes", 0)))})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("R07 composed report overwrite refused")
    root = args.root.resolve()
    r05 = root / "results/pilot3_sift10m_w1_r05/DGAI/cp01-05"
    r06_root = root / "results/pilot3_sift10m_w1_r06"
    r06 = r06_root / "OdinANN/cp01-06"
    r07_root = root / "results/pilot3_sift10m_w1_r07"
    disk = r07_root / "DiskANN/stale-cp00-07"
    required = [r05 / "FORMAL_W1_CANARY_OK", r06 / "FORMAL_W1_CANARY_OK", disk / "DISKANN_STALE_CONTROL_OK",
                r07_root / "preflight/r06_odinann_freeze.json", r07_root / "preflight/base_final_audit.json",
                r07_root / "preflight/preservation_final.json"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"R07 final prerequisites missing: {missing}")
    r05_freeze = load(r06_root / "preflight/r05_dgai_freeze.json")
    r06_freeze = load(r07_root / "preflight/r06_odinann_freeze.json")
    stale = load(disk / "stale_control.json")
    runtime = load(r07_root / "preflight/diskann_runtime_manifest.json")
    runtime_env = load(disk / "runtime_environment.json")
    if not all(item.get("status") == "pass" for item in (r05_freeze, r06_freeze, stale, runtime, runtime_env,
                                                           load(r07_root / "preflight/base_final_audit.json"),
                                                           load(r07_root / "preflight/preservation_final.json"))):
        raise SystemExit("R07 final evidence contains a failed component")
    systems = {"DGAI": r05_freeze, "OdinANN": r06_freeze}
    dynamic_rows = {"DGAI": normalized_dynamic_queries("DGAI", r05_freeze, r05),
                    "OdinANN": normalized_dynamic_queries("OdinANN", r06_freeze, r06)}
    summary = {
        "schema": "dynamic-vamana-w1-composed-result-v1", "status": "complete",
        "classification": "multi-attempt fail-closed composed W1 1% canary",
        "not_an_uninterrupted_controller_run": True,
        "sources": {"DGAI": "pilot3_sift10m_w1_r05/DGAI/cp01-05",
                    "OdinANN": "pilot3_sift10m_w1_r06/OdinANN/cp01-06",
                    "DiskANN": "pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07",
                    "GT": "groundtruth/sift10m/w1_r02/gt_cp01"},
        "dynamic_systems": {name: data["statistics"] for name, data in systems.items()},
        "diskann": stale,
        "runtime_identity": {"manifest": runtime, "environment": runtime_env},
        "validity": {"matched_recall_frontier": False, "higher_churn": False,
                     "diskann_is_dynamic": False, "visibility_semantics_directly_rankable": False},
    }
    (r07_root / "composed_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    tsv_rows = []
    for system, rows in dynamic_rows.items():
        for row in rows:
            tsv_rows.append({"system": system, "phase": row["phase"], "L": row["L"],
                             "repetition": row["repetition"], "recall_at_10": row["recall_at_10"],
                             "qps": row["qps"], "tail_latency_us": row["p99_latency_us"],
                             "tail_percentile": 99, "mean_ios": row["mean_ios"],
                             "nvme_read_bytes": row["nvme_read_bytes"]})
    for row in stale["points"]:
        tsv_rows.append({"system": "DiskANN stale-static", "phase": "cp00_index_vs_cp01_gt", "L": row["L"],
                         "repetition": row["repetition"], "recall_at_10": row["recall_at_10"],
                         "qps": row["qps"], "tail_latency_us": row["reported_tail_latency_us"],
                         "tail_percentile": row["reported_tail_percentile"], "mean_ios": row["mean_ios"],
                         "nvme_read_bytes": row["nvme_read_bytes"]})
    with (r07_root / "summary.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(tsv_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(tsv_rows)
    lines = ["# Composed W1 1% Canary Result", "",
             "## 结论", "",
             "本报告组合 R05 DGAI、R06 OdinANN、R07 DiskANN stale-static control 与 R02 checkpoint-1 exact GT。三个系统结果来自多个严格隔离、fail-closed continuation attempt，不是一次无中断 controller run。结果只支持固定 W0 policy 下的 W1 1% replace-new canary，不构成 matched-Recall frontier，也不支持更高 churn 外推。", "",
             "## Dynamic update 与可见性", "",
             "| System/source | Ingestion(s) | Ingestion ops/s | Online-visible(s/ops/s) | Fresh or restart-visible(s/ops/s) |",
             "|---|---:|---:|---|---|",
             f"| DGAI / R05 cp01-05 | {r05_freeze['statistics']['ingestion_seconds']:.3f} | {r05_freeze['statistics']['ingestion_ops_s']:.3f} | unsupported | {r05_freeze['statistics']['restart_visibility_seconds']:.3f} / {r05_freeze['statistics']['restart_visible_ops_s']:.3f} |",
             f"| OdinANN / R06 cp01-06 | {r06_freeze['statistics']['ingestion_seconds']:.3f} | {r06_freeze['statistics']['ingestion_ops_s']:.3f} | {r06_freeze['statistics']['online_visibility_seconds']:.3f} / {r06_freeze['statistics']['online_visible_ops_s']:.3f} | {r06_freeze['statistics']['fresh_visibility_seconds']:.3f} / {r06_freeze['statistics']['fresh_visible_ops_s']:.3f} |", "",
             "DGAI restart-visible 与 OdinANN online-visible 的语义不同，不作同列吞吐排名。DGAI 仅在 merge/publish 后由 fresh process 验证可见；OdinANN 同时提供 live online 与 save 后 fresh-process 证据。", "",
             "## Device I/O、空间与内存", "",
             "| System | Ingest R/W(B) | Publish R/W(B) | End-to-end R/W(B) | Persistent growth(B) | Peak RSS(B) | cgroup peak(B) |",
             "|---|---|---|---|---:|---:|---:|"]
    for system, freeze in systems.items():
        stats = freeze["statistics"]
        io = stats["phase_device_accounting"]
        lines.append(f"| {system} | {io['ingest_device_delta']['rbytes']}/{io['ingest_device_delta']['wbytes']} | {io['publish_device_delta']['rbytes']}/{io['publish_device_delta']['wbytes']} | {io['end_to_end_device_delta']['rbytes']}/{io['end_to_end_device_delta']['wbytes']} | {stats.get('persistent_index_growth_bytes', stats.get('persistent_growth_bytes', 0))} | {stats['peak_process_tree_rss_bytes']} | {stats['cgroup_memory_peak_bytes']} |")
    lines += ["", "Clone 与 permission normalization 属于 preparation，不计入 ingestion 或 visibility 区间。OdinANN 的 persistent growth 包含 save 后 shadow/fresh-process layout；DGAI persistent growth 为其正式 attempt 观测值。", "",
              "## Dynamic query stability", "",
              "| System | Phase | L | Recall median[min,max] | QPS median | P99 median(us) | Mean I/O median |",
              "|---|---|---:|---|---:|---:|---:|"]
    for system, rows in dynamic_rows.items():
        for phase in ("pre_cp00", "post_cp01"):
            for l in sorted({row["L"] for row in rows if row["phase"] == phase}):
                group = [row for row in rows if row["phase"] == phase and row["L"] == l]
                recall = [row["recall_at_10"] for row in group]
                lines.append(f"| {system} | {phase} | {l} | {median(recall):.5f}[{min(recall):.5f},{max(recall):.5f}] | {median([row['qps'] for row in group]):.2f} | {median([row['p99_latency_us'] for row in group]):.1f} | {median([row['mean_ios'] for row in group]):.2f} |")
    lines += ["", "## DiskANN stale-static negative control", "",
              "DiskANN 使用 immutable checkpoint-0 index 对 checkpoint-1 exact GT 查询。它允许返回 checkpoint-1 已删除 tag，不执行 update，也不参与动态 update throughput 排名。", "",
              "| L | Repeat | Recall@10 | QPS | Reported tail(us/percentile) | Mean I/O | NVMe read(B) |",
              "|---:|---:|---:|---:|---|---:|---:|"]
    for row in stale["points"]:
        lines.append(f"| {row['L']} | {row['repetition']} | {row['recall_at_10']:.5f} | {row['qps']:.2f} | {row['reported_tail_latency_us']:.1f} / P{row['reported_tail_percentile']} | {row['mean_ios']:.2f} | {row['nvme_read_bytes']} |")
    tcmalloc = next(row for row in runtime["dependencies"] if row["name"] == "libtcmalloc.so.9.9.5")
    lines += ["", "## Loader/runtime identity", "",
              f"DiskANN binary SHA256 为 `{runtime['binary']['sha256']}`，ELF interpreter 为 `{runtime['elf_interpreter']['resolved_realpath']}`。全部 `{len(runtime['dt_needed'])}` 个直接 DT_NEEDED 均已解析；实验私有 `libtcmalloc.so.9.9.5` 固定到 `{tcmalloc['resolved_realpath']}`，SHA256 为 `{tcmalloc['sha256']}`。正式 scope 以 ubuntu、CPU 0–23、NUMA node 0 和显式 `LD_LIBRARY_PATH` 运行。", "",
              "## 证据索引与边界", "",
              f"机器可读 composed summary 为 `{r07_root / 'composed_summary.json'}`，逐点汇总为 `{r07_root / 'summary.tsv'}`，R05/R06 freezes、runtime manifest 与 loader tests 位于 `{r07_root / 'preflight'}`，DiskANN raw evidence 位于 `{disk}`。本轮完成后停止，不自动执行更高 churn、DiskANN rebuild、Recall refinement、mixed workload、W2、DEEP 或 GIST。", ""]
    args.output.write_text("\n".join(lines))
    manifest_path = r07_root / "execution_manifest.json"
    manifest = load(manifest_path)
    manifest.update({"status": "complete", "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "report": str(args.output.resolve()), "summary": str((r07_root / "summary.tsv").resolve()),
                     "composed_summary": str((r07_root / "composed_summary.json").resolve()),
                     "composed_sources": summary["sources"]})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
