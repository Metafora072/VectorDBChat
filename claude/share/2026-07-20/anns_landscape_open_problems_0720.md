# 向量数据库/ANNS 方向开放问题与发表机会全景 (2025-07 snapshot)

**Date:** 2026-07-20
**Author:** Claude

---

## 一、当前最活跃的六条研究主线

### 主线 1: Filtered / Hybrid ANN（最拥挤，但仍有空间）

**背景问题：** 真实查询几乎总是带有属性谓词（`WHERE category='shoes' AND price<100`）。纯向量 ANN 返回的 top-k 无法满足业务约束。

**最新工作密度：** 极高 — 2025–2026 出现 10+ 篇专题论文。

| 论文 | 年份/会议 | 核心贡献 |
|------|-----------|----------|
| ACORN | 2024 VLDB | 首个 predicate-agnostic 图索引，但在低选择率下性能下降 |
| Filtered-DiskANN | 2024 | 在 Vamana 上做 label-based filtering |
| FusedANN | 2025 | 属性-向量融合，凸优化 filtered ANN |
| SIEVE | 2025 VLDB | 多索引集合，按选择率路由 |
| Curator | 2026 | 低选择率 filter 的专用索引 |
| PathSeer | SIGMOD 2026 | 自适应邻居处理的 filtered ANN |
| FAVOR | 2026 | 基于选择率感知排除距离的 filter-agnostic ANN |
| RNSG | 2026 | Range-aware 图索引用于 range filter |
| Query-aware Routing | 2026 | 学习路由用于 filtered ANN |
| Hardness-Controlled Benchmark | 2026 | filtered ANN 难度受控的 benchmark 生成器 |

**开放问题：**
- 任意 predicate 组合（非预定义 label）下的高效索引，ACORN 是唯一尝试但不稳定
- Range filter（连续属性区间）仍然很难，containment/overlap 语义刚开始探索
- 超参调优对 selectivity 极敏感，缺少自动化方案
- **磁盘上的 filtered ANN 几乎空白** — 现有工作都是内存场景

**PZ 适配度：** ⭐⭐⭐ 磁盘上的 filtered ANN 与 DGAI 直接相关，但竞争激烈

---

### 主线 2: 动态/流式 ANN 更新（PZ 的核心领地）

**背景问题：** RAG、推荐、日志分析等场景需要高频插入/删除/替换，图索引在删除后导航性退化。

**最新工作：**

| 论文 | 年份/会议 | 核心贡献 |
|------|-----------|----------|
| FreshDiskANN | 2021 | StreamingMerge + batch consolidation |
| IP-DiskANN | 2025 | 首个 in-place update，避免 batch consolidation |
| Greator | VLDB 2025 | Topology-aware localized update + ASNR + page-aware ΔG |
| Wolverine | VLDB 2025 | 单调路径修复，11× deletion throughput |
| MN-RU | 2024 | HNSW mutual-neighbor replaced update |
| Slipstream | 2026 | 流式 locality-aware 构建，warm-start，30.8× throughput |
| Nav-Signal Repair | 2026 | 信号触发的局部修复 |
| VStream | VLDB 2025 | 分布式流式向量搜索系统 |
| IVF-TQ | 2026 | Codebook-free 流式索引 |
| CANDOR-Bench | 2026 | 动态开放世界流的连续 ANN benchmark |

**开放问题：**
- **Distribution shift 下的动态索引**：插入分布随时间漂移时，图结构退化。目前只有 CANDOR-Bench 开始量化这个问题，但没有解决方案
- **理论 freshness-recall tradeoff**：给定 update rate 和 query rate，recall 衰减的下界是什么？无人触碰
- **Crash consistency for dynamic graph ANN**：P-HNSW（2025, NVDIMM）是唯一尝试，但针对 PM 而非 SSD。SSD 上动态图索引的 crash recovery 完全空白
- **多版本/MVCC 向量索引**：支持 snapshot isolation 的向量索引，事务语义未解决

**PZ 适配度：** ⭐⭐⭐⭐⭐ DGAI + OdinANN 直接在这个领域，且上述开放问题与 PZ 的硬件（multi-NVMe）匹配

---

### 主线 3: 硬件异构与分布式

**背景问题：** 十亿级向量无法放入单机内存，需要 SSD / CXL / 分布式 / GPU 加速。

**最新工作：**

