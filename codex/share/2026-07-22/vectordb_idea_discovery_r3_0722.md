# VectorDB / ANNS Wide-Scope Idea Discovery R3

日期：2026-07-22
方法：ARIS `idea-discovery` → 2024–2026 mechanism Kill Map → 14-candidate open generation → closest-work novelty audit → independent critical review → CPU/NVMe A0 → refinement ruling

## Executive verdict

本轮已经把视野从驻盘图/HNSW 放宽到整个 VectorDB/ANNS，包括新的 query primitive、全局耦合目标、概率对象、采样、join/range/reverse-kNN、mixed fidelity 与 semantic objective。结论仍是：

> **本轮 paper-level PASS = 0，最终保留 = 0。**

这不是搜索范围不足，而是三个最强候选分别被三种硬证据击杀：

1. **Capacity-Constrained Collective ANN** 有强场景和正 A0，但 SIGMOD 2008 已给相同正式问题与 incremental-NN expansion，STOC 2014 已有 ANN-assisted metric matching。`KILL-NOVELTY`。
2. **Compact Fresh-World Distributional ANN** 有最清晰的新 primitive 与理论 reduction，但实际 HNSW A0 表明：不确定性小时 mean-overfetch 几乎等价；不确定性大时 sound UCB 退化为扫描，而 approximate HNSW 又破坏保证。`KILL-MECHANISM`。
3. **Similarity-Proportional Vector Sampling** 被 Gumbel-MIPS、Fast Sampling for MIPS、RF-softmax、LSH/MIDX sampler 直接包围。`KILL-NOVELTY`。

因此没有把多个弱机制拼成“大系统”，也没有把 HOLD 冒充 PASS。

## 1. Phase 0：2024–2026 拥挤区域 Kill Map

| 必查区域 | 最近机制 | 本轮结论 |
|---|---|---|
| 动态插入/删除/局部修复/并发 | SPFresh、FreshDiskANN、CleANN、OdinANN、Slipstream、MFLI、IP-DiskANN | local repair/merge/arrival-aware maintenance 拥挤；换 edge score **KILL** |
| Streaming / 连续流 | Big-ANN streaming、Streaming VQ、SPFresh、Slipstream | generic streaming insert **KILL** |
| Adaptive beam / stopping / hard query | DARTH、DABS、Ada-ef、ConANN、GATE、PAG | 换 beam/threshold/hardness **KILL** |
| Workload/query-aware graph | Quake、GATE、CleANN、hard-query repair | query-log rewiring/entry/repair **KILL** |
| Filtered/dynamic/multi-predicate | UNIFY、SIEVE、Curator、GateANN、dynamic RFANN、KHI、RNSG | 拥挤且偏企业语义，**KILL** |
| Embedding migration | FastFill、WACV 2025 metric-compatible backfill、Drift-Adapter、Embedding-Converter | partial scheduling、mixed-version ranking 已有；Seed A **KILL** |
| Multi-vector / late interaction | MUVERA、PLAID、WARP、GEM、XTR | 新 token/page pruning **KILL** |
| Adaptive sequence / closed loop | adaptive distance estimation、MQO、QVCache、relevance feedback、adversarial adaptive query | Seed B 的算法身份此前已被审阅/A0 否定，**KILL** |
| Diverse/fair/robust/adversarial | diverse kNN、fair kNN、robust ANN、RetrievalGuard | 拥挤且不符合本轮偏好，**KILL** |

放宽后的新区域也做了机制检索：SimJoin/DiskJoin 封堵 generic similarity join；reverse/range/multi-k 已有专门工作；Certified HNSW/Almost Navigable Graphs 正在挤压 certificate；Semantic Recall 已直接研究几何 recall 与任务效用错位；AdANNS 封堵普通 mixed-fidelity；Gumbel/RF/LSH/MIDX 封堵相似度采样。

经典工作也纳入 hard boundary，尤其是 capacity assignment、probabilistic NN 和 relevance feedback。完整表见 `LITERATURE_LANDSCAPE.md`。

