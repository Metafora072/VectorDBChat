**Gpt(02:18:33)**：
Claude 的准备阶段审查可以通过，我接受其三个条件。Codex 已完成 12/12 query smoke、9/9 dynamic smoke，artifact provenance、GT、replace-new trace 和 visibility 基础口径均已打通，可以进入正式 W0/W1。具体执行要求见 `gpt/share/dynamic_vamana_formal_atlas_w0_w1_gate_0714.md`。

正式阶段需要补充一个关键公平性要求：更新性能必须同时报告 `ingestion throughput` 和 `visible-update throughput`。Fresh-Ref 与 OdinANN 在 API 完成后即可查询，DGAI 需要 merge/reload 后才对新 active set 可见，因此 DGAI 的 Vm 必须计入 merge 与 publish 时间，不能只比较 merge 前的插入速度。DiskANN 对应的是 rebuild + publish。

Codex，请先完成 SIFT10M 四系统 readiness 与 W0，再扩展到 DEEP10M 和 GIST1M；每个正式点至少重复三次，使用同一 NVMe、固定 NUMA/CPU 和 dedicated cgroup。W1 使用 canonical replace-new trace，在 5%、10%、20% checkpoint 重算 GT 并重跑 query sweep。Fresh-Ref/GIST 的 R32 结果作为受 4 KiB record 限制的 constrained point 保留，但不能用于无条件的架构支配结论。

本轮完成 W0+W1 后停止。它能够形成查询、更新、资源与 churn 稳定性的初步版图，但还不是最终联合 Vq–Vm frontier；W2 mixed workload 等看到 W0/W1 数据后再授权。

**PZ(02:19:01)**:
Codex，先估算下 Gpt 要求的实验大概需要跑多长时间，我评估下，等我确认后再跑实验。

**Codex(02:26:23)**:
已完成只读排期，详见 `codex/share/dynamic_vamana_formal_atlas_runtime_estimate_0714.md`；没有下载 SIFT10M、没有构建正式索引、没有启动任何 W0/W1 点。

完整 W0+W1 在 Gpt 要求的单 NVMe 串行、dedicated cgroup、每点三重复下，建议预留 **4--8 天墙钟**，保守上界 **10 天**。主要量级不是 12 个简单 smoke：W0 是 4 systems × 3 datasets × 4 Tq × 4 search settings × 3 repeats，共 576 个 Recall--performance 点（可合并为 144 个独立 cold-lifecycle sweep）；W1 的三动态系统在 5/10/20% checkpoint 重跑同样 sweep，共 1,296 个 checkpoint-query 点（324 个 sweep），外加 27 条到 20% churn 的三重复动态 trajectory 与 DiskANN checkpoint-20 rebuild。

最稳妥的第一段是 F0：先下载/校验 SIFT10M、冻结环境、跑四系统 build/load/query/resource/snapshot，估计 **12--24 小时**。这一步完成后可以用实际 10M build 时间、设备 I/O 与 visible-update throughput 把后续误差收敛到约 ±30%。随后 DEEP10M/GIST1M assets 约 8--20 小时，W0 约 10--22 小时；W1 的 checkpoint query 约 22--48 小时，动态 update trajectory 与 DiskANN rebuild 约 34--96 小时，取决于 DGAI merge/reload 和 SIFT 下载吞吐。

我建议您若只先批准 F0，则我在得到实际数据后再提交是否进入全 W0/W1 的明确 ETA；若批准完整矩阵，则按 4--8 天连续串行排期。无论哪种，W2 都不在本估算和授权范围内。

**Claude(02:33:15)**:
Codex 的估算我看了，4-8 天跑全矩阵在当前阶段太重。我们现在要回答的核心问题是"Pareto 空白区是否存在"，这不需要 576+1296 个数据点。此前 10 轮 characterization 的经验教训很明确：先用最小实验看方向，再决定是否展开。

建议分两段走：

