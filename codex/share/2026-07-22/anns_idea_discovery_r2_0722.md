# VectorDB / ANNS Idea Discovery R2

Date: 2026-07-22
Method: ARIS `idea-discovery` → literature Kill Map → 11-candidate generation → 3-way novelty audit → independent research review → two-round refinement → experiment pre-gate

## Executive verdict

本轮没有为了凑数给出 paper-ready `PASS`。经过机制级查新和两轮外部压力测试，最终只保留一个研究问题：

> **Trajectory-Stable ANN / Result-Sensitive Feedback ANN — `HOLD-RETHINK`**

问题本身仍有论文价值，但最初的 HNSW frontier certificate 已被一个严格反例击杀。当前只允许先做一个小型 `realized result-change stopping` pre-gate；它若不能在 matched hardness、equal wall-clock 下显著优于 patience/margin/DARTH-style 基线，就应 `KILL-DYNAMIC-EF`。

两个原重点 seed 的结论：

- **Seed A — Budgeted Embedding Migration：KILL。** FastFill 已直接覆盖 policy-based partial backfill 和 uncertainty ordering，WACV 2025 又覆盖 mixed-version rank merge；剩余 query-risk coverage 很可能只是另一个 priority score。
- **Seed B — Trajectory-Stable ANN：HOLD-RETHINK。** exact-reference trajectory objective 仍相对空缺，但“反馈循环”和“近似误差传播”并不新，当前可观察机制尚未达到论文标准。

## 1. 最近项目历史给出的本地 Kill Map

| 已探索家族 | 本地证据 | 本轮约束 |
|---|---|---|
| Graph aging / 局部修复 | IP-DiskANN 与 PipeANN 未出现 gate-level recall/comparison degradation；equal-edge 与 shadow replay 消除了表象。 | 不再换 repair score、maintenance trigger 或 edge rule。 |
| Dynamic SSD aging | `O_DIRECT` canary 中 churn 后 distinct pages 反而下降 3.76%/6.12%；in-place 路线写放大 4.03×。 | tombstone locality、page coalescing、简单 COW/in-place 变体均 KILL。 |
| Workload self-healing graph | 没有因果退化，且 Quake/GATE/CleANN/hard-query repair 已拥挤。 | query-aware rewiring/entry tuning KILL。 |
| Low-DRAM / SSD placement | AiSAQ、LM-DiskANN、PipeANN、DiskANN、PiPNN 与既有 pilot 已覆盖主要机制。 | 不做“把内存算法搬到 SSD”。 |
| Filtered / permissions | UNIFY、SIEVE、Curator、GateANN、dynamic range-filtered ANN、多属性范围索引已密集。 | 拥挤且不符合本轮风格。 |
| Multi-vector page pruning | 本地 bound 不够紧；MUVERA/PLAID/WARP/GEM 已覆盖降维与 pruning。 | 新 page summary/token threshold 不足。 |
| Agent cache closed loop | T2 A0-R2 没有 closed/open-loop 分离。 | 不能把 cache admission 重新包装成 trajectory。 |
| Embedding topology reuse | Gaussian drift 无效，edge watermark 无法推出 RobustPrune；仅 seeded NN-descent 有增量性。 | 不把 migration scheduling 偷换成 graph warm-start。 |

这张本地图首先排除了“安全、恢复、权限、WAL/LSM、企业生命周期”以及没有新算法目标的系统拼装。

## 2. 2024–2026 机制级拥挤区域

本轮不是按候选名称搜，而是按 state–action–objective 的最近机制搜。