## 2. 候选漏斗

共生成 14 个候选：capacity collective、MOVE、region certificate、sparse navigation certificate、distribution-valued top-k、semantic materialized view、persistent mixed fidelity、similarity sampling、delta-stable chunks、semantic aggregate、expensive oracle、continuous hybrid score、abstaining ANN、spectral fidelity。

进入深 novelty audit 的只有前三条不同机制家族：capacity collective、fresh-world distributional、similarity sampling。MOVE 与 region certificate 作为核心 bound 可行性 A0。其余候选因直接先例、无 admissible oracle、只剩 cache/view/threshold 或旧 R2 反例而淘汰。

## 3. Finalist A：Capacity-Constrained Collective ANN

### 3.1 正式问题定义

\[
\min_x \sum_{q,i}x_{qi}d(q,i),\qquad
\sum_i x_{qi}=k,\quad \sum_q x_{qi}\le c_i,
\]

其中 `x_qi∈{0,1}`。场景包括曝光容量、deduplicated dispatch、有限服务能力对象与批量匹配；独立 top-k 无法覆盖查询之间的耦合。

### 3.2 最接近工作与逐项边界

1. **Capacity Constrained Assignment, SIGMOD 2008**：同一目标，NIA/IDA 已按需调用 incremental NN；致命直接先例。
2. **Approximation Algorithms for Bipartite Matching with Metric and Geometric Costs, STOC 2014**：ANN-assisted high-dimensional matching；击穿算法身份。
3. **Approximate Correspondences, NeurIPS 2006**：ANN-to-matching 早期路线。
4. **Geometric Partial Matching, SoCG 2019**：几何 cost partial matching 近似。
5. **Preconditioning for Optimal Transport, 2019**：稀疏候选 cost graph 后求 transport。
6. **Approximate auction/b-matching, 2024**：capacity solver 已成熟。
7. **DISCo, ICLR 2026**：离散约束与组合检索正在升温。

### 3.3 最小核心机制

在 query–object top-L graph 上找 generalized Hall-deficient query set，只扩展这些 queries 的 ANN candidates。它能减少无关 query 的 candidate calls，但 Hall 只管 feasibility；若加入 dual/reduced-cost 保证低 cost，就回到 IDA/NIA。

### 3.4 能成立的理论性质

- generalized Hall 条件可认证 capacity feasibility；
- 若所有最优 assignment 边均在 candidate graph 中，可恢复最优解；
- 但没有新近似比，也不能只由 deficiency 推出 assignment regret。

### 3.5 一周 A0 Kill 实验

MovieLens rank-32 SVD，512 queries，capacity=1/2/4；比较 uniform top-L、deficiency expansion、oracle expansion。测 candidate edges、ANN calls proxy、feasibility、cost regret。

实测 top-1 collision 49%；相对 uniform 节省 12.2%/44.0%/35.6% candidate edges，regret <0.18%。现象为正，但不是 novelty。

### 3.6 若 A0 为正，完整论文所需实验

必须直接复现/击败 SIGMOD 2008 NIA/IDA、min-cost flow、auction/b-matching、STOC-style approximate oracle，并报告 end-to-end ANN calls、wall-clock、assignment approximation。当前没有超越机制，故不执行。

### 3.7 无 GPU 资源

16 CPU cores、32 GB RAM、<20 GB NVMe；MovieLens/embedding 均可预生成。

### 3.8 Venue fit

问题更接近 SIGMOD/VLDB；以当前贡献对 AAAI/IJCAI/NeurIPS/ICML 不足。

### 3.9 最强反方审稿

“这是 SIGMOD 2008 capacity-constrained assignment 换成 embedding，Hall witness 只是已有 incremental expansion 的弱化版本。”

### 3.10 裁决

**KILL-NOVELTY。** 正 A0 不能抵消直接先例。

## 4. Finalist B：Compact Fresh-World Distributional ANN

