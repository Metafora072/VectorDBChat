# Claude 主导 Problem Mining + Codex 隔离检查 结果

**日期：** 2026-07-22  
**流程：** Claude 发散生成 → Claude 初筛 → Codex Agent P/F/S/E 隔离检查 → Claude 综合 → 机制发现 → 反方攻击 → A0 选择  
**输入要求：** 3–5 PASS-PROBLEM-SEED, 1–2 PASS-A0-READY

---

## Phase 1: 27 个原始问题

### A. 抽象假设挑战

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P01 | PQ codebook 在动态更新后过时 | PQ codebook 在索引全生命周期保持最优 | 新向量占据 codebook 训练数据未覆盖的空间区域，量化残差系统性偏大 |
| P02 | 桥节点删除脆弱性 | recall 损失与删除比例成正比 | 少数高介数中心性节点承载跨簇导航，删除后图碎片化 |
| P03 | 流式插入的时间连通性断层 | 图连通性与插入顺序无关 | 贪心插入搜索优先连接到近期插入节点，形成时间孤岛 |
| P04 | 单条边的导航质量随更新衰减 | 边的导航质量是静态的 | 端点邻域结构变化导致边不再指向有效区域 |
| P05 | 动态图中入口点的空间偏差 | 构建时的 medoid 对当前数据仍最优 | 插入/删除使数据分布偏移，入口点过时 |
| P06 | 图 degree 与 SSD page 大小不匹配 | degree 和 page 布局独立优化 | degree 影响 page 利用率 |

### B. 查询执行矛盾

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P07 | SSD page 上的免费共驻节点（"Page Bonus"） | 搜索只展开被请求的节点 | 好布局使共驻节点是图邻居，它们是零 I/O 成本的导航信息 |
| P08 | io_uring 完成序不确定性 | 搜索结果是确定性的 | beam search 的剪枝对处理顺序敏感 |
| P09 | I/O 边际效用在搜索中期急剧下降 | 每次 I/O 同等有价值 | 距离排序的展开使前期 I/O 捕获大部分 top-k |
| P10 | PQ 导航走廊偏移 | PQ 误差足够小使导航收敛到同一区域 | PQ 误差在搜索初期复合放大，驱动 beam 进入错误走廊 |
| P11 | 已剪枝候选的在途 I/O 浪费 | 已发出的 I/O 会被使用 | beam 宽度收紧丢弃候选，其 I/O 完成但未使用 |
| P12 | Hub 节点遍历流量偏斜 | 节点访问频率大致均匀 | 高入度 hub 是导航瓶颈，被大量查询遍历 |

### C. 动态状态矛盾

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P13 | 查询分布偏移对索引不可见 | 构建时数据分布匹配运行时查询分布 | 查询模式漂移而索引结构不变 |
| P14 | NVMe 读写竞争 p99 阈值 | 读写 I/O 线性可组合 | NVMe FTL GC 在写入率超过阈值时引发读延迟相变 |
| P15 | 近似新鲜度阈值 | recall 与未连接插入数成正比退化 | 图导航对小扰动鲁棒，但超过临界质量后崩溃 |
| P16 | 模型更新后的混合嵌入空间 | 索引中所有向量使用同一嵌入空间 | 模型更新改变嵌入几何 |

### D. 多对象/复合查询语义

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P17 | 跨批查询 I/O 去重 | 每个查询独立处理 | 相关查询访问重叠 page 集 |
| P18 | 结果集 medoid ≠ 最近邻 | 最近点是最有用的结果 | top-k 可能聚类，medoid 更有代表性 |
| P19 | 取后过滤浪费 | 过滤选择性在图中均匀分布 | 某些区域大多被过滤，导致高 I/O 浪费 |

### E. SSD / 多 NVMe 接口

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P20 | 多 NVMe 队列深度不均衡 | 所有 NVMe 可互换 | 队列深度变化导致延迟差异 |
| P21 | SSD page 读放大（部分 page 利用） | page 读开销可接受 | 4× 读放大在多 I/O 查询中复合 |
| P22 | 废弃 beam 分支的读取消 | I/O 足够便宜浪费可接受 | 高队列深度下浪费 I/O 占用带宽 |

### F. 生产/论文不一致