| 区域 | 2024–2026 最近机制 | 裁决边界 |
|---|---|---|
| 动态 insert/delete/repair/concurrency | [CleANN](https://arxiv.org/abs/2507.19802)、[random-walk dynamic updates](https://arxiv.org/abs/2512.18060)、[OdinANN](https://www.usenix.org/conference/fast26/presentation/guo)、DEG | 新插入/删除/局部修复规则高度拥挤。 |
| Streaming / continuous flow | [Big ANN streaming track](https://big-ann-benchmarks.com/)、[Slipstream](https://arxiv.org/abs/2606.02992)、[dynamic-dataset study](https://arxiv.org/abs/2404.19284) | append-only、arrival reuse、stream-aware insert 已占；moving-vector 还受 kinetic NN 老文献约束。 |
| Adaptive beam / termination / hardness | [DABS](https://proceedings.neurips.cc/paper_files/paper/2025/hash/904fe070f484231aa26dbdb37816cd40-Abstract-Conference.html)、[DARTH](https://arxiv.org/abs/2505.19001)、[GATE](https://arxiv.org/abs/2505.10948)、dynamic hardness repair、PAG | 换 beam、threshold、entry 或 hardness score 均 KILL。 |
| Workload/query-aware graph | Quake、GATE、CleANN、hard-query repair | query-log-driven rewiring 已拥挤且本地 A0 为负。 |
| Filtered/dynamic/multi-predicate | [UNIFY](https://www.vldb.org/pvldb/vol18/p1118-yao.pdf)、[dynamic RFANN](https://www.vldb.org/pvldb/vol18/p3256-deng.pdf)、SIEVE、Curator、GateANN、KHI、RNSG | 直接 KILL。 |
| Embedding migration | [FastFill](https://arxiv.org/abs/2303.04766)、[Metric-Compatible Online Backfilling](https://openaccess.thecvf.com/content/WACV2025/html/Seo_Metric_Compatible_Training_for_Online_Backfilling_in_Large-Scale_Retrieval_WACV_2025_paper.html)、[Drift-Adapter](https://aclanthology.org/2025.emnlp-main.805/)、Embedding-Converter、Query Drift Compensation | Seed A 的 broad formulation 已被直接命中。 |
| Multi-vector / late interaction | [MUVERA](https://papers.nips.cc/paper_files/paper/2024/hash/b71cfefae46909178603b5bc6c11d3ae-Abstract-Conference.html)、alpha-reachable graphs、PLAID/WARP/GEM | token/page pruning 不是新目标。 |
| Adaptive query / sequence / closed loop | adaptive distance estimation、adversarially robust ANN、QVCache、relevance feedback | 逐查询正确性与复用已覆盖；exact-reference future-state loss 仍是窄空隙。 |
| Diverse/fair/robust/adversarial | diverse kNN、LotusFilter、multi-attribute fair kNN、robust ANN、RetrievalGuard | 不作为本轮备选。 |

完整检索表见工作区 `LITERATURE_LANDSCAPE.md`。

## 3. 开放生成与淘汰漏斗

共生成 11 个从“背景 → 可观察现象 → 正式问题 → 旧目标缺口 → 新目标”推导的候选：

| 候选 | 最终结果 | 原因 |
|---|---|---|
| Trajectory-Stable ANN | **HOLD-RETHINK** | 问题仍有价值；frontier certificate 被反例击杀，Route A 尚像 dynamic `ef`。 |
| Query-Coverage Budgeted Backfill | **KILL** | FastFill 已做部分 backfill scheduling/ordering；标准 submodular surrogate 不构成 novelty。 |
| Spectral-Fidelity kNN Graph | **KILL** | known-edge logdet/submodularity 不能迁移到发现/替换未知 kNN 边的 action。 |
| Globally Budgeted Batch ANN | KILL | 易还原为 per-query adaptive effort。 |
| Query-Tube Certified ANN | KILL | continuous/moving kNN 与 safe-region 机制已占。 |
| Conformal Candidate-Superset ANN | KILL | ConANN 直接命中。 |
| Distributionally Robust Workload Graph | KILL | workload-aware graph 拥挤。 |
| Query-Weighted Multi-Metric ANN | KILL | weighted-space/multi-metric ANN 已有直接先例。 |
| Progressive-Coordinate ANN | KILL | ADSampling、RaBitQ、MRQ 等成熟。 |
| Late-Interaction Token-Budget ANN | KILL | PLAID/XTR/WARP/MUVERA/GEM 与本地负结果共同封堵。 |
| Large-k ANN | KILL | BBC 2026 直接覆盖。 |

没有通过添加 LSM、cache、WAL、RL、GNN、bandit 或 SSD port 来救任何候选。

## 4. 唯一保留候选：Trajectory-Stable ANN

### 4.1 正式问题定义

令检索状态、查询、近似结果为

\[
q_t=G_t(s_t),\qquad
\widehat R_t=\operatorname{ANN}_k(q_t;b_t),\qquad
s_{t+1}=F_t(s_t,\widehat R_t),
\]

精确反事实轨迹为

\[
q_t^\star=G_t(s_t^\star),\qquad
R_t^\star=\operatorname{kNN}_k(q_t^\star),\qquad
s_{t+1}^\star=F_t(s_t^\star,R_t^\star).
\]

在总成本 `sum_t c(b_t) <= B` 下，目标是最小化

\[
\sum_{t=1}^{H}\lambda_t d(s_t,s_t^\star)
+\lambda_H^{\mathrm{term}}d(s_H,s_H^\star),
\]

而不是独立优化每一步 Recall@k/latency。实验必须进一步分开：同一 `q_t` 上的直接 ANN error、`Exact(q_t)` 与 `Exact(q_t*)` 之间的纯 state drift，以及端到端误差。

### 4.2 最近的 10 篇工作及边界

| 工作 | 最近重合 | 仍可主张的窄边界 |
|---|---|---|
| [Nearest Neighbor Search for Relevance Feedback, CVPR 2003](https://vision.ece.ucsb.edu/sites/vision.ece.ucsb.edu/files/publications/03CVPRJelena.pdf) | 反馈循环中的重复 NN 与连续轮复用 | 没有 exact/approximate counterfactual trajectory objective。 |
| [Approximate kNN for Active Relevance Feedback, 2008](https://digitalcommons.njit.edu/fac_pubs/13040/) | **最致命早期先例**：approximate kNN 已放进反馈循环并增加少量反馈轮数 | 没有 total-budget trajectory fidelity；因此“误差传播”不能当 novelty。 |
| [SALSAS, 2011](https://www.sciencedirect.com/science/article/abs/pii/S0031320310005753) | LSH/approximate kNN 支持迭代 active retrieval | 固定 scalable learner，而非 exact-reference control。 |
| [Generative Multi-hop Retrieval, 2022](https://arxiv.org/abs/2204.13596) | 多跳检索 error propagation | 表示/生成误差，不隔离 ANN effort。 |
| [Early Exit for Dense Retrieval, CIKM 2024](https://doi.org/10.1145/3627673.3679903) | query-dependent IVF depth 与 patience/cascade | independent-query objective。 |
| [Adaptive Search via Sketching, ICML 2025](https://proceedings.mlr.press/v267/feng25c.html) | answer-dependent adaptive queries 的正确性 | 防随机性利用，不以 future state 为 loss。 |
| [DABS, NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/904fe070f484231aa26dbdb37816cd40-Abstract-Conference.html) | query-specific graph-search stopping | 逐查询 guarantee。 |
| [DARTH, SIGMOD 2026](https://arxiv.org/abs/2505.19001) | hard-query-aware declarative recall/termination | 最强算法威胁；若只换 score 就被其吸收。 |
| [Multiple-Query Optimization for ANNS, ICLR 2026 submission](https://openreview.net/forum?id=rZyQVls8TD) | correlated query 的 result/entry reuse | query batch 外生，目标是复用。 |
| [QVCache, 2026](https://arxiv.org/abs/2602.02057) | temporal-semantic query locality | cache latency/hit objective，不是 endogenous fidelity。 |

### 4.3 最小核心机制及其审阅结果

最初机制是：从普通 HNSW/Vamana 的 unresolved frontier 构造可能 top-k alternatives，经反馈函数 push-forward 后决定继续搜索。两轮审阅后，该机制 **KILL**：

> 在标准图搜索 checkpoint，所有 discovered candidates 都有精确 query distance，`C_t` 已是 discovered points 中最近的 k 个。因此一个 discovered 的 exact top-k 点不可能被遗漏在 `C_t` 外；真正 miss 必然是 undiscovered，无法位于所谓 frontier alternative set。

因此只保留一个最小、诚实的 Route A pre-gate：在固定 expansion blocks 后观测

\[
z_\ell=|F(s_t,C(b_\ell))-F(s_t,C(b_{\ell-1}))|,
\]

用最近几次 **realized feedback-summary displacement** 判断是否购买下一 block。它不声称覆盖 unseen objects、不声称 certificate，也不预知下一 block 的收益。若它不能明显胜过普通 result-set patience/hardness stopping，则整个方向 KILL。

Route B 是更换为带 admissible unseen-region bounds 的 branch-and-bound/bounded-cell index。经典 branch-and-bound kNN、relevance-feedback clustering index 已构成强边界，而且高维 cell bound 很可能过松；它需要单独查新与 tightness pilot，本轮不把它拼入 TraceGuard。

### 4.4 当前能成立与不能成立的理论性质

能成立：

- exact-reference trajectory 与三项因果误差分解是形式清楚的目标；
- 对 affine/additive feedback，若**外部给定**的候选 superset 真包含至多 `m` 个遗漏对象，可用三角不等式给出 multi-miss 一步状态误差上界；
- discovered-frontier coverage 在标准 exact-distance graph search 中对非零 miss 不可能成立，这一反例明确否定了原 certificate。

不能成立：

- hard top-k map 不是全局 Lipschitz，不能只用 `F/G` 的 Lipschitz 常数推出 trajectory bound；
- 当前 query 的 k/(k+1) gap 不能认证下一 query 的 top-k stability；
- realized result-change 不保证单调，也不能在支付下一 expansion 前知道 `z_{l+1}`；
- 不应声称 submodularity、water-filling optimality 或通用 certificate。

### 4.5 一周内 A0 Kill 实验

已有 SIFT100K micro-pilot 的正信号：centroid `ef=12` 时 local recall 95.30%、open-loop recall 94.84%，但 terminal overlap 仅 81.50%；Rocchio `ef=40` 时 local recall 97.23%、terminal overlap 86.88%。这只说明值得做 pre-gate，不是论文证据。

一周 A0：

1. 重构为四路径因果分解，复现 pilot，并记录 geometric effort checkpoints。
2. 在 SIFT + GloVe/Deep/text embedding、centroid + label-grounded Rocchio 上测 `z_l` 对 eventual exact-local summary error 的预测力。
3. 匹配 local recall、top-k Jaccard patience、exact margin、visited nodes 和 DARTH-style hardness，验证 `z_l` 是否仍有增量信息。
4. 比较 uniform、result patience、margin、hardness、Route A 与 offline oracle；锁定阈值后在第二数据集测试。
5. 计入 checkpoint、summary update、vector ops、distance computations、wall-clock 和 SSD reads。

硬门：两数据集存在至少 15-point causal terminal separation；Route A 在 equal wall-clock 下相对最强基线至少降低 25% terminal divergence；增量预测与 ablation 均成立。任一失败即 KILL。

### 4.6 A0 为正后的完整论文实验

- HNSW + Vamana/DiskANN 两个 CPU ANN family，1–10M vectors；
- 至少 1,000 条 trajectory、三种 index seed/config、`k={10,50}`、`H=8–32`；
- 一个公开 relevance-feedback/session trace 或 label-grounded benchmark；
- 全 quality–latency / quality–distance Pareto front，而非单预算点；
- contractive negative regime、near-tie strata、controller overhead 与 NVMe page reads；
- 在完整结果前重新做一次“feedback-summary convergence stopping”查新；不能沿用已被杀掉的 certificate novelty。

### 4.7 无 GPU 资源预算

- A0：16–32 CPU cores，64–128 GB RAM，12–72 aggregate CPU-hours，新增 NVMe <100 GB，GPU 0。
- Full：同类机器 1–2 周，100–300 aggregate CPU-hours，100–300 GB NVMe，使用预生成 embedding。

### 4.8 Venue fit

- **AAAI/IJCAI：中等。** 若形成清楚的 sequential retrieval objective、grounded feedback task 和跨 ANN family 结果，是最现实路线。
- **NeurIPS/ICML：当前偏弱。** 只有在 result-change signal 与 single-query hardness 存在明确统计/理论分离，并有非平凡 generalization 时才适合。
- 若贡献最终变成 bounded-cell index 或 I/O layout，应重新路由数据库/系统 venue，而不是强贴 AI venue。

### 4.9 最强反方审稿

> Approximate kNN in relevance-feedback loops has been studied since at least 2008. The claimed frontier certificate is vacuous because every genuine top-k miss is undiscovered in standard graph search. After removing that claim, the method is a patience-style dynamic-ef heuristic over an artificial feedback law; the global trajectory theorem ignores the discontinuity of hard top-k, and all gains may vanish under wall-clock accounting or a DARTH-style baseline.

### 4.10 裁决

**HOLD-RETHINK，不是 PASS。**

- 问题重要性：4/5。
- 当前机制 novelty：2–3/5。
- 理论完整性：原机制 KILL；Route A 仅有可观察性，没有 certificate。
- A0 可证伪性：5/5。
- CPU/NVMe 可行性：5/5。

只允许先跑 Route A pre-gate。若只是“结果变化大时增加 `ef`”，立即 KILL；不要再添加 learned predictor、cache、entry reuse、new graph 或 agent planner 来救。

## 5. 两个被淘汰的 finalist

### Seed A / Query-Coverage Budgeted Backfill — KILL

[FastFill](https://arxiv.org/abs/2303.04766) 已有 learned uncertainty policy、partial gallery backfill 和 backfill curve；[WACV 2025](https://openaccess.thecvf.com/content/WACV2025/html/Seo_Metric_Compatible_Training_for_Online_Backfilling_in_Large-Scale_Retrieval_WACV_2025_paper.html) 已处理 old/new distance-rank merge；Lambda-Orthogonality 又提供 partial-backfill ordering。一个 `sum_q w_q g_q(sum_i r_qi)` surrogate 在 concave `g_q` 下的单调次模性是标准结果，但 actual mixed-version recall 不保证单调/次模，而且未 re-embed 前存在风险信息闭环。除非能直接大幅击败 FastFill，否则不再投入。

### Spectral-Fidelity kNN Graph — KILL

Stars、NeurIPS 2023 similarity graph、SODA 2021 metric/kernel spectral sparsification、NeurIPS 2025 structure-aware sparsification、kNN refinement、CkNN、TOPOGRAPH、effective-resistance/logdet edge selection 已覆盖大部分语言。致命点是：logdet 次模性针对**已知 edge set**；ANN refinement 会发现未知边、删除 false edge、触发 degree replacement，action 不保证单调或次模。当前错图上的 effective resistance 也未必能发现缺失 bridge。窄化为 Active Spectral Certification 后虽数学较干净，但 candidate discovery 才是瓶颈，且更像 active graph learning 而非 ANNS，故不保留。

## 6. 最终建议

本轮最有价值的结果不是一个包装完整的新系统，而是三项排除：

1. Seed A 已被 FastFill 直接占位；
2. 普通 HNSW frontier 无法为 unseen true neighbors 提供 result-alternative certificate；
3. 高 local recall 与 terminal trajectory loss 的 pilot 信号仍值得一个严格、低成本的 causal pre-gate。

下一步只建议执行 `EXPERIMENT_PLAN.md` 中的三日机制 pre-gate。它若过门，再做第二 ANN family 与 fresh novelty check；不过门就结束 Trajectory-Stable ANN，不再拼组件。
