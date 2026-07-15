# Architecture Idea Council Round 2：Codex 对抗审查

日期：2026-07-12

## 执行结论

本轮只做 prior-art、代码与机制闭环审查，没有运行实验。裁决为：

| 候选 | 裁决 | Novelty | 结论 |
|---|---|---:|---|
| A：跨 embedding 版本 warm-start 图重建 | **REVISE** | 5/10 | 问题真实，尚未发现完全同题系统；当前“检测失效边并局部 re-prune”不闭环，只值得先做真实 model-pair 的 finding gate |
| B：filtered search 标签感知物理布局 | **KILL** | 3/10 | GateANN、PipeANN-Filter 已直接解决同一 SSD I/O 问题；当前布局机制还被 page 粒度、任意谓词和 partition baseline 三重反证 |
| C：有限 DRAM 外存图构建 | **KILL** | 1/10 | DiskANN 官方 builder 已实现 RAM-budgeted partition/build/merge；PiPNN 又直接覆盖 bounded-memory 快速图构建 |

没有候选达到 `PROVISIONAL`，不进入 DGAI 实验。

## 核心 novelty claims

1. 旧 ANN 图能否作为新 embedding 空间的初始拓扑，并以显著低于 fresh build 的 I/O 修复到同等 recall。
2. 将 metadata label 与 graph proximity 联合编码进 SSD 物理布局，能否解决 filtered graph search 的无效 I/O。
3. 分区本地建图和跨分区连边，能否在有限 DRAM 下完成十亿级 Vamana 构建。

## A：跨 embedding 版本 warm-start 图重建

### Prior art 边界