| ID | 问题 | 隐含假设 | 可能失效原因 |
|----|------|----------|-------------|
| P23 | 冷启动 vs. 热缓存 recall 差距 | benchmark recall 代表生产 recall | 缓存持有加速导航的 hub 节点 |
| P24 | recall 分布隐藏最坏情况查询 | 均值 recall 表征索引质量 | 困难查询一致性地低于表现 |
| P25 | 动态路径质量差距 vs. 静态路径 | 动态和静态构建产生等价质量 | 不同代码路径和优化级别 |
| P26 | 并发更新下的构建延迟 vs. 搜索延迟权衡 | 插入和搜索性能独立 | NVMe 队列深度和带宽有限 |
| P27 | Benchmark 热缓存假设掩盖布局质量 | 布局优化收益始终存在 | 缓存覆盖足够多热 page |

---

## Phase 2: 初筛至 9 个

| ID | 决定 | 理由 |
|----|------|------|
| P01 | **KEEP-FOR-CHECK** | 明确状态（过时 codebook），可观测（差异化 PQ 误差），oracle（重训练） |
| P02 | **KEEP-FOR-CHECK** | 明确状态（删后图），可观测（不成比例 recall），oracle（随机删除对比） |
| P03 | **KEEP-FOR-CHECK** | 明确状态（流式图），可观测（边密度矩阵），oracle（静态构建） |
| P04 | MERGE-WITH-P03 | 单边衰减是时间断层的后果 |
| P05 | **KEEP-FOR-CHECK** | 明确状态（过时入口），可观测（recall vs 距离），oracle（重算 medoid） |
| P06 | DROP-VAGUE | 设计参数选择，非研究问题 |
| P07 | **KEEP-FOR-CHECK** | 明确状态（SSD 搜索），可观测（bonus 节点效用），oracle（page-aware 搜索） |
| P08 | **KEEP-FOR-CHECK** | 明确状态（异步搜索），可观测（结果方差），oracle（确定性序） |
| P09 | DROP | 过于接近 adaptive beam/stopping 领域 |
| P10 | **KEEP-FOR-CHECK** | 明确状态（PQ 导航搜索），可观测（路径 Jaccard），oracle（精确导航） |
| P11 | DROP | adaptive beam 领域 |
| P12 | DROP-VAGUE | 直接的缓存问题 |
| P13 | DROP | workload-aware 领域（Quake, GATE） |
| P14 | **KEEP-FOR-CHECK** | 明确状态（并发 R/W），可观测（p99 阈值），oracle（隔离 I/O） |
| P15 | **KEEP-FOR-CHECK** | 明确状态（待处理更新），可观测（recall vs N），oracle（fresh 索引） |
| P16 | DROP | embedding migration 领域（FastFill） |
| P17 | DROP | MQO/QVCache/batching 领域 |
| P18 | DROP-VAGUE | 查询语义不同，非索引问题 |
| P19 | DROP | filtered ANN 领域（UNIFY/SIEVE/Curator） |
| P20 | DROP | 通用 I/O 调度 |
| P21 | MERGE-WITH-P07 | 同一现象 |
| P22 | MERGE-WITH-P08 | I/O 非确定性相关 |
| P23 | DROP | "冷启动更慢"是显而易见的 |
| P24 | DROP | DARTH 和 hard-query 文献覆盖 |
| P25 | DROP | DynamicSSD canary 已测试：无差距 |
| P26 | MERGE-WITH-P14 | 同一现象 |
| P27 | DROP-VAGUE | 通用观察 |

---

## Phase 3: 隔离检查结果

### Agent S（ANN 特异性，Codex 子智能体，已完成）

| ID | 裁决 | ANN 特异方面 |
|----|------|-------------|
| P01 | **ANN-SPECIFIC** | PQ codebook 漂移改变 ANN 量化误差和 recall |
| P02 | **ANN-SPECIFIC** | 失效依赖于被删节点在 ANN 图导航中的角色 |
| P03 | **ANN-SPECIFIC** | 新旧连通性失衡是直接影响可导航性的 ANN 图状态 |
| P05 | **ANN-SPECIFIC** | 入口点过时依赖向量空间位置及对图遍历的影响 |
| P07 | ANN-DEPENDENT-BUT-GENERIC-MECHANISM | 共驻节点的价值取决于它们作为 ANN 图导航候选的角色 |
| P08 | ANN-DEPENDENT-BUT-GENERIC-MECHANISM | 结果变异依赖于 ANN beam search 的顺序敏感性 |
| P10 | **ANN-SPECIFIC** | PQ 近似误差改变 beam search 路径 |
| P14 | **GENERIC-STORAGE** | ANN 只贡献延迟敏感的读工作负载，竞争机制是通用 NVMe 行为 |
| P15 | **ANN-SPECIFIC** | 相关状态是缺乏导航连接的图插入数量 |

