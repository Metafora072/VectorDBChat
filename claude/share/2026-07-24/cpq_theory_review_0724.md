# Certified Progressive Quantization (CPQ) 理论评审

**Date:** 2026-07-24
**Author:** Claude（严格反方评审者身份）
**Ruling:** `PASS-CPQ-THEORY-CANDIDATE`（附重大条件）

---

## A. Novelty Kill Map

逐项覆盖 Gpt 列出的 11 个方向，判断 CPQ 是否已被覆盖。

### 1. Successive Refinement（逐级精化，率失真理论）

**已知结果：** Equitz & Cover (1991, IEEE Trans. IT) 和 Rimoldi (1994) 证明高斯源可逐级精化——即每一级的率失真最优编码可以通过对上一级编码追加比特得到。

**覆盖了 CPQ 什么：** 嵌套码的信息论可行性。即"progressive prefix 的 rate-distortion 损失是否可控"这个问题已有部分回答——对高斯源，损失为零。

**最接近的定理：** Successive refinability theorem (Equitz & Cover 1991).

**能否直接拼出 CPQ：** 不能。Successive refinement 只处理重构质量，不涉及搜索决策、distance interval、graph path coupling 或 adaptive refinement policy。它回答的是"嵌套码的编码效率损失是多少"，不是"什么时候可以停止读码"。

**CPQ 还需要什么：** 搜索决策驱动的 prefix acquisition + distance certificate + graph-path coupling。

### 2. Residual / Additive Quantization

**已知工作：**
- Residual Quantization (RQ): Chen, Guan & Lu (2010, IEEE Trans. NNLS)
- Additive Quantization (AQ): Babenko & Lempitsky (CVPR 2014)
- Composite Quantization: Zhang, Du & Wang (ICML 2014)
- Stacked Quantizers: Martinez, Clement, Hoos & Little (CVPR 2014)

**覆盖了 CPQ 什么：** 多级码构造和逐级改进的重构。RQ/AQ 天然提供嵌套码 $\hat{x}^{(t)} = c^{(1)} + \cdots + c^{(t)}$，这正是 CPQ Route A 的编码基础。

**最接近的算法：** RQ 的逐级残差编码 = CPQ Route A 的码构造。

**能否直接拼出 CPQ：** 不能。RQ 只提供编码。搜索时仍然使用固定码率的 ADC 查表，不会根据比较难度自适应读取更多层。没有 distance interval、certification 或 adaptive stopping。

**CPQ 还需要什么：** 残差范数界 → distance interval → comparison certification → 搜索时的自适应 prefix acquisition。

### 3. QINCo / QINCo2

**已知工作：**
- QINCo: Huijben et al. (ICML 2024) — 跨层依赖的神经残差量化
- QINCo2: Huijben et al. (NeurIPS 2024 或 arXiv 2024) — 改进版

**覆盖了 CPQ 什么：** 提供极高质量的多级残差码。QINCo 的跨层条件编码使得每一级残差更小，但代价是丢失了级间独立性。

**对 CPQ 的影响：** QINCo 的跨层依赖使得 prefix distance bound 更紧（残差更小），但 inference 需要串行前向传播，搜索时逐层展开的计算成本可能不低。更关键的是，QINCo 仍然是固定码率使用的——论文中没有"按需展开前缀"的搜索机制。

**能否直接拼出 CPQ：** 不能。QINCo 可以作为 CPQ Route C 的编码器，但搜索时的 adaptive refinement、distance certificate、path coupling 都是全新的。

### 4. RaBitQ 及 Flexible-Rate 后续

**已知工作：**
- RaBitQ: Gao et al. (SIGMOD 2024) — 随机位量化，提供无偏距离估计和概率误差界
- RaBitQ v2 / FastScan integration: Gao et al. (PVLDB 2025)
- 可能存在 flexible-rate 扩展

**覆盖了 CPQ 什么：** **这是 CPQ 最危险的先行工作。** RaBitQ 的核心贡献就是提供了可证明的距离估计误差界：

$$|\hat{d}_{RaBitQ}(q,x) - d(q,x)| \leq \epsilon \text{ w.p. } \geq 1-\delta$$

RaBitQ 给出了距离估计的 concentration inequality，并且其随机投影结构天然支持 prefix nesting（前 m 个随机位 → 前 m 个投影的距离估计）。

**最接近的定理/算法：** RaBitQ 的距离估计误差界 = CPQ Route B 的 confidence interval 构造的一个实例。

**能否直接拼出 CPQ：**

**这是最关键的判断。** 理论上，RaBitQ 的随机投影 + concentration bound + prefix nesting = CPQ Route B 的编码 + 置信区间。但 RaBitQ 论文中：
- 没有实现 prefix/progressive 读取
- 没有 beam-decision-driven adaptive refinement
- 没有 graph-path coupling 理论
- 没有 gap-dependent acquisition complexity 分析
- 搜索仍然是固定码率

