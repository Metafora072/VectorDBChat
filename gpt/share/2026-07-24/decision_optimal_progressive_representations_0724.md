# Decision-Optimal Progressive Representations for Graph Search
## 深化讨论稿：静态 Selective-OPQ 复盘与算法 A 会路线

## 0. 当前裁决

### Selective-OPQ

```text
STAGE-A-COMPLETE
KILL-STATIC-SELECTIVE-OPQ-AS-MAINLINE
ARCHIVE-WEAK-SELECTIVITY-SIGNAL
NO-STAGE-A.5
NO-STAGE-B
```

原因：

- 最强稳定点为 `L=50, budget=56, distance-regret`；
- Recall 提升 0.0127，但 reads 仅下降 0.631%，comparisons 仅下降 0.539%；
- 该配置给 75% 节点使用 OPQ64；
- visit-frequency 在同一点得到几乎相同结果；
- 两者选择集合 Jaccard 达 0.828；
- routing-aware selector 的唯一严格点在 work 指标 bootstrap CI 上跨 0；
- 60 个 mixed 点中仅 5 个满足严格数值门禁，只有 2 个三项 bootstrap 稳定；
- actual-memory 下仍需面对 OPQ61，当前低于 1% 的工作量改善很可能消失。

因此，继续做 held-out Stage A.5 即便成功，也只能证明一个很弱的热点相关现象，无法解决贡献强度和实际收益问题。

该负面结果反而支持一个更一般的观察：

> 节点是否需要高精度，主要不是节点永久固有属性；更可能取决于当前查询、当前 beam 状态和当前决策歧义。

---

## 1. 原 CPQ 为什么不够

原始 CPQ 由以下部分组成：

```text
progressive code
+ distance interval
+ adaptive refinement
+ path certification
```

SAQ 已覆盖渐进前缀、multi-stage distance estimation、距离界和按需减少访问位数；E-RaBitQ/RaBitQ 提供有理论误差界的距离估计。因此，仅将已有 progressive quantizer 接入图搜索，再用区间分离规则决定是否继续精化，难以形成独立的算法 A 会贡献。

真正需要研究的对象应从“渐进量化器”转向：

> 在受限的渐进观测模型下，如何以接近最小的信息获取成本，识别图搜索真正需要的决策结果；并反过来设计最适合这些决策的渐进表示。

---

## 2. 新抽象：图搜索是一个决策区域识别问题

固定：

- 数据库向量集合 \(X\)；
- 图 \(G\)；
- 查询 \(q\)；
- 确定性 exact-distance graph search \(A_{\rm exact}\)；
- 固定 entry、beam、termination 和 tie-breaking。

完整精确距离状态记为：

\[
h(q)=\{d(q,x_v):v\in V\}.
\]

在算法执行前，这些距离对搜索器而言是“昂贵但确定的隐变量”。

每一个可能的距离状态 \(h\) 都对应一个 exact search transcript：

\[
T(h)=A_{\rm exact}(h,G).
\]

可定义两种等价类。

### 2.1 Trace equivalence