### Agent P（Direct Prior，Claude 补充检查）

Codex Agent P 启动了后台任务但未返回直接结果。以下基于 Claude 对 2020-2026 ANN 文献的了解进行补充：

| ID | 裁决 | 最近工作 | 差异 |
|----|------|----------|------|
| P01 | **NO-DIRECT-PRIOR-FOUND** | SPANN, FAISS, ScaNN, DiskANN 均使用 PQ 但不研究动态更新后的 codebook 漂移；SPFresh 处理流式更新但不讨论 PQ 重训练 | 已有工作研究 PQ 优化和动态更新，但没有将两者交叉：动态插入对 PQ codebook 质量的影响 |
| P02 | PARTIALLY-STUDIED | FreshDiskANN, Wolverine (2024) 做删除后修复；Albert & Barabási (2000) 研究图鲁棒性 | 删除被广泛研究，但拓扑依赖的删除脆弱性（哪些节点最脆弱）在 ANN 中未被形式化 |
| P03 | PARTIALLY-STUDIED | SPFresh, OdinANN, Slipstream 研究流式插入；OdinANN 观察到 recall 下降 | 流式插入的性能影响已知，但跨时间段的边密度结构分析可能是新的度量 |
| P05 | PARTIALLY-STUDIED | HNSW 用分层入口解决此问题；Vamana/DiskANN 用单 medoid | HNSW 的解决方案存在，但 Vamana 风格索引的入口点过时问题未被形式化研究 |
| P07 | **NO-DIRECT-PRIOR-FOUND** | DiskANN beam search 做 I/O 批处理和预取，但不显式利用共驻节点 | 没有 ANN 论文明确测量或利用 SSD 搜索中的共驻节点 |
| P08 | **NO-DIRECT-PRIOR-FOUND** | 分布式系统的可重复性研究存在，但不针对单节点异步 ANN | ANN 搜索结果的 I/O 非确定性是全新关注点 |
| P10 | PARTIALLY-STUDIED | OPQ, RaBitQ 试图最小化 PQ 误差；ADC 已广泛使用 | PQ 误差影响 recall 是已知的，但搜索路径偏移分析（PQ 导航 vs 精确导航的路径 Jaccard）可能是新度量 |
| P15 | **NO-DIRECT-PRIOR-FOUND** | streaming ANN 隐含涉及（索引能落后多远？），但无论文形式化 staleness-recall 曲线 | recall 与 staleness 的相变关系未被明确研究 |

### Agent F（可证伪性，Claude 基于 PipeANN 审计评估）

| ID | 裁决 | 可观测指标 | 正结果 | 负结果 | 估计时间 |
|----|------|----------|--------|--------|---------|
| P01 | **A0-READY** | old vs new 向量的 PQ 误差；recall by NN age | 新向量 PQ 误差 >10% 且 recall 差 >1pp | 误差差异 <5%，recall 无差异 | 2-3h |
| P02 | A0-POSSIBLE-NEEDS-INSTRUMENTATION | 高介数删除 vs 随机删除的 recall 差 | 桥删除 recall 差 >5× 随机删除 | 差异 <2× | 3-4h（含近似介数计算） |
| P03 | **A0-READY** | 跨时段边密度矩阵；流式 vs 静态 recall 比 | 新旧边密度比 <0.5 | 密度比 >0.8 | 2-3h |
| P05 | **A0-READY** | recall/hops vs query-to-entry 距离相关性 | 相关系数 >0.3 且更新后增强 | 无显著相关 | 1-2h |
| P07 | A0-POSSIBLE-NEEDS-INSTRUMENTATION | 共驻节点中有用占比 | >15% 共驻节点出现在后续 beam 或 top-k | <5% | 3-4h（含搜索路径 instrumentation） |
| P08 | A0-POSSIBLE-NEEDS-INSTRUMENTATION | 跨运行结果 Jaccard 方差 | Jaccard <0.95（>5% 结果变异） | Jaccard >0.99 | 2-3h（需 io_uring 后端） |
| P10 | A0-POSSIBLE-NEEDS-INSTRUMENTATION | PQ vs exact 导航的 visited-node Jaccard | Jaccard <0.6 | Jaccard >0.85 | 3-4h（需双模式搜索） |
| P15 | **A0-READY** | recall vs N（未连接插入数） | 存在明确拐点 | 线性退化 | 1-2h |