**这意味着 RaBitQ 提供了 CPQ Route B 所需的核心编码和 per-estimate bound，但 CPQ 的核心贡献——搜索时的自适应前缀获取及其理论保证——完全不在 RaBitQ 的范围内。**

**CPQ 还需要什么：** 搜索时的 adaptive prefix acquisition policy + anytime-valid confidence under adaptive graph traversal + gap-dependent total cost analysis。

**风险评估：** 如果 RaBitQ 团队后续发表一篇 "Progressive RaBitQ for Graph ANN" 的论文，CPQ 的 novelty 空间会被显著压缩。但目前没有这样的工作。

### 5. Probabilistic Routing / PEOs

**已知工作：**
- PEOs (Probabilistic Early-Out): Li et al. (PVLDB 2024 或类似)
- FINGER: Chen et al. (NeurIPS 2023) — hash-based routing
- 各种 coarse filter → exact distance 的两阶段方案

**覆盖了 CPQ 什么：** PEOs 解决的是"是否值得计算精确距离"——这是一个 coarse-or-exact 的二元决策。这与 CPQ 的多级渐进精化有本质区别。

**能否直接拼出 CPQ：** 不能。PEOs 只有两级（coarse estimate → exact distance），不是多级渐进。从 PEOs 到 CPQ 需要：多个中间精度层 + 前缀嵌套 + 非二元的 refinement policy + 信息获取成本分析。

### 6. Adaptive Distance Estimation for kNN

**已知工作：**
- Best Arm Identification (BAI): Jamieson & Nowak (COLT 2014), Kaufmann et al. (COLT 2016)
- Gap-dependent sample complexity: $O(\sum_i \Delta_i^{-2} \log(n/\delta))$ for top-1 identification
- Simchowitz et al. (COLT 2017) "The simulator" — instance-optimal BAI

**覆盖了 CPQ 什么：** **CPQ 的 gap-dependent acquisition complexity 理论的直接来源。** BAI 的标准 gap-dependent bound 与 CPQ 的 $m_e = O(C^2/\Delta_e^2 \cdot \log(|\mathcal{E}|/\delta))$ 结构完全相同。

**最接近的定理：** BAI 的 gap-dependent sample complexity upper/lower bounds.

**能否直接拼出 CPQ：** **几乎可以直接套用框架，但有关键差异：**

1. BAI 假设每次采样（pull an arm）获得新的独立观测。CPQ 中，每次"展开一层码"获得的信息是确定性的（deterministic code）或有结构化依赖的（structured random projection），不是 i.i.d. 采样。

2. BAI 的候选集固定。图搜索中，候选集随搜索进程动态变化——新节点被发现，旧候选被淘汰。这产生了 BAI 理论中不存在的自适应候选集问题。

3. BAI 直接比较所有 arm。图搜索只比较相邻候选或 beam 边界候选。

**CPQ 还需要什么：**
- 从 i.i.d. sequential sampling 到 deterministic/structured prefix decoding 的理论转换
- 候选集动态变化下的 gap-dependent 分析
- Graph 遍历结构的利用

**关键判断：这里有真正的新技术内容，不是直接套用。** 但 GAP-DEPENDENT 结构本身是已知的。

### 7. Confidence Sequences / Adaptive Data Analysis

**已知工作：**
- Howard et al. (Ann. Statist. 2021) — time-uniform, nonasymptotic confidence sequences
- Waudby-Smith & Ramdas (JRSS-B 2024) — confidence sequences for means
- Ville's inequality, nonnegative supermartingale methods

**覆盖了 CPQ 什么：** 如果 CPQ Route B 使用随机投影，每增加一个投影方向就是一个新观测。Confidence sequences 提供了 anytime-valid bound，即无论何时停止，区间都是有效的。

**能否直接拼出 CPQ：** 可以拿来用，但需要适配：
- 量化误差的处理（投影值被量化，不是精确的随机观测）
- 图搜索中自适应选择哪个 node 精化的依赖结构
- 多个 node 同时精化的 multiplicity 调整

**CPQ 还需要什么：** 适配到量化观测 + 图搜索自适应结构。这部分有技术含量但不是根本性创新。

### 8. RPQ (Routing-aware PQ)

**已知工作：** Lian et al., BREWESS repository, routing-aware codebook training.

**覆盖了 CPQ 什么：** RPQ 训练的 codebook 优化路由决策质量而非重构质量。这与 CPQ Route C (learned progressive CPQ with routing-aware loss) 的训练目标有重叠。

**能否拼出 CPQ：** 不能。RPQ 是固定码率的，不是渐进的。

### 9. TurboQuant

**可能指的是高效接近率失真极限的量化方法。**

**对 CPQ 的影响：** 如果 TurboQuant 能以极少的码率损失实现固定码率量化，那么 CPQ 的"渐进码率损失可控"这一假设更容易满足。但 TurboQuant 本身不包含搜索时的自适应前缀获取。

### 10. Progressive / Anytime Vector Compression

