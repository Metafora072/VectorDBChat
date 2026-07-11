# Claude 当前立场

日期：2026-07-11，最后更新 21:43

## 已确认的 KILL

- **M08 Stable-ID Refresh**：删除占比 5%，stale edge 不自然剪枝。KILL 证据充分。
- **Dir 1 Deferred Topology Writes**：均匀模型验证后，billion-scale coalescing ratio → 1.0。KILL 证据充分。
- **Append-only 邻接表版本化**（早期讨论中的方向 A）：topology random write 仅占 insert 时间 6–10%。不构成主导成本，且 FreshDiskANN/LSM-VEC/OdinANN 已覆盖 out-of-place 主要形态。暂不推进。
- **Coordinate acquisition/rerank 子阶段优化**：900K stable 下无子阶段超过 6%，成本弥散。不构成明确机制靶点。
- **Application-cold io_submit 双峰**：非平稳、CI 不收敛、属 DGAI/Linux AIO 实现诊断。不生成系统 Idea。

## 当前判断

子阶段归因已完成。900K stable 下没有单一子阶段超过 6%，我的介入条件未触发。Gpt 已启动全局重排账作为最后一步。

**预判**：coordinate acquisition/rerank 在一级仍会超 30%（pilot 已测得 37–50%），但这很可能是 DGAI 解耦 topology/coordinate 布局的结构性代价，不是驻盘图索引共性瓶颈。DiskANN 的 co-located 布局不需要额外 coordinate I/O。即使全局账确认此为唯一 30%+ 阶段，我倾向于不以此开启新研究方向——它指向的是 co-located vs. decoupled 的已知 tradeoff，两侧已分别被 DiskANN 和 DGAI 代表。

**如果全局账没有其他 30%+ 共同主导阶段，建议关闭 DGAI 单系统 profiling。**

## 下次介入条件

全局重排账发布后，由 PZ 和 Gpt 决定是否继续或重新选题。如果需要我对新方向做高层判断，届时介入。

## 不会介入的事项

- Instrumentation 细节、数据集配置、R 矩阵参数、日常执行反馈
