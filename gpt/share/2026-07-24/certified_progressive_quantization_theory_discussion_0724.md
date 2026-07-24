# Certified Progressive Quantization（CPQ）方向讨论稿

## 0. 当前状态与边界

当前 `SELECTIVE-OPQ-ORACLE-A0 Stage A` 已由 Codex 独立执行。CPQ 讨论不得：

- 修改或中断 Codex 当前实验；
- 增加新的训练、trace、数据集或代码任务；
- 自动转入 CPQ 实现；
- 将当前 Selective-OPQ 的结果预设为 CPQ 的正面或负面证据。

CPQ 目前仅处于：

```text
THEORY-DISCUSSION
NOVELTY-KILL-MAP
NO-IMPLEMENTATION
NO-EXPERIMENT
```

目标是先判断：这个方向能否形成一个独立、一般、可证明、适合 ICML/ICLR/NeurIPS/AAAI 的算法问题。

---

## 1. 研究动机

图式 ANNS 通常为每个数据库向量维护一个固定码率的导航表示，例如 PQ32、OPQ64 或其他量化码。搜索过程中，无论某次候选比较非常容易，还是两个候选距离几乎相同，系统都会支付相同的码长和距离估计成本。

图搜索真正需要的并非对每个向量进行同等精度的重构，而是正确完成一系列搜索决策：

- 哪个候选更近；
- 新候选是否应进入 beam；
- 哪个候选应被弹出；
- 当前搜索是否可以终止。

这些决策的难度由当前查询和候选之间的距离间隔决定。设某次关键比较涉及候选 \(a,b\)：

\[
\Delta(q,a,b)=|d(q,a)-d(q,b)|.
\]

当 \(\Delta\) 很大时，很粗的表示已经足以确定顺序；当 \(\Delta\) 很小时，才需要更高精度。

因此，固定码率方案可能系统性浪费信息。CPQ 的核心问题是：

> 能否为每个向量构造可逐层展开的嵌套表示，并在图搜索过程中只获取完成当前决策所需的最少量化信息，同时对已完成的决策给出确定性或概率正确性保证？

---

## 2. 核心抽象

对每个数据库向量 \(x_v\)，存储一个分层码：

\[
C(v)=\left(c_v^{(1)},c_v^{(2)},\ldots,c_v^{(T)}ight).
\]

读取前 \(t\) 层后，获得：

\[
\hat d_t(q,v)
\]

以及一个包含真实距离的区间：

\[
d(q,v)\in I_t(q,v)=\left[L_t(q,v),U_t(q,v)ight].
\]

要求区间随 refinement 单调收缩：

\[
I_{t+1}(q,v)\subseteq I_t(q,v).
\]

对候选 \(a,b\)：

- 若 \(U_t(q,a)<L_s(q,b)\)，认证 \(a\) 比 \(b\) 更近；
- 若 \(L_t(q,a)>U_s(q,b)\)，认证 \(a\) 比 \(b\) 更远；
- 若区间重叠，只精化当前有歧义的候选；
- 到最高层仍不能区分时，使用最高精度码或完整距离作为 fallback。

CPQ 的优化目标不是最低重构误差，而是：

\[
\min_{	heta,\pi}
\mathbb{E}_{q}
\left[
	ext{acquired bits}
+
\lambda \cdot 	ext{distance operations}
ight]
\]

满足：

\[
\Pr\left[
A_{\mathrm{CPQ}}(q,G)

eq
A_{\mathrm{exact}}(q,G)
ight]
\le \delta.
\]

---

## 3. 最小确定性构造

设读取前 \(t\) 层后得到向量重构 \(\hat x_v^{(t)}\)，并具有有效残差上界：

\[
\|x_v-\hat x_v^{(t)}\|_2\le ho_v^{(t)}.
\]

由三角不等式：

\[
\left|
\|q-x_v\|_2-\|q-\hat x_v^{(t)}\|_2
ight|
\le ho_v^{(t)}.
\]