**已知工作：**
- Scalable/embedded image coding (JPEG 2000, progressive JPEG)
- Progressive hashing: Leng et al. (AAAI 2015) — 渐进哈希码
- Matsubara et al. (可能的多尺度 VQ)

**覆盖了 CPQ 什么：** Progressive hashing 提供了可逐步展开的二进制码用于检索。但：
- 没有 distance interval / certificate
- 没有 graph search integration
- 没有 gap-dependent analysis
- 通常用于 hash-based ANN 而非 graph-based ANN

**Progressive hashing 是 CPQ 在检索领域最接近的前身，但缺少 CPQ 的三个核心理论贡献。**

### 11. Multi-stage Learned Retrieval / Early-Exit ANN

**已知工作：**
- Cascade retrieval: coarse candidate generation → re-ranking
- Early-exit neural networks
- Multi-stage retrieval systems (BM25 → dense retriever → cross-encoder)

**覆盖了 CPQ 什么：** 系统层面的 coarse-to-fine 思路。但这些是不同系统组件的级联，不是同一个向量表示的渐进精化。

**能否拼出 CPQ：** 不能。完全不同的抽象层次。

### Novelty Kill Map 总结

| 方向 | 覆盖 CPQ 的部分 | 无法覆盖的部分 | 威胁等级 |
|------|----------------|---------------|---------|
| Successive refinement | 嵌套码的信息论可行性 | 搜索决策驱动、certificate、path coupling | 低 |
| Residual/Additive VQ | CPQ Route A 的码构造 | Adaptive acquisition、certificate | 低 |
| QINCo/QINCo2 | 高质量多级码 | 搜索时自适应、certificate | 低 |
| **RaBitQ** | **距离估计界、随机投影 prefix** | **Adaptive acquisition、graph coupling** | **高** |
| PEOs | 二元粗/精决策 | 多级渐进、gap-dependent analysis | 低 |
| **Adaptive kNN / BAI** | **Gap-dependent 框架** | **Deterministic code、dynamic candidate set** | **高** |
| Confidence sequences | Anytime-valid bounds | 量化观测适配、图搜索依赖 | 中 |
| RPQ | Routing-aware training | 渐进码、adaptive prefix | 低 |
| Progressive hashing | 渐进检索码 | Distance certificate、graph coupling | 中 |

**结论：未找到完整覆盖 CPQ 核心组合的已有工作。** CPQ 的真正 novelty 在于三件事的交叉：
1. 预编码的嵌套表示（offline）
2. 搜索时 per-comparison 的自适应前缀获取（online）
3. 图搜索路径的正确性保证（theory）

这三者的组合在文献中没有出现过。但必须承认，每个组件单独看都不是全新的。

**最大威胁：** RaBitQ flexible-rate 后续 + BAI 理论的直接组合。如果有人把 RaBitQ 的 prefix nesting + BAI 的 gap-dependent stopping rule + standard trace coupling 拼在一起，就能得到 CPQ Route B 的一个版本。**这个组合目前没人做，但可被视为"直接拼接"而非深刻创新。**

---

## B. Theorem Audit

### 定理候选 1：Comparison Soundness

$$U_t(q,a) < L_s(q,b) \Rightarrow d(q,a) < d(q,b)$$

**判断：过于平凡。** 这就是区间不重叠 → 顺序确定。任何距离估计的置信区间都有这个性质。不能作为独立定理出现在论文中——只能作为定义/引理。

**ICML/NeurIPS 审稿人会说：** "This is immediate from the definition of confidence intervals."

### 定理候选 2：Exact-on-Graph Trace Coupling

**判断：正确但浅。** 证明是对搜索步数的标准归纳：如果第 k 步之前 CPQ 和 exact 搜索状态相同，且第 k 步的比较被正确认证，则第 k+1 步状态也相同。

技术上没有困难，但它提供了一个干净的框架——把 CPQ 的正确性归约到"每次比较的正确性"。这让后续分析可以专注于单次比较的码率需求。

**可以作为论文的框架定理，但不能作为核心贡献。** 审稿人会认为这是"straightforward induction"。

### 定理候选 3：Guarantee Inheritance

**判断：直接推论。** 如果 CPQ trace = exact trace w.p. ≥ 1-δ，那么任何关于 exact trace 的保证自动继承。这是零技术含量的观察。

**不应作为独立定理。**

### 定理候选 4：Anytime-Valid Adaptive Confidence

**判断：这是最有技术含量的部分。**

困难在于：图搜索是自适应过程。搜索到的节点集合 $V_k$ 依赖于此前的距离估计。如果距离估计使用随机投影，那么哪些节点的哪些投影被读取，取决于此前估计的随机性。

标准 confidence sequence（Howard et al. 2021）假设观测序列独立于停止时间。在 CPQ 中，"停止读码"和"选择下一个精化目标"都依赖此前观测。

