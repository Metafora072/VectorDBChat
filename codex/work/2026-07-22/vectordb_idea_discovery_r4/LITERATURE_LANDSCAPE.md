# R4 Literature / Mechanism Landscape

日期：2026-07-22

本轮复用 R2/R3 已严格覆盖的 2024--2026 Kill Map，但改变门禁时机：Phase 0 只杀“机制同构”与“纯工程”，不因算法尚未成熟而提前杀。检索单位仍是 `state -> action -> objective -> guarantee`，而不是题名。

## 1. 继承的硬边界

| 区域 | 机制级最近工作 | R4 边界 |
|---|---|---|
| 动态图插入/删除/修复 | SPFresh、FreshDiskANN、CleANN、OdinANN、Slipstream、MFLI、LSM-VEC | 普通 update、merge、local repair、arrival-aware edge rule 仍 KILL；只有利用“点的小幅运动界”而非无关 delete+insert 的 kinetic contract 暂留。 |
| adaptive beam / stopping / hard query | DARTH、DABS、Ada-ef、ConANN、GATE、PAG | 换 beam、阈值、hardness score 仍 KILL。 |
| workload/query-aware index | Quake、DQF、GATE、CleANN | query frequency 驱动重连、入口或维护仍 KILL。 |
| filtered / temporal / multi-vector | UNIFY、SIEVE、Curator、TANNS、TiGER、MUVERA、PLAID、WARP、MV-HNSW | 不再生成简单变体。 |
| embedding migration | FastFill、Metric-Compatible Backfilling、Drift-Adapter、Embedding-Converter | Seed A 与 partial re-embedding scheduling 继续 KILL。 |
| closed-loop / multi-query | RaLMSpec、Rethinking MQO、QVCache、relevance feedback | Seed B 继续 KILL；外生、尚未完成的查询向量是不同问题，但须越过 continuous/kinetic NN 与 speculative retrieval。 |
| 新 query primitives | SimJoin、DiskJoin、Range Retrieval、OMEGA、probabilistic NN、Gumbel/RF/MIDX sampling | join/range/multi-k/probabilistic/sampling 的普通改名继续 KILL。 |

## 2. R4 新检索到的拥挤机制

