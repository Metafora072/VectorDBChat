# 动态场景深挖：SSD-Resident Graph ANN 的未解决问题与平行工作

**Date:** 2026-07-21 16:30
**Author:** Claude

---

## 1. "动态"远不只是 insert/delete

"动态"在向量搜索文献中至少有 **八个维度**，成熟度差异巨大：

| 维度 | 含义 | 研究成熟度 |
|------|------|-----------|
| **A. 向量增删** | 插入/删除向量，维护图连通性 | ★★★★ 最多 |
| **B. 图维护/压缩** | 图结构健康度、边质量、page 局部性退化修复 | ★★☆ 刚起步 |
| **C. 流式实时摄入** | 高速连续到达，立即可搜 | ★★☆ 多在内存 |
| **D. 分布漂移** | 数据/查询分布随时间变化 | ★★☆ 内存为主 |
| **E. 并发读写** | MVCC、快照隔离、无锁图操作 | ★☆☆ 几乎空白 |
| **F. 属性/元数据更新** | 标签/类别/范围变更 + filtered search 维护 | ★☆☆ overlay 为主 |
| **G. 索引 schema 演化** | 在线改量化/度数/索引类型 | ☆☆☆ 完全空白 |
| **H. 存储解耦/分层** | 向量与图拓扑解耦、disaggregated memory | ★★☆ 新兴 |

**所以"动态场景"不等于"动态更新/删除"。** 后者只是维度 A，但维度 B/C/E/F 都有实质性的未解决问题，且在 SSD 上特别突出。

---

## 2. 平行工作全景（2023–2026 核心论文）

### 维度 A：向量增删

| 论文 | 会议/年份 | 核心贡献 | SSD? |
|------|----------|---------|------|
| **SPFresh** | SOSP 2023 | LIRE 协议：IVF 分区的懒惰增量再平衡，仅重分配边界向量。10 亿规模 SSD，1% 日更新率下仅用 1% DRAM | ✅ |
| **FreshDiskANN** | arXiv 2021→2024 | FreshVamana：内存缓冲+SSD 主图，后台流式 merge。Tombstone 删除 | ✅ |
| **OdinANN** | FAST 2026 | Direct insert：直接插入 on-disk 索引而非缓冲+批量合并。消除搜索干扰的性能尖峰 | ✅ |
| **PipeANN** | FAST 2026 | io_uring 流水线异步 I/O。2025.7 后加入更新支持，与 OdinANN 集成 | ✅ |
| **DGAI** | arXiv 2025 | 向量与图拓扑解耦存储，三阶段查询+增量 page 级拓扑重排 | ✅ |
| **Greator** | VLDB 2026 | Topology-aware localized update：轻量图拓扑快速定位受影响节点，细粒度块减少 I/O 浪费。4.16x 加速 | ✅ |
| **Wolverine** | VLDB 2025 | Monotonic search path repair：修复删除后破坏的单调搜索路径。Wolverine++ 限制在 2-hop 内。11x 删除吞吐 | 内存 |
| **LSM-VEC** | arXiv 2025 | LSM-tree + HNSW 集成：out-of-place 更新，跨 LSM level 的分层图。50/50 插删下 88.4% recall vs SPFresh 75.5% | ✅ |
| **MicroNN** | SIGMOD Companion 2025 | 端侧 SSD 可更新向量数据库。Delta-store 暂存 + 周期性 IVF rebuild | ✅ |

### 维度 B：图维护/压缩

| 论文 | 会议/年份 | 核心贡献 |
|------|----------|---------|
| **Navigability-Signal-Triggered Repair** | IEEE Data Bulletin 2026 | 基于可导航性信号触发修复（而非固定周期）。probe-recall Spearman ρ~0.95 |
| **DecoupleVS / COMPASS** | arXiv 2026 | 向量数据与索引结构解耦。Elias-Fano 编码邻居 ID，存储减 58.7%。向量和拓扑可独立更新 |
| **Quake** | OSDI 2025 | 自适应 IVF：cost-model 驱动 split/merge/add-level/remove-level。按操作计数触发维护 |
| **CrackIVF** | VLDB 2025 | 数据库 cracking 理念用于向量搜索：索引从查询负载增量物化 |

### 维度 C：流式实时摄入

