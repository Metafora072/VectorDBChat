# 三系统 Pilot Atlas 预算复核

**状态：** 预算复核与 scope amendment 建议；尚未下载、构建或启动任何 F0 任务。  
**提案范围：** SIFT10M Pilot 仅运行 DiskANN、DGAI 与 OdinANN，Fresh-Ref 延后到 Pilot 出现值得进一步验证的 gap 时。

## 结论

Claude 的三系统表在算术、串行执行假设和 NVMe 容量上成立。总墙钟的未取整和为 17.5--56.3 小时，故写作 18--57 小时或 1.5--2.5 天是合理的。243 GB 是串行流程的**峰值**，不能把每一行空间相加；按 128 GB 完整 BIGANN 源文件、22 GB canonical/checkpoint/GT、30.7 GB 三套静态索引、17.1 GB 最大动态工作目录、25 GB DiskANN rebuild，以及约 20 GB 临时/日志保护计算，得到约 242.8 GB。

Fresh-Ref 可以从本轮 Pilot 中移除。DiskANN（静态 rebuild 基线）、DGAI（解耦、merge-visible）与 OdinANN（耦合、即时可见）仍覆盖要回答的核心架构对照。此选择减少一个 ASLR-off/legacy artifact 失败源，也不会改变三个保留系统的统一 80/20 active set、canonical replace-new trace 或资源口径。

但它是 scope amendment，不是上一版正式门禁的自动推论：`gpt/share/dynamic_vamana_formal_atlas_w0_w1_gate_0714.md` 的 F0 与 W0 均明确要求四系统。因此 Pilot 的表述必须是“三系统方向发现实验”，不能称作该四系统正式 W0/W1 的完整替代；不得据此对 Fresh-Ref/FreshDiskANN 作性能或架构支配结论。建议先请 GPT 在对话中确认此 amendment；确认后才生成三份 F0 脚本并提交审查，仍不启动 tmux。

## 逐项预算

| 阶段 | 内容 | 墙钟预算 | NVMe 口径 |
| --- | --- | ---: | ---: |
| 数据准备 | SIFT10M 取得、hash、canonical、80/20 split、checkpoint 0/20 与 GT | 2--6 小时 | 150 GB：最坏 128 GB 源文件 + 约 22 GB canonical/checkpoint/GT |
| F0-build | DiskANN 45--75 分钟；DGAI 90--150 分钟；OdinANN 15--30 分钟，串行 | 2.5--4.3 小时 | 三套稳定索引约 30.7 GB |
| F0-query | load、query smoke、GT/tag 验证、资源快照 | 1--2 小时 | 约 1 GB 增量日志/结果 |
| slim W0 | 3 systems × 2 `Tq` × 4 settings × 1 repeat = 24 点、6 次 cold sweep | 1.5--4.5 小时 | 约 3 GB 原始结果与 manifest |
| W1-churn | DGAI direct-to-20%，含 merge/reload/publish | 6--24 小时 | 14.2 GB 工作目录；24 小时 watchdog |
| W1-churn | OdinANN direct-to-20% | 2--8 小时 | 17.1 GB 工作目录 |
| W1-rebuild | DiskANN checkpoint-20 full rebuild | 1--3 小时 | 25 GB，计入旧/新索引与临时文件共存 |
| W1-query | 三系统 × 2 `Tq` × 4 settings = 24 点 | 1.5--4.5 小时 | 约 2 GB |
| **串行合计/峰值** | 不含 Fresh-Ref、无 W2 | **18--57 小时** | **不超过 243 GB 新增峰值** |

数据准备的 2--6 小时以可用下载源为前提。若只能完整下载 BIGANN 而网络吞吐低于预期，应把“下载等待”单独记录，并将 F0 启动推迟；不能用复制或重采样 SIFT1M 替代标准前 10M SIFT corpus。

## 与四系统 Pilot 的差异

| 项目 | 四系统 | 三系统 | 变化 |
| --- | ---: | ---: | --- |
| F0 稳态索引 | 38.4 GB | 30.7 GB | 减少 Fresh-Ref 的约 7.8 GB |
| slim W0 点数 | 32 | 24 | 减少 8 点、2 次 cold sweep |
| W1 dynamic trajectory | 3 条 | 2 条 | 移除 Fresh-Ref direct-to-20% |
| 总墙钟 | 约 2--3 天 | 约 1.5--2.5 天 | 主要减少 Fresh build 与 trajectory |
| Pilot 空间保护值 | 250 GB | 243 GB | 仅小幅下降，因为 OdinANN 的 17.1 GB 仍是最大动态工作目录，且 128 GB 源文件主导峰值 |

## 执行保护

1. 目录、索引、日志和 `TMPDIR` 仅允许位于 `/home/ubuntu/pz/VectorDB/data`；启动脚本必须拒绝系统盘路径。
2. 三个系统严格串行；W1 每个系统从对应 immutable base snapshot 创建独立副本。
3. DGAI 的 24 小时 watchdog 到期即保留进度、资源与可见性记录并标记 `timeout`；不得在同一目录静默重跑。
4. 每个成功阶段写入 environment manifest、hash、退出码、allocated/apparent bytes、设备 I/O 与 cgroup 资源记录后才创建完成标记。
