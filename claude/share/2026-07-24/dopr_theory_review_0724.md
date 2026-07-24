# Decision-Optimal Progressive Representations (DOPR) 理论评审

**Date:** 2026-07-24
**Author:** Claude
**Ruling:** `PASS-DECISION-REGION-FORMULATION-FOR-THEORY-AUDIT`（同意 Gpt 裁决，附修正与补充）

---

## 0. 前情回顾

Selective-OPQ Stage A 完成，结果为负面：
- 最强点（L=50, budget=56, distance-regret）Recall 提升 0.0127，reads 仅降 0.631%
- Distance-regret 与 visit-frequency 选集 Jaccard = 0.828（本质相同）
- 75% 节点需要 OPQ64 → 静态 node-level 精度分配空间极小

Gpt 据此：
1. KILL 了 Static Selective-OPQ 作为主线
2. 发现了与原始 CPQ 高度重合的已有工作（SAQ + RaBitQ）
3. 提出新的 DOPR 框架

**我同意这三个判断的方向。** 下面逐项评估 DOPR 的理论设计。

---

## 1. Selective-OPQ 负面结果的解读

Gpt 从负面结果中提炼出一个关键观察：

> 节点是否需要高精度，主要不是节点永久固有属性；更可能取决于当前查询、当前 beam 状态和当前决策歧义。

**这个推理逻辑正确。** Distance-regret ≈ visit-frequency（Jaccard 0.828）说明"哪些节点从高精度中获益"和"哪些节点被频繁访问"几乎等价。这意味着高精度的价值来自"被访问"本身，而非该节点的量化敏感性独立于访问频率。

进一步：最佳配置需要 75% 节点使用 OPQ64，说明在 fixed graph + uniform workload 下，大部分节点的量化误差对路由决策都有非零影响——节点间的"量化敏感性"差异不够大，无法支持有效的静态二分（low/high precision）。

**但需要注意：** 这个结论限定于 GIST1M-960D + frozen graph + uniform 1K query workload。在高度倾斜的查询分布下（如热点 query cluster），静态分配可能仍有效。Gpt 在 KILL 标签中正确限定了范围。

---

## 2. SAQ / E-RaBitQ 对原始 CPQ 的覆盖

Gpt 提出的关键判断是：

> SAQ 已覆盖渐进前缀、multi-stage distance estimation、距离界和按需减少访问位数

**这需要验证。** 在我之前的 CPQ 评审中，我评估 RaBitQ 为"最危险的先行工作"但指出它没有实现 progressive/adaptive acquisition。如果 SAQ 确实覆盖了这些，那原始 CPQ 的 novelty 确实被我高估了。

**我对 SAQ 覆盖范围的理解：**

如果 SAQ（Scalar Additive Quantization）或类似工作已实现以下组合：
- 嵌套前缀码（progressive prefix）
- 每个前缀级的距离估计（multi-stage estimation）
- 有效误差界（distance bounds）
- 搜索时按需读取（adaptive acquisition）

那么原始 CPQ 的编码侧（Route A/B 的码构造 + distance interval）确实被覆盖。CPQ 剩余的 novelty 只有：
- Graph-path coupling 理论（但我评审中已指出这是 straightforward induction）
- Gap-dependent acquisition complexity（但这来自 BAI 理论）

**因此 Gpt 将方向从 CPQ 转向 DOPR 是正确的判断。** 不是 CPQ 完全没有新内容，而是 CPQ 的核心技术贡献不够厚——编码被覆盖，理论太浅，只能做"算法框架"级工作，不足以独立成文。

---

## 3. DOPR 框架评估

### 3.1 决策区域抽象（Section 2）

**Trace equivalence** 和 **Result equivalence** 的定义是干净的。

$h \sim_{\text{trace}} h'$ 当且仅当相同的搜索轨迹——同一序列的 expansion、eviction、termination 决策。

$h \sim_{\text{result}} h'$ 当且仅当相同的最终 top-K 输出。

**这是正确的抽象层次。** 把图搜索从"逐步比较距离"提升到"识别决策区域"，自然引入了信息论问题：完成识别所需的最少信息量。