| 论文 | 会议/年份 | 核心贡献 | SSD? |
|------|----------|---------|------|
| **VStream** | VLDB 2025 | 分布式流式向量搜索。动态分区器适应分布变化。4 层存储（GPU/CPU/SSD/remote）| 多层 |
| **Slipstream** | arXiv 2026.6 | 流连续性利用：新点从上一次插入的候选开始搜索。自适应宽度控制 | 内存 |
| **UBIS** | arXiv 2026.1 | 解决高频更新下的并发冲突和不均衡分布。77% 准确率提升 | 内存 |
| **CANDOR-Bench** | SIGMOD 2026 | 连续 ANNS 基准：漂移建模、噪声注入、并发查询-更新。19 算法 × 12 数据集："没有单一算法全赢" | 基准 |

### 维度 D：分布漂移

| 论文 | 会议/年份 | 核心贡献 |
|------|----------|---------|
| **RoarGraph** | VLDB 2024 | 投影二部图桥接基础数据与历史查询，用于跨模态 OOD 搜索 |
| **Cross-Distribution Monotonic Graph** | SIGMOD 2026 | 高效鲁棒 OOD 搜索，单调性保证 |

### 维度 E：并发读写

| 论文 | 会议/年份 | 核心贡献 |
|------|----------|---------|
| **GaussDB-Vector** | VLDB 2025 | CONCURRENTLY 关键字：快照+增量 delta 更新。<50ms 延迟，>95% recall，10 亿规模 |
| **NAVIS** | arXiv 2025.5 | 并发搜索+更新：position-seeking 瓶颈识别，选择性向量读取，复用更新遍历信息。2.74x 插入吞吐 |

### 维度 F：属性/元数据更新

| 论文 | 会议/年份 | 核心贡献 |
|------|----------|---------|
| **EMA** | arXiv 2026.6 | Marker-based edge annotation：将属性邻域编码到图边上。支持动态更新 |
| **Dynamic Range-Filtering ANNS** | VLDB 2025 | 范围属性变更下的动态索引 |

---

## 3. 关键未解决问题（按学术潜力排序）

### ⭐ Gap 1：图索引没有写放大理论

LSM-tree 有完整的写放大/空间放大/读放大分析框架（Dostoevsky, SIGMOD 2018 等），指导了 20 年的存储系统设计。

**图索引完全没有对应物。**

- 更新一条边可能需要重写整个 4KB page（1 个邻居 ID 只有 ~8 bytes）
- 删除一个节点需要修复多跳邻居的入边，非局部效应
- DGAI 定性描述了这个问题（"耦合存储导致 excessive redundant vector reads and writes"），但没有定量模型
- **没有任何论文提供图索引更新的写放大比**，甚至没有统一的度量定义

**为什么重要**：这是存储系统（FAST）的核心语言。如果能建立图索引的 WA 分析框架，类似于 LSM-tree 的 Monkey/Dostoevsky，这就是一个 FAST/VLDB 级的理论+系统贡献。

### ⭐ Gap 2：图索引没有压缩/整理框架

LSM-tree 有 leveling/tiering/lazy-leveling 等可配置压缩策略。

**图索引的"压缩"是 ad hoc 的：**

- SPFresh/LIRE 只适用于 IVF，不适用于图索引
- LSM-VEC 把 LSM-tree 的压缩语义引入向量搜索，但只是初步尝试
- DGAI 的增量 page 级重排是第一步，但不是框架
- Wolverine 做 monotonic path repair，但只修边不重排
- **没有系统提供可配置的压缩策略**（何时压缩？压缩多少？局部还是全局？CPU/I/O 预算如何分配？）

**为什么重要**：compaction 是 SSD 存储系统的核心设计决策。如果能为图索引定义等价的 compaction 策略空间并分析 trade-off，这直接面向 FAST/OSDI。

### ⭐ Gap 3：SSD 上的局部性退化没有量化

SSD 图索引的核心优化是 page 局部性（DiskANN/PipeANN/PageANN 都做 graph layout optimization）。但：

- 插入/删除破坏局部性（新节点追加、删除留洞）
- **没有论文量化局部性退化速率**（多少次更新后 recall 下降 X%？page 利用率下降到什么程度？）
- DGAI 的增量 page 重排是唯一显式处理局部性退化的工作
- Navigability-signal（IEEE Data Bulletin 2026）是第一个提出图健康度代理指标的

**为什么重要**：如果能建立"更新量→局部性退化→recall/I/O 退化"的定量模型，就能指导何时触发 compaction、重排或重建。这是系统设计决策的基础。

### Gap 4：无 MVCC / 快照隔离

- **没有向量搜索系统实现真正的 MVCC**
- GaussDB-Vector 的 CONCURRENTLY 是 snapshot+delta，不是多版本
- 形式化的一致性保证（线性化、可串行化、最终一致性）在向量搜索文献中完全缺失
- 无锁图操作极难：图更新涉及多节点 CAS 链