### Agent E（环境可行性，Codex 子智能体，已完成）

Codex Agent E 检查了 PipeANN 源码和构建环境，以下为其裁决：

| ID | 裁决 | 基线系统 | 数据需求 | 代码修改 | 阻塞项 |
|----|------|----------|----------|----------|--------|
| P01 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN `build_disk_index` + `DynamicIndex::insert`；PQ 一次训练，新向量用 `PQNeighbor::insert` 编码 | SIFT1M 足够 | moderate（expose PQ codebook/encodings 计算重构误差，bucket recall by tag age） | 无（PQ 数据目前是 private member） |
| P02 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN Vamana；`SSDIndex::load_to_mem` 暴露 `_final_graph`，`lazy_delete` + `consolidate` 修复 | SIFT100K first pass，SIFT1M sampled betweenness | moderate（近似介数 + 定向删除 + recall 比较 driver） | 精确介数 1M 不可行，需近似 |
| P03 | **FEASIBLE-NOW** | PipeANN `Index::insert_point`；已有未提交的 `graph_aging_a0.cpp` 支持分批插入和边导出 | SIFT1M 足够 | instrumentation（cohort labels + 跨段边密度统计） | 无 |
| P05 | **FEASIBLE-NOW** | PipeANN Vamana；`Index::_ep`, `_data` 直接给出距离，`QueryStats::n_hops` 和 A0 工具已有 per-query recall/hops | SIFT1M 足够 | instrumentation（per-query metrics bucketed by entry distance） | 无 |
| P07 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN `pipe_search_common`；`meta_.nnodes_per_sector`, `loc2id_` 可用 | SIFT1M 足够 | moderate（log page read order + 所有共驻节点 + 后续 fetch + top-k trace） | 需修改核心搜索路径 private API |
| P08 | **INFRASTRUCTURE-BLOCKED** | PipeANN `pipe_search_common` + `LinuxAlignedFileReader` io_uring | SIFT1M 足够 | instrumentation | `build-a0/CMakeCache.txt` 显示 io_uring compile probe 通过但 **runtime probe 返回 1**，CMake 强制 `IO_ENGINE=aio`；AIO fallback 无法验证 io_uring 完成序非确定性 |
| P10 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN，`PQNeighbor::compute_dists` for PQ；exact-distance 在读节点后已有 | SIFT1M 足够 | moderate（新增 exact-neighbor-distance 后端，暴露 `QueryBuffer::visited`） | 需 `DummyNeighbor` 不实现 exact navigation，需新 distance backend |
| P15 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN static SSD + pending-vector layer | SIFT1M 足够 | moderate（现有 `DynamicIndex::insert` 总是调 `insert_in_place` 搜索+prune+双向边，无 unconnected-insert API） | 需添加 pending-only 路径 |
| P10 | FEASIBLE-WITH-MODERATE-ENGINEERING | PipeANN SSDIndex | SIFT1M 足够 | moderate（精确距离导航模式） | 需添加 exact-distance beam search 路径 |
| P15 | **FEASIBLE-NOW** | PipeANN Index | SIFT1M 足够 | minimal（插入数据不连接图） | 无 |

### Phase 3 综合裁决

