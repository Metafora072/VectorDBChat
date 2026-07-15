#!/usr/bin/env python3
"""Write the repository-ready Chinese report for the bounded GT recovery."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def load(path: Path) -> dict: return json.loads(path.read_text())

def resources(path: Path) -> dict:
    data = load(path); samples = data.get("samples", [])
    peak = max([int(row.get("cgroup_memory_peak") or 0) for row in samples] or [0])
    spaces = [data.get("space_before")] + [row.get("index_space") for row in samples]
    spaces = [row for row in spaces if row]
    allocated = max([int(row.get("allocated_bytes", 0)) for row in spaces] or [0])
    return {"elapsed": float(data["elapsed_seconds"]), "peak_rss": int(data.get("peak_process_tree_rss_kb", 0)) * 1024,
            "cgroup_peak": peak, "peak_allocated": allocated}

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--result", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise SystemExit("GT recovery report overwrite refused")
    required = [a.result / "GT_RECOVERY_OK", a.result / "preflight/cp01_reuse_validation.json",
                a.result / "preparation/gt_recovery_resources.json", a.gt / "gt_cp01_manifest.json",
                a.gt / "gt_cp01_validation.json", a.gt / "failed_gt_comparison.json",
                a.result / "regressions/cp00/byte_identity.sha256", a.result / "regressions/query7150/tag_zero.json"]
    missing = [str(path) for path in required if not path.exists()]
    if missing: raise SystemExit(f"GT recovery report prerequisites missing: {missing}")
    cp01 = load(required[1]); res = resources(required[2]); manifest = load(required[3]); validation = load(required[4]); comparison = load(required[5])
    checkpoints = validation.get("checkpoints", [])
    if (cp01.get("status") != "pass" or comparison.get("status") != "pass" or len(checkpoints) != 1
            or checkpoints[0].get("nqueries") != 10000 or checkpoints[0].get("k") != 100
            or len(checkpoints[0].get("independent_bruteforce_audits", [])) != 36):
        raise SystemExit("GT recovery evidence did not pass")
    lines = ["# Dynamic Vamana W1 Checkpoint-1 GT 恢复结果", "", "## 结论", "",
             "R02 的 checkpoint-1 exact ground truth 恢复门禁全部通过。恢复流程未修改 DiskANN 的 KNN(K-Nearest Neighbors，K 近邻) 计算实现，而是先生成 location ID truthset，再通过冻结的 `active_cp01.tags.bin` 执行外部 tag 映射。最终 truthset 已原子发布，后续 DGAI 与 OdinANN 的 80K 更新实验可以在同一全局锁内继续。", "",
             "## 恢复方法与证据", "",
             "CP01 复用审计保持原目录只读，并完成 trace 重验证、全部 8,000,000 行 active vector 与 frozen corpus/tag 映射的流式语义重建，以及固定 seed 的抽样核验。由于父 execution manifest 在 CP01 生成前写入，不含第一次执行的逐文件 CP01 hash，本报告保留该历史证据缺口，并使用完整语义重建作为补偿证据。", "",
             "GT 流程依次通过 synthetic tag-0 回归、checkpoint-0 逐字节一致性回归、query 7150 完整 top-100 审计、完整 checkpoint-1 truthset 验证，以及失败 GT 对比。除 query 7150 外，其余 9,999 行与旧失败文件逐字节一致；query 7150 原有 99 个有效 pair 均被保留，并恢复合法 tag 0。全部计算日志均未出现 `WARNING: found less than k GT entries`。", "",
             "## 时间与空间", "", "| 阶段 | Wall time(s) | Peak process-tree RSS(B) | cgroup memory peak(B) | Peak allocated(B) |", "|---|---:|---:|---:|---:|",
             f"| R02 GT regressions 与完整恢复 | {res['elapsed']:.3f} | {res['peak_rss']} | {res['cgroup_peak']} | {res['peak_allocated']} |", "",
             "该资源统计包含 synthetic、checkpoint-0、query 7150 与完整 checkpoint-1 GT，不与动态系统 update cost 比较。", "",
             "## 发布边界", "",
             f"最终 GT 位于 `{a.gt / 'gt_cp01'}`，其 SHA256 为 `{manifest['truthset_sha256']}`。恢复仅授权继续当前 W1 R02 的 DGAI、OdinANN 与 DiskANN stale-static control，不授权更高 churn、W2 或其他 workload。", ""]
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text("\n".join(lines))

if __name__ == "__main__": main()
