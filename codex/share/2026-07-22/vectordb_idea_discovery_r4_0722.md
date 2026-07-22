# VectorDB / ANNS Idea Discovery R4: Relaxed Entry, Hard A0

日期：2026-07-22
方法：ARIS `idea-discovery` → 2024–2026 mechanism Kill Map → 27 张 phenomenon cards → 11 OPEN → 6 个 A−1 → mechanism novelty audit → CPU A0 → independent xhigh review → corrective certified-enumeration A0 → review convergence

## Executive verdict

本轮专门修正了 R3 的门禁时机：概念期只因“机制同构”或“纯工程”淘汰，不因 theorem、完整算法或强 baseline 尚未齐备而杀；paper-level 强 KILL 只在 A0 后执行。漏斗实际为：

```text
27 generated → 11 OPEN → 6 A−1 → 1 A0 → 0 paper-level PASS
```

最终裁决仍是：

> **PASS = 0，HOLD finalist = 0，最终保留 = 0。**

这次 0 PASS 不能再主要归因于“把 paper gate 提前”：独立审阅确实纠正了 P01/P04 等数项过早候选级 KILL，因此它们回到 backlog；唯一 finalist P03 则完整进入 A0，并在保证级校正后追加了 sound-enumeration 实验才被杀。主要证据是：

1. **Motion-Bounded ANN 当前机制**：独立审阅纠正了 sound-vs-empirical baseline 的保证级混淆。追加的 4,096-cell sound enumeration 虽 160/160 exact，却访问 `4,047/4,096` cells、p95 做 `64,047` 次距离计算，并比 flat scan 慢 `4.15×`。`KILL-MECHANISM`。
2. **Downstream-Structural kNNG**：相同 0.8 edge recall 下低阶 eigenvalue error 相差 `6.76×`，现象为正。NeurIPS'23/ICML'25 研究的是 fully-connected kernel similarity graph，不能草率写成同构；但当前没有主动发现 kNNG critical missing edges 的算法。`HOLD-high-risk backlog`，不是 finalist。
3. **Ranking-Risk Precision Allocation**：test-oracle `0.9833` 超过 uniform 4-bit `0.9473`，所以 A−1 oracle gate 实际通过；失败的是 train-risk estimator（`0.8240`）而非整个问题。`HOLD backlog`，没有可部署机制，不是 finalist。

没有把 P01/P04/P07/P08/P11 的“尚未被杀”冒充 finalist，也没有用 delta index、radius buckets、prefetch、learned predictor 等部件拼成大系统。本轮 ledger 只否定当前形式化、当前机制或当前保证—成本路径；不主张对应研究问题永久无解。

## 1. Phase 0：拥挤区域 Kill Map

完整机制表见 `codex/work/2026-07-22/vectordb_idea_discovery_r4/LITERATURE_LANDSCAPE.md`。本轮继承并严格覆盖初始要求的全部区域：

| 必查区域 | 2024–2026/机制最近边界 | R4 结论 |
|---|---|---|
| 动态图插入、删除、修复、并发 | SPFresh、FreshDiskANN、CleANN、OdinANN、Slipstream、MFLI、Quake、Yi 2026 | 普通 update/local repair 已拥挤；只暂留利用 per-object displacement 的 P03。 |
| streaming / 连续向量流 | Big-ANN Streaming、Streaming VQ、SPFresh、Slipstream | generic streaming insert KILL。 |
| adaptive beam / early termination / hard-query | DARTH、DABS、Ada-ef、ConANN、GATE、PAG | 换 beam、阈值、hardness score KILL；P08 只能作为不同信号来源 WATCH。 |
| workload/query-aware 构建维护 | Quake、DQF、GATE、CleANN | query-log rewiring、入口和维护评分 KILL。 |
| filtered / dynamic filtered / multi-predicate | UNIFY、SIEVE、Curator、GateANN、dynamic RFANN、KHI、RNSG | 已拥挤且易偏企业场景，本轮不生成简单变体。 |
| embedding migration / compatibility | FastFill、Metric-Compatible Backfilling、Drift-Adapter、Embedding-Converter | partial scheduling、mixed-version merge 已有；Seed A 继续 KILL。 |
| multi-vector / late interaction | MUVERA、PLAID、WARP、GEM、XTR、MV-HNSW | token/page/entity 普通变体 KILL。 |
| adaptive query / sequence / closed loop | adaptive distance estimation、MQO、QVCache、relevance feedback、RaLMSpec | Seed B 已由评审与既有 A0 否定；外生 query prefix 单独作为 P05 探测。 |
| diverse / fair / robust / adversarial | diverse/fair kNN、robust ANN、RetrievalGuard | 机制拥挤；安全/攻击类也不符合本轮用户约束。 |

