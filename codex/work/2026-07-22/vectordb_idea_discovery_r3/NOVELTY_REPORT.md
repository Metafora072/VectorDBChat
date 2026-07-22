# Novelty Audit：三个最强候选

## A. Capacity-Constrained Collective ANN — KILL

### 正式问题

给定查询批 `Q`、对象 `V`、每个对象容量 `c_i` 与距离 `d(q,i)`，返回每个查询 `k` 个对象，同时最小化总匹配代价。与独立 ANN 不同，查询通过容量约束耦合。

### 最近的 7 篇工作及逐项边界

| 工作 | 直接重合 | 边界判断 |
|---|---|---|
| Capacity Constrained Assignment, SIGMOD 2008 | **同一正式目标**；NIA/IDA 按需调用 incremental NN 扩候选，并给 correctness/approximation 分析 | 致命先例；不能声称新问题或“只扩冲突查询”新机制 |
| Approximation Algorithms for Bipartite Matching with Metric and Geometric Costs, STOC 2014 | 用近似 NN/几何数据结构加速高维 metric matching | 直接覆盖 ANN-assisted matching 的算法身份 |
| Approximate Correspondences, NeurIPS 2006 | 用近似近邻建立大规模匹配/对应 | 更早的 ANN-to-matching 路线 |
| Geometric Partial Matching, SoCG 2019 | 几何 cost 下 partial matching 近似 | 限制条件不同，但继续挤压理论 novelty |
| Preconditioning for Optimal Transport, 2019 | 稀疏化 cost graph 后解 transport/matching | 候选边稀疏化并非新范式 |
| Approximate Auction / b-matching, 2024 | capacity/b-matching 的可扩展近似 | solver 侧已有成熟机制 |
| DISCo, ICLR 2026 | 把离散约束与检索/组合选择结合 | 场景不同，但表明 global constrained retrieval 也在升温 |

### 最小机制与可成立理论

机制：在当前 top-L candidate graph 上寻找 deficient query set，只给相关 query 扩候选。可证明若 candidate graph 满足所有需求节点的 generalized Hall 条件，则存在容量可行 assignment；若每条所需边都已包含，还可对 assignment cost 给界。

问题是：Hall 只认证**可行性**，不认证低 cost；一旦加入 reduced cost/dual price 指导扩展，就回到 SIGMOD 2008 的 IDA/NIA 与 assignment oracle。

### A0、资源、venue、反方

- 一周 A0：MovieLens SVD query-item 批，比较 uniform top-L 与 deficiency expansion。
- 实测：top-1 collision 49%；Hall expansion 相对 uniform 在 cap=1/2/4 节省 12.2%/44.0%/35.6% 候选，regret <0.18%。现象为正。
- 完整论文若继续：必须击败 NIA/IDA、auction、min-cost flow 与现代 ANN oracle；当前没有独立机制。
- 资源：CPU 16 cores、<32 GB RAM、<20 GB NVMe。
- Venue fit：数据库问题更像 SIGMOD/VLDB；对 AAAI/IJCAI/NeurIPS/ICML 的算法新意不足。
- 最强反方：这是 2008 capacity-constrained assignment 换成 embedding 数据。
- **裁决：KILL-NOVELTY。**

## B. Compact Fresh-World Distributional ANN — KILL

### 正式问题

数据库不存单点 `x_i`，而存紧凑分布 `P_i`。每次查询产生独立 fresh world：

\[
X_{is}\sim P_i,\quad
M_i(q)=\max_{s\le S_i}\langle q,X_{is}\rangle,
\quad R_k(q)=\operatorname{topk}_i M_i(q).
\]

目标是在不为每个对象物化 `S_i` 个向量的条件下，抽样并检索该 fresh world 的精确或高概率 top-k。

### 最近的 9 篇工作及逐项边界