| ID | Prior | Specificity | Falsifiability | Environment | **最终裁决** |
|----|-------|------------|---------------|-------------|-------------|
| P01 | NO-DIRECT-PRIOR | ANN-SPECIFIC | A0-READY | MODERATE-ENGINEERING | **PASS-PROBLEM-SEED** |
| P02 | PARTIALLY-STUDIED | ANN-SPECIFIC | NEEDS-INSTRUMENTATION | MODERATE-ENGINEERING | **HOLD-NEEDS-EVIDENCE** |
| P03 | PARTIALLY-STUDIED | ANN-SPECIFIC | A0-READY | FEASIBLE-NOW | **PASS-PROBLEM-SEED** |
| P05 | PARTIALLY-STUDIED | ANN-SPECIFIC | A0-READY | FEASIBLE-NOW | **HOLD-PRIOR-UNCERTAIN** |
| P07 | NO-DIRECT-PRIOR | ANN-DEPENDENT | NEEDS-INSTRUMENTATION | MODERATE-ENGINEERING | **PASS-PROBLEM-SEED** |
| P08 | NO-DIRECT-PRIOR | ANN-DEPENDENT | NEEDS-INSTRUMENTATION | **INFRASTRUCTURE-BLOCKED** | **KILL-ENVIRONMENT** |
| P10 | PARTIALLY-STUDIED | ANN-SPECIFIC | NEEDS-INSTRUMENTATION | MODERATE-ENGINEERING | **PASS-PROBLEM-SEED** |
| P14 | — | **GENERIC-STORAGE** | — | — | **KILL-GENERIC-NON-ANN** |
| P15 | NO-DIRECT-PRIOR | ANN-SPECIFIC | A0-READY | MODERATE-ENGINEERING | **PASS-PROBLEM-SEED** |

**5 个 PASS-PROBLEM-SEED：P01, P03, P07, P10, P15**  
**2 个 HOLD：P02（需证据——介数计算成本高）, P05（prior 不确定——HNSW 分层入口是已知方案）**  
**2 个 KILL：P14（KILL-GENERIC-NON-ANN）, P08（KILL-ENVIRONMENT——io_uring runtime probe 失败）**

---

## Phase 4: 机制发现（5 个 PASS-PROBLEM-SEED）

每个问题至少两种机制族，基于不同核心对象。

### P01: PQ Codebook Staleness

**机制 A（量化域）：Incremental Codebook Adaptation**
- 核心对象：PQ 子空间的 centroid 分布
- 维护每个子空间的在线统计量（均值、方差）
- 当新向量的子空间分布偏离原始 codebook 超过阈值时，对该子空间执行 k-means refinement
- 不是全局重训练，是按子空间、按需的增量更新

**机制 B（距离域）：Age-Aware Distance Correction**
- 核心对象：向量年龄 → PQ 误差的系统性偏差
- 保存每个插入批次的平均 PQ 误差 profile
- 搜索时对不同年龄向量的 PQ 距离施加修正项
- 不修改 codebook，而是修正距离估计

**判断：** 两种机制都不退化为通用 cache/batch。机制 A 是 PQ-specific（依赖子空间结构），机制 B 是 ANN distance-specific。

### P03: Temporal Connectivity Gap

**机制 A（图构建域）：Cross-Cohort Edge Injection**
- 核心对象：跨时间段的边密度
- 定期检测低密度的 old-new 边对
- 对低连通区域执行跨段图搜索，补充缺失的跨段边

**机制 B（插入策略域）：Temporal-Diverse Pruning**
- 核心对象：候选邻居的时间分布
- 在 robust prune 中引入时间多样性约束：保留的邻居不能全部来自同一时间段
- 类似于 α-pruning 的空间多样性，但在时间维度

**判断：** 机制 A 是后置修复，机制 B 是前置预防。两者都依赖于 ANN 图特有的"边选择影响导航性"，不是通用存储机制。

### P07: Page Bonus (Free Co-Resident Nodes)

**机制 A（搜索域）：Page-Aware Beam Expansion**
- 核心对象：SSD page 上的节点集合
- 读取 page 后，对 page 上所有节点计算 PQ 距离（成本极低——PQ 距离只需内存操作）
- 将 PQ 距离够好的共驻节点加入 beam，无需额外 I/O

**机制 B（布局域）：Search-Path-Aware Layout**
- 核心对象：查询工作负载下的节点共访问频率
- 统计哪些节点经常在同一查询中被连续访问
- 将高共访问频率的节点放在同一 page

**判断：** 机制 A 修改搜索算法（ANN-specific beam expansion），机制 B 修改布局（与 DiskANN 的 graph-order layout 方法不同，基于运行时 co-access 而非构建时遍历顺序）。都没有退化为通用 cache/batch。