\[
h \sim_{\rm trace} h'
\iff
T(h)=T(h').
\]

两种距离状态产生完全相同的节点扩展、beam 更新和终止过程。

### 2.2 Result equivalence

\[
h \sim_{\rm result} h'
\iff
\operatorname{Output}(T(h))
=
\operatorname{Output}(T(h')).
\]

结果等价比路径等价更宽松，可能显著降低信息需求。

CPQ 的真正目标不需要恢复所有距离，也不需要重构所有向量，只需把当前隐状态缩小到一个决策等价类。

---

## 3. Progressive code block 作为 test

每个节点 \(v\) 具有嵌套码段：

\[
z_v^{(1)},z_v^{(2)},\ldots,z_v^{(T)}.
\]

动作：

\[
e=(v,t)
\]

表示获取节点 \(v\) 的下一段码或第 \(t\) 级 refinement，成本为 \(c_{v,t}\)。

动作结果可以是：

- 一个量化投影块；
- 一个 residual block；
- 一个更紧的距离区间；
- 一个离散量化结果；
- 一个可用于多个候选比较的共享信息。

存在前缀约束：

\[
(v,t+1)\text{ 可执行}
\Rightarrow
(v,t)\text{ 已执行}.
\]

获取同一节点的码段后，可以被所有后续比较复用，因此成本按唯一节点—层动作计费，不按比较次数计费。

---

## 4. 新问题：Precedence-Constrained Decision Region Determination

给定：

- 隐状态先验 \(P(h)\)；
- 决策区域集合 \(\mathcal R\)；
- 有成本的测试集合 \(\mathcal E\)；
- 每个节点内部的前缀/precedence 约束；
- 搜索过程中动态出现的可测试节点；

设计 adaptive policy \(\pi\)，最小化：

\[
\mathbb E_h[
\operatorname{Cost}_{\pi}(h)
]
\]

直到所有仍与观测一致的状态属于同一决策区域。

这里的决策区域是：

- exact search trace；
- exact-on-graph top-k；
- 或允许 \(\delta\) 错误的近似结果类。

该问题与经典 Decision Region Determination / Equivalence Class Determination 相似，但有四个新限制：

1. 测试由渐进向量码产生，不能任意设计；
2. 测试具有节点内前缀依赖；
3. 新候选节点由图搜索动态揭示，测试集合随执行变化；
4. 编码器和获取策略需要联合设计。

如果仅把标准 HEC 算法直接套到固定候选集，不足以成为贡献。需要处理上述至少两个结构性差异。

---

## 5. Certificate Complexity

对固定查询和隐状态 \(h\)，定义一个 action set \(S\subseteq\mathcal E\) 为有效 certificate，当且仅当：

> 所有与 \(S\) 的观测结果一致的隐状态，都属于与真实状态 \(h\) 相同的决策区域。

定义最小离线 certificate：

\[
C^*(h)
=
\min_{S\in\mathcal C(h)}
\sum_{e\in S}c_e.
\]

它自然处理：

- 一个节点码段用于多次比较；
- expansion 是集合 argmin 决策；
- beam insertion/eviction 是边界决策；
- termination 是 frontier 与结果边界的集合决策；
- trace-equivalence 与 result-equivalence 的不同成本。

在线策略无法预先知道 \(h\)，目标是接近：

\[
\mathbb E_h[C^*(h)]
\]

或最优 adaptive policy：

\[
\operatorname{OPT}
=
\min_{\pi}
\mathbb E_h[\operatorname{Cost}_{\pi}(h)].
\]

---

## 6. 最可能的理论主线

### 6.1 Hardness

首先证明：

- 即使图和候选集合固定；
- 即使每个节点只有两层；
- 即使只需识别一次 beam argmin 或 top-k；

求最小 certificate / 最优 policy 仍为 NP-hard，可能从 Set Cover、Optimal Decision Tree 或 Decision Region Determination 归约。

Hardness 本身不足，但能说明问题不是一个直接的区间规则。

### 6.2 Adaptive cover formulation

构造 utility：

\[
F(S,\phi)
\]

表示当前观测已经排除或切断的跨决策区域 hypothesis pairs / hyperedges 的总权重。

当：

\[
F(S,\phi)=Q
\]

时，剩余状态均落入同一决策区域，搜索结果已被认证。

若可证明：

- adaptive monotonicity；
- adaptive submodularity；

则 minimum-cost adaptive submodular cover 的 greedy policy 可获得对数近似。

若严格 adaptive submodularity 不成立，可研究 adaptive submodularity ratio \(\gamma\)，得到依赖 \(\gamma\) 的近似保证。

### 6.3 前缀约束与动态 test availability

标准 adaptive cover 通常允许任意选择 item。我们的测试只能按节点前缀顺序获取，并且节点在图遍历中动态出现。

需要证明以下之一：

1. 将前缀链展开成合法 item system 后，greedy 仍有 \(O(\log Q)\) 近似；
2. 给出 precedence-constrained adaptive cover 的新近似算法；
3. 证明简单 greedy 在该结构下失败，并设计 chain-aware greedy；
4. 对动态可用测试给出 competitive ratio。

这一部分比单纯路径 coupling 更可能成为核心 theorem。

### 6.4 Result certification vs trace certification

证明：

\[
C^*_{\rm result}(h)
\le
C^*_{\rm trace}(h)
\le
C_{\rm fixed-rate}(h).
\]

进一步寻找严格分离实例：

\[
C^*_{\rm result}
\ll
C^*_{\rm trace}
\ll
C_{\rm fixed-rate}.
\]

如果能够构造图族，使 fixed-rate 必须对所有访问节点支付完整码，而 result certificate 只需读取少数关键节点的短前缀，可得到渐近分离。

---

## 7. 决策感知渐进表示

只研究 acquisition policy 仍可能被认为是已有 active decision theory 的应用。因此表示也需要参与设计。

### 7.1 训练数据

从训练查询执行 exact graph search，收集三类决策事件：

1. expansion argmin；
2. beam insertion/eviction；
3. termination boundary。

每个事件对应一组候选以及 exact outcome。

### 7.2 Hyperedge-cut objective

不同 exact outcomes 对应不同决策区域。一个码段的价值不是减少 MSE，而是切断多少跨区域 hypothesis pairs/hyperedges。

对码段 \(b\) 定义训练价值：

\[
V(b)
=
\mathbb E[
\text{newly separated cross-region mass}
].
\]

渐进表示应让早期码段具有最大的单位 bit 决策分离能力：

\[
\max_{\theta,\text{ordering}}
\sum_t
\alpha_t
\frac{
V_\theta(z^{(t)}\mid z^{(<t)})
}{
c_t
}.
\]

### 7.3 可实现的非神经版本

不必一开始训练神经码本。可以：

- 随机旋转或 PCA 得到投影坐标；
- 将坐标分成 blocks；
- 依据 graph-decision hyperedge cut gain 排序 blocks；
- 每个 block 使用低比特 scalar/SAQ-like quantization；
- 使用 held-out calibration 构造有效区间。

这与 SAQ 的区别：

- SAQ 依据幅值/量化误差分配维度和 bits；
- 新方法依据图搜索决策区域分离能力组织 prefix。

与 RPQ 的区别：

- RPQ 优化固定码率路由质量；
- 新方法要求每个 prefix 都具有高 decision value，并支持 adaptive acquisition。

### 7.4 Learned 扩展

后续可以学习正交投影：

\[
P_1,\ldots,P_T
\]

使每个 prefix 最大化 search-decision ranking margin，同时加入：

- prefix nesting；
- orthogonality；
- rate penalty；
- interval calibration；
- diversity，避免不同 blocks 重复携带相同决策信息。

---

## 8. 三个论文版本

### Version 1：Policy-only

```text
existing SAQ/RaBitQ code
+ decision-region acquisition policy
+ certificate complexity
```

评价：理论可能有趣，但容易被视为 active decision theory 在 ANNS 上的应用。A 会风险较高。

### Version 2：Policy + constrained theory

```text
precedence-constrained dynamic decision-region determination
+ hardness
+ logarithmic/competitive approximation
+ graph-search instantiation
```

评价：算法味道明显增强，有 ICML/NeurIPS/AAAI 机会。

### Version 3：Joint representation + policy

```text
decision-aware nested representation
+ precedence-constrained acquisition
+ approximation theory
+ multi-index experiments
```

评价：最完整，最可能形成 A 会论文，也是推荐目标。

---

## 9. 最小理论验证，不立即实现大系统

### Theory Gate T1

Claude 应先判断：

1. 图搜索 transcript/result identification 是否能严格归约为 Decision Region Determination；
2. 标准 HEC / adaptive submodular cover 是否已经直接覆盖有前缀链的测试；
3. 前缀约束是否保留 adaptive submodularity；
4. 动态出现测试是否已有直接适用定理；
5. 最小 certificate 是否 NP-hard；
6. 是否可得到 \(O(\log Q)\)、\(O(\log |\mathcal R|)\) 或依赖 submodularity ratio 的保证；
7. 是否存在 fixed-rate 与 adaptive certificate 的渐近分离实例。

### Oracle Gate A0

理论线存活后，再做小型离线 oracle：

- 不实现新 quantizer；
- 用已有 OPQ32/40/48/56/64 距离或模拟 nested blocks；
- 记录 exact search 的 expansion/eviction/termination decision regions；
- 计算 unique-node bytes，不按 comparison 重复计费；
- 在小候选子问题上用 ILP/DP 求离线最优 certificate；
- 比较：
  - fixed-rate；
  - pairwise margin greedy；
  - interval-width greedy；
  - HEC-like region-cut greedy；
  - offline certificate optimum。

核心门禁不是人为“30% 决策在 32B 完成”，而是：

\[
\frac{
\operatorname{Cost}_{\rm policy}
}{
\operatorname{Cost}_{\rm fixed-rate}
}
\]

和：

\[
\frac{
\operatorname{Cost}_{\rm policy}
}{
C^*
}.
\]

只有 HEC-like policy 显著优于简单 margin greedy，并接近 \(C^*\)，才说明新算法对象真实存在。

---

## 10. 与 Selective-OPQ 结果的联系

Selective-OPQ 的最佳配置需要给 75% 节点配置 OPQ64，且 distance-regret 与访问频率高度重合。这说明：

- 高精度价值不强烈集中于少数静态节点；
- 静态 per-node bit allocation 难以获得大收益；
- 当前查询访问到的热点节点确实重要，但热点只是 workload 平均属性；
- 更合理的粒度是 query-conditioned、state-conditioned 的动态码段获取。

因此 Selective-OPQ 的负面结果可作为新方向的经验动机：

> Static node-wise precision allocation is too coarse; precision should be acquired conditionally for the current graph-search decision.

它不应成为新论文的主要实验贡献，只作为 motivation/ablation。

---

## 11. 当前建议裁决

```text
KILL-STATIC-SELECTIVE-OPQ-AS-MAINLINE
NO-STAGE-A.5
NO-STAGE-B

PASS-DECISION-REGION-FORMULATION-FOR-THEORY-AUDIT
HOLD-JOINT-REPRESENTATION-AND-ACQUISITION
NO-CODE-YET
```

只有 Claude 的 Theory Gate T1 确认：

- 不是标准 HEC 的直接实例；
- 前缀/动态约束产生新的算法困难；
- 存在可证明近似或分离；

才准备下一步 oracle。
