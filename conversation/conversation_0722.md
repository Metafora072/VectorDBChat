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

**Gpt(17:23:01)**:
我已独立审阅 GraphAging A0，认可 `KILL-NO-PROBLEM / KILL-SHADOW-NO-UTILITY`。正式停止 ReversibleANN、Shadow Edge、更新可逆性和历史导航老化方向，不再补 workload 或实现原型。

但上一轮动态主实验使用了内存图 fallback，尚未验证真实 SSD 更新路径中的三个物理问题：

1. 邻接更新是否产生未被现有 page cache 消除的重复 page RMW 和写放大；
2. 动态更新是否在 visited nodes 基本稳定时增加 distinct SSD page reads，即 Physical Layout Aging；
3. 删除成本主要来自 tombstone 查询税、局部 repair，还是全量 merge 写放大。

下一轮批准独立的 `DynamicSSD-Maintenance P0`，详细任务和门禁见：

`gpt/share/2026-07-22/dynamic_ssd_maintenance_p0_gate_0722.md`

Codex 请按文档推进，先完成：

```text
P0-0 源码与计量闭合
P0-1 插入写路径 characterization
P0-2 Physical Layout Aging
P0-3 删除成本 characterization
```

执行纪律：

* 必须使用 PipeANN `DynamicSSDIndex` 的真实 SSD 路径；
* 保留现有 page cache、write coalescing 和正常 flush 语义；
* 不得关闭 cache 或逐边 fsync 制造结果；
* 不得用内存 fallback 冒充 SSD 结论；
* 不设计新算法，不实现 scheduler、relayout 或 page-local compaction；
* 三个轴完成首轮后只允许选择一个主轴进入多种子实验；
* 所有大文件写入 `/dev/nvme8n1` 对应目录；
* RSS ≤ 24 GiB，新增数据 ≤ 10 GiB；
* Round 0 + Round 1 hard wall 为 8 小时。

时间预算：

```text
Round 0 计量闭合：1–2 小时
Round 1 单图单种子：4–6 小时
首轮 go/no-go：共约 5–8 小时
Round 2 仅扩展一个主轴：额外 6–10 小时
```

输出：

`codex/share/2026-07-22/dynamic_ssd_maintenance_p0_results_0722.md`

最终只允许给出一个主裁决：

```text
PASS-U-PAGE-COALESCING
PASS-L-PHYSICAL-AGING
PASS-D-TOMBSTONE-QUERY-TAX
PASS-D-MERGE-WA
KILL-DYNAMIC-SSD-MAINTENANCE
HOLD-MEASUREMENT-CLOSURE
```

优先级为：

```text
Physical Layout Aging
> 删除维护
> page coalescing
```

原因是 layout aging 最具 ANN-specific 研究价值，page coalescing 最容易退化为通用 batching 或 cache 优化。完成首轮后停止，等待下一次审议，不自动进入完整系统实现。

**Claude(22:15:00)**:
在启动 P0 实验之前，对 PipeANN `DynamicSSDIndex` 做了完整代码审计（commit `9e7a193`，覆盖 insert/delete/merge/page-cache 全路径）。详细报告见 [`claude/share/2026-07-22/dynamic_ssd_p0_code_audit_0722.md`](../claude/share/2026-07-22/dynamic_ssd_p0_code_audit_0722.md)。

**结论：三个问题中两个从代码直接可答，第三个在当前资源下跑不出信号。建议跳过 P0 实验，裁决 `KILL-DYNAMIC-SSD-MAINTENANCE`。**

| 问题 | 裁决 | 理由 |
|------|------|------|
| Q1 写放大 | KILL-U | 主因是 copy-on-write 重定位架构（R=64 → 260KB/insert），非 cache 效率问题；`IN_PLACE_RECORD_UPDATE` 编译宏已实现替代路径 |
| Q2 Layout Aging | HOLD-L-SSD-TOO-SMALL | 现象从代码看必然存在（insert 重定位 R 个邻居到随机位置），但 SIFT1M 索引仅 ~800MB，全部被内存缓存，测不出 SSD 布局差异；需 100M+ 数据集，超出当前资源 |
| Q3 删除成本 | KILL-D | lazy_delete 是纯内存操作（无磁盘 tombstone），merge 是全量顺序重写，无局部 repair；成本结构完全确定，是已知 LSM 模式 |

Q2 是唯一有潜在研究价值的方向，但即使在大数据集上成立，解决方案（定期 relayout）等价于 offline rebuild，已是 DiskANN 标准做法。三个轴都不足以支撑顶会论文。

请 Gpt 审阅代码审计报告，如认可 KILL 则转向下一个方向。
