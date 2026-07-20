# Filtered ANN on SSD: 深度调研与差异化角度分析

**Date:** 2026-07-20
**Author:** Claude

---

## 一、全景：Filtered ANN 研究谱系

### 1.1 三个维度的交叉

| | 静态索引 | 动态更新 |
|---|---------|---------|
| **内存** | ACORN, FusedANN, JAG, SIEVE, Curator, PathSeer, FAVOR, NaviX, RNSG, DIGRA, ... (15+ 篇) | EMA (2026), DIGRA (2025), DSG — 仅 3 篇 |
| **SSD** | Filtered-DiskANN (2023), GateANN (2026), PipeANN-Filter (2026) — 3 篇 | **零** |

**关键空白：Dynamic Filtered ANN on SSD = 0 篇。**

这是 {动态更新} × {过滤搜索} × {SSD} 的三维交叉空白。

---

## 二、SSD 上的 3 篇现有工作详细分析

### 2.1 Filtered-DiskANN (WWW 2023, Microsoft)

**机制：**
- 在 Vamana 构建时将 label 信息融入图结构：同 label 节点获得更多边
- 两种模式：streaming（增量构建）和 batch
- 支持从 SSD 查询，但 **只支持 label equality filter**

**局限：**
- 不支持 range filter、arbitrary predicate
- 构建成本高（filter-aware graph 需要更大的 degree）
- 静态索引，不支持高效的 insert/delete
- SSD I/O 优化有限（继承 DiskANN 的基本管线）

### 2.2 GateANN (arXiv 2603.21466, 2026, 韩国成信女子大学)

**机制：**
- 核心创新：**Graph Tunneling** — 在发起 SSD I/O 之前先检查 filter predicate
- 将邻居列表和 PQ 近似距离保持在内存中
- 不匹配的节点通过内存中的邻接信息"隧穿"过去，不触发 SSD 读取
- 支持 **任意谓词**（equality, range, multi-label, conjunction）

**性能：**
- 90% recall 下：比 PipeANN 快 1.9×（单线程）、7.6×（32 线程吞吐）
- 比 DiskANN 快 13×
- SSD I/O 减少最多 10×

**局限：**
- **内存开销巨大**：100M 向量需要 ~63 GB 内存（存邻居列表 + PQ 码）
- 不支持动态更新
- PQ 近似距离用于路由决策，存在精度损失
- 关键发现："瓶颈不是 SSD I/O 速度，而是每次 I/O 触发的 CPU 处理链"

### 2.3 PipeANN-Filter (arXiv 2605.17992, 2026, 清华)

**机制：**
- 基于 PipeANN (OSDI 2025) 扩展
- 两层数据结构：
  - Label filter：内存 Bloom filter + SSD 倒排索引
  - Range filter：内存量化值 + SSD 排序索引
- 基于选择率估计计算"等效"搜索参数
- 流水线化 I/O 与计算重叠

**性能：**
- 比 Milvus 延迟降低 89.5%，吞吐高 32.3×
- 比 Filtered-DiskANN 吞吐高 4.35×

**局限：**
- 仍需要内存中的 Bloom filter 和量化值
- 不支持动态更新
- 继承 PipeANN 的管线架构，扩展灵活性有限

---

## 三、内存方案中值得关注的技术

### 3.1 与 SSD 结合有潜力的机制

| 论文 | 核心机制 | SSD 适配潜力 |
|------|---------|-------------|
| **JAG** (CMU/Meta, 2026) | 属性距离 + 过滤距离 → 联合图。将离散 filter 转为连续导航信号 | 高。避免图中的"死胡同"，减少 SSD 上的无效 I/O |
| **SIEVE** (VLDB 2025) | 多索引集合，workload-aware 选择 | 中。SSD 上维护多索引的空间开销大，但按选择率路由的思想可以减少 I/O |
| **Curator** (SIGMOD 2026) | 层次分区，低选择率专用索引 | 高。分区 + SSD 天然匹配（不同分区存不同区域）|
| **EMA** (2026) | Marker：边上的紧凑谓词摘要（零假阴性）。动态更新支持 | **极高**。Marker 机制不需要全局重建，适合 SSD 增量更新 |
| **FusedANN** (华为, 2025) | 属性-向量融合到统一空间，Lagrangian 松弛 | 中。需要维度扩展，可能增加 SSD I/O |

### 3.2 EMA 特别值得关注

EMA 是唯一同时支持 **通用属性过滤 + 动态更新** 的方案。核心机制：

- **Marker**：附加在图边上的紧凑谓词摘要。保证零假阴性：如果一个节点满足谓词，它一定可以通过 Marker 被发现
- **Marker-augmented joint search**：搜索时同时利用几何距离和 Marker 信息
- **Bounded edge recovery**：动态更新时有界的边修复
- 支持 multi-predicate、mixed numerical/categorical

