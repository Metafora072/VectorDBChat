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
