# Dynamic Vamana W1 R04 Continuation 停止报告

## 结论

R04 在 `DGAI_canary` 阶段以退出码 `255` fail closed。execution manifest 状态为 `stopped_failed`，后续系统未由 continuation controller 启动。本报告不支持任何尚未完整通过的 1% churn 结论。

## 执行边界

R04 仅复用已验证的 R02 GT 与 CP01，从系统阶段开始。控制器保留已经生成的 attempt、结果、资源和日志，不自动重试、不改参数，也不续写旧轮次。停止后的 reused-input preservation 状态为 `pass`。

## 证据

停止时间为 `2026-07-16T12:34:28.806917+08:00`。当前 R04 result tree 中共有 `39` 个证据文件，根目录为 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_r04`。具体失败位置以 `execution_manifest.json`、controller log 和阶段日志为准。