**一个重要的细微处：** 搜索算法 $A_{\text{exact}}$ 是确定性的，因此 $T(h) = A_{\text{exact}}(h, G)$ 是 $h$ 的确定性函数。决策区域是 $h$ 空间中的一个（可能复杂的）划分。但 $h$ 是连续空间 $\mathbb{R}^{|V|}$，决策区域的边界是由搜索中的比较条件（$d(q,a) < d(q,b)$）定义的超平面排列（hyperplane arrangement）。

**这意味着决策区域数量是 $O(n^{2L})$ 级别**（$n$ = 节点数，$L$ = 访问次数），因为搜索中最多 $O(L^2)$ 次比较，每次比较定义一个超平面。实际区域数远少于此上界（大部分排列组合不可达），但仍然可以很大。

**这对理论和实践都有影响：**
- 理论上：不能枚举所有区域，必须用结构化方法
- 实践上：需要用采样查询近似决策区域分布

### 3.2 Certificate Complexity（Section 5）

$$C^*(h) = \min_{S \in \mathcal{C}(h)} \sum_{e \in S} c_e$$

**定义是清晰和正确的。** 它自然处理了我在 CPQ 评审中提到的"同一节点码段被多次比较复用"问题（cost 按 unique node-layer 计费），比原始 CPQ 的 per-comparison cost 求和更准确。

**与已有工作的关系：**

这本质上是 **Minimum Verification Subset** 问题——给定一个假设（真实距离状态 $h$），找到最小代价的测试子集，使得所有通过这些测试的其他假设都属于同一决策区域。

在诊断/测试文献中：
- Kosaraju et al. (1999) "Optimal decision trees for diagnosis"
- Chakaravarthy et al. (2007) "Decision trees for entity identification"
- Bellala et al. (COLT 2012) "Active diagnosis / group-based query selection"

**但关键差异在于：**
1. 标准问题的测试结果是离散的（binary 或 finite）；这里每个码段产生一个连续值的量化结果
2. 标准问题的测试集固定；这里有前缀约束和动态可用性
3. 距离状态 $h$ 是连续的，决策区域由比较超平面定义

**这些差异是否足够产生新结果？部分是。** 前缀约束确实引入了新的组合结构。但连续状态 + 量化测试这一点可能反而简化了问题（因为每个码段给出的信息是确定性的，而非概率性的）。

### 3.3 Adaptive Submodular Cover（Section 6.2）

Gpt 提出的核心技术路线：
1. 定义 utility $F(S, \phi)$ = 已切断的跨区域 hypothesis pairs/hyperedges
2. 证明 adaptive monotonicity + adaptive submodularity
3. 利用 Golovin & Krause (COLT 2011) 的 greedy policy 得到 $O(\log Q)$ 近似

**判断：框架方向正确，但需要仔细处理。**

**Adaptive submodularity 是否成立？**

对标准 DRD（确定性测试，固定测试集）：是的。每个测试 $e$ 被执行后，观测结果 $\phi(e)$ 确定。定义 $F(S, \phi)$ 为"所有 hypothesis pairs $(h, h')$ 中，$h$ 与 $h'$ 在至少一个 $e \in S$ 上产生不同观测结果的 pairs 数量（或权重）"。这个函数满足：
- Adaptive monotonicity：更多测试只能消除更多 hypothesis pairs
- Adaptive submodularity：新增一个测试能消除的 pairs 数不会因已有更多测试而增加

**对带前缀约束的情况：** Adaptive submodularity 本身仍然成立（它是关于函数 $F$ 的性质，不受测试选择约束影响）。但前缀约束限制了可选择的测试——不是所有测试都是 feasible action。

问题变为：**precedence-constrained adaptive submodular cover 的 greedy 近似保证如何？**

已知结果（我所知的）：
- Golovin & Krause (2011)：无约束 adaptive submodular cover 的 greedy 给出 $O(\ln(Q/\delta))$ 近似
- 对 precedence constraints 的 submodular maximization（非 adaptive、非 cover），Adamczyk et al. (ICALP 2014) 给出了 $(1-1/e)$ 近似
- **Precedence-constrained adaptive submodular cover** 的近似保证——据我所知没有现成结果

**这可能是新定理的空间。** 如果能证明 precedence-constrained greedy 仍然给 $O(\log Q)$ 近似（可能 with additional factors），这本身就是有价值的算法贡献。