因此：

\[
L_t(q,v)
=
\max\left\{0,\|q-\hat x_v^{(t)}\|_2-ho_v^{(t)}ight\},
\]

\[
U_t(q,v)
=
\|q-\hat x_v^{(t)}\|_2+ho_v^{(t)}.
\]

这给出无分布假设、无经验阈值的 deterministic certificate。

### 定理候选 1：Comparison Soundness

若：

\[
U_t(q,a)<L_s(q,b),
\]

则必有：

\[
d(q,a)<d(q,b).
\]

### 定理候选 2：Exact-on-Graph Trace Coupling

固定一个确定性的 exact-distance 图搜索算法，包括 entry point、beam size、expansion rule、termination rule 与 tie-breaking。

若 CPQ 对每个影响搜索状态的比较只在区间分离后执行，并在无法认证时最终回退到完整距离，则：

\[
A_{\mathrm{CPQ}}(q,G)=A_{\mathrm{exact}}(q,G).
\]

证明可对搜索状态做归纳。该定理只消除量化引入的额外路径误差，不声称图索引本身是 exact NN。

### 定理候选 3：Guarantee Inheritance

若 exact-on-graph reference search 在图类 \(\mathcal{G}\) 上具有某种 ANN 保证，而 CPQ 以至少 \(1-\delta\) 的概率与其搜索轨迹一致，则 CPQ 以至少 \(1-\delta\) 的概率继承该保证。

---

## 4. 为什么确定性界可能失败

确定性残差范数是最坏方向界，可能非常宽。

要认证候选 \(a,b\)，粗略需要：

\[
ho_a^{(t)}+ho_b^{(s)}
<
|d(q,a)-d(q,b)|.
\]

高维量化残差范数可能明显大于 beam boundary 的距离 margin，导致绝大多数比较都展开到最高层。

因此 CPQ 的理论可行性几乎确定，但实践可行性取决于：

> 在真实图搜索的关键 comparison margin 分布下，短码产生的有效 uncertainty interval 是否足够窄。

若最坏情况界过宽，需要概率型投影界或数据依赖的校准界。

---

## 5. 概率型嵌套 sketch 路线

一种可分析构造是 nested random projection / random rotation sketch。

对向量 \(x\) 计算：

\[
z_i(x)=\langle r_i,xangle,\quad i=1,\ldots,M.
\]

数据库存储量化后的投影值。前缀长度为：

\[
m_1<m_2<\cdots<m_T=M.
\]

查询计算相同投影。使用前 \(m\) 个分量得到距离或内积估计：

\[
\hat d_m(q,x),
\]

其置信半径一般可能呈：

\[
\epsilon_m
=
O\left(
\sqrt{rac{\log(1/\delta)}{m}}
ight)
+
	ext{quantization error}.
\]

此构造天然支持 prefix nesting、逐步增加的信息量、弱训练/无训练、简单插入和可分析 concentration bound。

但 fixed-time concentration 不足以直接处理图搜索，因为搜索节点和 refinement 决策依赖此前观测。

---

## 6. 自适应搜索下的置信保证

图遍历是自适应过程：

1. 读取一些候选的粗估计；
2. 根据估计选择后续节点；
3. 决定精化哪个候选；
4. 新访问节点依赖此前随机误差。

因此不能简单对每次 fixed query-vector estimate 使用独立错误概率。

需要研究：

### 6.1 Simultaneous Confidence Bounds

对一次搜索可能访问的全部节点和全部 refinement stage 同时保证：

\[
\Pr\left[
orall v,t:
d(q,v)\in I_t(q,v)
ight]
\ge 1-\delta.
\]

最简单可使用 union bound，但可能产生较大的 \(\log(NT/\delta)\) 项。

### 6.2 Anytime-Valid Confidence Sequences

构造：

\[
\Pr\left[
orall t\le T:
d(q,v)\in I_t(q,v)
ight]
\ge 1-\delta_v,
\]

