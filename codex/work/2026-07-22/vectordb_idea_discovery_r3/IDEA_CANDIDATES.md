# 开放生成候选漏斗

每个候选均由“背景 → 可观察现象 → 正式问题 → 旧目标缺口 → 新目标/结构”生成。下表是第一轮 14 个候选；只有通过机制查新者才进入 A0。

| # | 候选 | 新目标/结构 | 初筛裁决 |
|---|---|---|---|
| 1 | Capacity-Constrained Collective ANN | 在对象容量约束下最小化整批 assignment cost，并用 Hall deficiency 驱动候选扩展 | GO A0 → **KILL-NOVELTY** |
| 2 | Mixed-Order Vector Evolution (MOVE) | 模型迁移中按安全 envelope 复用旧空间 order，只对不确定区重算 | GO A0 → **KILL-A0** |
| 3 | Region-Certified ANN | 用粗 cell/subcell lower bounds 认证未访问区域不含 top-k | GO A0 → **KILL-A0** |
| 4 | Sparse Navigability Certificate | 证明少量 landmark/path witness 足以界定 unseen graph nodes | **KILL**：普通图遍历不存在 admissible unseen bound，且 2026 certificate 工作拥挤 |
| 5 | Distribution-Valued Probable Top-k | 对每个对象的表示分布，检索一次“新实现世界”的 top-k，而非固定样本或均值 | refine 后 GO A0 → **KILL-A0** |
| 6 | Query-Triggered Semantic Materialized View | 只为反复出现的语义区域物化高精度子索引 | **HOLD/KILL**：容易退化为 cache/view selection，无新 ANN primitive |
| 7 | Persistent Mixed-Fidelity ANN | 同一索引长期并存多维度/多精度对象，在查询时联合决定读取精度 | **KILL**：AdANNS/Matryoshka 边界过近，剩余是 storage policy |
| 8 | Similarity-Proportional Vector Sampling | 以 `exp(sim/τ)` 为目标分布直接采样对象 | **KILL**：Gumbel-MIPS、RF-softmax、LSH/MIDX sampling 直接覆盖 |
| 9 | Delta-Stable Chunk Materialization | 对变化小的对象块复用距离/order，并以 delta bound 决定重物化 | **KILL**：若 bound sound 则与 MOVE 同样膨胀；否则是 CDC/preprocessing |
| 10 | Semantic Aggregate Vector Query | 不返回对象，而估计满足语义邻域的 count/sum/quantile | **KILL**：KDE/AQP/AQUA 相邻，算法身份需另一个完整领域 |
| 11 | Expensive-Oracle Candidate Search | 向量距离便宜、真实 relevance oracle 昂贵时最小化 oracle calls | **KILL**：active search/bandit/expensive black-box 优化直接覆盖 |
| 12 | Continuous Hybrid-Score ANN | dense score 与动态 scalar/metadata score 连续组合 | **KILL**：hybrid retrieval、MIPS augmentation 与 learned rank merge 拥挤 |
| 13 | Abstaining / No-Match ANN | 当不存在足够相似对象时允许拒答，并控制 false accept | **KILL**：range/threshold/certified retrieval 可直接表达 |
| 14 | Spectral-Fidelity kNN Graph | 在构图预算下保持原 kNN 图谱性质/扩散行为 | **KILL**：未知遗漏边使 logdet/effective-resistance action 不可识别，旧 R2 已否定 |

## 三个进入深审阅的候选

### A. Capacity-Constrained Collective ANN

背景是推荐曝光、去重分发和任务—对象匹配中，同一对象不能无限服务查询。现有独立 top-k 会产生冲突；形式目标是

\[
\min_{x\in\{0,1\}^{m\times n}}\sum_{qi}x_{qi}d(q,i),\quad
\sum_i x_{qi}=k,\quad \sum_q x_{qi}\le c_i.
\]

候选机制用小 top-L 图建 bipartite graph，从违反 Hall 条件的 query subset 只扩展必要查询的候选。它相对 uniform top-L 有实验收益，但 SIGMOD 2008 已用 incremental NN 构建 capacity-constrained assignment，STOC 2014 已做 ANN-assisted approximate matching。**不是新问题，也不是新核心算法。**

### B. Compact Fresh-World Distributional ANN

背景是同一对象的未来 embedding/augmentation/measurement 并非固定向量。对对象 `i` 有紧凑后验 `P_i`，查询希望在本轮独立重采样的世界中返回 top-k，而不是把一次 materialized sample 永久冻结。

对各向同性 Gaussian 与 `S_i` 个潜在实现，

\[
M_i=\max_{s\le S_i}\langle q,X_{is}\rangle,
\quad X_{is}\sim\mathcal N(\mu_i,\sigma_i^2I).
\]

其 fresh-world score 可由一个 uniform 随机数惰性生成；同时 UCB 可化成 `(d+1)` 维 MIPS。它是本轮唯一有明确新 primitive 和紧凑表示的候选，故进入真实 HNSW A0。结果显示 sound UCB 不确定性一大就失去选择性，而 approximate HNSW 无法保证找到全局最大 unseen UCB，最终 **KILL**。

### C. Similarity-Proportional Vector Sampling

目标是从

\[
p(i\mid q)=\frac{\exp(\langle q,x_i\rangle/\tau)}{\sum_j\exp(\langle q,x_j\rangle/\tau)}
\]

近似采样，而非 top-k。它有学习、负采样和多样探索场景，但 Gumbel-MIPS、Fast Sampling for MIPS、RF-softmax、LSH sampling 与 MIDX 已形成直接机制链。**KILL**。

## 漏斗总结

- 初始候选：14
- 进入深 novelty audit：3
- 进入 CPU A0：4 个机制（MOVE、region certificate、capacity、distributional）
- 论文级 PASS：0
- 最终保留：0

没有用多个弱机制拼成系统，也没有把经典问题换名后保留。