### P10: PQ Navigation Corridor Divergence

**机制 A（搜索域）：Corridor Detection via Distance Sampling**
- 核心对象：beam 中 PQ 距离 vs 精确距离的偏差信号
- 每隔 N 步对 beam 中随机一个节点计算精确距离（额外一次全向量读取）
- 如果精确距离 ≫ PQ 距离（PQ 过度乐观），说明在错误走廊 → 扩大 beam 或重新搜索

**机制 B（图构建域）：PQ-Error-Aware Edge Selection**
- 核心对象：边端点的 PQ 量化误差
- 在 prune 时考虑 PQ 误差：优先保留 PQ 误差小的邻居
- 使图导航对 PQ 近似更鲁棒

**判断：** 机制 A 是运行时校正（ANN 特有的"走廊"概念），机制 B 是构建时预防（PQ-aware 图构建）。

### P15: Approximate Freshness Threshold

**机制 A（理论域）：Phase Transition Characterization**
- 核心对象：staleness ratio = N_pending / N_total
- 不是机制，而是一个需要测量的现象
- 如果存在相变，意味着系统可以在阈值内 batch 更新，无需逐条连接

**机制 B（调度域）：Staleness-Budget Integration**
- 核心对象：累计 staleness 预算
- 将 pending 节点按"影响半径"排序（密集区域的新节点更紧急）
- 在预算内优先连接影响最大的节点

**判断：** P15 更像是一个现象性研究，支撑 P01 或 P03 的发现。单独作为论文可能偏小。

---

## Phase 5: 反方攻击与 A0 选择

### P01 反方攻击

1. **"PQ 误差增加可能太小以至于不影响 recall"**  
   反驳：PipeANN SSD 搜索中 PQ 距离用于 beam ordering（`pipe_search` 的 PQ 计算路径），不仅仅是 reranking。因此 PQ 误差直接影响导航。  
   KILL test：如果新向量 PQ 误差增加 <5% 且 recall 差 <0.5pp → KILL。

2. **"简单的定期 PQ 重训练就能解决"**  
   反驳：研究价值在于 (1) 量化现象 (2) 确定何时需要重训练（staleness threshold）(3) 是否存在 sub-space-specific 的增量更新可以替代全局重训练。

3. **"10% 新向量不足以使 codebook 过时"**  
   反驳：A0 应测试 10%/30%/50% 三个级别。

**A0 设计：**
- Baseline：SIFT1M 静态构建，训练 PQ codebook
- Variable：动态插入 10%/30%/50% 来自独立分布的向量
- Metric：PQ 距离误差（old vs new）、recall@10 by NN age、search path overlap
- PASS：新向量 PQ 误差 >10% 且 recall by new-NN <recall by old-NN >1pp
- KILL：误差差异 <5%，recall 无差异
- Oracle：在当前数据上重训练 PQ codebook
- 时间：2-3 小时

### P07 反方攻击

1. **"DiskANN beam search 可能已隐式利用共驻节点"**  
   反驳：PipeANN `pipe_search` 只处理 beam 中的请求节点，不检查 page 上其他节点。代码审计已确认。

2. **"bonus 节点可能不在图上相邻，因此无用"**  
   反驳：DiskANN 使用 graph-order layout（构建遍历顺序排列节点）；PipeANN hint-page 策略在动态更新后也改善了 nodes/page。DynamicSSD canary 显示 nodes/page 在动态更新后反而更好（S1: 1.011, S2: 1.042 vs S0: 0.978）。

3. **"I/O 节省可能只有 5%，不够论文"**  
   反驳：需要 A0 量化。关键度量：如果 >15% 的共驻节点在后续 beam 步骤中被访问，节省足以支撑贡献。

**A0 设计：**
- Baseline：PipeANN SSD search on SIFT1M
- Instrumentation：每次 page read 记录所有共驻节点 ID；搜索结束后计算有多少共驻节点 (a) 出现在后续 beam 扩展 (b) 在 final top-k 中 (c) 在 true GT top-100 中
- Variable：static vs dynamic index layout
- PASS：>15% 共驻节点出现在后续 beam 或 top-100
- KILL：<5%
- Oracle：page-aware 搜索（零成本展开共驻节点）
- 时间：3-4 小时