使算法可以自适应停止或继续 refinement，而无需预先固定 stage。

### 6.3 Adaptive Graph-Path Coupling

在“所有已查询 interval 同时有效”的事件上，证明 CPQ 的搜索状态始终与 exact reference 一致。最终得到：

\[
\Pr[
A_{\mathrm{CPQ}}(q,G)=A_{\mathrm{exact}}(q,G)
]
\ge 1-\delta.
\]

这一部分可能是最有理论价值的贡献，而不是简单的三角不等式区间。

---

## 7. Gap-Dependent Refinement Complexity

设一次关键比较的真实距离 margin 为：

\[
\Delta_e=|d(q,a_e)-d(q,b_e)|.
\]

若置信半径满足：

\[
\epsilon_m
\le
C\sqrt{rac{\log(M/\delta)}{m}},
\]

则认证该比较大致需要：

\[
m_e
=
O\left(
rac{C^2}{\Delta_e^2}
\lograc{M}{\delta}
ight).
\]

于是一次查询的总 acquisition cost 可能上界为：

\[
\sum_{e\in\mathcal{E}(q)}
\min\left\{
M_{\max},
O\left(
rac{C_e^2}{\Delta_e^2}
\lograc{|\mathcal E(q)|}{\delta}
ight)
ight\}.
\]

这给出自然解释：大 margin 决策只消耗短码，小 margin 决策自动精化，无需人工定义困难阈值。

---

## 8. 可能的下界与 Instance Optimality

考虑受限算法类：

- 数据库仅暴露每个向量的嵌套码段；
- 每读取一段获得附加随机或量化信息；
- 算法必须以错误概率不超过 \(\delta\) 判断候选顺序。

对 margin 为 \(\Delta\) 的二元比较，若新增信息为条件次高斯，可能证明任意算法至少需要：

\[
\Omega\left(
rac{\sigma^2}{\Delta^2}
\lograc1\delta
ight)
\]

的信息量。

若 CPQ refinement 达到同阶上界，则可在该 observation model 下获得 per-decision instance optimality，或至多相差常数/对数因子。

更强版本可构造由多个独立关键决策组成的图，给出整体 query acquisition lower bound。该点是否成立，需要 Claude 严格评估，不能预设。

---

## 9. 三条可能的算法路线

### Route A：Deterministic Residual CPQ

使用 residual/additive quantization：

\[
\hat x^{(t)}=c^{(1)}+\cdots+c^{(t)}.
\]

每级维护有效 residual norm bound。

优点：最容易证明、无需概率校准、搜索路径可确定性一致。

缺点：区间可能过宽，经典 MSE residual code 未必适合 routing margin。

定位：理论与框架原型。

### Route B：Probabilistic Nested Sketch CPQ

使用随机旋转/投影、量化投影前缀和 anytime confidence sequence。

优点：理论干净、可得到 gap-dependent complexity、动态插入简单。

缺点：可能需要较长码，需处理量化误差和 adaptive dependence。

定位：主要理论路线。

### Route C：Learned Progressive CPQ

使用 learned residual VQ、nested neural codebook 或 decision-aware training，使短前缀优先保留 routing-relevant information。

目标可包含：

\[
\mathcal L
=
\sum_t lpha_t
\mathcal L_{\mathrm{rank}}^{(t)}
+
eta \mathcal L_{\mathrm{rate}}
+
\gamma \mathcal L_{\mathrm{calibration}}.
\]

定位：在理论版本成立后的性能增强，不应作为最初入口。

---

## 10. 图搜索中的具体算法问题

“区间能比较两个候选”并不自动给出高效 beam search，需要定义区间搜索状态。

可能方案：

- 每个候选维护 \((L,U,t)\)；
- 使用 lower-bound heap 找到潜在最优候选；
- 使用 upper bounds 判断是否已能确定 exact reference 的 next expansion；
- 对造成顺序歧义的少量候选精化；
- beam eviction 只在新候选 upper bound 与当前 boundary lower bound 分离时认证；
- 无法分离时精化两侧或选择信息价值最大的候选。