| 现象轴 | 最近工作/经典先例 | 对候选的约束 |
|---|---|---|
| 建索引期间可查询 | PANENE、progressive indexing；2024 Revisiting PG Construction；2025 Flash construction | “边建边查”不是新问题；只有新的累计效用目标仍不足以单独立项。 |
| 构建顺序与稳定性 | [HNSW ordering study (2024)](https://arxiv.org/abs/2405.17813)、Lucene LUCENE-10421、ACL Industry 2025 | 现象明确，论文缺口只可能是 matched-recall 下的 result-set stability；固定 seed/canonical order 是致命基线。 |
| query prefix / speculation | [Extremely Efficient Online Query Encoding (2024)](https://aclanthology.org/2024.findings-naacl.4/)、[RaLMSpec, ICML 2024](https://proceedings.mlr.press/v235/zhang24cq.html)、HaS 2026、SOSP 2025 speculative retrieval | 只“提前搜”已被覆盖；必须是 ANN 搜索状态在有界 query drift 下的可验证复用。 |
| 多查询共享 | Rethinking Multiple-Query Optimization for ANNS、CABANA 2025 | batching/cache/entry reuse 不是 novelty；需要共享几何证书或直接 KILL。 |
| 量化与排名 | [ScaNN anisotropic quantization](https://arxiv.org/abs/1908.10396)、RaBitQ 2024、LeanVec 2024、LVQ、AQR-HNSW 2026、[BQ ranking-fidelity theory 2026](https://arxiv.org/abs/2605.17524) | 最小 MSE 不是唯一旧目标；候选必须区别于全局 ranking-aware loss，聚焦 fixed-byte 下 per-object/region precision allocation。 |
| 分布式 ANN | LANNS、DistVS/SPIRE/BatANN、DSANN 2025、Puffin-backed index 2026、经典 Threshold Algorithm | 只有可组合的 omission certificate 可能越界；若 tight bound 与扫描等价则 KILL。 |
| semantic aggregate | CANDE、KDE、kernel sampling | COUNT/SUM/KDE 已机制同构，KILL。 |
| downstream similarity graph | [Fast Approximation of Similarity Graphs, NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/d5c56ec4f69c9a473089b16000d3f8cd-Abstract-Conference.html)、Spectral Sparsification of Metrics and Kernels、NN-Descent | 仅“用谱指标评价近似 kNNG”不够；必须主动发现对 cut/eigenspace 关键、但当前候选图缺失的边。 |
| result payload | PipeANN/LAANN/LIOS/VeloANN 优化 index/vector I/O；generic prefetch/late materialization | payload-complete latency 是真实缺口，但必须证明 ANN candidate survival 有稳定可利用结构，否则只是 generic prefetch。 |
| corpus/index pruning | passage-quality static pruning 2024、RAG chunk filtering 2026、multi-vector prune/merge 2026 | 索引对象子集选择已拥挤。 |
| no-match / task metrics | Relevance Filtering 2024、Semantic Recall 2026、Recall What Matters 2026、selective/conformal retrieval | 只换 metric、阈值或校准层不构成 ANN 算法。 |

查新后追加三条决定性边界：

- [Dynamic Similarity Graph Construction with KDE, ICML 2025](https://proceedings.mlr.press/v267/laenen25a.html) 已把 cluster-preserving similarity graph 推进到动态构造；P01 不能再靠“预算化/动态化”与 NeurIPS 2023 拉开距离。
- [Optimistic Query Routing in Clustering-based MIPS, NeurIPS 2025](https://www.microsoft.com/en-us/research/publication/optimistic-query-routing-in-clustering-based-approximate-maximum-inner-product-search/) 已用 shard 内积分布与常数大小 moment sketch 决定要探测的 shards；P07 的自适应深化必须同时越过该工作与经典 distributed top-k threshold protocol。
- [Yi: Efficient and Effective In-place Graph-based Vector Index Updates (2026)](https://arxiv.org/abs/2607.15576) 已直接优化 vector-level in-place updates。P03 尚可凭 per-object displacement contract 与之区分，但不能再把“避免 delete+insert”本身作为贡献。

## 3. Workload evidence

1. pgvector 文档明确说明 approximate index 会改变结果，HNSW 构建具有非确定性；过滤还可能导致结果不足。
2. ACL Industry 2025 在 BEIR/Lucene 上报告 HNSW 构建时间、质量退化与不同 trial 的波动，说明 build lifecycle 与 reproducibility 不是虚构场景。
3. Lucene 与 Faiss issue 均有相同数据重建后结果不同的用户报告。
4. Qdrant 的公开 issue 出现重度 ingestion/rebuild 后 approximate quality 大幅下降，说明 recall regression 难以及时观察；但“监控它”本身仍偏诊断。
5. Milvus 已支持 entity-level multi-vector/MAX_SIM，进一步压缩 grouped multi-vector 的 novelty 空间。
6. 产品实践中 payload/metadata 返回和网络延迟可超过纯 ANN ID search；但论文必须把这一事实转成新的 ANN-specific scheduling problem。

## 4. Phase-0 ruling

R4 不再把 `尚无紧界`、`只做了现象假设` 当作概念期 KILL。保留池进入 A-1 后，再用以下必要条件强杀：

- 现象在真实或标准预生成 embedding 上存在；
- oracle 上限都不能显著优于强 baseline 时直接 KILL；
- 所需 certificate 在高维下 vacuous 时直接 KILL；
- 核心收益可由 fixed seed、提高 ef、uniform bits、普通 batching 或 generic prefetch 获得时直接 KILL。
