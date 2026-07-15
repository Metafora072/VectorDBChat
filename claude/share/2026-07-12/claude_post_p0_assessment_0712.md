# P0 Kill 后的方向评估（更新）

日期：2026-07-12，替代 claude_post_oracle_assessment_0712.md

## 候选 A Kill 的含义

我在 oracle 后建议优先考虑 A（并发 query/update SSD I/O 干扰），该建议已被 P0 实验否定。DGAI 在所有 mixed 点的 query p99 变化仅 −3.0%～+1.7%，没有退化趋势；OdinANN 有严重 tail stall，但设备延迟不随之变化、不随 update load 单调增长、p50/throughput/recall 不受影响。两个系统没有共同的 service curve 方向，P0 Kill 条件直接满足。

DGAI 无干扰的原因值得记录：解耦布局下，topology 更新只触及少量 4KB 页，相对 query 的高 IOPS（~590K read IOPS）是噪声级别。这反过来说明 DGAI 的解耦设计确实消除了 update/query 的 I/O 竞争——但这是 DGAI 论文已经 claim 的贡献，不是新发现。

## 已穷尽的空间（完整更新）

| 角度 | Kill 原因 |
|---|---|
| Topology write amplification | 占比仅 6–10% |
| Deferred topology write (coalescing) | Billion-scale ratio → 1.0 |
| Append-only adjacency versioning | Prior art 覆盖 + 写占比不足 |
| Coordinate acquisition optimization | DGAI 解耦布局特有 tradeoff |
| Search residual (PQ/visited/heap) | 成本弥散，主项因数据集而异 |
| 维护债务观测 | 跨系统维护机制不兼容 |
| Write-set piggyback relayout | Oracle 上界 ~1 页/事件 |
| 并发 query/update SSD 干扰 | 无跨系统共同退化模式 |

## 诚实评估

八个方向全部 Kill，其中两个是我直接建议的（候选二和候选 A）。Gpt 对我的"piggyback 根本不可行"这一过强表述的纠正也是对的。

这些 Kill 的共同信号是：**动态驻盘图索引领域的近期工作（6 个系统）已经高度覆盖了可行设计空间。** 不是我们的执行有问题——Codex 的实验质量极高——而是剩余空间确实很窄。

## 剩余选项

**B（查询侧退化曲线）**：与候选二重叠风险仍在。但有一个更窄的切入点：不追求通用维护指标，而是测量"持续更新 N 次后，recall@10 和 search IOPS 的退化速率是否跨系统可预测"。如果退化曲线在不同系统上形状一致且可建模，可能有分析贡献（但分析贡献在 FAST/VLDB 通常不够）。

**C（换赛道）**：考虑到 PZ 的存储/体系结构背景，可能的方向包括：
- 多级存储下的向量索引（DRAM/CXL/SSD 分层，决定什么数据放在什么层）
- 大规模图索引构建的 I/O 优化（构建比查询和更新更 I/O 密集，且现有工作较少）
- 非图结构的驻盘向量索引（IVF/cluster-based 在 SSD 上的行为可能有不同的优化空间）
- 向量搜索以外的存储系统问题

**D（接受领域饱和，寻找全新研究问题）**：最诚实的选项。当前积累的 DGAI/OdinANN 基础设施和阴性结果本身有价值——它们提供了对"这个问题为什么难"的深入理解——但强行从中挤出论文可能比重新选题更昂贵。

## 建议

PZ 应该做一个明确的战略决定：继续在动态驻盘 ANN 领域投入（选 B），还是利用已有的领域理解转向相邻但未饱和的问题（选 C/D）。这个决定不适合由实验门禁驱动，而需要 PZ 基于自己的研究直觉和投稿时间线做判断。
