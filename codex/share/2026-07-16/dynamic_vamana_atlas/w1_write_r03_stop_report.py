#!/usr/bin/env python3
"""Write a concise R03 fail-closed report from partial system-stage evidence."""
from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--result", type=Path, required=True)
    p.add_argument("--phase", required=True); p.add_argument("--exit-code", type=int, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise SystemExit("R03 stop report overwrite refused")
    evidence = [str(path.resolve()) for path in sorted(a.result.rglob("*")) if path.is_file()]
    manifest = json.loads((a.result / "execution_manifest.json").read_text()) if (a.result / "execution_manifest.json").is_file() else {}
    preservation_path = a.result / "preflight/preservation_after_stop.json"
    preservation = json.loads(preservation_path.read_text()).get("status") if preservation_path.is_file() else "unavailable"
    lines = ["# Dynamic Vamana W1 R03 Continuation 停止报告", "", "## 结论", "",
             f"R03 在 `{a.phase}` 阶段以退出码 `{a.exit_code}` fail closed。execution manifest 状态为 `{manifest.get('status', 'unavailable')}`，后续系统未由 continuation controller 启动。本报告不支持任何尚未完整通过的 1% churn 结论。", "",
             "## 执行边界", "", f"R03 仅复用已验证的 R02 GT 与 CP01，从系统阶段开始。控制器保留已经生成的 attempt、结果、资源和日志，不自动重试、不改参数，也不续写 R01/R02。停止后的 reused-input preservation 状态为 `{preservation}`。", "",
             "## 证据", "", f"停止时间为 `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`。当前 R03 result tree 中共有 `{len(evidence)}` 个证据文件，根目录为 `{a.result}`。具体失败位置以 `execution_manifest.json`、controller log 和阶段日志为准。", ""]
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text("\n".join(lines))

if __name__ == "__main__": main()