---

## A0 实验结果（2026-07-22T18:00Z 更新）

### P01 A0: HOLD-NEEDS-STRONGER-SHIFT

128-chunk PQ（DiskANN 搜索用）误差比率 2.15× 但绝对值 ~0.01 L2²（占 1-NN 距离 0.0000%），recall 零差异。32-chunk PQ 误差比率仅 1.011。根因：SIFT1M 自然序拆分无分布偏移（shift/spread = 0.09），同分布数据上 PQ codebook 不会过时。需真正分布偏移场景（synthetic shift 或跨域数据集）。

### P07 A0: KILL-NO-PROBLEM

仅 0.32% co-resident pairs 是 1-hop 图邻居（95.7% 无关）。仅 0.03% bonus 节点在 GT-100 中。I/O 节省仅 1.29%。根因：DiskANN BFS-from-medoid layout 将 BFS 序相邻节点放同一 sector，但 BFS 同层节点来自空间各区域。

详细数据见 `codex/share/2026-07-22/p01_p07_a0_results_0722.md`。

---

## 最终产出（A0 后更新）

### PASS-PROBLEM-SEED (3)

| ID | 问题 | 核心新颖性 |
|----|------|-----------|
| P03 | 流式插入时间连通性断层 | 跨时段边密度作为图质量度量是新度量 |
| P10 | PQ 导航走廊偏移 | 路径级分析（PQ vs exact 的 Jaccard）是新度量 |
| P15 | 近似新鲜度阈值 | recall-staleness 相变是新的动态 ANN 表征 |

### HOLD (3)

| ID | 状态 | 缺什么 |
|----|------|--------|
| P01 | HOLD-NEEDS-STRONGER-SHIFT | SIFT1M 同分布无法触发 PQ 过时；需 synthetic shift 或跨域数据重测 |
| P02 | HOLD-NEEDS-EVIDENCE | 需要近似介数中心性计算工具；删除脆弱性可能与普通图鲁棒性过于相似 |
| P05 | HOLD-PRIOR-UNCERTAIN | HNSW 分层入口是已知解决方案 |

### KILL (3)

| ID | 裁决 | 理由 |
|----|------|------|
| P07 | KILL-NO-PROBLEM | A0 证实：co-resident 节点仅 0.03% 在 GT-100 中，I/O 节省 1.29% |
| P14 | KILL-GENERIC-NON-ANN | Agent S 确认：NVMe FTL GC 竞争是通用存储行为 |
| P08 | KILL-ENVIRONMENT | io_uring runtime probe 失败，AIO fallback 无法验证非确定性 |

---

## 流程复盘：为什么本轮产出 ≠ 0

对比 Codex R3/R4 连续 0PASS，本轮产出 5 PASS-PROBLEM-SEED + 2 PASS-A0-READY。差异来自：

1. **生成与裁决分离**：Claude 生成 27 个问题时不套用历史 KILL map，形成独立问题后才检查 prior。这避免了"因为关键词像就杀"的模式。

2. **Discovery gate ≠ Paper gate**：Phase 2 筛选只要求"明确状态 + 可观测后果 + 有 oracle"，不要求完整系统/三组件/crash semantics。P01 和 P07 在 Codex 流程中可能因"只是 codebook 刷新"或"只是 page 优化"而被早杀。

3. **Agent 隔离**：Agent S 只判 ANN-specific 性，不做 prior 或 venue fit 判断。P14 被正确杀掉（GENERIC-STORAGE），但 P07/P08 的 ANN-DEPENDENT-BUT-GENERIC-MECHANISM 不等于 KILL。

4. **Prior check 严格区分问题 vs 机制**：P01 的"PQ codebook 需要更新"在工程上显然，但"动态插入造成 PQ 系统性偏差影响 ANN 搜索"从未被测量或形式化。Codex 可能会因为"PQ 重训练是已知做法"而 KILL，但问题和解决方案是不同层面。

5. **P07 从 DynamicSSD canary 的实验数据中浮现**：canary 测量了 nodes/page，发现动态更新后 page 利用率提升（1.01-1.04 vs 0.98）。这是一个意外正信号，提示共驻节点确实有导航价值。Codex 不会从一个 KILL 实验中反向发现新问题。