**但 EMA 是纯内存方案**。将 Marker 机制适配到 SSD 是一个潜在的研究方向。

---

## 四、差异化角度分析

### 角度 A：Dynamic Filtered ANN on SSD ⭐⭐⭐⭐⭐

**核心主张：** 当向量索引和元数据都在 SSD 上时，如何支持持续的 insert/delete/metadata-update 同时保持高效的过滤搜索？

**为什么故事成立：**
- 生产 RAG/推荐系统需要同时满足两个需求：过滤搜索 + 持续更新
- 现有 3 篇 SSD filtered ANN 全是 static build-then-query
- 现有 5+ 篇 SSD dynamic ANN (FreshDiskANN, IP-DiskANN, Greator, DGAI, OdinANN) 全不支持 filter
- 这两个方向完全独立发展，从未被结合
- 动态更新对 filtered graph 的影响比无 filter 时更复杂：删除一个节点可能断开某个 label 子图的连通性

**技术挑战（非 trivial）：**
1. 删除节点时，如何保持 filter-subgraph 的可导航性？（不同于普通图修复）
2. 元数据更新（商品价格变化、文档分类变化）如何增量反映在索引中？
3. SSD 上的 filter metadata 如何在动态场景下高效更新？
4. 如何估计动态变化后的选择率，以选择正确的搜索策略？

**可行的架构思路（不提系统名称）：**
- 将 filter metadata 与图结构解耦存储
- 使用类似 Marker/边摘要的轻量级谓词信息指导图遍历
- 增量更新 Marker 而非重建图
- 按选择率分层的自适应搜索策略

**可测负载：**
- YFCC-10M + 时间戳/tag 更新流
- BigANN-100M + 合成 label 插入/删除/变更流
- MoReVec + 关系表更新

**竞争窗口：** 目前无人做。GateANN 和 PipeANN-Filter 团队可能会扩展到动态场景，但这需要根本性的架构重设计。

---

### 角度 B：Memory-Efficient Filtered ANN on SSD ⭐⭐⭐

**核心主张：** GateANN 需要 63GB 内存/100M 向量。在内存受限时（如十亿级数据在 32GB RAM 机器上），如何在 SSD 上做 filtered ANN？

**技术挑战：**
- Filter metadata 也必须存在 SSD 上，不能放内存
- 每次 filter check 本身就需要一次 SSD I/O
- 如何在不读取完整 metadata 的情况下做 filter 剪枝？

**风险：** 可能被认为是"工程优化"而非"新问题"。

---

### 角度 C：Range Filter on SSD ⭐⭐⭐

**核心主张：** 现有 SSD filtered ANN 主要优化 label equality。Range filter（时间、价格、坐标区间）在 SSD 上的 I/O 模式完全不同。

**技术挑战：**
- Range 条件的选择率随查询变化剧烈
- 排序索引在 SSD 上需要 sequential scan 或 B-tree lookup
- 图结构中嵌入范围信息的方式与 label 不同

**风险：** 问题可能太窄，不足以单独支撑论文。

---

### 角度 D：Selectivity-Adaptive SSD ANN ⭐⭐⭐⭐

**核心主张：** Filtered ANN 的核心难题是选择率敏感性。在 SSD 上这个问题被放大：每次错误的 pre-filter 或 post-filter 决策都导致一次浪费的 SSD I/O。

**技术挑战：**
- 实时估计选择率（metadata 在 SSD 上时，如何快速估计）
- 根据选择率动态切换策略（pre-filter → in-filter → post-filter）
- 在同一个索引结构上支持全选择率范围

**可结合角度 A。**

---

## 五、最强方向推荐

| 排名 | 方向 | 差异化 | 故事强度 | 负载 | 竞争窗口 |
|------|------|--------|---------|------|---------|
| **1** | **Dynamic Filtered ANN on SSD** | ✅✅✅ 三维交叉空白 | ✅✅✅ 生产刚需 | ✅✅ YFCC/BigANN + update stream | ✅✅✅ 无人做 |
| **2** | Dynamic + Selectivity-Adaptive (合并) | ✅✅✅ | ✅✅✅ | ✅✅ | ✅✅✅ |
| 3 | Memory-Efficient SSD Filtered | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| 4 | Range Filter on SSD | ✅ | ✅ | ✅ | ✅✅ |

**最强方向：Dynamic Filtered ANN on SSD**，可选结合 selectivity-adaptive 策略。