| 工作 | 最近重合 | 尚存/消失的边界 |
|---|---|---|
| [DINOSAUR, 2026](https://arxiv.org/abs/2606.04603) | 对分布式/概率表示做可扩展相似搜索 | 最强当代威胁；其 sample/materialize/index 语义与 per-query fresh world 不同，但应用动机接近 |
| Top-k Probable Nearest Neighbor Queries in Uncertain Databases, VLDB 2008 | 概率对象的 top-k probable NN | 返回 marginal probability 排名，而非一次联合 fresh-world realization |
| Nearest Neighbor Queries on Uncertain Data, VLDB-era series | 对象位置分布与概率 NN | 同样证明“不确定 NN”不是新领域 |
| Nearest Neighbors under Uncertainty II, 2016 | 不确定距离/位置下的 NN 理论 | 语义边界窄，不能泛称首次 distributional ANN |
| [NNS under Uncertainty, UAI 2021](https://proceedings.mlr.press/v161/mason21a.html) | noisy distance/oracle 下识别 NN | uncertainty 在观测过程，不是 compact item posterior fresh sampling |
| Probabilistic Face Embeddings, ICCV 2019 | embedding 用 Gaussian 分布表达不确定性 | 表示层直接先例；未解决大规模 fresh-world top-k |
| Probabilistic Cross-Modal Embeddings, CVPR 2021 | 分布 embedding 与多样 sample | 应用动机相邻 |
| Optimistic Query Routing for MIPS, 2024 | 用不确定 upper score 做 shard routing | uncertainty 是 shard score estimator，不是对象后验；但 UCB 检索机制相邻 |
| Linear Bandits with Sublinear Time, ICML 2022 | posterior sample 后用 MIPS 做亚线性 action selection | 只采一个全局参数，items 条件相关；不是每对象独立 posterior，但“posterior sample → MIPS”并不新 |

### 最小核心机制

若 `P_i=N(μ_i,σ_i²I)`，令 `m_i=<q,μ_i>`、`r_i=||q||σ_i`。因为

\[
\Pr[M_i\le y]=\Phi((y-m_i)/r_i)^{S_i},
\]

可用 `U_i~Uniform(0,1)` 惰性生成

\[
M_i=m_i+r_i\Phi^{-1}(U_i^{1/S_i}).
\]

再给对象分配 `δ_i`，取

\[
\beta_i=\Phi^{-1}((1-\delta_i)^{1/S_i}),\qquad
U_i(q)=\langle q,\mu_i\rangle+\|q\|\sigma_i\beta_i.
\]

`U_i(q)` 可化为 `(d+1)` 维 MIPS。按上界顺序枚举对象，只在抽样后的第 k 大分数超过所有 unseen UCB 时停止。

### 可成立理论

- 每对象只存 `O(d)`，不存 `S_i d` 个样本。
- 若上界枚举 oracle 精确，union bound 给出停止结果等于完整 fresh world top-k 的概率至少 `1-Σ_iδ_i`。
- 若 oracle 本身有 missed-upper-bound probability `η`，总成功率最多降为 `1-Σδ_i-η`。

致命点：普通 HNSW/MIPS 只返回高分点，不提供“所有 unseen 对象的最大 UCB”认证；因此 exact guarantee 需要精确顺序 oracle，可能近线性扫描。

### A0、资源、venue、反方

- 一周 A0：20K–100K objects，128D Gaussian posterior；比较 exact full-world、exact-UCB progressive、HNSW-UCB 与 mean-index over-fetch。
- 实测详见 `A0_REPORT.md`：小 `α=0.1` 时 HNSW-UCB world Recall=0.9922，但 matched-candidate mean-overfetch 已有 0.9879，只有 0.43 point 差；`α=0.2` 时 exact UCB p50 需 2,239.5/20K candidates，HNSW-UCB Recall 0.8156，而 mean-overfetch 0.9859。
- 完整论文若 A0 正：需 DINOSAUR、probabilistic NN、mean/variance index、materialized samples、brute force、IVF/HNSW/PQ，全套真实 probabilistic embeddings 与 calibration。A0 已负，停止。
- 资源：CPU 16–32 cores、32–64 GB RAM、普通 NVMe <100 GB；无需 GPU。
- Venue fit：若机制成立，ICML/NeurIPS（probabilistic retrieval）或 AAAI/IJCAI；当前效率—保证矛盾使 fit 不成立。
- 预注册 gate 中 `50k` 指 `50·k` 个候选，即本实验 `k=10` 时的 500 个候选，而非五万个候选。
- 最强反方：fresh-world/max-of-S 是人为语义；当 uncertainty 真有意义时，上界被 variance 极端值支配而退化为扫描。
- **裁决：KILL-MECHANISM。**

## C. Similarity-Proportional Vector Sampling — KILL

### 正式问题

给定 `q`，以 `p(i|q)∝exp(sim(q,x_i)/τ)` 近似抽样对象，并约束 total variation/KL error 和 query cost。

### 最近的 7 篇工作及边界

| 工作 | 重合与边界 |
|---|---|
| Gumbel-Max / Gumbel-MIPS | 给每项加 Gumbel noise 后 top-1 等价于 softmax sample；几乎直接命中 |
| Fast Sampling for MIPS, AISTATS 2019 | 直接研究 MIPS-based sampling |
| RF-softmax, NeurIPS 2019 | 随机特征近似 large-vocabulary softmax sampling |
| Locality-Sensitive Sampling / MI estimation, IJCAI 2020 | LSH bucket 构造 query-dependent samples |
| MIDX Sampler, 2025 | 现代大词表/向量离散索引采样 |
| Fair Near Neighbor / Range Sampling | 从 near-neighbor/range 集合近似均匀采样 |
| Hashing-Based Estimators for KDE | 与归一化常数/密度估计直接相邻 |

### 机制、理论、A0、裁决

可设想 ANN 候选 + tail mass estimator + rejection/importance correction，并给 TV error bound。但这只是把已知 Gumbel/LSH/softmax sampler 的部件重新组合。

- A0：比较 Gumbel-MIPS、RF/MIDX、ANN top-L truncation 的 TV/ESS/latency；即使为正也难支持 novelty。
- 资源：CPU、<64 GB RAM、普通 NVMe。
- Venue fit：ML sampling 有 ICML/NeurIPS 可能性，但必须出现新的 sampling oracle；当前没有。
- 最强反方：这是 approximate softmax sampling 的旧问题。
- **裁决：KILL-NOVELTY。**

## 最终 novelty 结论

三者中，A 有现象但被经典算法直接覆盖；C 被现代 sampling 机制覆盖；B 有最窄的问题边界和最漂亮的 compact reduction，却被 A0 揭示出 guarantee 与 sublinear retrieval 不可兼得。最终保留数：**0**。