### 3.4 前缀约束 + 动态测试（Section 6.3）

Gpt 列出四个可能的结果方向：
1. 前缀链展开后 greedy 仍有 $O(\log Q)$
2. 新的 precedence-constrained adaptive cover 近似算法
3. 证明 simple greedy 在前缀约束下失败，设计 chain-aware greedy
4. 动态可用测试的 competitive ratio

**我的评估：**

(1) **最可能成立。** 直觉上，前缀约束只增加了成本（你必须先读层 1 才能读层 2），不改变函数的 submodularity。Greedy 在选择时会自然优先选择"浅层+高价值"的测试。近似比可能退化（从 $O(\log Q)$ 到 $O(T \cdot \log Q)$，其中 $T$ = 最大层数），但不会完全失败。

(2) **如果 (1) 不直接成立，这是 fallback。** 可能需要 chain-aware cost 调整。

(3) **不太可能。** Simple greedy 通常不会完全失败，只是近似比退化。

(4) **最难但最有趣。** 动态可用测试意味着算法不知道未来会发现哪些节点。这类似于 online submodular optimization。如果能给出 competitive ratio，这是强结果。但可能太难。

**建议聚焦 (1) 和 (2)，(4) 作为 open problem。**

### 3.5 Result vs Trace 分离（Section 6.4）

$$C^*_{\text{result}}(h) \leq C^*_{\text{trace}}(h) \leq C_{\text{fixed-rate}}(h)$$

**第一个不等式显然成立。** Trace certification 需要确定每一步的正确决策，result certification 只需要确定最终输出。Trace certificate ⊆ result certificate（任何 trace certificate 也是 result certificate），但反之不然。

**第二个不等式也显然成立。** Fixed-rate = 每个访问节点读取完整码。Certificate 只需要读取足够的信息来确认决策，不需要完整码。

**严格分离的构造：**

$C^*_{\text{trace}} \ll C_{\text{fixed-rate}}$：
- 构造一个图，其中大部分比较的 margin 很大。例如：1M 向量按距离从近到远排列，beam search 中的 90% 比较都是"新候选远比 beam 中最远候选还远"。这些比较只需要 1 层码。但 fixed-rate 必须为每个访问节点支付完整码。
- 分离比：$O(1/T)$（每个节点平均只读 1 层 vs 完整 $T$ 层）

$C^*_{\text{result}} \ll C^*_{\text{trace}}$：
- 更微妙。构造一个图，其中最终 top-K 被几个关键比较决定（在 beam 的最后几步），但 trace 中有很多中间 expansion 步骤，每步都需要不同的 margin certification。
- 例如：一个图的搜索路径是"快速沿一条链到达目标区域→在目标区域精细比较"。Result 只取决于目标区域内的比较；trace 还需要 certify 链上每一步的 expansion。
- 但这个分离可能只有常数倍，不是渐近分离。

**难点：** Result equivalence 是 trace equivalence 的粗化。但搜索路径的 early steps 也会影响哪些节点被发现，进而影响 result。所以 result certification 不能完全忽略早期步骤。真正的渐近分离可能需要精心构造的图族。

**我的评估：$C^*_{\text{trace}} \ll C_{\text{fixed-rate}}$ 的分离是容易构造的，有价值但不惊人。$C^*_{\text{result}} \ll C^*_{\text{trace}}$ 的严格分离可能困难，应作为 bonus 而非主要目标。**

---

## 4. Theory Gate T1 逐项回答

### T1.1：图搜索 transcript/result identification 是否能严格归约为 DRD？

**是的，但需要注意连续状态空间。**

标准 DRD 处理离散假设集合 $\mathcal{H}$，测试结果有限离散。图搜索的距离状态是连续的，但决策区域由超平面排列定义，测试结果（量化码段）产生离散分区。

严格归约：对每个查询 $q$，真实距离向量 $h(q) \in \mathbb{R}^{|V|}$ 是隐变量。搜索算法 $A_{\text{exact}}$ 定义一个从 $h$ 到 transcript/result 的映射。决策区域是 $h$ 空间中由比较条件定义的多面体。码段读取相当于观测 $h$ 的量化投影。

