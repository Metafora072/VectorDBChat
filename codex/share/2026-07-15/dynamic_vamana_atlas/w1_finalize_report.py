#!/usr/bin/env python3
"""Build the machine summary and repository-ready Chinese W1 canary report."""
from __future__ import annotations

import argparse, csv, datetime, json, re, statistics
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def device_delta(report: dict, device: str = "259:10") -> tuple[int, int]:
    samples = report.get("samples", [])
    def value(sample: dict, key: str) -> int:
        return next((int(row.get(key, 0)) for row in sample.get("cgroup_io_stat", []) if row.get("device") == device), 0)
    if not samples:
        return 0, 0
    return value(samples[-1], "rbytes") - value(samples[0], "rbytes"), value(samples[-1], "wbytes") - value(samples[0], "wbytes")


def resources(path: Path) -> dict:
    data = load(path)
    reads, writes = device_delta(data)
    spaces = [data.get("space_before")] + [row.get("index_space") for row in data.get("samples", [])]
    spaces = [row for row in spaces if row]
    return {"elapsed_seconds": float(data["elapsed_seconds"]), "peak_rss_bytes": int(data.get("peak_process_tree_rss_kb", 0)) * 1024,
            "cgroup_memory_peak_bytes": max([int(row.get("cgroup_memory_peak") or 0) for row in data.get("samples", [])] or [0]),
            "nvme_read_bytes": reads, "nvme_write_bytes": writes,
            "peak_apparent_bytes": max([int(row.get("apparent_bytes", 0)) for row in spaces] or [0]),
            "peak_allocated_bytes": max([int(row.get("allocated_bytes", 0)) for row in spaces] or [0]),
            "final_space": spaces[-1] if spaces else {}}