### 4.1 正式问题定义

对象不是点，而是 compact posterior `P_i`。每次查询独立生成 fresh world：

\[
X_{is}\sim P_i,\quad M_i=\max_{s\le S_i}\langle q,X_{is}\rangle,
\quad R_k=\operatorname{topk}_iM_i.
\]

目标是不物化所有潜在向量，直接抽样并检索该世界的 top-k。普通 ANN 的 deterministic distance 和 probable-NN 的 marginal ranking 都不等价于此目标。

### 4.2 最接近的 9 篇工作与边界

1. **DINOSAUR, 2026**：distributional representation search；最强当代威胁，常用 sample/materialize semantics。
2. **Top-k Probable NN, VLDB 2008**：按 marginal probability 排名，不返回单次联合世界。
3. **Uncertain database NN series**：证明领域并不新，语义边界必须严格。
4. **Nearest Neighbors under Uncertainty II, 2016**：不确定位置/距离理论。
5. **NNS under Uncertainty, UAI 2021**：noisy observation/oracle，不是 per-item posterior world。
6. **Probabilistic Face Embeddings, ICCV 2019**：Gaussian embedding 表示直接先例。
7. **Probabilistic Cross-Modal Embeddings, CVPR 2021**：分布表示与多样样本。
8. **Optimistic Query Routing for MIPS, 2024**：uncertain shard upper score，与 UCB route 相邻。
9. **Linear Bandits with Sublinear Time, ICML 2022**：posterior sample 后 MIPS，但只有一个全局 sampled parameter。

### 4.3 最小核心机制

对 `P_i=N(μ_i,σ_i²I)`：

\[
M_i=\langle q,\mu_i\rangle+|q|\sigma_i\Phi^{-1}(U_i^{1/S_i}).
\]

只在需要时用 `U_i` 抽样。用 `δ_i` 构造 simultaneous UCB

\[
U_i(q)=\langle q,\mu_i\rangle+|q|\sigma_i
\Phi^{-1}((1-\delta_i)^{1/S_i}),
\]

并化为 `(d+1)`-MIPS。按 UCB 枚举，直到 realized kth score 超过所有 unseen UCB。

### 4.4 能成立的理论性质

- storage 从显式 `O(S_id)` 降到 `O(d)`；
- exact ordered-UCB oracle 下，以至少 `1-Σδ_i` 返回完整 fresh-world top-k；
- oracle miss probability `η` 时最多给 `1-Σδ_i-η`；
- **不能**把普通 HNSW top-results 当作 unseen maximum certificate。

### 4.5 一周 A0 Kill 实验

20K×128D compact posteriors，fresh max-of-5；比较 brute-force world、exact progressive UCB、HNSW-UCB、matched-candidate mean-overfetch。预注册：Recall≥0.99、p95 candidates≤`50·k`（本实验 `k=10`，即 500）、对 mean 至少 +0.10。

结果：`α=0.1` 时 HNSW-UCB 0.9922 vs mean 0.9879，仅 +0.0043；`α=0.2` 时 exact UCB p50 枚举 2,239.5，HNSW-UCB 0.8156 vs mean 0.9859；`α=0.4` exact p50 枚举 7,365，HNSW-UCB 0.6953。无 regime 同时通过三门。

### 4.6 若 A0 为正，完整论文所需实验

原计划包括 DINOSAUR/probable-NN/materialized samples/mean/variance/brute force、HNSW/IVF/PQ、真实 probabilistic embeddings、posterior calibration、不同 `S_i/σ_i`、storage/latency/recall/coverage。A0 已否定核心 oracle，停止。

### 4.7 无 GPU 资源

16–32 CPU cores、32–64 GB RAM、<100 GB NVMe；可全部使用预生成 probabilistic embeddings。

### 4.8 Venue fit

若效率和 guarantee 同时成立，适合 ICML/NeurIPS（probabilistic retrieval）或 AAAI/IJCAI；当前不成立。

### 4.9 最强反方审稿