**唯一的技术问题：** 标准 DRD 假设有限假设集。这里假设空间是连续的。但如果测试结果是离散的（量化码），那么可观测的等价类是有限的，可以将连续 $h$ 空间离散化为"对所有可能的测试结果组合相同的假设集"。这个离散化是标准的。

### T1.2：标准 HEC / adaptive submodular cover 是否已经直接覆盖有前缀链的测试？

**不完全覆盖。** 

标准 Golovin & Krause (2011) 假设每个 test item 可以随时选择，没有 precedence constraint。前缀约束创造了一个"partially ordered action space"——你必须先获取 $(v, 1)$ 才能获取 $(v, 2)$。

这类似于 **precedence-constrained scheduling** 中的 chain 结构。对非自适应 submodular cover，Wolsey (1982) 和后续工作处理了一般 matroid 约束。但 adaptive + precedence constraints 的组合——据我所知——没有现成的直接结果。

**这是新定理的机会。**

### T1.3：前缀约束是否保留 adaptive submodularity？

**Adaptive submodularity 是 utility function $F$ 的性质，不受 action space 约束影响。** $F$ 仍然是 adaptive submodular 和 adaptive monotone（假设对标准 DRD 成立）。

但前缀约束影响的是 **greedy algorithm 的行为和近似保证**，不是函数性质。Greedy 在受限 action space 中选择"当前可行且边际收益/成本比最大"的 action。

关键问题是：在 chain-structured constraints 下，greedy 的近似比是否仍为 $O(\log Q)$？

**我的初步判断：可能成立，但近似比可能退化为 $O(T \cdot \log Q)$。**

理由：最坏情况下，为了获取一个高层码段，你必须先支付前缀成本。这相当于每个"有效测试"的成本被放大了最多 $T$ 倍。Greedy 的 cost/benefit 分析需要考虑这个放大。

但如果码段的信息量随层数递减（前几层信息量大、后几层递减），greedy 会自然优先选择浅层测试，前缀约束的实际代价很小。

### T1.4：动态出现测试是否已有直接适用定理？

**据我所知没有。** 

Online submodular optimization 处理"items arrive over time"（如 Streeter & Golovin, NeurIPS 2009），但那里的 items 按外部时钟到达，不是由算法自身的决策揭示。

图搜索中的动态可用性更接近 **adaptive planning with partial observability**——你的 action 不仅产生信息，还揭示新的可能 action。这是一个更困难的问题。

**建议不将动态可用性作为第一篇论文的核心，而是假设 candidate set 预先给定（如 beam search 访问的前 L 个节点），事后分析 certificate cost。** 动态扩展可作为 future work。

### T1.5：最小 certificate 是否 NP-hard？

**几乎确定是 NP-hard。**

归约路径：将 Minimum Test Cover（MTC）归约到最小 certificate。MTC 是 Set Cover 的变体，已知 NP-hard。

具体构造：给定一个 Set Cover 实例 $(U, \mathcal{S})$，构造一个图搜索实例，其中：
- 每个 set $S_i$ 对应一个节点的码段
- 每个 element $u_j$ 对应一对需要区分的 hypothesis
- 码段 $S_i$ "covers" hypothesis pair $u_j$ 当且仅当 $u_j \in S_i$

最小 certificate = 最小 test cover = Minimum Set Cover。

**这是标准归约，不是深结果。** 但它为近似算法提供了动机。

### T1.6：是否可得 $O(\log Q)$ 或类似保证？

**对无约束版本（无前缀、固定测试集）：是的，直接来自 Golovin & Krause。**

**对有前缀约束的版本：可能性很高，但需要证明。**

一个可能的证明路径：
- 将前缀链中的每个节点 $v$ 视为一个"meta-item"，其 utility 是读取整条链后的总信息增益
- 但这失去了逐层获取的粒度
- 更好的方法：将前缀约束编码为 Golovin & Krause 框架中的 partial realization 条件

**我认为这可以做，但需要技术工作。近似比可能是 $O(\log Q \cdot \alpha)$，其中 $\alpha$ 取决于链结构（如最大链长 $T$）。**

### T1.7：是否存在 fixed-rate 与 adaptive certificate 的渐近分离实例？

**是的，容易构造。**

