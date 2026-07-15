#!/usr/bin/env python3
"""Write the mandatory fail-closed GT recovery report from partial evidence."""
from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--result", type=Path, required=True); p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--phase", required=True); p.add_argument("--exit-code", type=int, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise SystemExit("GT recovery failure report overwrite refused")
    evidence = []
    for root in (a.result / "regressions", a.result / "preparation", a.result / "preflight", a.gt):
        if root.exists(): evidence.extend(str(path.resolve()) for path in sorted(root.rglob("*")) if path.is_file())
    lines = ["# Dynamic Vamana W1 Checkpoint-1 GT 恢复失败报告", "", "## 结论", "",
             f"R02 GT recovery 在 `{a.phase}` 阶段以退出码 `{a.exit_code}` fail closed。后续 DGAI、OdinANN 和 DiskANN 均未由恢复控制器继续启动。本报告只记录恢复失败，不支持任何 1% churn 性能结论。", "",
             "## 失败边界", "",
             "控制器保留所有已产生的回归、资源和日志文件，并将新 execution manifest 标记为 `stopped_failed`。恢复目标不自动重试，旧失败 GT、CP01 与父结果目录仍作为独立证据保留。", "",
             "## 部分证据索引", "", f"报告生成时间为 `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`。截至停止时发现 `{len(evidence)}` 个 R02 证据文件，根目录分别为 `{a.result}` 与 `{a.gt}`。详细失败位置以 execution manifest、systemd scope 输出和阶段日志为准。", ""]
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text("\n".join(lines))

if __name__ == "__main__": main()