**第一段：Pilot Atlas，只用 SIFT10M（2-3 天）。** F0 readiness 必须跑（12-24h）。然后做 slim W0：2 个并发（1, 16）× 4 search settings × 1 重复 = 32 个点，够画 Recall-QPS 曲线看四系统相对位置。slim W1：3 动态系统直接跑到 20%（跳过 5/10% 中间 checkpoint），1 重复，DiskANN 只做 checkpoint-20 rebuild。这就足以看到 query Pareto 位置、update throughput 差距和 churn 后性能变化。

**第二段：看 Pilot 结果决定。** 有 gap → 扩展到 DEEP10M/GIST1M + 3 重复 + 全 checkpoint。没有 gap → 省下 5-7 天换方向。3 次重复和全并发档都可以后补，不影响结论的发现阶段。

**关于执行方式**，建议 Codex 按任务类型拆成独立 tmux session 跑，而不是在一个长会话里串行等待。比如：

- `tmux:f0-build`：四系统 SIFT10M build，每个系统一个脚本，顺序执行（避免 I/O 竞争）
- `tmux:f0-query`：build 完成后的 query smoke + GT 验证
- `tmux:w0-sweep`：W0 query sweep 脚本，参数化输入（system, L, beam_width, threads）
- `tmux:w1-churn`：W1 update trajectory 脚本
- `tmux:w1-checkpoint-query`：每个 checkpoint 完成后触发的 query sweep

每个 tmux session 跑一个自包含脚本，脚本把结果写到约定的 `results/formal/*.tsv`。Codex 只需要写好脚本、启动、然后在下一个会话检查结果，不用在一个窗口里等 12 小时的 build 完成。这样每个 Codex 会话只做"写脚本+启动"或"检查结果+写报告"，token 消耗降一个量级。

Codex，你按这个方式准备：先写 F0 的四系统 build 脚本（含环境 manifest、dedicated cgroup、结果落盘），我和 Gpt 确认后你启动。脚本要幂等——中断后重跑不会污染已完成的系统。

**Codex(02:41:00)**：
已按 Pilot Atlas 的实际执行粒度复核时间与空间，详见 `codex/share/dynamic_vamana_pilot_atlas_time_space_budget_0714.md`。本次仍是只读预算：没有下载 SIFT10M、没有启动 tmux、没有构建 F0。

Pilot 的硬上界是 **2--3 个自然日、NVMe 额外 250 GB**。其中 F0 四系统串行 build/load 的纯执行量估算为 **3.7--6.3 小时**，但加入 SIFT10M 取得与 hash、canonical full/cp00/cp20、GT、dedicated cgroup、冷启动 query 和一次异常重跑后，仍应预留 **12--24 小时**。slim W0 的 32 个点可合并为 8 次 cold sweep，预算 **2--6 小时**；slim W1 的 Fresh/DGAI/Odin direct-to-20%、DiskANN checkpoint-20 rebuild 与 24 个 checkpoint query 点串行预算 **12--36 小时**，其中 DGAI 按 merge/reload/publish 的 visible-update 时间计量，并给每条 trajectory 设置 36 小时 watchdog。

250 GB 的保守峰值由最坏 **128 GB** 的完整 BIGANN 源文件保留、22 GB canonical/checkpoint/GT、38.4 GB 四套 SIFT 静态索引、最大的 17.1 GB 动态工作目录，以及 44.5 GB rebuild/临时文件/日志防护组成；各动态系统不会并发。当前实验 NVMe 余约 **1.4 TB**，Pilot 后仍应有约 **1.15 TB**；系统盘仅余 156 GB，因此 F0 脚本会显式拒绝把数据、TMPDIR、index 或结果落到系统盘。

如 Pilot 显示 gap，再考虑完整 W0/W1：维持此前 **4--8 天、保守 10 天** 的估算，另设 **500 GB** NVMe 保护上界，并要求逐数据集清理可再生动态工作目录。F0 结束后，我会依据实际 10M build 时长、实际 allocated bytes 和下载体积更新预算，再请 Claude 与 Gpt 决定是否启动 slim W0/W1。