“fresh-world max-of-S 语义人为且偏爱 variance；真正需要 uncertainty 时 UCB 必然变松。你要么只是 mean-overfetch，要么退化为大扫描。”

### 4.10 裁决

**KILL-MECHANISM。** 不允许靠 learned stopping、换图或系统拼装救场。

## 5. Finalist C：Similarity-Proportional Vector Sampling

### 5.1 正式问题定义

\[
p(i\mid q)=\frac{\exp(\operatorname{sim}(q,x_i)/\tau)}{\sum_j\exp(\operatorname{sim}(q,x_j)/\tau)}.
\]

不是返回 top-k，而是在 bounded TV/KL error 下近似采样，服务 negative sampling、exploration 和 stochastic retrieval。

### 5.2 最接近的 7 篇工作与边界

Gumbel-MIPS、Fast Sampling for MIPS、RF-softmax、Locality-Sensitive Sampling、MIDX Sampler、Fair Range Sampling、hashing-based KDE estimator。前五者已直接覆盖 noisy-maximum、softmax approximation 和 query-dependent sampling；只把 ANN candidate truncation 加 tail correction 不足构成新 oracle。

### 5.3 最小核心机制

ANN candidate set + tail-mass estimator + rejection/importance correction。该组合可以工作，但部件与目标均已有。

### 5.4 能成立的理论性质

在 tail estimator 有相对误差界、proposal 覆盖所有 support 时可给 TV/acceptance bound；这些是标准 importance/rejection sampling 推论，不形成新的 ANNS 结构理论。

### 5.5 一周 A0 Kill 实验

对 synthetic/word embeddings 比较 Gumbel-MIPS、RF/MIDX、top-L truncation 与 tail-corrected sampling，测 TV、ESS、latency。因 direct prior art，实验不再执行。

### 5.6 若 A0 为正，完整论文所需实验

必须给出比 Gumbel/RF/MIDX 更强的 sublinear oracle 或误差—成本界，并在大词表、negative sampling、retrieval exploration 上证明 downstream value；当前机制不具备该条件。

### 5.7 无 GPU 资源

16 CPU cores、32 GB RAM、<50 GB NVMe；预生成词向量即可。

### 5.8 Venue fit

若有新 sampler，适合 ICML/NeurIPS；当前像旧 approximate softmax sampling。

### 5.9 最强反方审稿

“Gumbel-Max 已把 softmax sampling 化为 maximum search，后续 MIPS/LSH/RF sampler 都做过；本文只有工程组合。”

### 5.10 裁决

**KILL-NOVELTY。**

## 6. 四组 A0 的统一结论

| A0 | 必要 gate | 结果 | 裁决 |
|---|---|---|---|
| MOVE | tight sound migration envelope | p50 17.25–47× expansion，certificate=0 | KILL |
| Region certificate | 高维 region bound 有选择性 | p50 扫描约 100% | KILL |
| Capacity collective | 新机制而非经典 CCA | 现象正，但 direct prior art | KILL |
| Fresh-world distributional | recall、tail、mean gain 同时通过 | 没有 uncertainty regime 同时通过 | KILL |

## 7. 为什么“零保留”是本轮正确结果

这轮放宽视野确实找到了两个现实且典型的场景：容量耦合检索与不确定对象检索。失败不在故事，而在论文核心：前者已有同构算法，后者没有既可靠又亚线性的 unseen-bound oracle。

一个可信的下一轮入口应同时满足：

1. 场景可从公开 workload/benchmark 观察，不靠 20–50 轮强反馈或极端 noise 构造；
2. 新目标不能还原为 top-k、assignment、range、softmax sampling 或 cache/view selection；
3. 核心 oracle 在高维数据上有可测选择性，而不是先写 theorem 再假设能枚举 unseen upper bound；
4. 一周 CPU A0 能同时杀现象、机制与最强 baseline。

当前三条均不满足全部条件，因此本轮不提交 paper-ready idea。