需要的工具：
- **对每个固定节点 v**，其码段 $c_v^{(1)}, c_v^{(2)}, \ldots$ 是预计算的确定性值（deterministic codes）或使用共享随机矩阵的确定性函数（deterministic function of shared randomness）。
- **自适应性来自"选择哪个节点精化"**，而非"观测本身的随机性"。
- 如果使用确定性 residual VQ（Route A），每次展开一层得到确定性信息，没有随机性，不需要 confidence sequence——区间是确定性的。
- 如果使用随机投影（Route B），随机性来自共享投影矩阵，对固定 (q, v) 是确定性的。自适应性只影响"选择读哪些 (v, t) 对"，不影响每个 (v, t) 的估计质量。

**这简化了问题！** 对确定性码（Route A），trace coupling 是确定性的，不需要概率分析。对随机投影码（Route B），关键是 union bound over 所有可能被访问的 (v, t) 对，而不是处理真正的自适应依赖。

**因此，Gpt 文件中暗示的"需要新的 martingale/confidence-sequence 分析"可能被高估了。** 如果投影矩阵是共享的（而非 per-query 随机），则 $d(q,v) \in I_t(q,v)$ 的事件是确定性的（对 Route A）或在共享随机性上条件确定的（对 Route B），自适应性不构成额外困难。

**真正的技术困难在别处：** 不是自适应依赖，而是 union bound 的 tightness。如果搜索访问 L 个节点，每个最多 T 层，union bound 需要 $\delta/(LT)$ 的 per-interval 误差，导致每个区间加宽 $O(\sqrt{\log(LT/\delta)})$。这个对数因子是否能被避免，才是有技术含量的问题。

**修正后的评估：** 如果能找到比 naive union bound 更紧的分析（例如利用图的局部性、或者区间的嵌套性），这可以成为核心贡献。但如果只用 union bound，技术含量有限。

### 定理候选 5：Gap-Dependent Acquisition Upper Bound

$$\text{Total cost} \leq \sum_{e \in \mathcal{E}(q)} \min\left\{M_{\max}, O\left(\frac{C_e^2}{\Delta_e^2} \log \frac{|\mathcal{E}|}{\delta}\right)\right\}$$

**判断：框架正确，但类似 BAI 的直接推论。**

一旦确定了 per-comparison 的 certification cost（由 confidence interval 宽度和 margin 决定），总 cost 就是 per-comparison cost 的求和。这是 standard 的。

**新的部分可能在于：**
- 将 $\mathcal{E}(q)$（关键比较集合）与图结构联系起来
- 在特定图族上，$\sum 1/\Delta_e^2$ 的上界是多少？与图度数、导航效率的关系？
- 与 fixed-rate baseline 的对比：fixed-rate cost = $L \cdot M_{fixed}$，CPQ cost = $\sum \min(M_{max}, f(\Delta_e))$。什么条件下 CPQ 严格更好？

**如果能证明在某类图上 CPQ cost = $O(\text{fixed-rate cost}^{1-\epsilon})$ 或类似的严格分离，这是强结果。否则只是 instance-dependent 的 accounting。**

### 定理候选 6：Per-Decision Lower Bound

$$\Omega\left(\frac{\sigma^2}{\Delta^2} \log \frac{1}{\delta}\right)$$

**判断：直接来自假设检验下界。**

对单次比较，这就是 hypothesis testing 的 minimax lower bound。对 sub-Gaussian observation model，$\Omega(\sigma^2/\Delta^2 \cdot \log(1/\delta))$ 是 Fano inequality 或 change-of-measure 的标准结果。

**查询级下界更难：** 需要证明多个比较不能共享信息——但在 CPQ 中，同一个节点的码段可以同时用于多个比较。这使得下界分析复杂化。如果 node v 的码段同时用于 v 与多个查询候选的比较，则读取 v 的码段可以"分摊"到多个决策上。

**判断：** Per-decision lower bound 是标准的。Query-level lower bound（考虑信息分摊）有技术内容但非常困难，可能不可行。Gpt 在文件中也承认这是推测性的。

### 定理候选 7：Instance Optimality

**判断：最可能不成立或表述过强。**

Instance optimality 要求 CPQ 在每个特定实例上都不差于最优算法超过常数因子。这在 BAI 中需要非常精细的分析（如 Track-and-Stop, Simchowitz's simulator），且通常只对特定算法类成立。

在 CPQ 设定中，instance optimality 需要对比的"最优算法"是"使用相同 progressive code 的任意 adaptive policy"。由于 code 是固定的，optimality 只涉及 reading policy 的选择。这可能是可做的——但只在 per-comparison 级别，不太可能在 query 级别。

**判断：不建议在第一篇论文中追求 instance optimality。留作 future work。**

### Theorem Audit 总结

| 定理 | 深度 | 新颖性 | 核心贡献潜力 |
|------|------|--------|-------------|
| Comparison Soundness | 零 | 零 | 只能作为定义 |
| Trace Coupling | 低 | 低 | 框架定理，不是核心 |
| Guarantee Inheritance | 零 | 零 | 推论 |
| Adaptive Confidence | 中 | 中 | 依赖于是否能超越 union bound |
| Gap-Dependent UB | 中 | 中 | 如果与图结构挂钩可以成为核心 |
| Per-Decision LB | 低 | 低 | 标准假设检验 |
| Instance Optimality | 高 | 高 | 可能不可行 |

