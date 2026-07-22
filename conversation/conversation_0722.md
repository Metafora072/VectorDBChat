**PZ(01:30:00)**:
Gpt 提出了 ReversibleANN / GraphAging 方向，见 `gpt/share/2026-07-22/ReversibleANN_GraphAging_Idea_Report.md`。Claude 评审下值不值得深挖。如果 PASS，在 0722 对话中推进，让 Codex 做 A0 验证。

**Claude(01:48:07)**:
评审完成，裁决 **PASS-A0**。详细评审见 [`claude/share/2026-07-22/graphaging_idea_review_0722.md`](../claude/share/2026-07-22/graphaging_idea_review_0722.md)。

**核心判断：这是本轮讨论中最好的 idea。** 三个 novelty 支点：

1. **新现象（History-Induced Graph Aging）**：相同终态向量集合，不同更新历史→不同图结构→不同查询性能。OdinANN 确认 recall 随 insert 下降 15pp，但没有论文做过"同终态不同历史"的控制实验。

2. **新机制（Shadow Edge / Edge-Displacement Dependency）**：保存 pruning provenance（哪条边被哪个 insert 淘汰），删除时用 shadow candidates 代替 Wolverine 式重新搜索。文献中无先例。

3. **新存储设计（Semi-Coupled Base+Delta）**：保留读路径的 coupled 局部性，将频繁变化的拓扑增量从基础记录分离。不同于 DGAI/DecoupleVS 的完全解耦。

**PASS 条件：**
- A0 必须包含 IP-DiskANN（arXiv 2502.13826）作为 baseline——如果 IP-DiskANN 在同终态下无明显老化，立即 KILL
- Shadow storage 增长率必须在 A0 量化
- 不要过早实现 semi-coupled 存储——A0 只做 instrumentation + oracle shadow replay
- 最大风险：IP-DiskANN 可能已通过更好的 prune 策略使老化不可观测

**给 Codex 的 A0 任务已下达。** A0 分四个子实验：
- A0-1：插入—删除可逆循环（1/10/100/1000 轮）
- A0-2：同终态不同历史（7 种 update pattern）
- A0-3：耦合式更新 I/O 分层账本
- A0-4：Oracle Shadow Replay（shadow vs search-based repair）

KILL gates 与 Gpt 报告一致：IP-DiskANN 无老化、shadow 无价值、存储膨胀不可控任一成立即 KILL。

**Claude(02:05:30)**:
Codex A0 任务已下达并启动（task ID: `task-mruyanw0-xu9gq3`）。工作目录 `codex/work/2026-07-22/graph_aging_a0/`，结果将输出至 `codex/share/2026-07-22/graph_aging_a0_results_0722.md`。

任务优先级：A0-1（insert-delete 可逆循环）和 A0-2（同终态不同历史）先行，验证现象是否真实。A0-3/A0-4 在现象确认后再做。如 PipeANN 动态 SSD 路径不稳定，允许先用内存 Index 类验证。

**Claude(02:25:00)**:
Codex 上一轮完成了代码编写和编译，但没来得及执行实验。已验证所有前置条件就绪：

- Binary 可用（`build-a0/tests/graph_aging_a0`，27MB，支持 build/a01/path2/path3 四种模式）
- SIFT1M 数据就绪（`full_1m.bin` 1M×128d, `query.bin` 10K×128d, `gt_cp00` 10K×100 NN）
- GT 格式已验证兼容 PipeANN `load_truthset`

详细执行计划见 [`claude/share/2026-07-22/graph_aging_a0_execution_plan_0722.md`](../claude/share/2026-07-22/graph_aging_a0_execution_plan_0722.md)。

**执行分两轮：**
- Round 1（1-2h）：建 5 个 G0 baseline + 1 组 A0-1 pilot + A0-2 path2 → 初步判断
- Round 2（4-9h）：A0-1 full（5 build seeds × 3 update seeds × 100 cycles）→ 统计显著性

**KILL gates 不变：** recall drop < 1pp 且 < build-seed variance → KILL-NO-PROBLEM。

**Codex(03:24:09)**:
A0 已完成并按预注册 gate 提前终止，裁决 **KILL-NO-PROBLEM / KILL-SHADOW-NO-UTILITY**。完整报告见 [`codex/share/2026-07-22/graph_aging_a0_results_0722.md`](../codex/share/2026-07-22/graph_aging_a0_results_0722.md)。

核心结果：
- 官方 DiskANN3 显式 IP-DiskANN 删除路径，100 轮同终态循环后 Recall@10 −0.006 pp，mean comparisons +0.414%；没有明显 aging。
- PipeANN/FreshDiskANN-style 100 轮后 Recall −0.01 pp，comparisons +0.93%；结构 Jaccard 下降但查询质量稳定。
- A0-2 原先 +9.68% comparisons 是 degree inflation 混杂；统一裁剪为 64M edges 后差异 −0.024%。
- Oracle Shadow 可恢复结构，但 A0-2 上 Recall 仅 +0.06 pp、comparisons 反而 +2.98%，候选存储 201–302 MB。

因此未继续七历史 × 多种子的 Round 2、物理 block I/O tracing 或 semi-coupled 系统实现。该早停严格遵循 Claude 设定的“IP-DiskANN 无明显老化立即 KILL”。所有代码、runbook、原始 JSON、tracker 和机器可读 summary 均保留在 `codex/work/2026-07-22/graph_aging_a0/` 原目录结构内。

**Codex(16:39:36)**:
A0 的完整结果、复现脚本、原始 JSON、tracker 与机器可读汇总已经整理在原项目结构中，主报告仍为 [`codex/share/2026-07-22/graph_aging_a0_results_0722.md`](../codex/share/2026-07-22/graph_aging_a0_results_0722.md)。请 Gpt 独立审阅实验口径、KILL gate 是否成立，以及 Oracle Shadow Replay 能否支持 `KILL-SHADOW-NO-UTILITY`；本消息不预置 Gpt 结论。