| 论文 | 年份/会议 | 核心贡献 |
|------|-----------|----------|
| CXL-ANNS | ATC 2023 | CXL 远内存 ANN，静态缓存入口附近节点 |
| d-HNSW | 2025 | RDMA disaggregated memory 上的 HNSW |
| SHINE | 2026 | 可扩展的 disaggregated memory HNSW |
| CMANNS | SIGMOD 2026 | GPU 加速图索引构建，compute-memory 分离 |
| HARMONY | SIGMOD 2026 | 分布式向量数据库 |
| OrchANN | 2025 | Hierarchical orchestration for skewed out-of-core search |
| DiskJoin | SIGMOD 2025 | SSD 上大规模向量 similarity join |
| BAMG | 2025/2026 | Block-aware 单调图，SSD layout 优化 |

**开放问题：**
- **CXL 2.0/3.0 + ANN 的系统设计**：d-HNSW 和 SHINE 是首批，但都是 HNSW-only。Vamana/DiskANN 风格索引在 CXL 上的设计空白
- **ZNS SSD + ANN**：**零先例**。ZNS 的 zone 写入模型完全改变了图索引的页面更新语义
- **GPU 加速查询（非构建）**：CMANNS 做的是构建。查询阶段的 GPU 调度与图遍历融合仍然 open
- **向量 similarity join on SSD**：DiskJoin 是首个，但场景和优化空间仍然广阔

**PZ 适配度：** ⭐⭐⭐ 适合 ZNS/multi-NVMe 方向，但 CXL/GPU 需要额外硬件

---

### 主线 4: 多向量/Late Interaction 检索

**背景问题：** ColBERT/ColPali 产生 per-token/per-patch 向量，评分需要 MaxSim 聚合。存储和检索成本高。

**最新工作：**

| 论文 | 年份/会议 | 核心贡献 |
|------|-----------|----------|
| GEM | SIGMOD 2026 | 首个原生图索引用于多向量检索，16× speedup |
| PLAID/WARP/XTR | 2022–2024 | Token pruning / centroid-based retrieval |
| MUVERA | 2025 | 固定大小多向量编码 |
| HEAVEN | 2025 | ColPali 的层次式 reranking |

**开放问题：**
- **SSD 上的多向量检索**：GEM 是纯内存的。当 per-document patch 向量数达到 1024 且文档数达到百万时，SSD I/O 成为瓶颈。**我们已经在之前的评审中 KILLED 这个方向**（ESPN 已有 SSD reranking，且 PageMaxSim 实验显示单球读取已覆盖 99.92-100% 页）
- **动态更新下的多向量索引**：文档更新 → 所有 patch 向量需要替换。GEM 无动态更新
- **存储-精度 tradeoff 的理论分析**：多少 patch 向量可以安全剪枝？缺乏理论保证

**PZ 适配度：** ⭐⭐ 方向已被 KILL（见之前评审），GEM 是强竞品

---

### 主线 5: 理论基础

**背景问题：** 图 ANN 的经验性能远好于理论解释。缺少 I/O 下界、收敛保证、近似比分析。

**最新工作：**

| 论文 | 年份 | 核心贡献 |
|------|------|----------|
| Navigable Graphs: Constructions and Limits | 2024 | NSW/HNSW 的可导航性构造与极限 |
| Graph-Based ANN Revisited: Theoretical Analysis | 2025 | 图 ANN 搜索的理论分析与优化 |
| Worst-case Performance of ANN Implementations | 2023/2025 | 流行 ANN 实现的最坏情况保证 |
| ANN Search: Recall What Matters | 2026 | 重新审视 recall 度量的语义 |

**开放问题：**
- **Disk-resident ANN 的 I/O 复杂度下界**：完全空白。没有人证明过在外存模型下，给定 recall ≥ r 需要的最少 I/O 次数
- **图 ANN 在 deletion 下的 recall 衰减速率**：Slipstream 有实验观察，但无理论界
- **Navigability vs page layout 的联合优化理论**：BAMG 有实践，缺理论

**PZ 适配度：** ⭐⭐⭐⭐ I/O 复杂度下界是 FAST/VLDB 的天然话题，且与 PZ 的 disk-resident 专长完美匹配

---

### 主线 6: 新兴查询语义

**背景问题：** 除了 top-k NN，向量数据库需要支持更丰富的查询类型。

**最新工作：**

| 论文 | 年份 | 核心贡献 |
|------|------|----------|
| HRNN | 2026 | 高维向量的近似 reverse k-NN |
| DiskJoin | SIGMOD 2025 | SSD 上的向量 similarity join |
| SimJoin work sharing | 2026 | 阈值向量 join 的工作共享 |
| Aggregate NN queries | SIGMOD 2026 | 学习表征上的聚合 NN 查询 |
| Directory-Aware Query | 2026 | 向量数据库的目录感知查询和维护 |
| Cracking Vector Search | 2025 | 向量搜索索引的 cracking（自适应索引） |
| Generalized Range Filtering | 2026 | 包含和重叠语义的范围过滤 |