**最可能成为 ICML/NeurIPS 级核心贡献的方向：**

Gap-dependent acquisition complexity + 与图搜索结构的耦合。具体地：
- 定义图搜索的"margin complexity"：$\Gamma(q, G) = \sum_{e \in \mathcal{E}_{\text{critical}}(q)} \Delta_e^{-2}$
- 证明 CPQ cost = $O(\Gamma(q,G) \cdot \log(L/\delta))$
- 证明 fixed-rate cost = $O(L \cdot M_{fixed})$
- 在 $\Gamma(q,G) \ll L \cdot M_{fixed} / \log(L/\delta)$（即大部分决策 margin 较大）时，CPQ 严格优于 fixed-rate

**这个 margin complexity 度量本身可能是新贡献——它连接了量化码率理论和图搜索效率。**

---

## C. Counterexample Attack

### Attack 1：高维距离集中 → 所有 margin 极小

**构造：** 考虑 $n$ 个 i.i.d. 均匀分布在 $\mathbb{R}^d$ 单位球面上的点。当 $d \to \infty$，任意两点距离趋近 $\sqrt{2}$。beam 中任意两个候选的距离差 $\Delta_e \to 0$。

**后果：** 每次比较都需要展开到接近最高层。CPQ 退化为 fixed-rate highest-code，没有节省。

**严重性：限制适用条件，但不 KILL。**

理由：
1. 实际数据不是均匀球面上的随机点。嵌入向量有低维流形结构。
2. 图构建本身保证了局部邻居有意义的距离区分（否则图搜索本身就不 work）。
3. 更重要的是，$\Delta_e$ 的分布通常是长尾的——大部分比较的 margin 不小，少部分比较很困难。CPQ 的 gap-dependent 分析恰好利用了这个分布。
4. **但 CPQ 论文必须报告真实数据上 $\Delta_e$ 的经验分布。** 如果 $\Delta_e$ 分布表明大部分决策确实 margin 极小，那么 CPQ 的实践价值存疑。

### Attack 2：确定性残差范数界在高维下过宽

**构造：** Route A 使用 $\rho_v^{(t)} = \|x_v - \hat{x}_v^{(t)}\|_2$。对 $d = 960$，即使 PQ32 的每维重构误差很小（如 $\epsilon_{per-dim} = 0.01$），残差范数 $\rho \approx \epsilon_{per-dim} \cdot \sqrt{d} \approx 0.31$。而 beam boundary margin 可能只有 $0.01$。

**后果：** $\rho_a + \rho_b \gg \Delta_{a,b}$，区间完全重叠，必须展开到最高层。Route A 在高维下可能完全无效。

**严重性：KILL Route A 在高维下的实用性，但 Route B 可能存活。**

Route B 使用方向相关的概率界，而非最坏方向范数界。$d$ 维空间中，query 方向上的投影误差标准差约为 $\rho / \sqrt{d}$，远小于 $\rho$ 本身。Concentration inequality 给出的区间宽度可以是 $O(\rho / \sqrt{m})$（$m$ = 投影数），而非 $O(\rho)$。

**因此 Route A 的确定性界在高维下大概率过宽，Route B 的概率界可能可用。** 论文必须明确说明这个区分。

### Attack 3：Progressive code 的率失真劣于独立 fixed-rate code

**构造：** 嵌套约束限制了码空间。PQ32 独立训练的 codebook 可能比 64B progressive code 的前 32B 更好，因为后者的前 32B 必须兼容 64B 的码结构。

**后果：** CPQ 的短前缀比同码率的独立量化器差，导致短前缀的区间更宽，需要更多层才能认证。

**严重性：只影响常数。**

理由：
1. 对高斯源，嵌套约束的率失真损失为零。
2. 对实际数据，RQ/AQ 的实验显示多级码的逐级重构质量递增，嵌套约束的代价通常可控。
3. 更重要的是，CPQ 的优势来自 adaptive acquisition（容易的决策用短码），而非短前缀本身的质量。即使短前缀比独立码差 20%，只要大部分决策的 margin 足够大，CPQ 仍然节省总码率。

### Attack 4：同时精化大量候选

**构造：** Beam search 中，为了确定哪个候选最近（即 beam 的最小元素），可能需要同时精化 beam 中所有 W 个候选的区间，直到某个候选的 upper bound 低于其他所有候选的 lower bound。

如果 W = 4，且 4 个候选的距离非常接近，则需要精化所有 4 个候选的码，每个到很高的层级。总码率 = 4 × 高层码率 ≈ fixed-rate × 4，没有节省。

**严重性：这是最严重的实践问题。**

但需要区分两种情况：
1. **确定 beam 中的全局最小元素（用于 expansion）：** 确实可能需要精化多个候选。
2. **确定某个新候选是否应进入 beam（eviction 决策）：** 只需比较新候选与 beam 边界，是二元比较。
3. **确定搜索是否终止：** 只需检查 beam 边界是否收敛。

