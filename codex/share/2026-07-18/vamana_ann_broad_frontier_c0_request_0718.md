# Vamana / Disk-Resident ANNS Broad Frontier C0：Bounded Idea Report and Gate Request

## 0. Decision

**结论：放宽到 Vamana 驻盘图与相关 ANNS 后，研究空间不是零；但空间不在恢复 M0–M3/A0/B0，而在重新定义理论成本、embedding-generation 演化或 query-specific guarantee。**

本轮由主执行者与独立发散审稿共生成 12 个方向，快速筛选出 3 个 pre-candidate：

1. `Navigation-Only Poisoning`：恶意向量即使被排除在结果外，是否仍能作为 Vamana hub/bridge 改写 topology、search path与page I/O；
2. `Page-Cost-Aware Navigability`：把 DiskANN 的 `alpha`-reachability / sparsest navigable graph 从 edge/degree cost提升到 page-capacitated I/O cost；
3. `ACL / Deletion Navigation Non-Interference`：unauthorized/deleted node不返回仍不够，是否必须保证其不改变 authorized answer或可观测trace。

三者都只是 **problem-gate candidates**，不是获准 idea，更不是实验计划。Rank 1 有最便宜且清晰的正/负 pilot；Rank 2 最接近新的算法理论对象；Rank 3 的意义取决于是否能建立现实 threat model，暂列 HOLD。独立审稿原本把 same-ID/crash transaction contract列为第一，但这会复活 PZ 已明确暂停的 ContractANN/correctness路线，本报告主动 Reject。

建议请求 Gpt 只批准一次 2–3 天、只读 primary-work/formalization 的 `Broad Frontier C0`，最多保留一个对象。C0 不运行实验、不修改 DGAI/OdinANN、不生成 trace、不自动进入 prototype。

## 1. Scope and inherited closures

本报告回答的是：

> 不限定动态写优化，允许系统、算法和理论贡献时，Vamana/DiskANN 及邻近 ANNS 是否仍有可研究空间？

以下 closure 全部继承，不得改名复活：

- M0–M3 Dynamic Vamana write optimization；
- queue coalescing、ordinary page buffering、neighbor-repair suppression；
- A0 memory-delta/direct-update/localized-patch/LSM architecture recombination；
- B0 fixed-radius deletion-local exact repair oracle；
- ContractANN、Write Reducibility、matched-R；
- 原 multi-NVMe placement 与 generic SSD scheduler；
- PageMaxSim residual-certificate、generic DiskColBERT 与 VAQ advisor；
- “现有工作目标相同就必然 Kill”这一错误标准。

新候选必须由新 formal object、真实 embedding/query workload或独立 runtime observation驱动，并与 strongest prior 在 matched quality/semantics 下比较。

## 2. Landscape map

### 2.1 Node-level Vamana theory is moving quickly