需要严格回答：

1. 每次 exact reference 的 heap/beam 操作需要认证哪些比较？
2. 是否必须同时精化大量候选才能确定全局最小项？
3. refinement policy 是否影响 correctness，还是只影响 cost？
4. 哪种 policy 具有近似最优 acquisition cost？
5. tie 和极小 margin 如何处理？
6. 最高层是完整距离、固定高精度码，还是高概率精确表示？

---

## 11. 与相关方向的初步边界

以下只是待验证假设，Claude 必须严格查新。

### Successive Refinement / Residual VQ

已有：嵌套或多级重构、rate-distortion 分析。

CPQ 需要新增：搜索决策驱动的自适应 prefix acquisition、distance certificate、graph-path coupling。

### RaBitQ / Flexible-Rate Bounded Quantization

已有：距离估计、理论误差界、多码率或更灵活压缩率。

CPQ 需要新增：同一向量的可嵌套前缀、查询时逐步展开、beam-decision-aware stopping、adaptive-valid guarantee。

### Probabilistic Routing / PEOs

已有：用概率保证决定图邻居是否值得执行高成本精确距离计算。

CPQ 需要新增：多个中间精度层，而非 coarse-or-exact 二元决策；码率复杂度和 progressive information acquisition。

### Adaptive kNN Distance Estimation

已有：逐步采样/估计候选距离、gap-dependent sample complexity。

CPQ 需要新增：离线预编码数据库表示、图遍历产生的自适应候选、内存码率与 ANN search path coupling。

### RPQ / Routing-Aware Quantization

已有：搜索路由目标训练固定码率 quantizer。

CPQ 需要新增：nested variable-rate representation、query-conditioned refinement、certificate 和 anytime cost。

### QINCo/QINCo2

已有：高质量多级 residual neural quantization。

CPQ 需要新增：每个 prefix 的可用距离区间、搜索时 adaptive prefix selection 和正确性保证。

### TurboQuant / Rate-Distortion Quantization

已有：高效或接近理论极限的 fixed-rate quantization。

CPQ 需要新增：decision-conditioned variable acquisition，而非仅改善固定码率失真。

---

## 12. 可能的新颖性失败模式

Claude 必须主动寻找以下 KILL 证据：

1. 已有工作完整实现 nested vector code、prefix distance bound、graph search 中按 beam ambiguity 自适应 refinement，以及路径/结果正确性保证。
2. 现有 adaptive distance estimation 可直接无实质修改地应用到预编码图 ANNS。
3. Flexible RaBitQ 或其他 bounded quantizer 已支持 bitstream prefix、anytime estimation 和 graph traversal。
4. PEOs 或后续工作已包含多级 progressively refined sketches，而不只是 coarse-to-exact。
5. 该问题只是经典 successive refinement 加普通 union bound 的直接组合，没有新的算法或 theorem。
6. lower bound / instance optimality 已被 adaptive nearest-neighbor estimation 文献完整覆盖。

---

## 13. 理论生死门

### PASS-THEORY-SURVIVES

至少满足：

- 未发现完整覆盖该组合的已有工作；
- 能形式化 exact-on-graph reference 与 progressive search；
- 至少有一个非平凡 theorem 超出直接三角不等式；
- adaptive-valid path guarantee 有明确技术内容；
- gap-dependent acquisition complexity 可建立；
- 存在可实现的嵌套码构造。

### HOLD-THEORETICALLY-VALID-BUT-INCREMENTAL

出现以下情况：

- correctness theorem 只是直接区间比较和归纳；
- complexity theorem 可由已有 adaptive kNN 结果直接套用；
- 算法只是 residual VQ + 现有 bound + PEOs routing 的拼接；
- 没有新的 lower bound 或 adaptive-dependence 处理。

### KILL-CPQ-THEORY

