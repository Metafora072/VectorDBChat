# Architecture Idea Council Round 2：Claude 修订假设

日期：2026-07-12

## 前置反思

Round 1 的四个候选中三个被 Kill，核心原因是 prior-art 盲区：AiSAQ (2024)、LM-DiskANN (2023)、PageANN (2025)、SkipDisk (2026) 已解决低 DRAM PQ 问题；PipeANN SPDK 已用 4KB 条带多盘；Quake (OSDI'25) 和 GATE (2025) 已覆盖查询分布适应。这反映了一个结构性问题：我对 2023–2026 低内存图索引和 workload-adaptive indexing 文献存在系统性盲区。

本轮修正策略：（1）每个候选明确标注"需要 Codex 验证的 prior-art 假设"；（2）不声称 novelty，只声称"结构性差异点"；（3）从 PRODUCTION PAIN POINT 出发而非从已知文献缝隙反推。

---

## 候选 A：跨 Embedding 版本的 Warm-Start 图重建（候选三修订版）

### 这是 Codex REVISE 建议的落实。

### 1. 被挑战的架构假设

**"图索引绑定一个固定的 embedding 空间；模型变更 = 全量重建。"**

所有 Vamana 系系统在 RobustPrune 时用当前坐标的精确距离决定边。当 embedding model 更新后，旧边在新空间中可能不再满足剪枝条件，但现有系统唯一的选择是 delete-all + reinsert-all（等价全量重建）或 shadow index switch（需 2× 存储 + 构建时间窗口）。

### 2. 真实失效场景

- 推荐系统 embedding model 周期性重训（Meta: 每 1–2 周, Google: 每月, 字节: 每周）
- 十亿规模全量重建：12+ 小时（DiskANN SIFT1B benchmark）
- Shadow switch 需双倍存储（2× 4TB NVMe = $$$）+ 构建期间新数据的双写复杂性
- Drift-Adapter/QDC 是 QUERY-SIDE workaround（映射新 query 到旧空间），不解决 CORPUS-SIDE 的图质量退化

**失败表现：** 要么花费小时级重建（不可接受的运维停机/成本），要么接受持续 recall 退化直到下次重建窗口。

### 3. 架构级桥梁假设

> 因为现有系统把 **图拓扑的有效性** 绑定为"构建时刻的坐标距离关系"，embedding model 变更后拓扑整体失效，只能全量重建。若将重建重构为 **warm-start refinement**——以旧拓扑作为初始化（而非从空图构建），在新坐标空间中只对"确实失效"的边执行局部 re-prune——并能量化"旧图在新空间的结构性复用度"，则重建工作量可能从 O(N×R) 降低到 O(δ×R)（δ = 受影响节点比例）。

核心抽象：**Graph Topology Recycling**——旧图不是垃圾（需要丢弃），而是一个高质量初始解（可以复用和修复）。系统需要的是一个 **差异检测器** + **增量修复引擎**，不是全量重建器。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **FreshDiskANN (2024)** | Streaming + periodic merge rebuild | Merge 不处理坐标变化；它假设 base 坐标不变，只是把新点融入 |
| **Drift-Adapter (EMNLP 2025)** | 学习 query-space 映射，保留旧 corpus embedding | Query-side workaround，不修复图结构；旧图质量仍退化 |
| **HAKES (PVLDB 2025)** | 快速 build/rebuild 系统 | 降低重建时间但仍是全量重建；不复用旧拓扑 |
| **NN-Descent / Refinement** | 迭代式图构建，可从任意初始化开始 | 通用图改进算法，但无人研究"以旧版图为初始化在新空间 refine"的收益/成本；不处理 SSD-resident 场景 |

**需要 Codex 验证的 prior-art 假设：**
1. 是否有论文明确研究"旧 graph 在新 embedding 空间做 warm-start refinement"？
2. HAKES 的 fast rebuild 是否已包含某种 topology recycling 机制？
3. 是否有 NeurIPS/ICML graph learning 工作把"topology reuse across metric changes"作为主题？

**审稿人最强拒稿理由：** "如果新旧 embedding 的 kNN overlap 低（<30%），warm-start 不如 fresh build；如果 overlap 高（>70%），直接用旧图 serve 新 query 也不需要修复。只有中间地带（30–70% overlap）warm-start 才有意义，而这个区间可能很窄或不稳定。"

### 5. 最小 Kill 实验

**必须先获取的数据：** 同一 corpus 在两个真实 model checkpoint 下的 paired embeddings。选项：
- MTEB benchmark 中可用多个 sentence transformer versions（e.g., all-MiniLM-L6-v1 vs v2）
- 或使用 SIFT → 对 SIFT 做 random rotation + small noise 模拟坐标变化（仅作为 sensitivity 附录，不作为主证据）

**实验：**
1. 在旧 embeddings 上建 Vamana 图（DGAI 工具链，SIFT-1M 作为 pilot）
2. 替换坐标为新 embeddings（保持相同 node IDs）
3. 测量：
   - (a) 新旧空间 kNN graph overlap（ground truth 级）
   - (b) 旧图在新坐标下的 recall@10（不修任何边）
   - (c) 违反 α-RobustPrune 条件的节点比例（需要全图扫描邻接表 + 新坐标计算距离）
   - (d) 只对违反节点做 re-prune 后的 recall 恢复
   - (e) 增量 re-prune 的 I/O 成本 vs. 全量 from-scratch rebuild

**通过条件：**
- kNN overlap ∈ [30%, 70%]（问题存在且 warm-start 有意义的窗口）
- 旧图在新空间 recall 下降 > 5%（问题真实）
- 增量修复后 recall 恢复到 fresh-build 的 95%+
- 增量修复 I/O < fresh rebuild 的 50%

**Kill 条件：**
- kNN overlap < 20%（空间差异太大，旧拓扑无复用价值）
- kNN overlap > 80%（差异太小，直接用旧图即可）
- 增量修复 I/O > fresh rebuild 的 70%（warm-start 收益不够显著）

**无真实 paired embeddings 前不进入 DGAI gate。** 第一步是确认是否能获取 ≥2 个 model checkpoints 对同一 corpus 的 embeddings（Codex 可检查 MTEB/HuggingFace 可用性）。

### 6. 系统论文形态

- **核心机制：** 跨空间差异检测（edge validity checker）+ 局部 re-prune 引擎（SSD-efficient batch scan）
- **核心不变量：** recycled graph 的 recall ≥ (1-ε) × fresh-built graph
- **成本模型：** kNN overlap → 需修复节点比例 → I/O 成本（可闭式）
- **端到端系统：** 是。需要完整 pipeline：detect drift → identify broken edges → batch repair → verify quality
- **必要实验：** 多 model pairs 的 overlap/recall 曲线、warm-start vs. fresh rebuild 时间对比、repair 期间 query 不受阻塞、真实 embedding transition（不只 SIFT noise）

---

## 候选 B：筛选型图搜索的 I/O 放大与标签感知存储布局

### 1. 被挑战的架构假设

**"图索引的物理布局只需优化无条件 ANN 搜索的访问局部性；filtered search 是算法层问题。"**

所有 SSD-resident 图索引（DiskANN、OdinANN、NAVIS、DGAI）的节点物理布局由构建时的 graph locality 或插入顺序决定。Filtered search（带 metadata 谓词的 ANN，如"找 category='electronics' 的最近邻"）在图遍历时遇到不满足 filter 的节点，仍然付出了 SSD I/O 代价但结果被丢弃。

### 2. 真实失效场景

**场景：高选择性 filter (selectivity < 10%) + 大规模 SSD 驻盘图索引。**

- Production vector search 中 >60% 的查询带有 metadata filter（Qdrant/Milvus/Weaviate 用户反馈）
- 当 filter 选择性低（如"brand=Nike"只匹配 3% 数据），beam search 需要遍历大量不满足 filter 的节点才能找到 K 个满足条件的结果
- 每个被遍历的不满足 filter 的节点都产生一次 4KB SSD 读
- **I/O 放大 = 总 SSD 读 / 有效 SSD 读**。在 selectivity=3% 时，若图遍历不优化，放大可达 30×+
- 现有算法优化（label-based pruning、filtered entry points）减少了遍历的节点数，但没有减少每个节点的 I/O 成本

**失败表现：** Filtered search QPS 随 filter selectivity 下降呈超线性恶化。IISWC 2025 也报告了 "attribute-based filtering" 场景的极低带宽利用。

### 3. 架构级桥梁假设

> 因为现有系统把 **物理布局** 只绑定为"graph proximity"（图上相近 = 物理相邻），高选择性 filter 遍历时大量读取的页面中包含不满足 filter 的无关节点。若将物理布局重构为 **双维度组织**——在保持图可导航性的前提下，使同一 label 的节点尽量物理聚集（label-clustered pages）——并维护不变量"beam search 每次 page read 中满足当前 filter 的节点比例 ≥ 某阈值"，则 filtered search 的 I/O 放大可显著降低。

核心抽象：**Label-Graph Co-Layout**——不是"先按 label 分区，再在每个分区建独立图"（这会破坏跨 label 的图连通性），而是在统一图内将节点按 (label, graph_proximity) 的联合目标进行物理放置，使得一次 page read 尽量对当前 filter 有效。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **DiskANN Filtered (NeurIPS 2023)** | Label-based graph construction，为每个 label 建独立 starting point | 改变搜索起点和剪枝策略（算法），不改变物理布局（节点仍按构建顺序存储在 SSD 上） |
| **ACORN (SIGMOD 2025)** | Attribute-aware navigable graph construction | 在图构建时考虑 attributes，但论文是内存系统，不处理 SSD 物理布局问题 |
| **Filtered-DiskANN / CAPS** | Pre-filter + post-filter 策略优化 | 减少遍历节点数（算法），不优化 per-page 的 filter-hit ratio（物理布局） |
| **MARGO (PVLDB 2025)** | 按 path importance 重排图节点的磁盘布局 | 优化无条件搜索的局部性，不考虑 label/filter 维度 |
| **Starling / VeloANN** | 空间或 affinity 聚类做物理 co-placement | 按距离/访问亲和聚集，不按 metadata label 聚集 |

**需要 Codex 验证的 prior-art 假设：**
1. 是否有论文将 **SSD 物理布局** 与 **filtered search** 联合优化？（区别于只做算法优化的 DiskANN Filtered / ACORN）
2. MARGO 是否考虑了带 filter 的 workload mix？
3. 是否有数据库系统在 B-tree/LSM 上做"label-clustered layout"的先例，可以直接迁移到图索引？
4. Qdrant 或 Milvus 的 segment 策略是否已按 label partition（实质上等价于 label-clustered layout）？

**审稿人最强拒稿理由：** "Label-clustered layout 就是 per-label partition + cross-partition edges，这是朴素的 partitioned graph；且动态更新时维护 label clustering 的成本（node migration when label changes / new inserts break clustering）可能过高。简单baseline 是 per-label building a separate small graph，在低选择性时直接搜该小图。"

### 5. 最小 Kill 实验

**输入：** SIFT-1M + 合成 label（zipf 分布，20 个 label，最稀疏 label 占 1%）

**Baseline：** 
- DGAI 默认布局 + DiskANN-style label filtering 的 filtered search QPS 和 I/O amplification
- 独立 per-label 小图（partition baseline）的 recall 和 QPS

**实验：**
1. 在标准 DGAI 图上执行 filtered search（beam search + filter check），记录每次搜索的总 page reads 和 filter-matching page reads。计算 I/O amplification。
2. 将节点按 (label, graph_proximity) 重排物理位置，重新存储到 SSD。测量相同 query 下的 I/O amplification。
3. 对比 partition baseline（每个 label 独立建图 + 合并结果）的 recall。

**通过条件：**
- 默认布局下 selectivity < 5% 的 filter query 的 I/O amplification > 10×（问题存在）
- Label-clustered layout 的 I/O amplification 下降 ≥ 50%
- Label-clustered layout 的 recall 不低于 partition baseline

**Kill 条件：**
- I/O amplification < 3× 即使在 selectivity 1%（问题不存在，filter pruning 已经足够）
- Label-clustered layout vs. default 的 I/O 差异 < 20%（布局改变没有显著效果）
- Partition baseline 在所有 selectivity 下都优于 unified graph（统一图本身是错误选择）

**所需：** 3–4 天。合成 label assignment、物理重排脚本、filtered search instrumentation 约 250 行。SIFT-1M ~2 GB。

### 6. 系统论文形态

- **核心机制：** Label-Graph Co-Layout 算法 + 动态维护协议（insert/delete 时保持 label clustering）
- **核心不变量：** per-page filter-hit ratio ≥ 下界（对当前 workload 的 dominant filters）
- **成本模型：** selectivity × layout_quality → I/O_amplification 的闭式关系
- **端到端系统：** 是。需要完整的 build + serve + dynamic update，且需要多 label workload
- **必要实验：** 多 selectivity 下的 I/O amplification 曲线、vs. DiskANN Filtered / ACORN / partition baseline、动态更新下布局维护开销、真实 label workload（Qdrant/Milvus benchmark traces if available）

---

## 候选 C：外存图构建——有限 DRAM 下的十亿级图索引快速构建

### 1. 被挑战的架构假设

**"图索引构建需要全量 PQ 码和向量驻留内存以支持随机访问距离计算。"**

DiskANN、OdinANN、PipeANN 的构建流程假设：RobustPrune 过程中需要随机访问任意两点间的 PQ 距离（用于候选排序和剪枝决策）。十亿级 PQ 码占 32–128 GB DRAM；全精度向量更多。这使得构建阶段对硬件的要求远高于服务阶段（服务时 AiSAQ/LM-DiskANN 已证明可用 <1GB DRAM）。

### 2. 真实失效场景

**场景：十亿级索引构建在受限硬件或频繁重建需求下。**

- 服务阶段：AiSAQ 证明 10 MiB DRAM 即可服务十亿级查询
- 构建阶段：仍需 32–128 GB DRAM 装载 PQ 码以执行 RobustPrune
- 结果：构建需要的服务器 spec 远高于服务，导致额外硬件成本或长时间占用生产机器
- 与候选 A（embedding migration）组合：如果模型每周重训需要重建，且每次重建占用高配机器 12+ 小时，运维成本极高
- 云实例：构建时租用 256 GB RAM 实例 12 小时 ≈ $30–100；若能用 32 GB 实例完成（可能更慢但更便宜），总成本可能更低

**失败表现：** 构建成为十亿级 ANN 系统的运维瓶颈——不是因为算法慢，而是因为硬件要求高。

### 3. 架构级桥梁假设

> 因为现有系统把 **构建阶段的距离计算** 绑定为"全量 PQ 在内存中随机访问"，有限 DRAM 下构建不可行。若将构建重构为 **分区-本地构建 + 跨分区连边**——先把数据按空间分区（每个分区 fit 在 DRAM 中），独立构建分区内图，再用 SSD-efficient 的 batch 访问模式计算跨分区边——并维护不变量"跨分区连通性使全局 recall 不低于全内存构建的 95%"，则构建可在 O(partition_size) DRAM 中完成。

核心系统问题：如何设计 **SSD-efficient 的跨分区边计算**？朴素方法（对每个 border 节点随机读取远程分区的候选）产生海量随机 I/O。需要 batch + sort + merge 的外存算法思路。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **DiskANN 原始 build** | 2-pass build (in-memory → prune to disk) | 全量内存假设；不处理 DRAM < PQ size 场景 |
| **SPANN (NeurIPS 2021)** | 按 cluster partition 构建，每 cluster fit in RAM | IVF-based，不是 Vamana graph；cluster 间用 centroid 路由不是图边 |
| **BigANN (NeurIPS 2021 competition)** | 十亿级 graph build | 使用大内存机器（>256 GB），不处理受限 DRAM |
| **External-memory graph algorithms** | I/O-efficient graph construction (theory) | 通用理论，无 ANN/Vamana 特化 |
| **PageANN (2025) / SkipDisk (2026)** | 受限内存的图 **查询**（非构建） | *需要 Codex 验证：这些是否也解决了构建阶段的内存问题？* |

**需要 Codex 验证的 prior-art 假设：**
1. PageANN 和 SkipDisk 是否处理了 BUILD phase 的内存限制，还是只处理 SERVE phase？
2. 是否有论文明确研究"external-memory Vamana/DiskANN construction"？
3. LM-DiskANN 的 build process 是否也需要全量 PQ 在内存？
4. ParlayANN 或其他并行构建库是否有外存 variant？

**审稿人最强拒稿理由：** "Partition-then-connect 是 SPANN/IVF 的图版本；如果 partition 足够多以 fit in RAM，跨分区边计算的随机 I/O 使构建总时间反而更长（I/O-bound 比 compute-bound 慢）。不如直接租一台大内存机器构建。"

### 5. 最小 Kill 实验

**输入：** SIFT-1M，人为限制可用 DRAM 为 32 MB（模拟十亿级中每分区 ~1M 的场景）。

**Baseline：** 全 PQ 内存构建的 DGAI graph，recall@10。

**实验：**
1. 将 SIFT-1M 按 k-means 分成 K=10 个分区，每分区 100K 向量（PQ 约 3.2 MB，fit in 32 MB DRAM）
2. 为每个分区独立构建 Vamana 子图
3. 用 batch I/O 方式计算跨分区 border 节点的边（扫描相邻分区的 PQ 码，sort-merge join 思路）
4. 测量：（a）全局 recall@10；（b）总构建时间 vs. full-memory build；（c）跨分区 I/O volume

**通过条件：**
- 全局 recall ≥ 0.90 × full-memory baseline
- 构建时间 ≤ 5× full-memory build（I/O penalty acceptable）
- 跨分区边计算可通过 sequential scan 完成（non-random I/O pattern）

**Kill 条件：**
- 全局 recall < 0.75（分区方法导致不可恢复的 connectivity loss）
- 构建时间 > 20× full-memory（I/O 代价过高，不如租大机器）
- 跨分区边计算仍需大量随机 I/O（external-memory 方法不适用）

**所需：** 4–5 天（k-means partition + per-partition build + cross-partition edge computation 约 400 行）；~5 GB 磁盘。

### 6. 系统论文形态

- **核心机制：** 分区-本地构建 + external-memory 跨分区连边算法
- **核心不变量：** 全局图的 greedy navigability（从任意入口可 greedily 到达真实最近邻）
- **成本模型：** DRAM_budget × partitions → I/O_cost × build_time 的 trade-off 模型
- **端到端系统：** 是。需要完整的 partition + build + connect + serve 流程
- **必要实验：** SIFT1B 级构建在 32/64/128 GB DRAM 下的 recall/time 曲线、vs full-memory DiskANN build、vs SPANN（IVF baseline）、incremental rebuild（与候选 A 组合的可行性）

---

## 总结

| 候选 | 问题来源 | 系统味道 | 核心不确定性 | Prior-art 风险 |
|---|---|---|---|---|
| A：Warm-start 重建 | Codex REVISE | 中-强（SSD-efficient scan/repair） | kNN overlap 窗口是否存在 | 中（NN-Descent warm-start 可能已有研究） |
| B：Filtered search I/O 放大 | Production pain | 强（物理布局 co-design） | Partition baseline 是否足够 | 中-高（可能已有 Milvus segment 策略覆盖） |
| C：外存图构建 | 运维痛点 | 强（external-memory algorithm） | 跨分区连边的 I/O efficiency | 中（可能 PageANN/HAKES 已覆盖） |

个人排序：B > A > C。候选 B 的"物理布局与 filter 联合优化"是一个纯粹的存储系统问题（data placement optimization under heterogeneous access patterns），与 PZ 的背景最匹配，且不太可能被纯算法工作覆盖（ACORN、DiskANN Filtered 都不处理物理布局）。但需要 Codex 确认 MARGO 和 Milvus segment 策略未覆盖此点。
