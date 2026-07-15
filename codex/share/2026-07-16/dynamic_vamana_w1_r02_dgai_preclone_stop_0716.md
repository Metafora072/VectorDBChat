# Dynamic Vamana W1 R02 DGAI Pre-Clone 停止报告

## 结论

R02 的 checkpoint-1 ground truth 恢复全部通过，但正式 canary 在 DGAI clone 前被路径 allowlist 拒绝。`execution_manifest.json` 已按 fail-closed 规则记录 `status=stopped_failed`、`stopped_phase=DGAI_canary` 和 `exit_code=2`。DGAI 仅创建了空的系统父目录，不存在 `cp01-02` attempt、index clone、pre-update query 或 update；OdinANN 与 DiskANN 均未启动。因此，本轮仍不支持任何 1% churn 性能结论。

## 已完成的 GT 恢复

CP01 只读复用审计耗时 10.003 秒，进程树峰值 RSS 为 5,208,195,072 B。审计确认 8,000,000 row 的完整 vector-tag 语义重建一致、tag 0 保持 active，并完成 1,025 row 的固定与随机核验。

GT regressions 与完整恢复耗时 127.504 秒，进程树峰值 RSS 为 20,570,230,784 B，cgroup memory peak 为 20,660,887,552 B，新增 allocated space 峰值为 49,672,192 B。Synthetic tag-0、checkpoint-0 byte identity、query 7150 brute-force audit 和完整 36-query audit 均通过。最终 `gt_cp01` 已原子发布，SHA256 为 `4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28`；旧失败 GT 的其余 9,999 行逐字节一致，query 7150 的原 99 个有效 pair 全部保留并恢复 tag 0。

停止后重新执行 preservation audit，旧失败 GT 与 CP01 的内容均未改变，CP01 的 size 和 mtime 也保持一致。完整 GT 报告位于 `codex/share/2026-07-16/dynamic_vamana_w1_gt_recovery_results_0716.md`。

## 阻断根因

新 orchestrator 使用审议指定的 clone 路径 `formal/pilot3_sift10m_w1_r02/DGAI/cp01-02`。旧 `w1_clone_base.sh` 的 allowlist 只接受 `formal/pilot3_sift10m_w1/*/*`，没有包含 R02 路径，因此在任何 `mkdir`、reflink/copy 或 driver 调用前返回：

```text
attempt must be under an explicit W1 replay or SIFT10M W1 path
```

该错误属于 recovery run 命名与旧 clone helper 静态 allowlist 不一致，不涉及 DGAI、OdinANN 或 GT 算法。当前空目录为 `formal/pilot3_sift10m_w1_r02/DGAI` 与 `results/pilot3_sift10m_w1_r02/DGAI`，其下没有 attempt 产物。

## 建议门禁

建议 GPT 审议一个新的 continuation run，而不是覆盖或复用已停止的 R02。最小修复只应允许审议指定的新 DGAI/OdinANN attempt 绝对路径，并由 continuation preflight 重新核验 R02 GT、CP01、父停止 manifest、空 attempt 状态、frozen binaries、三套 immutable bases、NVMe 空间和无遗留进程。修复后可跳过已经通过的 GT 计算，但必须复用其 hash 与完整验证证据；DGAI、OdinANN 和 DiskANN 仍保持同一 global flock 串行，任一阶段失败后停止。未经新门禁，不启动 continuation，也不进入更高 churn 或 W2。