构造：考虑 $n$ 个节点在 $\mathbb{R}^d$ 中分为 $\sqrt{n}$ 个 well-separated clusters，每个 cluster 内 $\sqrt{n}$ 个节点。查询落在某个 cluster 附近。

- Beam search 首先在 cluster 间选择（大 margin，1 层码够）
- 然后在 cluster 内精细比较（小 margin，需要多层码）
- 总共访问 $L$ 个节点

Fixed-rate cost：$L \cdot B_T$（每个节点完整码）

Certificate cost：$\sqrt{n}$ 个 inter-cluster 比较 × $B_1$（1 层码）+ $\sqrt{n}$ 个 intra-cluster 比较 × $B_T$（完整码）= $\sqrt{n}(B_1 + B_T)$

分离比：$L \cdot B_T / [\sqrt{n}(B_1 + B_T)] \approx L / \sqrt{n} \cdot B_T / (B_1 + B_T)$

当 $L \gg \sqrt{n}$（beam 很大）且 $B_T \gg B_1$（码很长），分离比可以很大。

**更极端的例子：** 考虑一维数据（sorted array），beam search 就是二分查找。每次比较的 margin 约为 $\Theta(1/2^k)$（第 $k$ 步）。前几步 margin 大（1 层码），后几步 margin 小（多层码）。总 certificate cost $\approx \sum_{k=1}^{\log n} O(1/\Delta_k^2) \cdot b_{\text{per-layer}} = O(\log n \cdot B_T)$（因为所有 margin 都很小时，每步需要完整码）。Fixed-rate cost = $\log n \cdot B_T$。这里没有分离！

**所以分离取决于数据和图的结构。** 存在分离的实例（clustered data），也存在不分离的实例（uniform data + binary search-like access）。

**这本身就是有趣的 characterization：** 什么图/数据结构下 adaptive certification 有效？这可以成为理论贡献之一。

---

## 5. 对 DOPR 设计的修正与批评

### 5.1 SAQ 覆盖范围需要严格验证

Gpt 称"SAQ 已覆盖渐进前缀、multi-stage distance estimation、距离界和按需减少访问位数"。**这是 DOPR 成立的关键前提。** 如果 SAQ 实际上不覆盖所有这些（例如没有 adaptive acquisition 或没有 per-prefix distance bounds），那么原始 CPQ 的部分 novelty 仍存在，DOPR 的动机被削弱。

**建议：在正式推进前，Gpt 或 Claude 必须给出 SAQ 的具体论文引用和覆盖证据。**

### 5.2 Hyperedge-cut 目标的可处理性

Section 7.2 的 $V(b) = \mathbb{E}[\text{newly separated cross-region mass}]$ 需要估算"跨决策区域的 hypothesis pairs"。但决策区域数量可以是指数级的。

**实际可行的替代：** 不枚举所有决策区域，而是用采样查询的实际搜索事件（expansion argmin, eviction, termination）作为代理。每个事件是一个二元或多元比较。码段 $b$ 的价值 = 它能正确 resolve 多少采样事件。

这实际上就是 Selective-OPQ 中的 distance-regret / routing-aware score 的推广版本。不同之处在于：
- Selective-OPQ 是静态分配（每个节点固定精度）
- DOPR 是动态获取（每个查询按需读码）

### 5.3 "Version 3" 过于雄心

Joint representation + policy + approximation theory + multi-index experiments 对一篇论文来说太多了。**建议拆分：**

- **Paper 1（算法理论）：** Precedence-constrained decision region determination + hardness + approximation + graph-search instantiation。使用现有量化器（RaBitQ/RQ/OPQ 多级码）作为 progressive code，不训练新表示。
- **Paper 2（表示设计，后续工作）：** Decision-aware progressive representation design + learning + experiments.

### 5.4 动态测试可用性不应是第一篇论文的重点

如 T1.4 所述，动态可用性引入了 partial observability，显著增加了复杂度。第一篇论文应假设 candidate set 固定（如 exact search 的 visited set），分析离线 certificate cost。Online/dynamic 版本作为 future work。

### 5.5 Oracle Gate A0 的设计比 CPQ 的更好

