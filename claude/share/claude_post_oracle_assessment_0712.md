# Oracle Kill 后的方向评估

日期：2026-07-12

## Oracle 结果的结构性含义

Write-set constrained relayout 被 Kill 不只是一个候选失败，它揭示了一个更深的约束：**单次 insert 的写集合与未来查询的读集合之间的交集天然很小。** DGAI 每次 insert 写 47–59 页 topology，OdinANN 写 6–8 页，但即使用完美未来知识在这些页上做最优 partition，收益也只有 ~1 页/事件。这说明 insert-path piggyback 在图索引上不可能构成有效的布局优化手段——与 database cracking 不同，graph index 的写路径由拓扑邻居决定，读路径由查询向量的几何邻域决定，二者的页级重合由局部性决定而非可控。

## 已穷尽的空间

从 M08 到 oracle，我们已经系统性地排除了以下角度：

| 角度 | Kill 原因 |
|---|---|
| Topology write amplification | 占比仅 6–10%，不构成主导成本 |
| Deferred topology write (coalescing) | Billion-scale ratio → 1.0 |
| Append-only adjacency versioning | Prior art 覆盖 + 写占比不足 |
| Coordinate acquisition optimization | DGAI 解耦布局特有 tradeoff，非共性 |
| Search residual (PQ/visited/heap) | 成本弥散，两数据集主项不同 |
| Maintenance debt observability | 跨系统维护机制不兼容，统一指标不可行 |
| Write-set piggyback relayout | Oracle 上界 ~1 页/事件，历史信号无预测力 |

这些 Kill 覆盖了 insert 成本的每一个一级和二级阶段，以及两个跨系统候选和一个具体系统假设。

## 当前困境的诊断

问题不是执行不够细致——恰恰相反，Codex 的执行质量极高，每一步都有严格闭合和对照。问题是 **动态驻盘图索引的 insert 路径本身不存在一个跨系统共同的、可通过单一系统设计显著改善的主导瓶颈**。成本是弥散的，多个小项各占 5–12%，且因数据集而异。

这对定位 FAST/VLDB 论文意味着：如果贡献叙事是"我们发现了 X 瓶颈并设计了解决 X 的系统"，这条路已经走不通——不存在这样的 X。

## 可能的重新定位

以下是我认为仍有可能的窄方向，按系统味道从强到弱排序。仅供 PZ 和 Gpt 讨论，不构成立项建议。

**A. 并发查询/更新的 SSD I/O 干扰。** NAVIS 报告并发更新导致搜索吞吐下降 27.89%。这不是 insert 路径内部的问题，而是 insert 和 query 共享 SSD 时的带宽/延迟干扰。这个问题对 PZ 的存储/体系结构背景适配度最高，且 NAVIS 的解法（入口图+缓存）不是 I/O 层面的，留有 SSD-aware I/O scheduling 的空间。风险：需要在至少两个系统上复现该干扰，且解法不能只是优先级队列或 I/O 隔离这类已知技术。

**B. 放弃 insert 路径，转向查询侧。** 所有系统在持续更新后查询性能如何变化？退化曲线的形状是否跨系统一致？如果退化在某个更新量之后急剧恶化，那个拐点是否可预测并作为维护触发？这比候选二窄——不追求统一指标，只追求一个可观测的退化现象。风险：与候选二的 Kill 理由部分重叠。

**C. 完全换赛道。** 如果 PZ 的核心优势是存储/体系结构而非算法，考虑 vector search 的其他存储密集环节：大规模向量构建/索引的 SSD 优化、PQ/OPQ 编码与 SSD page 对齐、多级存储（DRAM + SSD + CXL）下的图索引分层。这些方向与当前积累的 DGAI/OdinANN 基础设施不直接相关，需要重新投入。

## 建议

PZ 应在 A/B/C 或其他方向中选择一个值得花一周时间做最小验证的方向。我可以在选定后对 novelty 和系统味道做判断。不建议在当前 insert 路径上继续投入。
