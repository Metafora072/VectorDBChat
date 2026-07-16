# Dynamic Vamana W1 CP05 R02 Static Smoke 停止分析

## 停止结论

`pilot3_sift10m_w1_cp05_trajectory_r02` 的启动准备于 `2026-07-16 23:56:27 UTC+8` 前在 DGAI static load smoke 的 evidence gate 停止。直接错误为 `I/O engine differs from frozen artifact manifest`。冻结的 canonical-v6 artifact manifest 将 DGAI `io_engine` 定义为 `aio`，而 R02 编排错误地向 evidence validator 传入了 `pread`。该差异属于编排层的 identity 标签错误，不是查询二进制、immutable base、数据、内存或 NVMe 故障。

R02 execution manifest 尚未激活，新的 replay/formal delta 尚未派生，OdinANN static smoke、1M sequential replay、SIFT10M formal update 和 DiskANN CP05 stale control 均未开始。因此，本次停止不包含任何 replay 或正式动态系统实验结果，也没有消耗 `trajectory-cp05-02`、`sequential-cp80-02` 或 `stale-cp05-02` 的正式数据语义。

## 已完成证据

DGAI 与 OdinANN 的独立 immutable replay-base copies 已成功创建并通过实时只读复核。两者均锚定 accepted `pilot3_w1_formal_path_replay_r07` 的 before、after 和 after-attempt content manifest，并证明当前共享 source content 未发生变化。正式 root 视图下，`cp00` 与 `index` 目录的数值 UID/GID 为 `0:0`、mode 为 `0555`，regular file 为 `0:0/0444`；ubuntu 的 open-write、create、rename 和 unlink denial 全部通过。共享的 `index/atlas1m` source 未执行原地 chmod 或其他修改。

DGAI static smoke 已真实执行 `L=64` 与 `L=128` 各一次，两次进程返回码均为 0，均加载新 immutable copy，并输出完整的 `36×10` result IDs。`L=64` 的 Recall@10 为 `0.9833`，资源探针 wall time 为 `0.878 s`，峰值进程树 RSS 为 `567,017,472 B`，读取 `29,900,800 B`；`L=128` 的 Recall@10 为 `0.9917`，wall time 为 `0.853 s`，峰值进程树 RSS 为 `564,264,960 B`，读取 `39,186,432 B`。两点的 result IDs 均全部属于 CP00 active set，`oom`、`oom_kill` 与 `oom_group_kill` 均为 0。Recall 仅作为诊断值记录，不构成通过阈值。

## 根因与修复

查询命令未通过运行时参数选择 `pread`。DGAI canonical binary 已由 artifact manifest 固定为 `aio`，错误仅存在于 orchestrator 传递给 evidence validator 的 `--io-engine` 字段。修复将 R02 编排中 DGAI static smoke、1M replay 与 SIFT10M formal 三处 I/O engine identity 从 `pread` 统一改为 `aio`，并在 R02 preflight 中新增 `artifact.systems.DGAI.io_engine == aio` 的 fail-closed 检查。OdinANN 继续保持冻结的 `uring` identity。

停止时的 partial static-smoke 目录和 controller log 将整体归档为只读诊断证据，不作为后续 PASS smoke 复用。后续启动使用原定 R02 run 和 attempt identities，但从 absent 的 canonical static-smoke 路径重新执行 DGAI 与 OdinANN 四个 smoke 点；已发布且验证通过的 immutable replay bases 只进行 read-only verify，不重新复制。任何新的 identity、I/O、OOM、active-set 或 preservation 失败仍会立即停止。

## 有效性边界

本次两条 DGAI 查询证明 immutable copy 可由 canonical binary 正常加载并产生完整 active results，但由于 evidence identity 不一致，它们不能替代完整 static smoke gate。修复后必须在新鲜路径重新执行 DGAI `L64/L128` 与 OdinANN `L29/L46`，并由 validator 统一生成 PASS 汇总，之后才允许激活 R02 execution manifest。CP10 与 CP20 继续 HOLD。