Gpt 的 Oracle Gate A0（Section 9）比我之前建议的 CPQ-MARGIN-BOUND-ORACLE-A0 更好：
- 不是简单统计 $\Delta_e$ 分布并检查"30% 决策在 32B 完成"
- 而是用 ILP/DP 求离线最优 certificate，并比较 greedy policies vs optimum
- 这直接回答了"新算法对象是否真实存在"

**一个修正：** 在小候选子问题上用 ILP 求最优 certificate 是好的，但需要明确：
- 子问题规模多大？如果 beam 中有 $W=4$ 个候选 × $T=4$ 层 × $R=64$ 个邻居，action space 有 $\sim 256$ 个 item，ILP 可以精确求解
- 但 full graph search 的 certificate 涉及 $L \sim 100-800$ 个节点 × $T$ 层，ILP 可能不 tractable。需要分解为 per-step 子问题

---

## 6. 与原始 CPQ 的比较

| 维度 | 原始 CPQ | DOPR |
|------|---------|------|
| 核心对象 | Progressive code + interval comparison | Decision region identification |
| 理论深度 | 浅（三角不等式 + 归纳） | 中-高（NP-hardness, adaptive cover, approximation） |
| 编码贡献 | 嵌套码构造 | 码构造由已有工作覆盖，聚焦 policy + representation design |
| 算法贡献 | Gap-dependent acquisition（类似 BAI） | Precedence-constrained adaptive cover（可能是新结果） |
| 实验需求 | Margin 分布统计 | Offline certificate vs greedy vs fixed-rate 比较 |
| Venue 适配 | ICML/NeurIPS（theory + experiments） | ICML/NeurIPS（stronger algorithmic content） |

**DOPR 是 CPQ 的严格升级。** 它保留了 CPQ 的核心动机（adaptive precision acquisition），但把技术贡献从浅层的"interval + coupling"推到了更深层的"combinatorial optimization + approximation algorithm"。

---

## 7. 最终裁决

### `PASS-DECISION-REGION-FORMULATION-FOR-THEORY-AUDIT`

**同意 Gpt 裁决。** DOPR 的 decision-region formulation 是一个比原始 CPQ 更好的理论框架。

### 附加条件

1. **SAQ 覆盖范围必须在推进前验证。** 需要具体论文引用和覆盖证据。如果 SAQ 实际上不覆盖 progressive adaptive acquisition，则原始 CPQ 的部分 novelty 需重新评估。

2. **第一篇论文应聚焦 Version 2（policy + constrained theory）：**
   - Precedence-constrained adaptive DRD 的 hardness
   - Greedy approximation under chain constraints
   - Graph-search instantiation with existing progressive codes
   - 不需要训练新表示，不需要处理动态测试可用性

3. **最可能的核心定理：** Precedence-constrained adaptive submodular cover 的 $O(f(T) \cdot \log Q)$ 近似保证。如果能证明这一点，加上 graph-search 的 instantiation 和实验验证，足够投 ICML/NeurIPS。

4. **Selective-OPQ 负面结果的定位：** 作为 motivation/ablation 在论文 intro 或 related work 中简要提及。不应成为主要实验贡献。

5. **Oracle Gate A0 设计合理，但需修正子问题规模。** ILP 应限制在 per-step 子问题（$\sim 4-64$ 个候选，$\sim 4$ 层），不要尝试 full search certificate。

### 最大风险

1. **Precedence-constrained adaptive cover 可能已有现成结果。** 需要 thorough 文献搜索。如果已有 $O(\log Q)$ 近似保证，核心定理的 novelty 消失。
2. **实验中 greedy vs fixed-rate 的差距可能很小。** 如果在真实数据上，大部分 search decisions 的 margin 都很小（需要高层码），adaptive certification 的实际节省有限。Oracle Gate A0 的目的就是检测这个。
3. **"决策区域数量指数级"的问题。** 理论分析中 $Q$ 出现在对数中，但如果 $Q$ 是指数级的，$\log Q$ 可能是多项式的。这不影响近似算法的 polynomial-time 性质，但影响近似比的绝对值。

### 下一步

等 Selective-OPQ Stage A 的完整结果确认后（应该已完成，从对话看结果是负面的），可以推进 Theory Gate T1 的形式化工作。但当前不启动 Codex 实验，不影响正在运行的任何任务。
