# Phase 0：VectorDB / ANNS 2024–2026 机制级 Kill Map

日期：2026-07-22

本轮把检索单位从论文题名改为 `state → action → objective → guarantee`。没有同名论文不构成 novelty；凡是最近机制已经覆盖问题中的关键 action/目标，或本地 A0 已否定必要现象，均进入 Kill Map。

## 1. 强制覆盖区

| 区域 | 2024–2026 最近工作与更早直接先例 | 机制边界 | 本轮裁决 |
|---|---|---|---|
| 动态图 ANN：插入、删除、修复、并发 | [SPFresh, SOSP 2025](https://arxiv.org/abs/2410.14452)、FreshDiskANN、[CleANN](https://arxiv.org/abs/2507.19802)、[OdinANN, FAST 2026](https://www.usenix.org/conference/fast26/presentation/guo)、[Slipstream](https://arxiv.org/abs/2606.02992)、[MFLI](https://arxiv.org/abs/2602.16124)、IP-DiskANN、Wolverine | merge/split、local repair、lazy deletion、concurrent maintenance、arrival-aware updates 已形成密集机制族。 | 新局部 edge score、repair threshold、batch rule：**KILL**。 |
| Streaming ANN / 连续向量流 | Big-ANN Streaming、Streaming Vector Quantization、SPFresh、Slipstream、dynamic-dataset studies | arrival、bounded memory、online quantizer/index update 已被直接覆盖。只有改变查询语义或数据不确定性才可能越界。 | 通用 streaming insert：**KILL**。 |
| Adaptive beam / early termination / hard query | [DARTH](https://arxiv.org/abs/2505.19001)、DABS、Ada-ef、ConANN、GATE、PAG | query difficulty、recall prediction、adaptive `ef`、stopping certificate/estimator 均拥挤。 | 换 beam/阈值/难度分：**KILL**。 |
| Workload-aware / query-aware construction | Quake、GATE、CleANN、hard-query repair、workload-aware graph partition/rewiring | query log 已被用于分区、入口、边与维护。 | query frequency × repair 的变体：**KILL**。 |
| Filtered / dynamic filtered / multi-predicate | UNIFY、SIEVE、Curator、GateANN、dynamic range-filtered ANN、KHI、RNSG | label graph、range predicate、multi-attribute filtering、dynamic update 都已有强工作。 | 且偏企业语义，本轮整体：**KILL**。 |
| Embedding migration / cross-version | [FastFill](https://arxiv.org/abs/2303.04766)、[Metric-Compatible Online Backfilling, WACV 2025](https://openaccess.thecvf.com/content/WACV2025/html/Seo_Metric_Compatible_Training_for_Online_Backfilling_in_Large-Scale_Retrieval_WACV_2025_paper.html)、Drift-Adapter、Embedding-Converter、query-drift compensation | partial backfill policy、uncertainty ordering、mixed-version rank merge/compatibility 已直接出现。 | Seed A 及通用 priority scheduling：**KILL**。 |
| Multi-vector / late interaction | [MUVERA, NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/hash/b71cfefae46909178603b5bc6c11d3ae-Abstract-Conference.html)、PLAID、WARP、GEM、XTR、alpha-reachable graphs | fixed-dimensional encoding、centroid/token pruning、late-interaction graph search 已密集。 | 新 token/page threshold：**KILL**。 |
| Adaptive query / sequence / closed loop | adaptive distance estimation、multi-query optimization、QVCache、relevance feedback、adversarial adaptive queries | repeated-query reuse、randomness robustness、反馈检索均有先例；此前 Trajectory-Stable A0/审阅又证明核心算法身份不足。 | 通用 trajectory budget：**KILL**。 |
| Diverse / fair / robust / adversarial | diverse kNN、multi-attribute fair kNN、robust ANN、RetrievalGuard、adversarial ANN | objective 与约束已有直接定义；安全/对抗方向也不符合本轮偏好。 | 本轮不延伸：**KILL**。 |

## 2. 放宽后新增的机制区域

| 新区域 | 最近邻机制 | 结论 |
|---|---|---|
| Similarity join / all-pairs retrieval | [SimJoin, SIGMOD 2025](https://dl.acm.org/doi/10.1145/3725403)、[DiskJoin](https://arxiv.org/abs/2508.18494) | self/cross join、disk join 已是独立成熟问题；不能把 top-k ANN 改名为 join。 |
| Reverse / range / multi-k NN | ICDE 2024 reverse kNN、[Range Retrieval](https://arxiv.org/abs/2502.13245)、[OMEGA multi-K](https://arxiv.org/abs/2603.06159) | query primitive 已有专门索引和界；“支持另一个 k/range”不足。 |
| Certified graph navigation | [Certified HNSW](https://arxiv.org/abs/2607.02338)、[Almost Navigable Graphs](https://arxiv.org/abs/2607.14564) | graph-search certificate/navigation 理论在 2026 年快速拥挤；普通 frontier 不能界定 unseen objects。 |
| Semantic rather than geometric recall | [Semantic Recall for Vector Search](https://arxiv.org/abs/2604.20417) | 已直接质疑几何 Recall@k 与任务效用的错位。若只换 metric，不足形成算法。 |
| Distribution/uncertainty-valued objects | [DINOSAUR](https://arxiv.org/abs/2606.04603)、probabilistic NN、NNS under uncertainty | 不确定向量查询不是空白；仍可能有“compact fresh-world top-k”窄缺口，需算法 A0。 |
| Capacity/global assignment | Capacity-Constrained Assignment (SIGMOD 2008)、Approximation Algorithms for Bipartite Matching with Metric and Geometric Costs (STOC 2014) | 已直接把增量 NN oracle 用于容量匹配，并有高维近似匹配算法。集体 Hall 缺口不是新算法。 |
| Similarity-proportional sampling | Gumbel-MIPS、Fast Sampling for MIPS、RF-softmax、LSH sampling、MIDX sampler | sampling primitive、Gumbel trick 与近似归一化已有直接路线。 |
| Mixed fidelity / variable dimension | Matryoshka Representation Learning、AdANNS | 按查询/对象调整表示维度与搜索精度已出现。 |
| Grouped/distinct-ID retrieval | group-aware/vector-database product primitives、distinct nearest neighbor、diversified kNN | group cardinality/去重是已知语义；需要强新结构而非 post-filter。 |

## 3. 经典工作造成的跨年份硬边界

2024–2026 检索不能忽略早期直接机制：

1. **容量约束检索**：SIGMOD 2008 的 Capacity-Constrained Assignment 已给出基于增量 NN 的 NIA/IDA；STOC 2014 又给出 metric/geometric-cost bipartite matching 的 ANN 加速。这直接击穿“Hall witness + ANN 扩候选”的 novelty。
2. **概率最近邻**：VLDB 2008 已定义 top-k probable NN；uncertain database 系列研究对象分布和概率结果。新工作必须在查询语义、存储复杂度和 oracle 上同时越界。
3. **反馈检索**：早期 relevance-feedback kNN 已把 approximate NN 放入迭代循环。Trajectory error propagation 不能靠新名字成立。
4. **相似度采样**：Gumbel-Max/MIPS、LSH sampling、RF-softmax 已覆盖按相似度分布抽样的主要套路。

## 4. 本地实验 Kill Map

| 方向 | 本地证据 | 结果 |
|---|---|---|
| Graph aging / dynamic SSD maintenance | churn 后 distinct pages/query 下降 3.76%/6.12%；in-place 写放大为 COW 的 4.03×。 | **KILL** |
| Budgeted migration / MOVE | 迁移阶段 kNN overlap 0.847–0.894，但 sound region envelope 的 p50 候选膨胀为 17.25–47×；简单 margin certificate 为 0。 | **KILL** |
| Region certificate | 100K×128 合成数据中，p50 需扫描约 100%，zero lower-bound cell 达 69.7–89.2%。 | **KILL** |
| Capacity collective ANN | 相对 uniform top-L 有正信号，但候选生成没有实际 ANN 加速，且被 SIGMOD 2008/STOC 2014 直接先例覆盖。 | **KILL-NOVELTY** |
| Compact fresh-world distributional ANN | 小不确定性下 HNSW-UCB 与 mean-overfetch 的 Recall 差仅 0.43 point；较大不确定性下 exact UCB 枚举 p50 需 2,240–7,365/20K 对象，HNSW-UCB Recall 降至 0.816/0.695。 | **KILL-MECHANISM** |

## 5. Phase 0 结论

本轮没有发现可诚实升级为论文主线的空白。剩余“空白”大多属于三类：

- 问题新但可靠 oracle 退化为大扫描；
- 现象存在但最接近算法早已由经典 assignment/probabilistic-NN/sampling 工作覆盖；
- 可实现但贡献只剩 query score、阈值或 over-fetch。

因此 Phase 0 的正确产物是 **零保留**，而不是从 HOLD 候选中拼装系统。