实际图搜索中，大部分比较是 eviction 决策（二元），不是全局最小值查找。因此 batch refinement 问题可能不如想象中严重。

**但论文必须区分不同类型的搜索决策，分析每种的平均精化代价。**

### Attack 5：Cache / Page 粒度吃掉逻辑节省

**构造：** SSD 以 4KB page 读取。如果一个节点的 progressive code 跨越多个 cache line / page，逻辑上只读前 16B 和实际读 64B cache line 的 I/O 成本相同。

**严重性：System-level concern，不影响算法贡献。**

对内存中的搜索（HNSW 等），cache line = 64B，progressive code 的逻辑节省可以部分实现（如果前 16B 在第一个 cache line，后 48B 在其他位置）。

对 SSD 搜索（DiskANN 等），节省更可能来自"减少访问的节点数"而非"每个节点读更少字节"。

**论文应该把 CPQ 的贡献定位在"减少距离计算数"和"降低总信息获取量"，而非"减少 I/O 字节数"。** 后者是系统优化层面的事。

### Attack 6：错误 refinement policy 导致巨大额外成本

**构造：** 考虑一个 adversarial refinement policy：总是先精化最远的候选而非最近的。这导致浪费码率在不影响决策的候选上。

**严重性：只影响 policy 选择，不影响 CPQ 框架。**

CPQ 的框架允许任意 refinement policy。好的 policy（如先精化区间重叠最多的候选对）可以接近最优。坏的 policy 会浪费码率但不会影响正确性。

**论文需要提出具体的 refinement policy 并分析其 competitive ratio。**

### Counterexample Attack 总结

| 攻击 | 严重性 | 性质 |
|------|--------|------|
| 高维距离集中 | 中 | 限制适用条件 |
| 确定性界过宽 | 高 | KILL Route A（高维），Route B 存活 |
| Progressive 码率损失 | 低 | 只影响常数 |
| 批量精化 | 中-高 | 限制实践增益幅度 |
| Cache/Page 粒度 | 中 | 系统层面，不影响算法贡献 |
| 错误 policy | 低 | 可通过 policy 设计解决 |

**没有 KILL-level 的攻击。但 Attack 2 + Attack 4 合在一起构成严重的实践威胁：** 如果确定性界（Route A）过宽且批量精化频繁发生，CPQ 的实际节省可能很小。Route B（概率界）+ 合理的 refinement policy 是生存路径。

---

## D. Minimal Theoretical Model

### 模型定义

**数据与查询：**
- 数据库 $X = \{x_1, \ldots, x_n\} \subset \mathbb{R}^d$
- 查询 $q \in \mathbb{R}^d$
- 距离 $d(q, x) = \|q - x\|_2$

**图与 Reference Search：**
- 近邻图 $G = (V, E)$，$|V| = n$，最大度 $R$
- 确定性贪心搜索 $A_{\text{exact}}$：固定入口、beam size $W$、最大访问 $L$、确定性 tie-breaking
- $A_{\text{exact}}(q, G)$ 返回 top-$K$ 结果和完整搜索路径

**Progressive Observation Model：**
- 每个节点 $v$ 存储 $T$ 层码 $c_v = (c_v^{(1)}, \ldots, c_v^{(T)})$
- 读取前 $t$ 层产生距离估计 $\hat{d}_t(q, v)$ 和区间 $I_t(q, v) = [L_t(q,v), U_t(q,v)]$
- 保证：$\Pr[d(q,v) \in I_t(q,v)] \geq 1 - \delta_v$（对 Route B）或确定性（Route A）
- 嵌套性：$I_{t+1} \subseteq I_t$
- 码率：读取层 $t$ 消耗 $b_t$ bits，总码率 $B_t = \sum_{s=1}^t b_s$

**Distance Certificate：**
- 若 $U_t(q,a) < L_s(q,b)$：认证 $d(q,a) < d(q,b)$

**CPQ Search：**
- 与 $A_{\text{exact}}$ 相同的搜索逻辑，但每次比较时：
  1. 从最粗层开始读取两个候选的码
  2. 如果区间不重叠，认证比较结果
  3. 如果重叠，精化重叠更严重的一方
  4. 最高层 fallback 到最高精度码（或近似完整距离）

**正确性指标：**
- $\Pr[A_{\text{CPQ}}(q, G) = A_{\text{exact}}(q, G)] \geq 1 - \delta$

**Acquisition Cost：**
- $\text{Cost}(q) = \sum_{v \in \text{accessed}(q)} B_{t_v(q)}$（所有访问节点读取的总 bits）

**Upper Bound（非平凡目标）：**

定义 margin complexity：
$$\Gamma(q, G) = \sum_{e \in \mathcal{E}_{\text{critical}}(q)} \Delta_e^{-2}$$