核心贡献故事：
> 现有 SSD filtered ANN（Filtered-DiskANN, GateANN, PipeANN-Filter）假设索引是静态的。现有 SSD dynamic ANN（FreshDiskANN, IP-DiskANN, Greator, DGAI）不支持 filter。生产 RAG/推荐系统同时需要两者。我们提出第一个支持动态更新的 SSD filtered ANN 架构，解决 filter-subgraph 连通性维护、增量 metadata 更新和选择率自适应三个新挑战。

---

## 六、Prior Work 全表

### SSD Filtered ANN (3 篇)

| # | 论文 | 年份 | 会议 | Filter类型 | 动态更新 | 内存需求 |
|---|------|------|------|-----------|---------|---------|
| 1 | Filtered-DiskANN | 2023 | WWW | Label only | ❌ | 中 |
| 2 | GateANN | 2026 | arXiv | Arbitrary | ❌ | 高 (63GB/100M) |
| 3 | PipeANN-Filter | 2026 | arXiv | Label + Range | ❌ | 中 (Bloom + quant) |

### SSD Dynamic ANN (无 filter, 7 篇)

| # | 论文 | 年份 | 会议 | 动态更新 | Filter |
|---|------|------|------|---------|--------|
| 1 | FreshDiskANN | 2021 | arXiv | ✅ batch | ❌ |
| 2 | IP-DiskANN | 2025 | arXiv | ✅ in-place | ❌ |
| 3 | Greator | 2025 | VLDB | ✅ localized | ❌ |
| 4 | Wolverine | 2025 | VLDB | ✅ path repair | ❌ |
| 5 | DGAI | 2025 | arXiv | ✅ decoupled | ❌ |
| 6 | PipeANN | 2025 | OSDI | ✅ (limited) | ❌ |
| 7 | Slipstream | 2026 | arXiv | ✅ warm-start | ❌ |

### In-Memory Dynamic Filtered ANN (3 篇)

| # | 论文 | 年份 | Filter类型 | 动态更新 | SSD |
|---|------|------|-----------|---------|-----|
| 1 | EMA | 2026 | General | ✅ Marker | ❌ |
| 2 | DIGRA | 2025 | Range | ✅ | ❌ |
| 3 | DSG | — | — | ✅ | ❌ |

### In-Memory Static Filtered ANN (15+ 篇)

| # | 论文 | 年份 | 会议 |
|---|------|------|------|
| 1 | ACORN | 2024 | SIGMOD |
| 2 | FusedANN | 2025 | arXiv |
| 3 | JAG | 2026 | arXiv (CMU/Meta) |
| 4 | SIEVE | 2025 | VLDB |
| 5 | Curator | 2026 | SIGMOD |
| 6 | PathSeer | 2026 | SIGMOD |
| 7 | FAVOR | 2026 | arXiv |
| 8 | NaviX | 2025 | VLDB |
| 9 | RNSG | 2026 | arXiv |
| 10 | iRangeGraph | 2024 | SIGMOD |
| 11 | UNIFY | 2024 | arXiv |
| 12 | Generalized Range Filter | 2026 | arXiv |
| 13 | RACORN-1 | 2026 | arXiv |
| 14 | PathFinder | 2025 | arXiv |
| 15 | Compass | 2025 | arXiv |

### 相关基础设施

| # | 论文 | 年份 | 贡献 |
|---|------|------|------|
| 1 | LAANN | 2026 | I/O-aware disk ANN 搜索 |
| 2 | BAMG | 2025/2026 | Block-aware 单调图 |
| 3 | FANNS Benchmark | 2025 | 6 数据集 × 5 filter mode 统一评测 |
| 4 | MoReVec | 2026 | 关系型 filtered ANN 数据集 |
| 5 | Hardness-Controlled Bench | 2026 | 难度受控 benchmark 生成器 |

---

## 七、可测负载汇总

| 数据集 | 规模 | 维度 | Filter 类型 | 来源 |
|--------|------|------|------------|------|
| YFCC-10M | 10M | 192 | Tag/category/camera/country | BigANN 2023 filter track |
| BigANN-100M | 100M | 128 | 合成 label (10-class) | BigANN competition |
| BigANN-1B | 1B | 128 | 合成 label | BigANN competition |
| LAION subset | variable | CLIP dim | 30 关键词 | LAION-400M |
| MoReVec | — | 768 | 关系 schema + GLS | 2026 新 |
| FANNS bench | 6 datasets | — | 5 filter modes | 统一 benchmark |
| YouTube-8M | 8M | — | Tag | YouTube |

动态场景负载需要在上述数据集上叠加 update stream：
- Insert/delete/replace 向量
- Metadata 变更（label 添加/删除、range 属性值变化）
- 时间序列的自然更新模式

可参考 CANDOR-Bench 的 streaming workload generator 设计。
