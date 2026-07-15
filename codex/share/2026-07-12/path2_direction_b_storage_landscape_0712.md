# 路径二方向 B：向量存储效率与分层管理 prior-art 审计

日期：2026-07-12

## 执行摘要

本轮结论不是“方向 B 仍是一块低密度空白”。截至 2026 年 7 月，静态向量压缩、DRAM/SSD/object storage 分层、冷热加载、渐进精度、full-vector rerank、删除回收和 store-vs-recompute 已分别被论文或生产系统覆盖；其中 Claude 初表没有纳入的 **DecoupleVS、LEANN、FaTRQ、Milvus 2.6、S3 Vectors** 显著改变了判断。

因此，以下题目不应再立项：普通 hot/cold tiering、普通 PQ/SQ/低比特量化、相邻向量 XOR/delta compression、vector/index decoupling、删除后 segment GC、把 full vector 放远端并渐进 rerank、以及“不存 embedding、查询时重算”。方向 B 尚可验证的空间已经从“再发明一个 codec 或 tier”收缩到 **representation lifecycle 与 query-control-aware physical design**。

本轮没有候选达到可直接实现的 `PROVISIONAL`。唯一建议做零实现 G0 的窄假设是：**以 graph search routing-criticality 而非重构误差来分配异构精度**。跨 embedding 版本 lazy migration 和 snapshot-consistent ANN 是相邻问题登记项，但前者必须继承刚刚完成的 topology-reuse Kill 边界，后者必须先证明真实需求；均不能直接实验。第二评审者提出的 query-frontier cooperative I/O fusion 与 M08 deferred coalescing 的既有 Kill 路线重合，本轮明确驳回。

## 1. 覆盖版图

