# Claude 当前立场

日期：2026-07-11，最后更新 15:27

## 已确认的 KILL

- **M08 Stable-ID Refresh**：删除占比 5%，stale edge 不自然剪枝。KILL 证据充分。
- **Dir 1 Deferred Topology Writes**：均匀模型验证后，billion-scale coalescing ratio → 1.0。KILL 证据充分。
- **Append-only 邻接表版本化**：topology random write 仅占 insert 时间 6–10%，且 FreshDiskANN/LSM-VEC/OdinANN 已覆盖 out-of-place 主要形态。
- **Coordinate acquisition/rerank 子阶段优化**：900K stable 下无子阶段超过 6%，成本弥散。
- **Application-cold io_submit 双峰**：非平稳、CI 不收敛、属 DGAI/Linux AIO 实现诊断。
- **DGAI 单系统 profiling 整体关闭**：全局重排账确认 search residual 是唯一 30%+ 宽阶段，但直接分解后成本分散至多个小项（最大 12.34%），且两套数据主项不同。没有共同 30% 直接测量子阶段。
- **跨系统候选二（维护债务观测）**：KILL。成功概率极低——维护机制和债务载体跨系统不兼容，统一指标极大概率退化为已有触发器打包或 ML 组合，不具备系统味道。

## 保留但未立项

- **跨系统候选一（局部性迁移）**：方向不 Kill，但当前不满足立项条件。测量本身不能做论文核心贡献；需要一个从测量到系统设计的桥梁假设。三种可能的测量结果（高重合/低重合/工作负载相关）中，只有最后一种有研究价值，且必须同时提出自适应机制。

## 方向性提示

事实地图暴露的最一致跨系统事实：所有 direct-insert 系统在持续更新后面临物理局部性退化，且所有恢复手段（merge/reorder/delete-merge/page-split）都是重量级操作，竞争前台查询的 SSD 带宽。如果存在轻量级、可与查询/更新 I/O 交错的增量局部性维护机制，这有可能构成 FAST 级贡献。但这只是提示，不是已验证假设。

## 下次介入条件

PZ 和 Gpt 在上述方向（或其他新方向）形成了具体系统假设，并需要 novelty/可行性判断时。日常证伪实验和代码审计不需要我参与。

## 不会介入的事项

- Instrumentation 细节、数据集配置、R 矩阵参数、日常执行反馈
- Codex 的跨系统代码审计与 trace 采集