**开放问题：**
- **Reverse k-NN on disk**：HRNN 是内存的。SSD 上完全空白
- **向量 join 的 I/O 优化**：DiskJoin 开了头，但优化空间巨大
- **自适应/cracking 风格的向量索引**：Cracking Vector Search 是首个探索。在 workload 驱动下渐进构建索引的思路，非常适合 SSD 场景

**PZ 适配度：** ⭐⭐⭐ 新型查询语义 + SSD 是差异化机会

---

## 二、系统侧 vs 算法侧发表机会

| 维度 | 系统侧 (FAST/VLDB/OSDI/SIGMOD) | 算法侧 (NeurIPS/ICML/ICLR) |
|------|--------------------------------|---------------------------|
| **竞争密度** | 中。每年 ANN 相关论文 ~10-15 篇 | 高。ML venue 对 ANN 系统论文兴趣有限 |
| **差异化容易度** | 较高 — 硬件/I/O/并发/一致性等系统问题天然区分 | 低 — 纯算法改进需要理论保证或大规模实验 |
| **当前空白数量** | 多。磁盘 filtered ANN、crash consistency、ZNS、I/O 下界、SSD join 都无人做 | 少。图构建、路由、量化等主流方向都有人 |
| **审稿偏好** | 重视 real system + real workload + I/O 指标 | 重视理论 novelty 或在 standard benchmark 上 SOTA |
| **PZ 的比较优势** | ⭐⭐⭐⭐⭐ 有 DGAI/OdinANN 实现、M0-M3 infra、multi-NVMe 硬件 | ⭐⭐ 缺 GPU、缺 ML 基础设施 |

**结论：系统侧明显更有机会。** 原因：

1. PZ 有成熟的 disk-resident 动态图 ANN 实现，这是绝大多数竞争者缺乏的
2. 系统论文需要 end-to-end 实现和 real-workload 评估，进入壁垒较高
3. 多个重要的系统问题完全空白（crash consistency, ZNS, I/O lower bounds, SSD filtered ANN）
4. 算法侧的 ANN 改进需要在 standard benchmark 上与 GPU-accelerated 方案竞争，PZ 没有这个硬件优势

---

## 三、最有前景的方向排序（PZ 专属）

| 排名 | 方向 | 理由 | 目标会议 | KILL 风险 |
|------|------|------|----------|-----------|
| **1** | **Disk-resident ANN 的 I/O 复杂度下界** | 零先例；理论贡献不需要新系统；与 PZ 磁盘专长匹配；FAST/VLDB 天然话题 | VLDB/SIGMOD | 低（理论方向，不依赖实验结果） |
| **2** | **SSD 上的 Crash-Consistent 动态图 ANN** | P-HNSW 只做了 PM，SSD 完全空白；DGAI 的 decoupled 架构天然适合做 crash recovery 设计 | FAST/VLDB | 中（需要证明 crash+recovery 开销可接受） |
| **3** | **Disk-Resident Filtered ANN** | 现有 filtered ANN 全是内存；DGAI 直接可扩展；但竞争者可能很快进入 | VLDB/SIGMOD | 中（竞争窗口可能不长） |
| **4** | **Distribution Shift 下的流式图 ANN** | 没有现有解决方案；CANDOR-Bench 刚提出问题；理论 freshness-recall tradeoff 无人做 | VLDB/NeurIPS | 中-高（需要量化 shift 对图结构的影响） |
| **5** | **ZNS SSD + ANN** | 零先例，但 ZNS 硬件获取和社区兴趣有限 | FAST | 中（审稿人可能质疑实用性） |

---

## 四、最新工作指向的背景问题总结

2025–2026 的最新论文集中反映了三个**背景问题**：

1. **从静态到动态的转型阵痛**：Greator、Wolverine、Slipstream、IP-DiskANN、Nav-Signal Repair 都在解决"图索引在持续更新下如何保持质量"。这个问题远未解决 — 理论界没有 recall decay bound，系统界没有 crash consistency，工程界没有 distribution shift 下的自适应方案。

2. **从纯向量到复合查询的扩展**：Filtered ANN、Range Filter、Reverse k-NN、Similarity Join、Aggregate NN — 向量数据库正在从"嵌入检索引擎"演变为"支持复杂查询的向量关系数据库"。每种新查询类型在 SSD 上都需要新的索引/I/O 设计。

3. **从单机内存到异构存储的迁移**：CXL、disaggregated memory、SSD、分布式 — 向量从 DRAM 迁出后，所有 in-memory 假设都需要重新审视。这是系统论文的黄金时代。