- [Drift-Adapter（EMNLP 2025）](https://aclanthology.org/2025.emnlp-main.805/)明确确认 embedding model upgrade 会触发 corpus re-encoding 与 ANN rebuild，并用 paired old/new embeddings 学习 query-side 映射。它没有修复新坐标上的图，因此没有直接覆盖 A。
- NN-Descent 本身允许从已有邻居图开始迭代 refinement；[Dynamic Exploration Graph](https://arxiv.org/abs/2307.10479)也已有 continuous edge replacement/refinement。把旧图作为初始化并不是独立的新算法贡献。
- [Topology-Aware Localized Update](https://arxiv.org/abs/2503.00402)已覆盖 SSD 图上的 affected-node detection、局部页面更新与轻量 neighbor repair，但场景是 insert/delete，不是所有节点坐标同时变化。

截至本轮检索，没有找到“同一 corpus 跨 embedding model version，复用旧 Vamana topology 并原地修复”的直接同题系统，因此问题和实验 finding 仍有空间；但 Claude 当前机制不足以放行。

### 机制不闭环

1. **检测成本没有降到 `O(δR)`。** 要知道哪些节点失效，至少要用新坐标扫描旧图的 `O(NR)` 条边；候选把 repair work 写成 `O(δR)`，遗漏了全图 detection cost。
2. **只检查旧边无法发现新近邻。** 坐标变化不仅使旧边失效，也会产生旧邻域中不存在的新候选。对原邻接表 re-prune 只能删/重排已有候选，不能保证恢复 fresh graph 的 navigability 或 recall。
3. **edge-wise violation 不是质量证书。** RobustPrune 是候选集级操作；“旧边仍满足局部条件”不能推出不存在遗漏边，也不能推出全局 greedy path 仍有效。
4. **方法 novelty 偏弱。** 若最终实现只是 old-graph-seeded NN-Descent/continuous refinement，审稿人会把它视为已知构建器在 model migration 场景的应用。可能新的是“不同真实 model pair 的 topology reuse window”这一 empirical finding，而不是算法。

### 允许的下一步

只保留一个不改 DGAI 的 **A0 finding gate**：复用 Drift-Adapter 的真实 MTEB/CLIP model-pair 设置，测 `(i)` exact kNN overlap、`(ii)` old graph/no repair recall、`(iii)` old-graph-seeded refinement 相对 random/fresh initialization 的更新轮数、距离计算数和总工作量。必须同时对比：old graph no repair、seeded NN-Descent/DEG、fresh DiskANN/HAKES rebuild、Drift-Adapter。

只有多个真实 model pair 都出现稳定的中间复用窗口，并且 seeded refinement 的**总成本（含检测与新候选发现）**显著下降，才重新提出系统机制。届时剩余 delta 必须包含：低于全图扫描的 drift detector、能引入新候选的 bounded-I/O repair，以及 repair/serve 并发一致性协议。当前裁决仍为 **REVISE**，不是 `PROVISIONAL`。

## B：filtered search 标签感知物理布局

### 直接同题工作

- [GateANN（2026）](https://arxiv.org/abs/2603.21466)研究的正是 SSD graph filtered search 的无效 I/O。它在发 I/O 前检查谓词，让不匹配节点仅靠内存中的邻接与近似距离继续 graph tunneling，不读取 SSD full vector；报告 SSD reads 最多下降 10×、吞吐最多提高 7.6×，且无需改图、支持任意谓词。
- [PipeANN-Filter（2026）](https://arxiv.org/abs/2605.17992)也直接面向 SSD filtered vector search，用 speculative filtering 与概率结构减少 attribute I/O。
- Filtered-DiskANN 与 [ACORN](https://arxiv.org/abs/2403.04871)分别提供 label-aware graph 和 predicate-agnostic traversal；[Milvus partition key isolation](https://milvus.io/docs/use-partition-key.md)则已实现按 key 分组、每组独立索引并限定搜索范围。
- [DiskANN++](https://arxiv.org/abs/2310.00402)与 MARGO 已覆盖磁盘图物理重排，但没有 filter 维度。这只说明“filter-aware physical layout”在字面机制上可能不同，不代表 filtered SSD I/O 仍是未解决问题。

### Kill 原因

1. **同一问题已有更强且更通用的解。** GateANN 对不匹配节点直接做到零 SSD vector read；Label-Graph Co-Layout 若不能在 GateANN 之上继续降低 I/O，就只是替代机制，不构成新的未解问题。
2. **物理布局和谓词语义不匹配。** 一个静态顺序无法同时聚集多标签、范围谓词、合取/析取谓词以及随时间变化的 workload。为 dominant label 优化会伤害其他谓词，动态维护又退化成持续 relayout。
3. **page-hit ratio 指标不适用于当前记录布局。** DiskANN/PipeANN 常见路径按 node record/4 KiB sector 读取。只重排 node ID 不会让一次 node read 自动包含更多 matching candidates；若改成 multi-node page-node，候选已经变成 PageANN/布局 co-design，且需重新证明导航语义。
4. **简单 baseline 已覆盖目标场景。** 单 label/tenant equality filter 可由 per-label graph 或 Milvus partition-key isolation 直接避免读取其他 label。2026 的系统评测还显示低选择性下 partition-based IVF 可能优于 HNSW，这必须先于统一图新机制。
5. **原计划的 30×+ 是选择性倒数推算，不是已验证的系统测量。** 访问无效节点的比例、SSD reads 与 page utilization 不能直接用 `1/selectivity` 等同。

若未来重开，唯一可辩护的问题应改成“GateANN 后 residual”：在 arbitrary predicates、相同 DRAM 预算下，filter-aware multi-node page layout 是否还能相对 GateANN/PipeANN-Filter 获得稳定端到端收益。Claude 当前候选没有这个 delta，因此 **KILL，不做 3–4 天实验**。

## C：有限 DRAM 外存图构建

### 一手代码反证

候选的基本前提与现有 DiskANN 实现不符：

- 本地官方 DiskANN 文档 `VectorDB/repos/DiskANN/workflows/SSD_index.md:16` 明确提供 `--build_DRAM_budget`；当单次构建放不下时，用 divide-and-conquer 让 sub-graph 适配 RAM，再 overlay 成总图，文档估计最多约 1.5× 慢。
- `VectorDB/repos/DiskANN/src/partition.cpp:523` 的 `partition_with_ram_budget()` 会估算最大 shard RAM，持续增加分区数直到满足预算，并生成 overlapping cluster membership。
- `VectorDB/repos/DiskANN/src/disk_utils.cpp:690` 先按 RAM budget 分区，`:698` 起逐 shard 构建 Vamana，`:758` 再 `merge_shards()` 形成总图。

这已经是 Claude 所提“分区本地构建 + 跨分区连边”的工程化基线，而不是只做 serving 的 PageANN/AiSAQ。

此外，[PiPNN（2026）](https://arxiv.org/abs/2602.21247)用 overlapping sub-problems、bulk distance comparisons 和 bounded-memory HashPrune 构建高质量 ANN 图，报告相对 Vamana 最多 11.6× build speedup，并在单台多核机器上完成 billion-scale build。ScaDANN 2025 也明确以减少 DiskANN overlapping partitions 的构建冗余为目标。

### Kill 原因

问题并非“PageANN/HAKES 是否覆盖 build phase”，而是 Claude 漏掉了 DiskANN 自身已有的 RAM-budget build path；其提议与官方实现同构，又被 PiPNN 在速度和有界内存上进一步推进。除非提出 DiskANN/PiPNN 都不能满足的新约束，否则没有剩余 delta。裁决为 **KILL**，不运行 SIFT-1M 模拟实验。

## 独立复核与最终建议

独立审稿代理得到同样结论：`A=REVISE, B=KILL, C=KILL`。本轮应提交给 Gpt 做统一裁决，不直接推进实验。

A 若继续，也应被表述为“先验证 topology reuse window 是否普遍存在”，而不是预设 warm-start repair 已是系统贡献。B、C 进入 Kill 清单；后续 Architecture Idea Council 必须先把 GateANN、PipeANN-Filter、DiskANN RAM-budget builder 与 PiPNN 纳入基础文献表，避免再次从已被解决的问题出发。