出现以下任一情况：

- 已有论文完整覆盖核心组合；
- 任何有效短码 bound 在高维下必然过宽，理论下界表明无法优于固定高精度码；
- progressive prefix 无法同时实现嵌套性、快速距离计算和有效 confidence；
- adaptive graph traversal 使可用保证退化到读取几乎全部表示；
- 唯一可证明版本需要不现实的独立样本/投影存储。

---

## 14. 后续最小 Oracle（当前不执行）

若理论查新通过，下一步不应直接实现完整 CPQ，而应先做 `CPQ-MARGIN-BOUND-ORACLE-A0`。

它只回答：

> 在真实 exact-on-graph beam comparison margin 下，给定若干实际或假设的 uncertainty shrinkage curve，需要多少前缀字节才能认证搜索决策？

建议内容：

1. 从 exact-distance graph search 记录真正改变 beam/heap 状态的 comparison events；
2. 统计 \(\Delta_e\) 分布；
3. 对 deterministic residual bounds、RaBitQ-like probabilistic bounds、理想化 \(C/\sqrt m\) bound 分别估算所需码长；
4. 报告 16B/32B/64B/128B 可认证比例、平均/p50/p95 acquired bytes/decision、acquired bytes/query、fallback 比例和相对 fixed-rate code 的理论节省；
5. 只有大量关键决策能在短前缀完成认证，才实现真实 quantizer。

---

## 15. 请 Claude 完成的任务

Claude 本轮只做理论与查新讨论，不调用 Codex，不启动实验。

### A. Novelty Kill Map

覆盖至少：

- successive refinement；
- residual/additive quantization；
- QINCo/QINCo2；
- RaBitQ 及 flexible-rate 后续；
- probabilistic routing / PEOs；
- adaptive distance estimation for kNN；
- confidence sequences / adaptive data analysis；
- RPQ；
- TurboQuant；
- progressive or anytime vector compression；
- multi-stage learned retrieval / early-exit ANN。

逐项回答：

- 已覆盖哪一块；
- 与 CPQ 最接近的 theorem/algorithm；
- 是否能直接拼接得到 CPQ；
- 还剩下什么不可替代的新问题。

### B. Theorem Audit

逐条评估：

1. comparison soundness 是否过于平凡；
2. exact-on-graph trace coupling 是否已有标准结论；
3. adaptive-valid confidence sequence 是否真正需要新证明；
4. gap-dependent acquisition upper bound 是否能直接套用；
5. lower bound / instance optimality 是否可能；
6. 哪一条 theorem 最可能成为论文核心。

### C. Counterexample Attack

构造并分析：

- 所有 beam margins 很小，必须完整展开的图；
- residual norm 大但查询投影误差小的情形；
- 单次局部认证正确，但错误 refinement policy 导致巨大额外成本的情形；
- 自适应选点使 fixed-time confidence 失效的情形；
- progressive code prefix 的 rate-distortion 显著差于独立 fixed-rate quantizer 的数据分布；
- cache-line 粒度使逻辑码率节省无法转化为运行时间的情形。

### D. Minimal Theoretical Model

给出一个最小但非玩具的正式模型：

- 数据源、查询源；
- 图和 reference search；
- progressive observation/code model；
- error guarantee；
- cost metric；
- upper bound；
- plausible lower bound。

### E. Venue Assessment

分别判断：

- ICML/NeurIPS 所需理论和实验强度；
- ICLR 是否更适合 learned progressive quantizer；
- AAAI 的最低完整度；
- 该方向更可能成为纯理论算法论文、算法系统论文，还是只能作为组件。

### F. Final Verdict

只允许以下之一：

```text
PASS-CPQ-THEORY-CANDIDATE
HOLD-CPQ-INCREMENTAL
KILL-CPQ-NOVELTY
KILL-CPQ-PRACTICAL-BOUND
```

并给出最关键证据和下一步最小验证，不得直接建议实现大系统。