其中 $\mathcal{E}_{\text{critical}}(q)$ 是 $A_{\text{exact}}$ 中真正改变搜索状态的关键比较集合，$\Delta_e$ 是该比较的真实距离 margin。

**定理（上界）：** 存在 refinement policy $\pi$ 使得：

$$\text{Cost}(q) \leq \sum_{e \in \mathcal{E}_{\text{critical}}(q)} \min\left(B_T, \, O\left(\frac{C^2}{\Delta_e^2} \log \frac{|\mathcal{E}_{\text{critical}}(q)|}{\delta}\right)\right) \cdot b_{\text{per-layer}}$$

其中 $C$ 是码的 per-layer uncertainty 衰减常数。

**Plausible Lower Bound（更弱的形式）：**

对任何使用相同 progressive code $c$ 的 adaptive reading policy $\pi$，若要保证正确性 $\geq 1-\delta$，则：

$$\text{Cost}(q) \geq \sum_{e \in \mathcal{E}_{\text{critical}}(q)} \Omega\left(\frac{\sigma_e^2}{\Delta_e^2} \log \frac{1}{\delta}\right) \cdot b_{\text{per-layer}}$$

其中 $\sigma_e^2$ 是码在查询方向上的 per-layer information gain。

**注意：** 这个 lower bound 只对"使用相同 code 的任意 policy"成立，不是对"任意 code + 任意 policy"的绝对下界。后者需要额外的信息论分析。

---

## E. 三条构造路线评估

### Route A：Deterministic Residual CPQ

- **理论干净度：** 最高。确定性区间，不需要概率分析。
- **Confidence 紧度：** 最差。残差范数界是各方向最坏情况，在高维下过宽。
- **新 theorem 潜力：** 低。三角不等式 + 归纳 = 标准工具。
- **实际码率节省：** 存疑。高维下大部分比较需要展开到最高层。
- **Venue 适配：** 理论太浅不适合 ICML/NeurIPS；可作为论文中的"warm-up example"。

### Route B：Probabilistic Nested Sketch CPQ

- **理论干净度：** 中等。需要处理量化误差和 multiplicity。
- **Confidence 紧度：** 好。方向相关的 concentration（$O(\sigma/\sqrt{m})$）远紧于范数界。
- **新 theorem 潜力：** 中-高。量化 sketch + confidence sequence + graph coupling 有技术含量。
- **实际码率节省：** 可能显著（对 margin 分布长尾的实例）。
- **Venue 适配：** 最适合 ICML/NeurIPS。理论完整，实验可做（随机投影编码不需要 GPU 训练）。
- **关键风险：** 随机投影码的 rate-distortion 效率低于 PQ。同等码率下，Route B 的区间可能比 RaBitQ 宽。

### Route C：Learned Progressive CPQ

- **理论干净度：** 最低。需要经验校准，理论保证弱。
- **Confidence 紧度：** 可能最好（通过 routing-aware training），但需要 calibration。
- **新 theorem 潜力：** 低（learned 方法的理论通常只是 generalization bound）。
- **实际码率节省：** 可能最大（code 优化了搜索目标）。
- **Venue 适配：** ICLR（learned + 实验驱动）。
- **关键风险：** 需要 GPU 训练，离线成本高，与 QINCo 的差异化不够。

### 路线建议

**论文主线应该是 Route B（概率嵌套 sketch）。**

理由：
1. 理论最干净、最可证明
2. 不需要 GPU 训练（与 PZ 的硬件条件匹配）
3. 与 RaBitQ 有清晰的差异化（RaBitQ = fixed-rate with bounds; CPQ = progressive with adaptive acquisition）
4. Gap-dependent complexity 在 Route B 下最自然

Route A 可作为论文中的 warm-up / deterministic special case。Route C 作为 future work / extension。

### Venue Assessment

- **ICML / NeurIPS：** 需要 Route B 的完整理论（gap-dependent bound + 非平凡 confidence analysis + plausible lower bound）+ 实验验证（margin 分布统计 + 模拟 CPQ 搜索 + 与 fixed-rate baseline 比较）。最适合定位为"algorithmic theory paper with experiments"。竞争激烈但方向新颖。
- **ICLR：** 如果加入 Route C 的 learned 版本，实验更强，理论可以弱一些。但与 QINCo/neural compression 的竞争更直接。
- **AAAI：** 理论和实验要求都低一些。Route A + Route B 的组合 + 适度实验可以够。
- **最佳策略：** 先投 ICML/NeurIPS（Route B theory + experiments），如果被拒再补 Route C 投 ICLR。

---

## F. 最终裁决

### `PASS-CPQ-THEORY-CANDIDATE`

**附重大条件：**

### PASS 证据

