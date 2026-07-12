# VAQ 物理设计 advisor：prior-art 与 novelty 对抗审计

**日期**：2026-07-12
**对象**：`claude/share/IDEA_REPORT_0712.md` 中 Idea 2（Vector-Augmented Analytical Query Physical Design）
**裁决**：**REVISE / Problem-to-validate；禁止直接实现 advisor**

## 1. 执行摘要

“VAQ 的物理设计完全空白、只要把传统 advisor 搬到 vector+SQL 就能立项”不成立。直接覆盖已经形成四层夹击：

1. [Exqutor](https://arxiv.org/abs/2512.09695) 已建立 vector-augmented TPC-H/TPC-DS benchmark，并覆盖 vector threshold/range 的 cardinality、join order、join method 与 scan strategy。
2. [MINT](https://arxiv.org/abs/2504.20018) 已正式定义 multi-vector search index tuning：给定 workload、storage 和 recall constraints，联合选择 multi-column HNSW/DiskANN indexes，并通过 what-if planning/configuration search 获得 2.1–8.3× latency speedup。
3. [BoomHQ](https://arxiv.org/abs/2604.24552) 已覆盖 multiple vector columns + scalar predicates、vector–scalar correlation、execution strategy/index parameter recommendation 和 benchmark extension。
4. PostgreSQL-V、Cosmos DB、filtered-vector systems 与传统 physical-design advisors 已分别覆盖 page-integrated vs decoupled vector index、per-partition vector index、attribute-aware partition/index，以及 index/partition/columnstore/materialized-view 的 workload-driven selection。

因此原 Idea 的 novelty 不能是“首个 VAQ physical design advisor”，也不能是 inline/separate、partition、index selection、materialized view 四个普通旋钮的拼盘。唯一可能保留的研究问题是：**ANN 的局部 recall/error 是否会在 join、group-by 和 aggregate 中非线性传播，并与 vector–scalar correlation、partition/layout 产生不可分解交互，使“传统 advisor 后接 MINT”或“MINT 后接传统 advisor”违反端到端 answer-quality SLO 或系统性远离 joint optimum？**

这仍只是 `Problem-to-validate`。只有先证明 joint design 相对最强 sequential/independent advisors 有跨 workload、跨数据集的显著 oracle gap，才值得设计 advisor；否则它是 MINT + AutoAdmin/CoPhy 的显然组合，应 Kill。

## 2. 核心 claims 与 novelty

| Claim | Novelty | 最接近工作 | 裁决 |
|---|---:|---|---|
| 首个面向 VAQ workload 的物理设计 advisor | **Low-Medium** | MINT + AutoAdmin/CoPhy + Exqutor | 字面交集可能未命名，但组合显然 |
| 自动选择 vector index / multi-column vector indexes | **Low** | MINT | 已直接覆盖 |
| 自动选择 scalar filter 与 vector search 的执行路径/参数 | **Low** | Exqutor、BoomHQ、ADBV、filtered-ANN systems | 已覆盖 query-time optimization |
| inline vectors vs decoupled vector storage | **Low as mechanism** | PostgreSQL-V；SingleStore-V/BlendHouse | 已有系统级对比，作为 workload knob 尚未证明 |
| attribute partition + local vector indexes | **Low-Medium** | Cosmos DB、Filtered-DiskANN、UNIFY、SIEVE、SeRF/iRangeGraph | 已有 partition/index mechanisms，advisor delta 有限 |
| B-tree/columnstore/vector index 的 joint design | **Medium** | MINT + SIGMOD 2018 hybrid physical design | 唯一可保留，但必须证明 vector-specific non-separability |
| vector-aware materialized views | **Low / weak need** | 传统 materialized-view selection；query vectors 高变使复用性可疑 | 无需求证据，不应列核心机制 |
| vector-aware buffer management | **Low / underspecified** | PostgreSQL FVS study、Cosmos cache、通用 buffer advisor | 当前只是“新 cost model” |

## 3. 直接竞争工作及边界

### 3.1 Exqutor 已定义 workload 与 optimizer boundary

[Exqutor: Extended Query Optimizer for Vector-augmented Analytical Queries](https://arxiv.org/abs/2512.09695) 不只是 filtered top-k：它扩展 TPC-H/TPC-DS，向 analytical tables 注入 embeddings，并让 vector range/threshold predicates 与 filters、joins、aggregates 共存。其 exact-cardinality query optimization 或 adaptive sampling 改善 ANN cardinality，进而改变 join ordering、join type 和 scan choice，在 pgvector、VBASE、DuckDB 上最高获得四个数量级改善。

**未覆盖**：离线选择要创建哪些 physical structures。
**已覆盖**：benchmark、VAQ query semantics、cardinality 与 physical-plan selection。新工作必须直接复用并强于 Exqutor，不能重新定义一个较弱的 TPC-H+vector workload。

### 3.2 MINT 直接覆盖 vector index advisor

[MINT: Multi-Vector Search Index Tuning](https://arxiv.org/abs/2504.20018) 是原 Idea 最大的 novelty threat：

- 每行包含多个 vector feature columns；
- 给定 query workload、storage budget 与 recall threshold；
- 搜索单列/多列 HNSW 或 DiskANN index configurations；
- query planner 决定用哪些 hypothetical indexes、取多少 candidates 再 rerank；
- 使用 sample-based cost/recall estimator 与 configuration search；
- 相对 per-column baseline 获得 2.1–8.3× latency speedup。

MINT 明确建立在 AutoAdmin what-if analysis 与 relational physical tuning 文献上。因此，“把 what-if advisor 用于 vector index selection”已经发表为完整框架。剩余空间只能是**vector + relational structures 的 joint selection**，不能是再做一次 vector index tuner。

### 3.3 BoomHQ 已覆盖 correlation 与 multi-column runtime choice

[BoomHQ: Learning to Boost Multiple Hybrid Queries on Vector DBMSs](https://arxiv.org/abs/2604.24552) 面向 multiple vector columns、multiple scalar predicates 和动态 weights，学习 vector–scalar correlations 与 query-neighborhood selectivity，然后推荐 seq/index scan、各 index candidates、HNSW parameters 及 query rewrite。它还扩展 benchmark 以包含相关的 vector/scalar attributes，并报告 2× average、25× peak speedup。

BoomHQ 不创建新的 physical structures，但已经覆盖原 Idea 最可能声称的“相关性驱动 workload model”。一个物理 advisor 若只使用相同 features 选择 partition/index，将很容易被评价为 BoomHQ 的 offline extension。

### 3.4 PostgreSQL-V 与生产系统已覆盖主要布局旋钮

- [PostgreSQL-V, CIDR 2026](https://www.cidrdb.org/cidr2026/papers/p2-liu.pdf) 明确指出 pgvector 复用 PostgreSQL page-oriented structure 的 legacy overhead，并采用 decoupled vector indexes + lightweight consistency，vector search 最多快 8.9×。因此 inline/page-integrated vs decoupled 不是空白机制。
- [Cosmos DB + DiskANN](https://arxiv.org/abs/2505.05885) 选择每 physical partition 一个 vector index、使用现有 Bw-Tree 存储 index terms、按需 caching，并显示 partition fan-out 与每分区大小直接影响端到端 latency/cost。
- [An In-Depth Study of Filter-Agnostic Vector Search in PostgreSQL](https://arxiv.org/abs/2603.23710) 已把 page accesses、tuple/data retrieval、filter checks 纳入生产 DBMS 分析，发现 graph 与 clustering indexes 的优劣由系统开销和 workload selectivity/correlation 共同决定。
- Filtered-DiskANN、UNIFY、SIEVE、SeRF、iRangeGraph、ACORN 等已经提供 attribute-aware graph/partition/index mechanisms。advisor 可以选择它们，但不能把机制本身算作贡献。

### 3.5 DiskJoin 不是通用 VAQ advisor，但压缩了 join/layout claim

[DiskJoin, SIGMOD 2026](https://doi.org/10.1145/3769780) 解决 SSD 上 billion-scale vector similarity self-join，使用 vector bucketization、连续 disk layout、dependency-aware task order 与 cache management。它不覆盖 Exqutor 式 multi-operator VAQ，也不直接 Kill joint advisor；但“向量 join 的物理布局/缓存完全空白”已经不成立。

## 4. 传统 physical design 是否已经解决问题

传统 advisor 已覆盖绝大多数搜索框架：

- AutoAdmin/what-if analysis：hypothetical indexes + optimizer cost；
- [Automatic Physical Database Tuning: A Relaxation-Based Approach, SIGMOD 2005](https://doi.org/10.1145/1066157.1066184)：联合 physical structures 的可扩展搜索；
- CoPhy：portable workload-level index advisor；
- [Columnstore and B+ Tree — Are Hybrid Physical Designs Important?, SIGMOD 2018](https://doi.org/10.1145/3183713.3190660)：扩展 SQL Server DTA 联合推荐 B+ tree 与 columnstore；
- 传统 partition/materialized-view advisors：在 storage budget 下联合选择结构；近期工作还继续研究 index + partition joint tuning。

这些框架没有原生 recall、ANN stochasticity、vector–scalar local correlation 或 candidate-reuse semantics，所以**没有完全解决** VAQ joint design；但它们已经解决搜索、workload compression、what-if costing 和 budgeted selection 的大部分通用部分。论文贡献必须来自新的 vector-specific coupling，而不是 advisor 外壳。

## 5. 唯一建议保留的问题

### Quality-constrained cross-operator physical design

考虑同一 VAQ workload 的候选结构：

- scalar B-tree / bitmap / columnstore structures；
- global 或 attribute-partitioned HNSW/IVF/DiskANN；
- per-partition local vector indexes；
- vector payload/index integrated 或 decoupled；
- 受 storage、build/update cost 和 recall SLO 共同约束。

潜在非分离性来自：一个 scalar partition/index 会改变每个 local vector index 的规模、图连通性和 recall/candidate budget；vector index 的 approximate false negatives 又会被 downstream join multiplicity、group distribution、COUNT/SUM/AVG 非线性放大。两个物理设计即使具有相同局部 Recall@k，也可能产生完全不同的 join false-negative rate 或 aggregate relative error。因此，先独立优化 scalar design 再优化 vector design，不一定等价于满足端到端 answer-quality SLO 的 joint optimum。

这是与 MINT、Exqutor 和传统 advisor 都不同的唯一清晰 delta：MINT 约束局部 vector recall，Exqutor 处理 cardinality/plan，传统 advisor 默认不同访问路径语义等价，均未建模 ANN error 的跨算子传播。检索未发现直接研究 ANN error 经 VAQ join/aggregate 传播的工作；相邻 approximate query processing 研究 sampling error 与 aggregate confidence bounds，但不是 ANN physical design。当前仍没有证据表明该 interaction 足够强，不能从“存在组合空间”直接跳到 advisor 实现。

## 6. 零实现 G0 与 Kill 条件

### G0：joint-oracle gap，而非先写 advisor

使用 Exqutor 的 TPC-H/TPC-DS vector benchmark，再加入至少一个具有真实 vector–scalar correlation 的公开数据集。只枚举一个受控的小设计空间，不开发搜索算法：

1. scalar structures：none、B-tree/bitmap、columnstore/zone-map；
2. vector structures：global HNSW/IVF、attribute-partitioned local indexes；
3. storage：pgvector integrated 与 PostgreSQL-V-style decoupled baseline（若不可直接运行，至少分开报告，不用模拟数字冒充）；
4. constraints：固定 total storage、build/update budget 与 Recall@k；
5. query families：vector range → join、scalar filter → vector → join、vector predicate + group/aggregate、multi-vector-column weighted queries；
6. quality metrics：除 Recall@k 外，必须报告 join false-negative、group coverage、COUNT/SUM/AVG relative error 与 top-group ranking error。

比较：

- `Exqutor + default physical design`；
- 传统 advisor 先选 scalar structures，再由 MINT 选 vector indexes；
- MINT 先选 vector indexes，再由传统 advisor 选 scalar structures；
- independent per-structure best；
- exhaustive joint oracle（仅小空间）；
- BoomHQ-style runtime strategy/parameter choice。

### 通过门槛

只有全部满足才进入 advisor 设计：

- joint oracle 相对最佳 sequential/independent baseline，在相同 storage/update budget 与端到端 quality SLO 下达到 **geomean 至少 3×、P95 至少 2×**；
- 改善出现在至少三类 VAQ，而非单个特制 query；
- 在 TPC-derived 与真实 correlated dataset 上均成立；
- 最优设计随 selectivity、vector–scalar correlation 或 recall SLO 发生可解释切换；
- 至少 25% queries 出现 vector-only 与 relational-only design ranking reversal，最佳组合 baseline 对 oracle regret 至少 30%；
- 在相同 ANN recall 下，下游 answer error 至少出现 3× spread，证明局部 recall 不能代表 SQL semantic quality；
- 收益不能由 Exqutor 的 plan/cardinality fix、BoomHQ parameter tuning 或单独 MINT index tuning吸收；
- 简单 selectivity/correlation rule 不能达到 oracle 收益的 80%。

### 立即 Kill

- exhaustive joint oracle 相对最佳 sequential baseline 改善不足 3×，或任一 MINT+traditional-advisor 顺序已在 oracle 的 20% 内；
- 最优设计几乎总是“decoupled vector index + 普通 B-tree/columnstore”，无 workload-dependent choice；
- 设计差异主要来自 vector index parameters，而非 relational–vector interaction（MINT/BoomHQ 已覆盖）；
- 普通 ANN recall 已足以稳定预测 join/aggregate answer error；
- 只在 synthetic independent/correlated data 上成立，held-out real data 消失；
- materialized view 或 partition 的收益来自普通 relational selectivity，与 vector semantics 无关；
- advisor 需要完整构建所有 vector indexes 才能估价，tuning cost 接近 exhaustive search。

## 7. 最终建议

原 Idea 2 的 novelty 估计应从 7/10 下调到 **4/10**。不建议直接做“pgvector 三种 layout 比较”，因为 PostgreSQL-V 与生产 FVS work 已经证明 layout/index 的系统影响，单纯得到 >3× spread 不能说明需要新 advisor。

建议仅保留上述 joint-oracle G0，状态为 `Problem-to-validate`。它比此前 co-access gate 更值得一次受控验证，因为 Exqutor 提供现成 VAQ benchmark，MINT 与传统 advisors 提供明确强基线，而且结果无论正负都能快速回答“vector-specific joint physical design 是否真实存在”。未经 Claude/Gpt 明确同意，不运行 G0。