def query_rows(result_root: Path, attempt: str) -> list[dict]:
    rows = []
    for system in ("DGAI", "OdinANN"):
        directory = result_root / system / attempt
        for path in sorted(directory.glob("*_L*_r*.metrics.json")):
            match = re.fullmatch(r"(pre_cp00|post_cp01)_L(\d+)_r(\d+)\.metrics\.json", path.name)
            if not match:
                continue
            phase, l, repetition = match.groups()
            metric = load(path); validation = load(path.with_name(path.name.replace(".metrics.json", ".validation.json")))
            res = resources(path.with_name(path.name.replace(".metrics.json", ".resources.json")))
            rows.append({"system": system, "phase": phase, "L": int(l), "repetition": int(repetition),
                         "recall_at_10": float(validation["recall_at_10_normalized"]),
                         **{key: float(metric[key]) for key in ("qps", "mean_latency_us", "p50_latency_us", "p95_latency_us", "p99_latency_us", "mean_ios")},
                         "nvme_read_bytes": res["nvme_read_bytes"], "serving_peak_rss_bytes": res["peak_rss_bytes"]})
    return rows


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--chat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-name", default="pilot3_sift10m_w1")
    p.add_argument("--attempt", default="cp01-01")
    p.add_argument("--stale-attempt", default="stale-cp00-01")
    p.add_argument("--cp01-resource", type=Path)
    p.add_argument("--gt-resource", type=Path)
    p.add_argument("--recovery", action="store_true")
    p.add_argument("--continuation", action="store_true")
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("formal report overwrite refused")
    result_root = a.root / "results" / a.run_name
    cp01_resource = a.cp01_resource or result_root / "preparation/cp01_preparation_resources.json"
    gt_resource = a.gt_resource or result_root / "preparation/gt_cp01_resources.json"
    required = [result_root / "preflight/execution_preflight.json", cp01_resource, gt_resource,
                result_root / f"DGAI/{a.attempt}/FORMAL_W1_CANARY_OK",
                result_root / f"OdinANN/{a.attempt}/FORMAL_W1_CANARY_OK",
                result_root / f"DiskANN/{a.stale_attempt}/DISKANN_STALE_CONTROL_OK"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"formal report prerequisites missing: {missing}")
    prep = resources(required[1]); gt = resources(required[2]); queries = query_rows(result_root, a.attempt)
    canaries = {system: load(result_root / system / a.attempt / "canary.json") for system in ("DGAI", "OdinANN")}
    gates = {system: load(result_root / system / a.attempt / "preupdate_gate.json") for system in ("DGAI", "OdinANN")}
    stale = load(result_root / "DiskANN" / a.stale_attempt / "stale_control.json")
    raw = result_root / "raw"; raw.mkdir(exist_ok=True)
    (raw / "artifact_index.json").write_text(json.dumps({"schema": "dynamic-vamana-w1-artifact-index-v1",
        "dynamic_system_results": {system: str((result_root / system / a.attempt).resolve()) for system in canaries},
        "diskann_control": str((result_root / 'DiskANN' / a.stale_attempt).resolve()),
        "preparation": ({"cp01_resource": str(cp01_resource.resolve()), "gt_resource": str(gt_resource.resolve())}
                        if a.continuation else str((result_root / 'preparation').resolve()))}, indent=2) + "\n")
    with (result_root / "summary.tsv").open("w", newline="") as stream:
        fields = list(queries[0]) if queries else []
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t"); writer.writeheader(); writer.writerows(queries)
    aggregate = []
    for system in ("DGAI", "OdinANN"):
        for phase in ("pre_cp00", "post_cp01"):
            for l in sorted({row["L"] for row in queries if row["system"] == system and row["phase"] == phase}):
                subset = [row for row in queries if row["system"] == system and row["phase"] == phase and row["L"] == l]
                aggregate.append({"system": system, "phase": phase, "L": l, "runs": subset})
    title_suffix = "R03 Continuation " if a.continuation else ("R02 GT 恢复后" if a.recovery else "")
    method = ("本次 continuation 重新核验并只读复用 R02 已恢复的 checkpoint-1 exact GT 与 CP01，从 DGAI 系统阶段开始。"
              if a.continuation else ("本次执行复用已通过只读语义审计的 CP01，并使用 location-ID GT 后置映射恢复 checkpoint-1 exact GT。"
              if a.recovery else "本次执行重新生成 CP01 与 checkpoint-1 exact GT。"))
    lines = [f"# Dynamic Vamana W1 1% Replace-New Canary {title_suffix}实验结果", "",
             "## 结论", "", "本次 SIFT10M checkpoint-1 1% replace-new canary 全流程通过。DGAI 与 OdinANN 均完成 80K 删除和 80K 插入，持久化 active tag 与预期 checkpoint-1 active set 精确一致；DiskANN 仅作为 `stale-static negative control`，不参与动态更新吞吐排名。该结果只支持固定策略下的 1% churn stability 结论，不构成 checkpoint-1 matched-Recall frontier。", "",
             "## 方法与执行边界", "", f"实验在项目 NVMe 上持有单一 global flock 串行执行。{method}门禁通过后，依次执行 DGAI、OdinANN 与 DiskANN stale-static control。正式 trace 使用 seed `20260713`，包含 80,000 个唯一删除和 80,000 个唯一插入，最终 active cardinality 为 8,000,000。DGAI ingestion 仅覆盖原生 insert/delete API，trace 解析、clone、load、publish 与 probe 均排除在该区间之外。", "",
             "## Preparation 与 GT 资源", "", "| 阶段 | Wall time(s) | Peak RSS(B) | cgroup memory peak(B) | NVMe read(B) | NVMe write(B) | Peak allocated(B) |", "|---|---:|---:|---:|---:|---:|---:|",
             f"| {'CP01 R02 reuse audit (source evidence)' if a.continuation else ('CP01 reuse audit' if a.recovery else 'CP01 preparation')} | {fmt(prep['elapsed_seconds'])} | {prep['peak_rss_bytes']} | {prep['cgroup_memory_peak_bytes']} | {prep['nvme_read_bytes']} | {prep['nvme_write_bytes']} | {prep['peak_allocated_bytes']} |",
             f"| {'R02 checkpoint-1 GT recovery (source evidence)' if a.continuation else ('checkpoint-1 exact GT recovery' if a.recovery else 'checkpoint-1 exact GT')} | {fmt(gt['elapsed_seconds'])} | {gt['peak_rss_bytes']} | {gt['cgroup_memory_peak_bytes']} | {gt['nvme_read_bytes']} | {gt['nvme_write_bytes']} | {gt['peak_allocated_bytes']} |", "",
             "以上两项属于实验准备开销，不与动态系统 update cost 比较。", "", "## Correctness 与可见性", "", "| 系统 | Active set exact | Fresh probes | Online probes | Online visibility |", "|---|---|---:|---:|---|"]
    for system, data in canaries.items():
        fresh_rows = data["visibility_probe"]["rows"]
        online_path = result_root / system / a.attempt / "online_probe.json"
        online = load(online_path)["rows"] if online_path.exists() else []
        visibility = "live instance verified" if data["online_visibility_supported"] else "unsupported"
        lines.append(f"| {system} | {data['active_tag_audit']['expected_exact_match']} | {sum(x['passed'] for x in fresh_rows)}/{len(fresh_rows)} | {sum(x['passed'] for x in online)}/{len(online) if online else 0} | {visibility} |")
    lines += ["", "DGAI 的 restart-visible throughput 与 OdinANN 的 online-visible throughput 语义不同，因此不作同列排名。", "", "## Update、I/O 与空间", "", "| 系统 | Ingestion(s) | Ingestion ops/s | Online visible ops/s | Restart visible ops/s | Ingest R/W(B) | Publish R/W(B) | E2E R/W(B) | Persistent growth(B) | Temp peak allocated(B) |", "|---|---:|---:|---:|---:|---|---|---|---:|---:|"]
    for system, data in canaries.items():
        phase = data["phase_device_accounting"]
        pair = lambda row: f"{row.get('rbytes', 0)}/{row.get('wbytes', 0)}" if row else "N/A"
        update_res = resources(result_root / system / a.attempt / "resources.json")
        lines.append(f"| {system} | {fmt(data['ingestion_seconds'])} | {fmt(data['ingestion_throughput_ops_s'])} | {fmt(data['online_visible_throughput_ops_s'])} | {fmt(data['restart_visible_throughput_ops_s'])} | {pair(phase['ingest_device_delta'])} | {pair(phase['publish_device_delta'])} | {pair(phase['end_to_end_device_delta'])} | {data['persistent_index_growth_bytes']} | {update_res['peak_allocated_bytes']} |")
    lines += ["", "## Fixed-policy query stability", "", "| 系统 | 阶段 | L | Recall median[min,max] | QPS median | P50/P95/P99 median(us) | Mean I/O median | NVMe read median(B) | Serving RSS median(B) | ΔRecall vs W0 |", "|---|---|---:|---|---:|---|---:|---:|---:|---:|"]
    pre_median = {}
    for group in aggregate:
        runs = group["runs"]; med = lambda key: statistics.median(row[key] for row in runs)
        recall_values = [row["recall_at_10"] for row in runs]
        if group["phase"] == "pre_cp00": pre_median[(group["system"], group["L"])] = med("recall_at_10")
        delta = med("recall_at_10") - pre_median.get((group["system"], group["L"]), med("recall_at_10"))
        lines.append(f"| {group['system']} | {group['phase']} | {group['L']} | {med('recall_at_10'):.4f}[{min(recall_values):.4f},{max(recall_values):.4f}] | {med('qps'):.2f} | {med('p50_latency_us'):.2f}/{med('p95_latency_us'):.2f}/{med('p99_latency_us'):.2f} | {med('mean_ios'):.2f} | {med('nvme_read_bytes'):.0f} | {med('serving_peak_rss_bytes'):.0f} | {delta:+.4f} |")
    lines += ["", "每个点均包含 3 次 raw value；完整逐次数据位于 `summary.tsv`，pre-update gate 的 identity、合法区间与逐次 NVMe 读取证据位于各系统的 `preupdate_gate.json`。", "", "## DiskANN stale-static negative control", "", "| L | Repeat | Recall@10 | NVMe read(B) |", "|---:|---:|---:|---:|"]
    for row in stale["points"]:
        lines.append(f"| {row['L']} | {row['repetition']} | {row['recall_at_10']:.4f} | {row['nvme_read_bytes']} |")
    preflight_kind = "continuation preflight" if a.continuation else ("recovery preflight" if a.recovery else "fresh execution preflight")
    recovery_evidence = (f"Clone capability tests 位于 `{result_root / 'preflight/clone_target_tests.json'}`，最终 reuse preservation audit 位于 `{result_root / 'preflight/preservation_final.json'}`；R02 source resource evidence 位于 `{cp01_resource}` 与 `{gt_resource}`。" if a.continuation else (f"CP01 reuse 位于 `{result_root / 'preflight/cp01_reuse_validation.json'}`，最终 preservation audit 位于 `{result_root / 'preflight/preservation_final.json'}`，GT recovery evidence 位于 `{result_root / 'preparation/gt_recovery_resources.json'}`。" if a.recovery else ""))
    lines += ["", "DiskANN 使用 immutable checkpoint-0 index 对 checkpoint-1 GT 查询，允许返回 checkpoint-1 已删除 tag。该数据仅用于展示 stale static baseline 的退化，不与 DGAI 或 OdinANN 的更新吞吐进行排名。", "", "## 有效性边界", "", "本次实验固定使用 DGAI `L=64/128`、OdinANN `L=29/46` 与 DiskANN `L=29/53`，query thread 数均为 1。结果未执行 checkpoint-1 Recall refinement，也未覆盖 5% 以上 replacement、mixed query/update workload、DEEP、GIST 或 W2。因此，后续实验必须由本轮 1% canary 的独立审议决定，不得由本脚本自动推进。", "", "## 证据索引", "", f"执行证据根目录为 `{result_root}`。机器汇总位于 `{result_root / 'summary.tsv'}`，原始产物索引位于 `{raw / 'artifact_index.json'}`，{preflight_kind} 位于 `{result_root / 'preflight/execution_preflight.json'}`。{recovery_evidence}", ""]
    a.output.write_text("\n".join(lines))
    manifest_path = result_root / "execution_manifest.json"; manifest = load(manifest_path)
    manifest.update({"status": "complete", "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "report": str(a.output.resolve()), "summary": str((result_root / 'summary.tsv').resolve())})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