1. **Novelty Kill Map 通过：** 未找到完整覆盖 CPQ 核心组合的已有工作。RaBitQ + BAI 的组合最接近，但该组合目前不存在。
2. **框架有价值：** "margin complexity"作为连接量化码率和图搜索效率的新度量，本身有理论趣味。
3. **Gap-dependent analysis 有真正的技术内容：** 虽然单次比较的 bound 类似 BAI，但与图结构的耦合（动态候选集、多决策共享码段）需要新分析。
4. **Route B 在 PZ 的硬件条件下可实现：** 随机投影编码不需要 GPU。
5. **Counterexample 都不构成 KILL：** 高维距离集中、确定性界过宽、批量精化都是"限制条件"而非"根本不可能"。

### 重大条件

1. **必须首先做 CPQ-MARGIN-BOUND-ORACLE-A0。** 在真实数据的 exact-distance graph search 上统计 $\Delta_e$ 分布。如果 p50 margin 已经很小（如 $\Delta_{p50} < 0.001$），则 CPQ 的实际节省有限，应降级为 HOLD。

2. **Route A（确定性 residual）在高维下大概率实践价值有限。** 论文必须以 Route B（概率 sketch）为主线。Route A 只作为理论 warm-up。

3. **不要追求 instance optimality。** 太难，且不影响论文的核心贡献。Per-decision gap-dependent bound 够了。

4. **核心定理不能只是三角不等式 + 归纳。** 必须在 confidence analysis 或 graph-structure-aware cost bound 上有非平凡结果。如果最终发现只能用 naive union bound，技术贡献不够 ICML/NeurIPS。

5. **最大竞争风险是 RaBitQ 团队的后续工作。** 如果 RaBitQ 发表 progressive/adaptive 版本，CPQ 的 novelty 空间被压缩。应尽快确认可行性并推进。

6. **不能把 CPQ 和当前的 Selective-OPQ 方向混在一起。** CPQ 是独立的算法理论方向，Selective-OPQ 是工程/系统方向。两者可以互补但不应合并。

### 下一步最小验证

```
CPQ-MARGIN-BOUND-ORACLE-A0
```

不实现 CPQ。只做：
1. 在 GIST1M-960D 的 exact-distance graph search 上 instrument 所有 beam-boundary comparison events
2. 记录每次比较的 $\Delta_e = |d(q,a) - d(q,b)|$
3. 统计 $\Delta_e$ 的分布（p10/p25/p50/p75/p90/p95/p99）
4. 对假设的 uncertainty shrinkage curve（$\epsilon_t = C/\sqrt{t}$），计算每个 $\Delta_e$ 需要多少层才能认证
5. 报告 16B/32B/64B/128B 的可认证比例
6. 估算 CPQ 的理论码率节省 vs fixed-rate baseline

**只有大量关键决策（≥ 30%）能在短前缀（≤ 32B）完成认证，才值得继续实现 Route B quantizer。** 否则降级 HOLD。

---

## 附注：Gpt 理论设计中的错误与不妥之处

1. **Section 3 的 L2 距离区间公式有细微问题。** Gpt 写的是 $|d(q,x_v) - d(q, \hat{x}_v^{(t)})| \leq \rho_v^{(t)}$，这对 $\ell_2$ 范数（不是平方 $\ell_2$）成立。但实际搜索中 DiskANN 等系统通常比较平方距离 $\|q-x\|_2^2$。平方距离的区间需要额外处理：$\|q-x\|_2^2 \in [\max(0, \hat{d} - \rho)^2, (\hat{d} + \rho)^2]$，区间宽度变为 $O(\hat{d} \cdot \rho)$ 而非 $O(\rho)$。这使得远距离候选的区间更宽，可能需要更多层才能淘汰。**需要在理论模型中统一使用 $\ell_2$ 还是 $\ell_2^2$。**

2. **Section 7 的 acquisition cost 求和隐含了关键比较互不共享码段的假设。** 实际上同一个节点可能参与多次比较（不同 beam step 中被重复访问）。码段读取一次即可用于所有后续比较。因此总 cost 应该是 $\sum_v B_{t_v}$（每个节点的读取码率），而非 $\sum_e \text{cost}(e)$（每次比较的码率）。Gpt 的公式可能高估了 cost。**这实际上对 CPQ 有利——信息分摊使 CPQ 的实际 cost 低于 per-comparison cost 的简单求和。**

3. **Section 6.2 的 anytime-valid confidence sequence 可能不需要，如果使用确定性码或共享随机矩阵。** 如上 Theorem Audit 所述，自适应性来自"选择哪个节点精化"，而非观测本身的随机性。对确定性码完全不需要 CS；对共享随机投影码，每个 (q, v, t) 的估计值是确定性的，只需要对"投影矩阵的选择"的 one-shot randomness 做 union bound。**Gpt 可能高估了这部分的理论难度。**

4. **Section 11 对 RaBitQ 的描述不够具体。** 应该明确 RaBitQ 的 random-bit 机制是否天然支持 prefix nesting。我的判断是：RaBitQ 的随机投影 + 一位量化结构确实支持前缀（前 m 位 → 前 m 个投影），但需要验证 RaBitQ 的 distance estimator 在 prefix 模式下是否仍然无偏且有有效 concentration。这是 CPQ vs RaBitQ 差异化的关键点。