| 问题单元 | 代表工作 | 已覆盖内容 | 对新 idea 的约束 |
|---|---|---|---|
| 四级存储 + 冷热搜索 | [VStream, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p1593-gao.pdf) | state memory、local memory、local disk、remote disk；按访问、命中、贡献、freshness 排序并 early stop | “向量冷热分层”本身已不是空白 |
| 跨向量无损压缩 | [VStream](https://www.vldb.org/pvldb/vol18/p1593-gao.pdf) | 相邻向量逐维 XOR，再以 Gorilla 编码；报告 61%–65% compression ratio | 普通 delta/XOR idea 已覆盖；而且论文已显式处理递归解码和 cache |
| 向量/元数据解耦与专用压缩 | [DecoupleVS, 2026 preprint](https://arxiv.org/abs/2604.09173) | vector/index 分文件；chunk base XOR+Huffman；邻接 Elias–Fano；随机读取、prefetch、append-only vector、segment GC | “解耦后各自压缩、回收、预取”整组已被占据 |
| 精度—介质协同 | [DistVS, NSDI 2026](https://www.usenix.org/conference/nsdi26/presentation/yin) | compute 侧低精度、远端内存高精度、SSD 全精度，PRESS 渐进筛选 | 固定的三层渐进精度已覆盖 |
| 远内存 residual refinement | [FaTRQ, 2026 preprint](https://arxiv.org/abs/2601.09985) | tiered residual quantization、渐进 distance estimator、可证 early stop、CXL 侧 refinement | “分层 residual + 不读 full vector”也已有直接竞争者 |
| 对象存储冷向量 | [Milvus 2.6 tiered storage](https://milvus.io/docs/tiered-storage-overview.md)、[Amazon S3 Vectors](https://aws.amazon.com/s3/features/vectors/) | segment/index 按需加载与驱逐；对象存储原生低成本向量查询 | 仅把冷数据移到 object storage 是产品功能，不是研究贡献 |
| Store vs. recompute | [LEANN, MLSys 2026](https://arxiv.org/abs/2506.08276) | 紧凑图 + selective on-the-fly embedding recomputation；索引小于原始数据 5% | “不保存 embedding、需要时重算”已覆盖 |
| 动态 LSM 存储 | [LSM-VEC, 2025 preprint](https://arxiv.org/abs/2505.17152) | 图边进入 LSM levels、out-of-place updates、compaction、query heatmap reordering | LSM 化与 compaction/reorder 已覆盖 |
| 删除与空间回收 | [GaussDB-Vector, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p4951-sun.pdf)、DecoupleVS | 10% tombstone 触发 vacuum；segment garbage-ratio 触发异步 GC | 普通 vacuum/GC 不是空白 |
| 冷索引零内存成本 | [Cosmos DB DiskANN, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p5166-upreti.pdf) | Bw-Tree term storage、按需缓存、cold collections 不占最低内存 floor | 长尾冷 collection 的基本 cost story 已覆盖 |
| 压缩后不保留 full vector | [LVQ, PVLDB 2023](https://www.vldb.org/pvldb/vol16/p3433-aguerrebere.pdf) | per-vector local adaptation + 两级 remainder，避免 auxiliary full vectors | “压缩 + residual rerank，无原向量”已覆盖 |
| 有误差界的低比特表示 | [RaBitQ, PACMMOD 2024](https://arxiv.org/abs/2405.12497)、[TurboQuant, ICLR 2026](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/) | D-bit 表示与理论界；data-oblivious 极低比特压缩 | 单纯发明低比特 codec 的竞争强度极高 |
| 降维 + 量化 | [LeanVec](https://arxiv.org/abs/2312.16335)、[AdANNS](https://arxiv.org/abs/2305.19435) | ID/OOD 降维；Matryoshka representation 在 ANNS 各阶段使用不同容量 | progressive dimension/compute-aware search 已覆盖 |
| 在线/个性化量化 | [Quantization under Streaming Updates](https://arxiv.org/abs/2512.18335)、[Individualized non-uniform quantization](https://arxiv.org/abs/2509.18471) | stream distribution 下维护 quantizer；逐向量 non-uniform quantization | “每个向量不同精度”字面上也不是空白 |
| 分布式 filter/refine 解耦 | [HAKES, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p3049-ooi.pdf) | compressed filter layer 与 full-vector refine layer 独立扩展；学习压缩参数 | 分离压缩搜索和 exact refine 已覆盖 |
| multi-vector storage | [Constant-Space MVR](https://arxiv.org/abs/2504.01818)、[Multi-Vector Index Compression](https://arxiv.org/abs/2602.21202)、[ColBERTSaR](https://arxiv.org/abs/2606.05568) | 固定向量预算、跨模态 token 压缩、稀疏/倒排化 | 多向量存储是活跃赛道，但不是无人区 |

## 2. 四个关键边界修正

### 2.1 VStream 已覆盖 cross-vector compression

VStream 不是只把 vector segment 放入不同介质。它先通过 LSH/space-filling curve 让相近向量进入同一分区，再保留首向量，并把后续向量与前一向量逐维 XOR 后进行 Gorilla 可变长编码。论文也明确承认这种链式编码破坏随机访问，因此缓存的是解压值，并从最近 cached vector 开始恢复。也就是说，“利用相似向量做 delta encoding，再加 cache 缓解解码链”已经有直接 prior art。

### 2.2 DecoupleVS 封住了最自然的系统补丁

DecoupleVS 对向量选择以 chunk base 为参照的 lossless XOR/Huffman，对邻接 ID 选择 Elias–Fano；同时提供 block/chunk/segment hierarchy、sparse locator、compressed-neighbor cache、adaptive prefetch、append-only update 和 segment GC。它报告相对 DiskANN 最高 58.7% 空间下降。由此，“把 vector 与 adjacency 拆开，再各自压缩和回收”的整套设计不能作为新系统骨架。

### 2.3 分层不仅是 hot/cold，也已经与 precision 联动

DistVS 将 low/high/full precision 映射到 compute/memory server/SSD，FaTRQ 又把 residual 分层并以 distance bound 决定是否继续 refinement。VStream/Milvus 已处理热度，S3 Vectors 已提供低成本冷查询。因此新工作若只是在 DRAM、SSD、object store 上分别放 FP32、INT8、PQ，并根据频率迁移，容易被评为现有组件拼装。

### 2.4 “full vector 可丢弃”已有三种答案

LVQ 用二级 remainder 避免保存原向量；FaTRQ 用远端 residual 渐进精化而不取 full vector；LEANN 在本地 RAG 场景直接按需重算 embedding。新的 store/recompute 方案必须解释它处理的 lifecycle 或一致性约束，而不能只展示空间下降。

## 3. 候选与裁决

### B1. Routing-criticality-aware heterogeneous fidelity

**状态：仅 `Continue-to-trace-G0`，不是立项。**

核心假设不是“重构误差大的向量多给 bits”，而是 graph traversal 中少量节点的距离顺序误差会改变 frontier、停止点或后续页面集合；这些 routing-critical 节点应拥有更高 precision 或更完整 residual，而低影响节点可以更激进压缩。优化目标是固定 byte budget 下的 **marginal Recall–I/O benefit**，而不是 MSE、norm、density 或统一 code length。

最近风险工作是 Individualized non-uniform quantization、AQR-HNSW、VSAG、RaBitQ 和 HAKES。当前检索没有确认这些工作以 counterfactual frontier flip 作为逐节点 bit-allocation objective，但这个差异仍可能被审稿人视为“换了 importance score”。

零实现 G0：在现有 DGAI/DiskANN 查询 trace 上，为各节点注入 4/8/16-bit codec 的真实 distance error；重放相同 frontier，统计哪些节点的 score perturbation 改变 expansion、termination 或 page set。使用一个离线 knapsack 将 bit budget 分给高 criticality 节点，对比 uniform precision、reconstruction-error allocation、density allocation。至少跨 SIFT、GIST 和一个 768D deep-text dataset。

预注册 Kill：同字节下 Recall@10 或 unique-page Pareto 改善不足 5%；criticality 在 query split、时间窗或数据集间不稳定；所需 metadata 超过节省空间的 5%；训练 trace 上有效但 held-out query 上消失。只有跨 workload 出现大且稳定的 Pareto gap，才值得进入 novelty 深查。

### B2. 跨 embedding 版本 lazy migration

**状态：登记为相邻 lifecycle 问题，不重启实验。**

可能机制是旧空间只负责 routing，候选按需取得新 embedding 并逐步物化新索引。然而它必须同时面对 Drift-Adapter、LEANN 和刚刚关闭的 one-topology/multi-coordinate G1。Claude 已指出相近模型上的有效性不能外推到跨家族升级，且旧 topology finding 本身撑不起系统贡献。因此本轮不因第二评审者推荐就重新进入 G0。只有出现真实的在线 migration workload、明确的 rebuild SLO，以及区别于“映射 query 回旧空间”的新一致性/迁移机制时才重审。

### B3. Snapshot-consistent ANN physical sharing

**状态：`Problem-to-validate`，属于方向 A/B 交界。**

候选问题是多个可查询历史 epoch 共享 immutable base vector/graph pages，只用 edge patches、tombstones 和 changed vectors 表示版本。LSM-VEC、DecoupleVS 和 GaussDB-Vector 没有以 time-travel snapshot 为核心，但普通 MVCC/LSM 已提供强 prior art。必须先找到 CDC replay、RAG audit 或 reproducible retrieval 的真实历史查询需求；若没有生产需求，它只是“把 MVCC 套到 ANN”。不应先做实现。

### B4. Query-frontier cooperative I/O fusion

**状态：Kill，不再做 trace gate。**

第二评审者建议用微秒窗口合并并发查询的相同 page read。它在读路径上与 M08 deferred topology write coalescing 不完全相同，但核心价值仍依赖大页域中的短窗碰撞。既有 EXP-5 已证明：R64 在真实 100 ms 窗口只有 1.03×，32-thread 模拟也只有 2.10×；按 1B 规模 66.67M pages 外推，batch=1000 仅 1.0005×。没有新的跨查询 page-overlap 证据足以推翻该规模规律；同时普通 cache/request coalescing 构成强攻击。因此不以“read-side”换名复活。

## 4. 明确 Kill registry

| 候选字面 | Kill 原因 |
|---|---|
| 相邻向量 lossless delta/XOR | VStream 与 DecoupleVS 已直接覆盖两种 reference 组织及 cache/random-read 路径 |
| vector/adjacency 分离压缩 | DecoupleVS 完整覆盖 |
| hot vector 放 DRAM、cold vector 放 object storage | VStream、Milvus 2.6、S3 Vectors 已覆盖研究与产品两侧 |
| low/high/full precision 三层 | DistVS 与 FaTRQ 已覆盖 |
| 删除 tombstone 后后台 GC/vacuum | GaussDB-Vector、DecoupleVS、LSM-VEC 已覆盖 |
| 不存 full vector，查询时重算 | LEANN 已覆盖 |
| certificate 决定是否读取 full vector | RaBitQ/FaTRQ/已有 bound-based rerank 太接近，单独贡献弱 |
| 按维度 stripe，partial distance 后少读页面 | 传统 partial-distance elimination；SSD block/IOPS 会吞噬收益 |
| query-aware segment residency | 容易退化为 VStream/Milvus + workload-aware cache admission |
| provenance-aware 跨 collection dedup | 普通 content-addressed storage；需先证明真实重复率，论文机制弱 |
| ANN-aware erasure-coded cold tier | 标准 EC + cache，ANN-specific 部分只剩参数选择 |
| 多向量 token 压缩 | 2025–2026 已有 constant-space、attention clustering、sparse coding 与 ColBERT invertedization 密集竞争 |

## 5. 建议执行顺序

1. **只做 B1 半天到一天的离线 trace gate。** 不改系统、不建立大索引；输入与输出都放 NVMe 数据盘。
2. 若 B1 未跨过 5% Pareto gate，正式关闭“静态向量存储效率”方向，不继续枚举 codec/tier。
3. B2 只有在 PZ 提供真实 model-migration 约束后才重审；否则继承 G1 Kill。
4. B3 先做需求访谈/产品语义审计，确认历史 snapshot query 是否真实存在，再谈算法。
5. 不再推进 B4 或其他 coalescing 变体。

## 6. 结论

方向 B 比初表判断更拥挤：最自然的系统机制分别被 VStream、DecoupleVS、DistVS、FaTRQ、Milvus/S3 Vectors 和 LEANN 占据。当前不应把“存储成本很大”直接等价为“存储系统 idea 仍空白”。本轮唯一尚有信息价值的动作是 B1 的小型反事实 trace：它的价值不在于证明某个方案有效，而在于快速判断 graph routing sensitivity 是否真的提供了超出 individualized quantization 的新优化信号。若没有显著且稳定的 Pareto gap，应结束该方向，而不是继续组合已有组件。