### Gap 5：SSD 流式摄入几乎空白

- VStream、Slipstream、UBIS 都是内存或多层
- **没有系统专门优化 SSD-only 图索引的流式摄入**
- 摄入吞吐 vs 搜索延迟的 trade-off 没有理论建模

### Gap 6：删除为主/混合负载研究不足

- 大多数 benchmark 是插入为主
- CANDOR-Bench（SIGMOD 2026）是第一个系统性变化 churn 模式的基准
- SPFresh 在 50/50 插删下只有 75.5% recall，LSM-VEC 88.4%——两者都不理想
- 删除密集场景（如 GDPR 合规删除、内容过期）是真实需求但没有好的解决方案

### Gap 7：属性更新未融入图结构

- 当前方法把属性当 overlay（独立元数据存储）
- 属性变更不触发图拓扑调整
- EMA 的 marker-based edge annotation 是第一个尝试，但 2026 年 6 月刚出现

### Gap 8：分布漂移 + SSD 完全未探索

- RoarGraph 等 OOD 工作全在内存
- SSD 上的 OOD 问题更严重：重建代价更高、在线适应更难

---

## 4. 哪些 gap 最适合 PZ 的定位？

### PZ 的优势

- SSD graph ANN 基础设施（PipeANN + OdinANN + multi-NVMe）
- 清华存储系统背景
- 目标 FAST/VLDB/OSDI

### 匹配度分析

| Gap | FAST/VLDB/OSDI 契合度 | PZ 基础设施匹配 | 学术 novelty | 工程可行性 |
|-----|---------------------|----------------|-------------|-----------|
| **Gap 1: WA 理论** | ★★★★★ | ★★★★ (PipeANN+OdinANN 可测) | ★★★★★ (空白) | ★★★ (需要理论功底) |
| **Gap 2: Compaction 框架** | ★★★★★ | ★★★★★ (直接在 PipeANN 上做) | ★★★★ (LSM-VEC 开了头) | ★★★★ |
| **Gap 3: 局部性退化量化** | ★★★★ | ★★★★★ | ★★★★ | ★★★★★ |
| Gap 4: MVCC | ★★★ (偏 DB) | ★★★ | ★★★★ | ★★ (难) |
| Gap 5: SSD 流式 | ★★★★ | ★★★★ | ★★★ | ★★★★ |
| Gap 6: 删除密集 | ★★★ | ★★★★ | ★★★ | ★★★★ |
| Gap 7: 属性更新 | ★★★ | ★★★ | ★★★ | ★★★ |
| Gap 8: OOD+SSD | ★★★ | ★★★★ | ★★★★ | ★★ |

### 最有潜力的方向组合

**Gap 1 + Gap 2 + Gap 3 可以构成一个完整的系统论文：**

> "SSD-Resident Graph Index 的更新代价分析与自适应维护"
>
> - 贡献 1：图索引更新的写放大/空间放大/读放大分析模型
> - 贡献 2：基于代价模型的自适应 compaction/重排策略
> - 贡献 3：局部性退化的在线检测与修复触发
> - 贡献 4：在 PipeANN/OdinANN 上的端到端实现和评估

这个方向：
- 说的是存储系统（FAST 语言）
- 有理论贡献（WA 分析模型）
- 有系统贡献（自适应维护框架）
- 直接建立在 PZ 已有基础设施上
- 不依赖企业场景绑定
- 与 LSM-tree 文献形成类比（审稿人容易理解 framing）

---

## 5. 现有工作的缺陷总结

| 系统 | 关键缺陷 |
|------|---------|
| **SPFresh** | 仅 IVF，不适用图索引；50/50 插删 recall=75.5% |
| **FreshDiskANN** | merge 间隙搜索需探测两个区域；tombstone 积累导致空间膨胀 |
| **OdinANN** | direct insert 牺牲 page 局部性；无 compaction 策略 |
| **DGAI** | 增量重排不保证跟上高 churn；仍需解耦度量 |
| **Greator** | 仅限局部拓扑更新，不处理 page 局部性退化 |
| **Wolverine** | 仅修复搜索路径单调性，不处理局部性；内存工作 |
| **LSM-VEC** | 初步尝试，跨 level 搜索开销大；88.4% recall 仍不理想 |
| **VStream** | 分布式系统开销大，单机 SSD 场景不适用 |
| **CANDOR-Bench** | 仅基准，不提供解决方案 |
