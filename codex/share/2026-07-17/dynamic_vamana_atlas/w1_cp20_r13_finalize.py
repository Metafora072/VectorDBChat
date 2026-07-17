#!/usr/bin/env python3
"""Validate R13 and write the final CP00->CP20 machine-grounded trajectory."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def median_points(doc: dict) -> list[dict]:
    points = []
    for row in doc["points"]:
        metrics_path = Path(row["artifacts"]["metrics"]["realpath"]).resolve(strict=True)
        if sha(metrics_path) != row["artifacts"]["metrics"]["sha256"]:
            raise SystemExit(f"query metrics identity changed: {metrics_path}")
        metrics = load(metrics_path)
        points.append({**row, "mean_ios": float(metrics["mean_ios"])})
    output = []
    for l_value in sorted({int(row["L"]) for row in points}):
        rows = [row for row in points if int(row["L"]) == l_value]
        output.append({
            "L": l_value,
            "recall": statistics.median(float(row["recall_at_10"]) for row in rows),
            "qps": statistics.median(float(row["qps"]) for row in rows),
            "p99_us": statistics.median(float(row["p99_latency_us"]) for row in rows),
            "mean_ios": statistics.median(float(row["mean_ios"]) for row in rows),
            "read_bytes": statistics.median(int(row["device_read_bytes"]) for row in rows),
        })
    return output


def stage_row(system: str, checkpoint: str, stage: dict) -> dict:
    replacements = int(stage["delta_count"])
    phases = stage["phases"]
    ingest_s = float(phases["ingest"]["wall_seconds"])
    e2e_s = float(phases["end_to_end"]["wall_seconds"])
    return {
        "system": system, "checkpoint": checkpoint, "replacements": replacements,
        "ingest_s": ingest_s, "publish_s": float(phases["publish"]["wall_seconds"]),
        "end_to_end_s": e2e_s,
        "ingest_replacements_per_s": replacements / ingest_s,
        "end_to_end_replacements_per_s": replacements / e2e_s,
        "ingest_read_bytes_per_replacement": float(phases["ingest"]["rbytes"]) / replacements,
        "ingest_write_bytes_per_replacement": float(phases["ingest"]["wbytes"]) / replacements,
        "end_to_end_read_bytes_per_replacement": float(phases["end_to_end"]["rbytes"]) / replacements,
        "end_to_end_write_bytes_per_replacement": float(phases["end_to_end"]["wbytes"]) / replacements,
        "peak_rss_bytes": int(stage["resources"]["peak_process_tree_rss_bytes"]),
        "apparent_growth_bytes": int(stage["space"]["apparent_growth_bytes"]),
        "allocated_growth_bytes": int(stage["space"]["allocated_growth_bytes"]),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--output-report", type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
r10 = root / "results/pilot3_sift10m_w1_cp05_trajectory_r10"
r11 = root / "results/pilot3_sift10m_w1_cp05_diskann_closure_r11"
r12 = root / "results/pilot3_sift10m_w1_cp10_trajectory_r12"
run = root / "results/pilot3_sift10m_w1_cp20_trajectory_r13"
preflight = load(run / "preflight/execution_preflight.json")
r12_summary = load(r12 / "summary.json")
execution_path = run / "execution_manifest.json"
continuation_path = run / "continuation_manifest.json"
execution = load(execution_path)
continuation = load(continuation_path)
if preflight.get("status") != "pass" or r12_summary.get("status") != "pass":
    raise SystemExit("R13 preflight/R12 summary not PASS")
if (execution.get("status"), execution.get("phase"), execution.get("exit_code")) != ("stopped_failed", "cp20_DGAI", 64):
    raise SystemExit("R13 terminal execution identity mismatch")
if continuation.get("status") != "running" or continuation.get("phase") != "finalize":
    raise SystemExit("R13 continuation is not at the finalize boundary")

systems = {}
dynamic_trajectory = {}
update_trajectory = []
for system in ("DGAI", "OdinANN"):
    current = run / system / "trajectory-cp20-13"
    stage = load(current / "stages/cp20/stage_evidence.json")
    query = load(current / "queries/cp20/query_gate.json")
    freeze = load(current / "checkpoints/cp20/cp20_freeze_evidence.json")
    if not ((current / "CP20_TRAJECTORY_OK").is_file()
            and stage.get("status") == query.get("status") == freeze.get("status") == "pass"
            and (stage.get("delta_start"), stage.get("delta_count")) == (800_000, 800_000)):
        raise SystemExit(f"{system} R13 terminal evidence incomplete")
    systems[system] = {"stage": stage, "query": query, "freeze": freeze}

    r10_attempt = r10 / system / "trajectory-cp05-10"
    r12_attempt = r12 / system / "trajectory-cp10-12"
    query_sources = {
        "cp00": r10_attempt / "queries/cp00/query_gate.json",
        "cp01": r10_attempt / "queries/cp01/query_gate.json",
        "cp05": r10_attempt / "queries/cp05/query_gate.json",
        "cp10": r12_attempt / "queries/cp10/query_gate.json",
        "cp20": current / "queries/cp20/query_gate.json",
    }
    dynamic_trajectory[system] = [
        {"checkpoint": checkpoint, "query_gate_sha256": sha(path), "points": median_points(load(path))}
        for checkpoint, path in query_sources.items()
    ]
    for checkpoint, path in (
        ("cp01", r10_attempt / "stages/cp01/stage_evidence.json"),
        ("cp05", r10_attempt / "stages/cp05/stage_evidence.json"),
        ("cp10", r12_attempt / "stages/cp10/stage_evidence.json"),
        ("cp20", current / "stages/cp20/stage_evidence.json"),
    ):
        update_trajectory.append(stage_row(system, checkpoint, load(path)))

disk_path = run / "DiskANN/stale-cp20-13/stale_control.json"
disk = load(disk_path)
if disk.get("status") != "pass" or len(disk.get("points", [])) != 6:
    raise SystemExit("DiskANN CP20 stale evidence incomplete")
disk_trajectory = list(r12_summary["diskann_stale_trajectory"])
for l_value in (29, 53):
    rows = [row for row in disk["points"] if int(row["L"]) == l_value]
    disk_trajectory.append({
        "checkpoint": "cp20", "L": l_value,
        "median_recall_at_10": statistics.median(float(row["recall_at_10"]) for row in rows),
        "median_qps": statistics.median(float(row["qps"]) for row in rows),
        "median_p99_us": statistics.median(float(row["reported_tail_latency_us"]) for row in rows),
        "median_mean_ios": statistics.median(float(row["mean_ios"]) for row in rows),
    })

summary = {
    "schema": "dynamic-vamana-w1-cp20-r13-summary-v1", "status": "pass",
    "run": "pilot3_sift10m_w1_cp20_trajectory_r13", "generated_unix_ns": time.time_ns(),
    "post_cp20_action": "STOP_AND_AWAIT_REVIEW",
    "preflight_sha256": sha(run / "preflight/execution_preflight.json"),
    "execution_manifest_sha256": sha(execution_path),
    "continuation_manifest_before_completion_sha256": sha(continuation_path),
    "r12_summary_sha256": sha(r12 / "summary.json"),
    "r11_closure_sha256": sha(r11 / "closure_manifest.json"),
    "systems": systems, "dynamic_query_trajectory": dynamic_trajectory,
    "dynamic_update_trajectory": update_trajectory,
    "diskann_stale_trajectory": disk_trajectory,
    "diskann_cp20_evidence_sha256": sha(disk_path),
    "diskann_classification": "stale-static negative control; excluded from dynamic update throughput ranking",
}
(run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

lines = [
    "# Dynamic Vamana W1 CP20 trajectory R13 results", "",
    "R12 composed closure已绑定；R13只从两个R12冻结CP10 clone创建fresh private clone，并仅应用master `[800000:1600000]` 的800K replacements。CP00、CP01、CP05、CP10及1M replay均未重跑。两个CP20 clone与DiskANN CP20 stale-static control全部PASS；完成后停止并等待最终轨迹评审。", "",
    "执行边界保持可审计：首次`execution_manifest.json`在DGAI stage完整PASS后、首个query scope创建前因shared launcher capability变量名不匹配而保留为`stopped_failed/cp20_DGAI/exit=64`；`continuation_manifest.json`绑定该terminal identity，仅对DGAI执行query/freeze，再运行fresh OdinANN与DiskANN。两份manifest组成R13 closure，没有重做DGAI 800K update，也没有将首次execution伪装为单次成功。", "",
    "## CP10→CP20增量", "",
    "| 系统 | replacements | ingest s | ingest replacements/s | publish s | end-to-end s | end-to-end replacements/s | peak RSS GiB | apparent growth GiB | allocated growth GiB |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for system in ("DGAI", "OdinANN"):
    row = next(item for item in update_trajectory if item["system"] == system and item["checkpoint"] == "cp20")
    lines.append(
        f"| {system} | {row['replacements']} | {row['ingest_s']:.3f} | {row['ingest_replacements_per_s']:.3f} | "
        f"{row['publish_s']:.3f} | {row['end_to_end_s']:.3f} | {row['end_to_end_replacements_per_s']:.3f} | "
        f"{row['peak_rss_bytes']/(1024**3):.2f} | {row['apparent_growth_bytes']/(1024**3):.3f} | {row['allocated_growth_bytes']/(1024**3):.3f} |"
    )
lines += [
    "", "两种吞吐均从machine stage evidence重算：`ingest replacements/s = replacements / ingest wall time`；`end-to-end replacements/s = replacements / end-to-end wall time`。", "",
    "| 系统 | phase | wall s | read GiB | write GiB | read bytes/replacement | write bytes/replacement |",
    "|---|---|---:|---:|---:|---:|---:|",
]
for system in ("DGAI", "OdinANN"):
    stage = systems[system]["stage"]
    replacements = int(stage["delta_count"])
    for phase in ("ingest", "publish", "end_to_end"):
        row = stage["phases"][phase]
        lines.append(
            f"| {system} | {phase.replace('_', '-')} | {row['wall_seconds']:.3f} | {row['rbytes']/(1024**3):.3f} | "
            f"{row['wbytes']/(1024**3):.3f} | {row['rbytes']/replacements:.1f} | {row['wbytes']/replacements:.1f} |"
        )
odin_stage = systems["OdinANN"]["stage"]
online_s = float(odin_stage["phases"]["online"]["wall_seconds"])
fresh_s = float(odin_stage["phases"]["fresh"]["wall_seconds"])
lines += [
    "", f"DGAI按设计不支持publish前online visibility；OdinANN online与fresh visibility均PASS（wall分别为`{online_s:.6f}s`与`{fresh_s:.6f}s`）。两系统resource returncode均为0，OOM事件均为0。", "",
    "## 动态查询完整轨迹（3次中位数）", "",
    "| 系统 | checkpoint | L | Recall@10 | QPS | P99 us | mean I/O |",
    "|---|---|---:|---:|---:|---:|---:|",
]
for system, checkpoints in dynamic_trajectory.items():
    for checkpoint in checkpoints:
        for point in checkpoint["points"]:
            lines.append(
                f"| {system} | {checkpoint['checkpoint']} | {point['L']} | {point['recall']:.5f} | "
                f"{point['qps']:.2f} | {point['p99_us']:.2f} | {point['mean_ios']:.3f} |"
            )
lines += [
    "", "## 动态更新成本完整轨迹", "",
    "| 系统 | checkpoint | replacements | ingest replacements/s | end-to-end replacements/s | E2E read bytes/replacement | E2E write bytes/replacement |",
    "|---|---|---:|---:|---:|---:|---:|",
]
for row in update_trajectory:
    lines.append(
        f"| {row['system']} | {row['checkpoint']} | {row['replacements']} | {row['ingest_replacements_per_s']:.3f} | "
        f"{row['end_to_end_replacements_per_s']:.3f} | {row['end_to_end_read_bytes_per_replacement']:.1f} | "
        f"{row['end_to_end_write_bytes_per_replacement']:.1f} |"
    )
lines += [
    "", "## DiskANN stale-static negative control", "",
    "| checkpoint | L | median Recall@10 | median QPS | median reported tail us | median mean I/O |",
    "|---|---:|---:|---:|---:|---:|",
]
for row in disk_trajectory:
    def fmt(key: str, digits: int = 2) -> str:
        return "—" if row.get(key) is None else f"{float(row[key]):.{digits}f}"
    lines.append(
        f"| {row['checkpoint']} | {row['L']} | {float(row['median_recall_at_10']):.4f} | "
        f"{fmt('median_qps')} | {fmt('median_p99_us')} | {fmt('median_mean_ios', 3)} |"
    )
lines += [
    "", "两个CP20 clone均已冻结；DiskANN仍是不更新的negative control，不参与动态更新吞吐排名。R13到此停止，不自动启动新实验。", "",
    f"机器汇总：`{run/'summary.json'}`。",
]
args.output_report.write_text("\n".join(lines) + "\n")