- [Sort Before You Prune, ICML 2025](https://proceedings.mlr.press/v267/gollapudi25a.html) 给 DiskANN family 更强 approximation factor，并首次分析 practical beam search 的 worst-case behavior。
- [Sparse Navigable Graphs, SODA 2026](https://epubs.siam.org/doi/10.1137/1.9781611978971.58) 把最稀疏 `alpha`-navigable graph与 Set Cover 联系，给 approximation与 hardness；这直接占据“只优化 degree/edge count”的理论主轴。
- [Fast-Convergent Proximity Graphs](https://arxiv.org/abs/2510.05975) 继续修改 pruning rule，给 bounded intrinsic dimension 下的收敛保证和 practical variant。
- [Instance-based Approximation Guarantees, ICAPS 2025](https://ojs.aaai.org/index.php/ICAPS/article/view/36113) 使用 search-path diagram找固定 graph 的最坏 query，说明 empirical query sampling可能漏掉真正坏例。

这意味着“为 Vamana 再设计一个 diversity score或调 `R/alpha`”不足以成立；新 theory 必须改变成本对象、query model或metric-generation model。

### 2.2 SSD layout/search pipeline is crowded, but theory and I/O remain partly disconnected

- [PipeANN, OSDI 2025](https://www.usenix.org/conference/osdi25/presentation/guo) 已把 best-first dependency与 SSD pipeline 对齐。
- [PageANN](https://arxiv.org/abs/2509.25487) 已提出 page-node graph与 page-aligned layout。
- [OctopusANN / I/O DSE](https://arxiv.org/abs/2602.21514) 已给 page locality/path length complexity model，并联合 memory layout、disk layout与 dynamic-width search。
- [VeloANN](https://arxiv.org/abs/2602.22805) 已覆盖 affinity placement、record cache、coroutine runtime、prefetch与 beam-aware search。
- [2026 experimental evaluation](https://arxiv.org/abs/2603.01779) 将系统分为 storage、layout、cache、query与update五组件，报告 dimension-sensitive effects和现有 layout 很低的有效 I/O utilization。

所以普通 page shuffle、cache-aware beam、prefetch、page dedup或把多个已有优化组合起来都不够。尚值得核验的是：node-level approximation/navigability theorem能否被提升为**带 page capacity与page-read objective的正式问题**，而不是又做一个 empirical layout。

### 2.3 OOD/adaptive query handling is no longer blank

- [RoarGraph, PVLDB 2024](https://www.vldb.org/pvldb/vol17/p2735-chen.pdf) 用 historical query–base bipartite relation处理 cross-modal OOD。
- [Dynamically Detect and Fix Hardness](https://arxiv.org/abs/2510.22316) 已定义 query-conditioned Escape Hardness并做局部修复。
- [Quake, OSDI 2025](https://www.usenix.org/conference/osdi25/presentation/mohoney) 已按动态分布、访问 skew与 cost/recall model调节 partition和 query parameters。
- [VIBE 2025](https://arxiv.org/abs/2505.17810) 已提供现代 embedding与 ID/OOD dataset benchmark。

因此“识别 hard/OOD query后扩大 beam”已高度 covered。只有可证明的 query-specific certificate、或与 SSD page cost的新关系，才可能留下独立 delta。

### 2.4 Adjacent application axes also have direct incumbents

- Embedding migration已有 [Drift-Adapter, EMNLP 2025](https://aclanthology.org/2025.emnlp-main.805/)，它把新 query映射回 legacy space以延迟重建；但没有直接回答旧 graph topology在新 metric下的 edge-level validity与minimum rebuild。
- Quantization-aware graph routing已有 [RPQ](https://arxiv.org/abs/2311.18724)；[QuIVer 2026](https://arxiv.org/abs/2605.02171) 更直接在2-bit metric内做 Vamana pruning与beam search；普通“量化感知构图”不再是空白。
- Private graph ANN已有 [PACMANN, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/391d50b3fe1c59b3e2b8b644e0c8fe81-Abstract-Conference.html) 与 [Compass, OSDI 2025](https://www.usenix.org/conference/osdi25/presentation/zhu-jinhao)。
- filtered/vector-relational search已有 DiskANN filters、[VBASE](https://www.usenix.org/conference/osdi23/presentation/zhang-qianxi)及 [2025 FANNS survey](https://arxiv.org/abs/2505.06501)。
- multi-vector理论已有 [`alpha`-Reachable Graphs for Multi-vector NNS](https://openreview.net/forum?id=v8jSxLHEE9)；本地 PageMaxSim又已经通过真实 embedding gate证伪当前 residual-certificate机制。
- vector-database poisoning已有 [Black-Hole Attack](https://arxiv.org/abs/2604.05480)，它让中心恶意向量高频进入top-k；但“恶意点从结果中被过滤后，是否仍只靠graph navigation破坏 recall/I/O”不是其主claim。
- RBAC vector search已有 [HONEYBEE, PACMMOD 2026](https://doi.org/10.1145/3786625)，其目标是partition/replication下的authorized result效率；它没有把unauthorized node对graph path、timing或page trace的非干扰作为核心contract。

## 3. Twelve generated ideas and first-pass filtering

| ID | Idea | Core hypothesis / cheapest falsification | Closest threat | Decision |
|---|---|---|---|---|
| I1 | Page-Cost-Aware Navigability | page capacity `B` 与 packing纳入 `alpha`-navigability；证明 approximation/hardness或构造在相同 quality下减少worst/expected page expansions。先做 formal reduction与小图 exact enumeration，不跑系统 | SODA sparse navigable graph、PageANN、OctopusANN | `TOP-2 / GATE` |
| I2 | Embedding-Generation Topology Transfer | 给定同一 object set 的旧/新 metric，利用 distortion/edge-order stability界定旧 Vamana edges何时仍保证 reachability，并求最小 rebuild/edit | Drift-Adapter、bi-metric ANN、M08/M10；弱假设可能无法约束global paths | `HOLD` |
| I3 | Certified Query-Specific Page Budget | 根据 frontier distances、PQ error envelope与graph invariant，输出每 query 的 safe stop/expand certificate，而非经验 beam predictor | adaptive beam、Escape Hardness、instance guarantee、Quake | `ELIMINATE / crowded` |
| I4 | OOD-aware online graph refinement | 用 live query distribution更新 Vamana routes | RoarGraph、NGFix、OOD-DiskANN、Quake直接覆盖主要对象 | `ELIMINATE` |
| I5 | Quantization-robust Vamana topology | 在 compressed metric中构图并按 query选择精度 | RPQ、QuIVer、FINGER、ANNS-AMP已密集覆盖 | `ELIMINATE`；除非有新 formal error theorem |
| I6 | Local intrinsic-dimension degree allocation | 固定总edge/page budget，把degree分配给高LID region | SNG truncation theory、alpha-CG、k-diverse/angular methods；容易退化为参数调优 | `ELIMINATE` |
| I7 | Correlation-aware filtered Vamana | 联合vector/scalar correlation、selectivity与page layout | Filtered-DiskANN、ACORN、VBASE、DIGRA及FANNS survey | `ELIMINATE` |
| I8 | Page-oblivious/private Vamana | 隐藏 query与page access pattern | PACMANN与Compass已直接占据 | `ELIMINATE` |
| I9 | SSD multi-vector Vamana/MaxSim | 为 non-metric set similarity构建 disk graph | multi-vector reachability、ESPN/ColBERT serving；本地 PageMaxSim机制已失败 | `ELIMINATE` |
| I10 | Distributed/object-store Vamana | graph cluster + HA/distributed storage | DSANN及大量distributed vector systems；偏离当前单机证据与优势 | `ELIMINATE` |
| I11 | Navigation-Only Poisoning | 插入少量恶意hub/bridge，随后禁止它们进入结果；检验其是否仍通过Vamana pruning/path造成recall或page-I/O损害 | Black-Hole Attack的恶意点进入top-k；与纯navigation effect有可测delta | `TOP-1 / GATE` |
| I12 | ACL/Deletion Navigation Non-Interference | 两索引只差secret/unauthorized node；authorized answer、visited/page trace是否应不可区分 | HONEYBEE、filtered ANN、PACMANN/Compass | `TOP-3 / HOLD` |

本表不是 exhaustive novelty check。它的用途是避免再次花数周验证显然拥挤的轴，并把下一步约束在最多两个真正改变 formal object 的问题上。

## 4. Ranked pre-candidates

### Rank 1: Navigation-Only Poisoning

**Problem.** Black-Hole Attack证明中心向量可高频进入top-k；而 Vamana 构图还会让插入点参与reverse links、RobustPrune与后续graph traversal。一个恶意点可能在结果层被filter/tombstone/admission rule排除，却已经成为hub/bridge，持续改变合法节点的边槽、search basin和page reads。这是 topology/navigation attack，不是“让恶意文档被召回”。

**Candidate object.** 固定 benign dataset、Vamana builder/search与结果过滤策略；攻击者加入不超过 `m` 个最终不可返回的向量。度量：

```text
authorized Recall@k loss
visited benign-node/path divergence
unique/completed page-read amplification
p95/p99 search work
attack persistence after malicious nodes become non-returnable
```

**Minimum C0/P0.** 先核验 Black-Hole、ANN poisoning、filtered graph traversal与hubness defense是否已有同一threat model。只有novelty成立才允许一个100K–1M CPU/SSD canary：插入中心、bridge与optimized adversarial vectors，随后强制过滤攻击点，比较rebuild/no-rebuild下的recall和page trace。预计单点≤2小时、增量<5 GiB；本轮不运行。

**Natural Kill.** 过滤攻击点后 benign recall/page reads无稳定变化；影响完全来自攻击点进入top-k；普通degree/hubness admission已消除；或已有工作已把non-returning navigation effect作为主攻击。

### Rank 2: Page-Cost-Aware Navigability

**Problem.** 现有 `alpha`-reachability/sparsity theory主要优化edge数、maximum/average degree或node-level search steps；SSD系统实际支付的是page reads。若多个被扩展节点共页，edge/step count与I/O cost可能分离。PageANN与OctopusANN经验上利用这个分离，但尚需核验是否已有正式的 capacitated page-navigability optimization。

**Candidate object.** 给定 metric dataset、page capacity `B`、degree/space budget与fixed beam procedure，同时选择 directed edges及vertex-to-page packing，使：

```text
quality: alpha-reachability / sorted-alpha reachability / fixed-beam approximation
cost: worst-case or distributional number of distinct expanded pages
```

研究最小 page cost 的 hardness、approximation与可实现 construction。其核心必须是 page ownership/capacity改变了 combinatorial problem；不能只是先建 Vamana再做 graph partition。

**Minimum C0.** 只读核验 PageANN/OctopusANN/SODA/ICML guarantees；尝试对 toy metric给出 edge-optimal与page-optimal分离例，或证明问题退化为已知 capacitated set cover/graph layout。2–3天，<1 GiB，无正式index build。

**Natural Kill.** 若 formal objective等价于 ordinary sparse navigability后接通用 packing；若 PageANN/OctopusANN已有同等 theorem；若任何 guarantee都要求全页全展开，不能预测实际 beam I/O；或只能得到“NP-hard”而无近似/结构性结果。

### Secondary HOLD: Embedding-Generation Topology Transfer

**Problem.** embedding model upgrade通常被处理为full re-embedding/rebuild、dual index，或把新 query映射回旧空间。另一个算法问题是：同一 object set 上，旧 metric构造的 Vamana graph在新 metric下保留多少 navigability？哪些 edge失效是必须修，哪些 topology可证明复用？

**Candidate object.** 固定 `X` 与两个 metric `d_old,d_new`，给定 `G_old`。在 distortion、neighbor-order stability或local margin假设下，定义：

```text
minimum edge edits / rebuilt vertices
such that G' is alpha-reachable or fixed-beam successful under d_new.
```

目标是 topology-transfer certificate与最少重建算法，而不是运行双索引、stable-ID publish或再训练一个 adapter。

**Minimum C0.** primary-work核验 bi-metric ANN、Drift-Adapter、graph transfer/reuse与model-upgrade literature；建立一个非trivial sufficient condition或反例。若通过，未来 pilot才使用 paired old/new embeddings比较edge overlap、path validity和partial rebuild；本轮不跑。

**Natural Kill.** 若有用 certificate必须检查all-pairs或完整新graph；若弱metric distortion不能约束finite-beam success；若 Drift-Adapter/dual-index在相同quality下完全支配；或结果只等于“变化大的点重建”。

### Rank 3: ACL / Deletion Navigation Non-Interference

**Problem.** filtered ANN通常要求返回集合合法；但若unauthorized/deleted节点仍参与共享graph导航，它可能改变authorized top-k、延迟、cache与page trace。更强的contract是：对观察权限内的用户，两索引只在秘密节点上不同，不应导致可观察检索行为可区分。

**Minimum C0.** 先固定threat model：攻击者能观察answer、latency、shared-cache effect还是server-side trace；再对照HONEYBEE、filtered ANN、PACMANN与Compass。纸面构造paired graph反例即可，不直接做per-role index。

**Natural Kill.** 实际contract只要求结果authorization而明确允许内部导航使用secret节点；攻击者无法观察任何path/I/O side channel；或满足non-interference只能完全物理分区，退化为per-role/tenant index。

**Current status.** `HOLD`。它的novelty可能高，但threat model若不真实就没有significance。

### Eliminated: Certified Query-Specific Page Budget

**Problem.** fixed beam浪费easy query预算，但普通 adaptive width/termination、learned predictor和hard-query repair已有大量工作。唯一可能的新 delta 是：利用正式 graph invariant与已观察的search state，对单query给出可审计的 approximation/recall或failure certificate，并把certificate直接对应到额外page reads。

**Minimum C0.** 对照 Sort Before You Prune、instance-based guarantee、Escape Hardness、Distance Adaptive Beam、Quake与PQ-error bounding；判断online-observable state是否足以产生non-vacuous certificate。先纸面反例，不做learned threshold。

**Natural Kill.** 证书需要true NN、完整search-path diagram、全图scan或historical ground truth；只能得到经验置信度；或与adaptive termination/recall estimator等价。

**Current status.** `ELIMINATE for now`。相邻工作过密，除非未来出现新的online-observable formal state，不再申请gate。

## 5. Scores and reviewer objections

评分顺序为 `significance / novelty / depth / feasibility`，门槛建议 `7 / 6 / 7 / 6`。

| Rank | Idea | Score | Strongest reviewer objection |
|---|---|---|---|
| 1 | Navigation-Only Poisoning | `8 / 7 / 7.5 / 8.5` | 可能只是Black-Hole Attack换指标；必须证明攻击点不返回且损害发生在Vamana topology/path层 |
| 2 | Page-Cost-Aware Navigability | `8 / 6.5 / 8 / 6.5` | PageANN/OctopusANN加一个NP-hard packing theorem，可能仍是理论包装而非新算法；必须产生可测 construction或非显然分离 |
| 3 | ACL/Deletion Navigation Non-Interference | `8.5 / 7.5 / 8 / 6.5` | 若服务端内部使用unauthorized节点本来就被允许且不可观察，强contract可能没有现实threat model |

三项都没有 pilot result：`SKIPPED — no experiment authorization`。这不是负信号，而是遵守当前停止边界。

## 6. Requested gate

建议 Gpt/Claude 只审议是否批准：

```text
Vamana / ANNS Broad Frontier C0
time: 2–3 days
space: <1 GiB
actions: primary-paper/code reading + formal counterexample/reduction only
output: prior matrix + at most one fixed formal object + PASS/KILL
```

C0 优先顺序：

1. 先审 Rank 1 的threat-model/novelty，决定是否值得一个≤2小时canary；
2. 若 Rank 1 被 direct prior Kill，再审 Rank 2 的formal object；
3. Rank 3保持HOLD，除非先建立现实可观察者模型；
4. 不并行生成系统实现。

C0 PASS 必须同时满足：

- 找到一个 strongest prior未直接定义的 formal object；
- 给出至少一个非trivial separation、theorem skeleton或完整反例；
- 说明未来最小 pilot及其quality/compute/time/space预算；
- 不能只是 Vamana + generic page packing、adapter、learning或cost model。

C0 KILL 时应接受“当前 Vamana/DiskANN邻域对本项目没有高期望值候选”，转到由新应用/数据语义驱动的更远问题，而不是继续在关闭清单中换名字。

## 7. Resource and stop record

- 本轮只读取本地已有报告与公开 primary pages；没有下载PDF或新数据；
- experiments/builds/traces/instrumentation/code changes：`0`；
- 新增持久空间：仅本报告与对话/gate文本，远小于1 GiB；
- 没有恢复Dynamic Vamana内部优化或任何已Kill候选；
- 完成本请求后停止，等待 Gpt/Claude/PZ 裁决。