本轮新增的决定性边界包括 [Dynamic Similarity Graph Construction, ICML 2025](https://proceedings.mlr.press/v267/laenen25a.html)、[Optimistic Query Routing, NeurIPS 2025](https://www.microsoft.com/en-us/research/publication/optimistic-query-routing-in-clustering-based-approximate-maximum-inner-product-search/)、[Yi in-place graph update, 2026](https://arxiv.org/abs/2607.15576)、[Fast Approximation of Similarity Graphs, NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/d5c56ec4f69c9a473089b16000d3f8cd-Abstract-Conference.html)。

## 2. 开放生成与门禁审计

27 张卡中，11 个在 Phase 0 保持 OPEN：structural kNNG、cross-build stability、motion-bounded、ranking-risk precision、query-in-flight、correlated query packet、shard certificate、replica disagreement、epsilon-indifference、payload speculation、decision-preserving ANN。

首批只执行六个正交 A−1：P01/P02/P03/P04/P05/P10。其余边界如下：

- P06 与 HQI multi-query optimization、CABANA、dual-tree/batch NN 紧邻，尚无“共享证书”优于已有 batching 的证据；降为 WATCH，不进入最终候选。
- P07 同时被 optimistic shard routing 与经典 distributed top-k threshold protocol 夹住；但二者都没有直接给出 local ANN 的 sound missing-best contract。未运行 bound A0，只能 HOLD-backlog，不能写 KILL-BOUND。
- P08 的 two-replica probe 至少双倍起步成本，且与 hard-query detection/ensemble ANN 高度相邻；未探测，不升级。
- P11 尚未找到比 kNN voting 更广的可认证函数族，并与 Semantic Recall/decision-aware retrieval 相邻；未探测，不升级。

六个 A−1 的机器可读结果与判定见 `A_MINUS_1_RESULTS.md`。P01/P04 得到正必要信号但没有可执行、可分界的最小算法，只列 backlog；只有 P03 进入 A0。

## 3. Finalist A：Motion-Bounded ANN

### 3.1 正式问题定义

给定旧向量集合 `X={x_i}`、旧索引 `I(X)`、稀疏更新集合 `M` 与位移契约

\[
x_i'=x_i+\Delta_i,\qquad \|\Delta_i\|_2\le r_i,
\]

在不对每个移动点执行完整 delete+insert 的条件下，回答 fresh-world top-k `NN_k(q,X')`。目标是让查询与维护工作取决于查询决策边界带中的移动点质量，而非 `|M|`。

### 3.2 最接近工作与逐项边界

1. **Yi (2026)**：直接做 graph-based vector-level in-place update；P03 只能靠 displacement contract 区分，不能靠“避免 delete+insert”。
2. **Quake, OSDI 2025**：动态、偏斜 workload 下 adaptive partition/index maintenance；不使用已知移动半径。
3. **Approximate NNS on Dynamic Datasets (2024)**：系统评估在线数据/特征学习的动态 ANN；没有 displacement-sensitive algorithm。
4. **Graph-based NN with Dynamic Updates via Random Walks (2025)**：动态删除与 hitting-time preservation；不处理同一 ID 的小幅运动界。
5. **SPFresh / FreshDiskANN**：以 append、delete、merge/repair 维持 freshness；把新旧位置当独立更新。
6. **OdinANN / CleANN / Slipstream / MFLI**：优化并发、插入、局部维护或 SSD update path；不把位移半径转为 query certificate。
7. **Kinetic kd-Trees**：低/固定维 moving points 的 kinetic ANN；理论设置与现代高维 embedding 不同，但确立 kinetic NN 并非新领域。
8. **Indexing Moving Points**：已有 approximate NN among moving points；再次限制 P03 的问题新颖性。

### 3.3 最小核心机制

冻结旧索引，保存每个移动对象的 `r_i`。先用旧 top-k 的 fresh distance 得到可行上界 `U`；任何 fresh winner 必满足

\[
d(q,x_i)-r_i\le U.
\]

只检索该 additive-weighted boundary set 并重排。没有加入 delta graph、learned scheduler 或新 edge rule。

### 3.4 能成立的理论性质

- triangle inequality 给出 no-false-negative candidate condition；
- candidate work 上界等于 boundary-band mass `|{i:d(q,x_i)-r_i<=U}|`；
- 当该集合被完整枚举时，fresh top-k 是 exact。

理论的缺口同样明确：普通 HNSW 不能免费枚举 additive-weighted range；radius buckets 会增加多次搜索，且最坏情况仍线性。

### 3.5 一周内 A0 Kill 实验

已完成。60K MiniLM corpus、160 queries、k=10；10/20% points；random/workload-aligned movements；radius 为 median kth distance 的 0.05/0.1/0.2。预注册门要求同一 regime 同时有 stale recall `<=.95`、envelope p95 `<=5k`、old-top50 rerank `<.99`。

初始结果：gate `FAIL`。0.1 stress 下 stale recall `0.8838` 且 oracle envelope p95 `3.50k`，但 top50=`0.9994`；0.2 stress 下 top50 降至 `0.9738–0.9900`，envelope p95 却升至 `21.26–42.73k`，top100=`0.9988–1.0`。

独立审阅指出 top-L 没有 soundness，不能直接杀 certified search。于是追加固定、不可调参的 corrective A0：4,096 个旧空间 Lloyd cells，使用 `||q-c_C||-R_C-max r_i` sound lower bound best-first 枚举，禁止读取全库旧距离或 exact old order。

结果是决定性失败：160/160 exact，但 p95 做 `64,047` 次 centroid+point distance，访问 `4,047/4,096` cells；median `0.1143 s`，flat scan `0.02758 s`，慢 `4.15×`。oracle candidate set 虽小，高维 cell bound 却无法亚线性找到它。

### 3.6 若 A0 为正，完整论文所需实验

原本需要真实 paired update traces（user/item profile、continual aggregates）、HNSW/IVF/DiskANN、delete+insert、base+delta、fixed overfetch、radius buckets；报告 update throughput、query p50/p99、candidate I/O、recall 与 radius calibration。A0 已否定最小机制，不执行扩展。

### 3.7 无 GPU 资源预算

16 CPU cores、32 GB RAM、<20 GB NVMe；所有 embedding 预生成。A0 实际主 sweep 约 16 秒计算时间，不依赖 GPU。

### 3.8 Venue fit

若存在 tight/selective regime，可作为 AAAI/IJCAI 算法论文；若实现真实 NVMe update path，更像 SIGMOD/VLDB。当前结果不足以适配四个目标 AI venue。

### 3.9 最强反方审稿

“这是旧索引 overfetch 加 triangle inequality。小位移时 top-L 已解决，大位移时 bound 爆炸；你还没有计算如何亚线性找出满足 per-object bound 的点。”

### 3.10 裁决

**KILL-MECHANISM after corrective A0。** 精确含义是 KILL `motion-expanded spherical-cell certified enumeration`，不是宣称 bounded-motion ANN 永久无解。

## 4. Deep-audited Backlog B：Downstream-Structural kNN Graph Construction

### 4.1 正式问题定义

给定距离计算预算 `B`，构造 approximate kNN graph `G_B`，不再最大化无差别 edge recall，而最小化 exact graph `G*` 的结构误差，例如

\[
\|\Lambda_r(L_{G_B})-\Lambda_r(L_{G_*})\|,
\quad \|\sin\Theta(U_r(G_B),U_r(G_*))\|,
\]

或关键 conductance/cut 的失真。

### 4.2 最接近工作与逐项边界

1. **Fast Approximation of Similarity Graphs with KDE, NeurIPS 2023**：从点集直接构造 cluster-preserving sparse similarity graph；核心问题直接重叠。
2. **Dynamic Similarity Graph Construction with KDE, ICML 2025**：把同一 cluster-preserving objective 推进到动态 setting；堵住“再加更新”的逃生路径。
3. **Dynamic Spectral Clustering with Provable Approximation, ICML 2024**：维护 spectral clustering guarantee；与 downstream spectral objective 直接相邻。
4. **Spectral Sparsification of Metrics and Kernels**：证明无需完整 dense graph 也可保留 quadratic forms；理论工具与目标均相邻。
5. **Fast and Simple Spectral Clustering, NeurIPS 2023**：低成本 spectral clustering 已有强算法基线。
6. **Randomized Near-Neighbor Graphs**：从 larger-K 邻域随机选边可改善 connectivity/clustering；说明 edge identity 早已被区别对待。
7. **Refining a kNN Graph for Spectral Clustering (2021)**：直接为 spectral clustering refine kNN graph。
8. **aKNNO (2024)**：shared-neighbor/adaptive-k graph 服务 clustering；局部 overlap proxy 也不是新结构。
9. **NN-Descent / modern kNNG builders**：优化 approximate graph construction；是效率 baseline，但不直接保证 spectrum。

### 4.3 最小核心机制

从一个 overcomplete candidate graph 中，用 local neighbor overlap/cut-risk 决定保留或继续发现哪些边；预算优先给可能改变低阶 spectrum 的局部区域。

### 4.4 能成立的理论性质

若能构造

\[
(1-\epsilon)L_*\preceq L_B\preceq(1+\epsilon)L_*,
\]

则 Rayleigh quotient、eigenvalue 和带 eigengap 的 eigenspace 均稳定。困难在于从不完整候选图主动发现 unknown critical edges；在错图上估计 effective resistance 不自动得到该保证。

### 4.5 一周内 A0 Kill 实验

已先完成 A−1：2,504 个 MovieLens semantic vectors、11 groups、k=15；构造相同 directed edge recall 的近似图。edge recall 同为 0.8 时，低阶 eigenvalue error 从 `0.0171` 到 `0.1154`（`6.76×`）。必要现象明确为正。

独立审阅纠正了 novelty 表述：最近工作构造的是 fully-connected kernel similarity graph 的 cluster-preserving sparsifier，而这里是有限 ANN distance budget 下主动发现 kNNG 的 critical missing edges。两者高度相邻，但不能仅凭标题/下游目标宣布同构。当前仍因没有“发现缺失关键边”的可执行算法而不进入 A0。

### 4.6 若 A0 为正，完整论文所需实验

必须在相同 distance calls 下直接击败 KDE similarity graph、spectral sparsification、NN-Descent/HNSW kNNG、random larger-K selection，并证明能发现候选图中原本缺失的 critical edges；还需 spectral clustering、label propagation、UMAP 多任务与至少 1M scale。当前没有区别机制。

### 4.7 无 GPU 资源预算

16 CPU cores、32–64 GB RAM、<50 GB NVMe；谱分解只对 sparse graph，embedding 预生成。A−1 实际约 11 秒。

### 4.8 Venue fit

问题天然适合 NeurIPS/ICML，但当前 proposal 与已有 NeurIPS/ICML 工作高度相邻且没有区别性算法；venue fit 不能弥补这一缺口。

### 4.9 最强反方审稿

“你重新发现了 cluster-preserving similarity graph construction。用 edge-recall 反例说明 spectrum 更重要是动机，不是新算法；local overlap 也不能发现当前候选图里根本不存在的边。”

### 4.10 裁决

**HOLD-high-novelty-risk backlog。** 必要现象通过；当前 local-overlap mechanism 不足，且不是本轮 finalist。

## 5. Deep-audited Backlog C：Ranking-Risk Precision Allocation

### 5.1 正式问题定义

对 corpus objects/regions 分配离散精度 `b_i`，满足 `sum_i b_i<=B`，最小化 query distribution 下的 top-k ranking inversion risk，而非平均重构误差：

\[
\min_{b_i}\;\mathbb E_{q\sim Q}
\big[\ell(\operatorname{topk}(s(q,X)),
\operatorname{topk}(s(q,\hat X(b))))\big].
\]

### 5.2 最接近工作与逐项边界

1. **ScaNN anisotropic vector quantization**：明确最小化与 ranking 更相关的方向误差，而非 isotropic MSE；击穿“首次 ranking-aware quantization”。
2. **RaBitQ (2024)**：提供高效且有理论误差控制的 binary quantization/distance estimation。
3. **LeanVec (2024)**：低维/低精度 primary representation 加高精度 secondary refinement；强 mixed-fidelity baseline。
4. **Locally-adaptive Vector Quantization (LVQ)**：按局部数据分布调整量化，而非纯全局 codebook。
5. **AQR-HNSW (2026)**：ranking-aware quantization 与 HNSW 结合；直接压缩 loss-level novelty。
6. **Binary Quantization Ranking-Fidelity Theory (2026)**：把 quantization error 与 ranking fidelity 理论联系起来。
7. **AdANNS**：联合选择 representation/search fidelity；限制 query-adaptive mixed precision 的空间。
8. **Product Quantization / OPQ / Quicker ADC**：固定字节下的经典压缩与强性能基线。

P04 唯一可能的边界是“per-object/region bits allocation”，而不是新的 ranking loss。

### 5.3 最小核心机制

从 train query margins 估计每个 object 升级精度带来的 inversion-risk reduction，若离散收益递减，则用 greedy/water-filling 在 fixed total bytes 下分配 residual precision。

### 5.4 能成立的理论性质

- 在独立风险 surrogate 且每项收益递减时，greedy/water-filling 最优或有标准近似保证；
- 量化误差包络可上界 pairwise inversion；
- 但 top-k loss 有对象交互，真实 objective 不天然可分解或次模。

### 5.5 一周内 A0 Kill 实验

A−1 已执行 oracle-headroom gate：100K MiniLM，150 train/150 test，2/8-bit mixture 的平均预算等于 4 bits。uniform 4-bit Recall@10=`0.9473`；train ranking-risk mixed=`0.8240`；MSE mixed=`0.8133`；random mixed=`0.8100`；泄漏 test-risk oracle=`0.9833`。

按 A−1 的原始定义，必要条件其实通过：test-oracle 比 uniform 4-bit 高 `3.6` recall points。失败的是当前 train-risk estimator：收益高度 query-specific，静态 per-object score 不泛化；两级 mixture 输 uniform precision `12.3` recall points。没有识别出既可部署、又不退化为 query-conditioned progressive rerank 的最小机制，故不进入 A0。

### 5.6 若 A0 为正，完整论文所需实验

需要 SIFT/Deep/GloVe/text 多数据集、PQ/LVQ/LeanVec/RaBitQ/AQR-HNSW、相同 bytes/latency、query shift、region/object granularity、bits levels、risk calibration 与 allocation ablation。还必须显示不是 query-conditioned residual fetch 或普通 two-stage rerank。当前 gate 已失败。

### 5.7 无 GPU 资源预算

16 CPU cores、32 GB RAM、<20 GB NVMe；预生成 embedding 与 scalar/PQ code 足够。A−1 约数十秒。

### 5.8 Venue fit

若 allocation objective 与近似性质成立，适合 ICML/NeurIPS/AAAI；当前只是一个不能泛化的 workload heuristic。

### 5.9 最强反方审稿

“ranking-aware quantization 已有；你的新意只剩把 bits 分给不同对象，但某对象是否在 top-k boundary 完全取决于 query。静态风险不泛化，query-conditioned 精度又退化成已有 reranking/refinement。”

### 5.10 裁决

**HOLD backlog；KILL current static train-risk estimator。** 不是本轮 finalist。

## 6. 其余候选的裁决账本

| 候选 | 证据 | 裁决 |
|---|---|---|
| P02/P09 stability | ef80 recall=.9887、Jaccard=.9811、any-swap=6.67%，多数 churn 是 near-tie；未跑 fixed-seed/order 对照 | HOLD-low-priority |
| P05 query-in-flight | 75% prefix top100 对 final top10 coverage p10=.29；final 前无 sound certificate | KILL-MECHANISM |
| P10 payload speculation | walker ANN recall=.57，不能外推高 recall；current form 缺 ANN-specific survival mechanism | INVALID probe；KILL current form as generic prefetch |
| P06 correlated packet | HQI/CABANA/dual-tree/MQO 边界强；尚无非 batching 的实证 | WATCH，不是 finalist |
| P07 shard certificate | optimistic routing + distributed TA 很近，但 local-ANN sound missing bound 未实验 | HOLD-backlog，非 finalist |
| P08 replica disagreement | two-probe 起步成本与 hard-query/ensemble 边界未越过 | WATCH，不是 finalist |
| P11 decision-preserving | 只在窄 voting case 有明显 certificate，task-aware recall 先例强 | WATCH，不是 finalist |

## 7. 对“方向饱和还是 KILL 太强”的更新

R4 提供了比主观拆分更直接的过程证据：

- 11/27 候选在概念期保留，6 个得到可执行 probe，说明 entry gate 已明显放宽；
- 3/6 得到必要正信号（P01、P03、P04 oracle），说明没有要求初稿就 paper-ready；
- P01/P04 因没有稳定的、与最近工作可分界的可执行机制进入 backlog，而非候选级 KILL；P03 经独立审阅要求的 corrective A0 才被杀；
- 其余 4 个不是“理论不完整”，而是 oracle 不泛化、真实 tail 失效、现象太小或收益/平台均不足。

因此本轮 0 PASS 更接近“局部空间拥挤 + 唯一可执行最小机制经 sound enumeration 失败”。审阅也确认：P01/P04/P07 只能是证据意义的 backlog，不能用“尚未失败”冒充 finalist。合理动作不是继续放松 A0，而是下一轮换一个新的 workload corpus/primitive。

## 8. 可复现性与资源

工作目录：`codex/work/2026-07-22/vectordb_idea_discovery_r4/`

- literature / candidates：`LITERATURE_LANDSCAPE.md`、`IDEA_CANDIDATES.md`
- A−1 汇总：`A_MINUS_1_RESULTS.md`
- A0 汇总：`A0_RESULT.md`
- scripts：`a_minus_1/`、`a0/`
- raw JSON：`results/`
- 独立审阅与收敛：`INDEPENDENT_REVIEW.md`

所有实验使用 CPU 与已有预生成 embedding；无 GPU 训练、无外部服务、无完整 VectorDB/OS 实现。
