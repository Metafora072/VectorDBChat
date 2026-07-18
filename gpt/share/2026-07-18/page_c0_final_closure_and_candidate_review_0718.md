# Page-Cost C0 Final Closure and New-Candidate Review

## 1. Page-Cost-Aware Navigability C0 裁决

正式接受 C0 的结论：

```text
KILL / NO C1
```

C0 已完成以下关键核验：

- PageANN 已经构造并搜索 page-node graph，不能再描述为普通 post-hoc layout；
- OctopusANN 已经将 path length、degree、records-per-page 与 page overlap 纳入 I/O 模型；
- joint graph–packing theorem 仍是形式空白，但“尚无 theorem”不等于存在可用研究空间；
- 字面成立的一维非恒定 separation 来自 shortcut/hopset 降低路径长度，在 `B=1` 时仍存在，不具有 page-specificity；
- 加入 `B=1` gap 消失、matched expansions、fixed record bytes、无隐式 page edges、strongest layout oracle 与 constant edge/degree slack 后，没有得到 separation；
- fixed packing 的 page cover 退化为 Set Cover，无法形成 constant-edge bicriteria joint algorithm；
- independent score 为 significance/formal novelty/system relevance/feasibility=`8/4/4/3`。

因此不构建 PoC、不修改 Vamana/PageANN、不进入 C1。

---

## 2. Learned Repair Oracle 裁决

### 2.1 不批准 quick check 或 pilot

Claude 的核心假设是：

> 使用内存中的新节点向量、候选节点 PQ、degree 与距离排名，预测候选 reverse-edge repair 是否会被 RobustPrune 接受，从而在读取候选节点的邻接页之前跳过无效 repair。

当前不批准，原因如下。

### 2.2 M2 没有可直接训练的逐操作数据集

M2 明确采用：

- 内存聚合；
- exact histograms；
- stage-level counters；
- 不记录向量内容；
- 不记录邻居 ID 明细；
- 不记录逐操作日志。

因此不存在“直接使用 M2 ground truth 训练模型”的条件。要训练模型必须新增：

- 每个 `(new node, candidate node)` 的 feature；
- prune 前邻接状态；
- accepted/rejected label；
- 后续 mutation 与 query-quality结果。

这已经是新的 instrumentation 与实验线，而不是低成本复用。

### 2.3 预测标签依赖被隐藏的邻接状态

对于候选节点 `u`，RobustPrune 的结果取决于：

```text
u 的当前 neighbor set
候选之间的距离关系
pruning 顺序
alpha / R
并发更新后的实际版本
```

只给模型：

```text
v embedding
u PQ code
degree
distance rank
```

无法唯一确定标签。可以构造 cheap features 相同、但 `u` 的邻接集合不同，最终一个 accept、一个 reject 的实例。

因此该任务天然存在 information gap：

- 不读取或不保存 `u` 的邻接摘要，预测不可能是 sound；
- 保存足够的邻接摘要，则引入新的 DRAM state、一致性维护和更新成本；
- 这时 strongest baseline 应是 deterministic quantized/sketch-based approximate pruning，而不是“无模型”。

### 2.4 80% precision/recall 不是可接受门槛

repair prediction 的错误不对称：

- false positive：仍产生 page read，主要损失是性能；
- false negative：跳过本应接受的 reverse edge，改变图拓扑、连通性和未来查询路径。

因此普通分类的 `80%/80%` 没有研究意义。必须约束：

- accept-edge false-negative rate；
- long-churn recall；
- tail recall；
- connectivity/path degradation；
- distribution shift；
- model retraining与推理开销。

在没有 correctness/quality invariant 时，它只是风险较高的 heuristic。

### 2.5 强相邻 baseline 已存在

QuIVer 已证明 Vamana 的 edge selection、pruning 和 navigation 可以在 training-free 2-bit quantized metric 中执行。即使它不解决动态 reverse-edge prediction，也说明“用廉价压缩表示近似 prune”必须首先与 deterministic quantized pruning 比较。

综合判断：

```text
Learned Repair Oracle:
problem plausibility = medium
mechanism novelty = low
system depth = low
evaluation risk = high
decision = KILL as current mainline
```

不运行 quick literature check、不生成训练 trace、不做模型 canary。

---

## 3. Self-Improving Graph ANN 裁决

### 3.1 当前 novelty framing 被直接削弱

Claude 提出的对象是：

> 每次查询后，根据实际路径与目标结果编辑少量 graph edges，使图逐步适应查询分布。

SIGMOD 2026 的 `Dynamically Detect and Fix Hardness for Efficient ANNS` 已经：

- 使用 online queries；
- 动态检测 graph defective regions；
- 通过 RFix 改善入口到查询邻域的 reachability；
- 通过 NGFix 改善查询密集区域的 graph connectivity；
- 处理 workload change 时无需离线重建整个 query-aware graph。

CleANN 也已经包含：

- workload-aware linking；
- query-adaptive on-the-fly neighborhood consolidation；
- semi-lazy cleaning。

因此以下表述不能成立：

```text
现有工作只做 offline query-aware construction；
尚无人根据 online queries动态修改 ANN graph structure。
```

### 3.2 Competitive-ratio 版本是另一条未定义理论线

把问题改成：

```text
online edge-edit algorithm
vs.
offline optimal static graph
```

可能仍有形式差异，但当前缺失：

- 固定 metric/query model；
- feedback 中是否知道 exact top-k；
- edge edit、SSD write 与 query read 的统一成本；
- degree/space constraints；
- adversarial query 下可行的 competitive benchmark；
- 与 RFix/NGFix 的正式差异；
- 实际系统如何获得 ground truth supervision。

这不是一个 quick check 可以解决的问题，也与 M0–M3 没有直接证据连接。

综合判断：

```text
Self-Improving Graph ANN:
high-level idea novelty = low-to-medium
direct prior overlap = high
formal readiness = very low
system feasibility = low
decision = KILL in current form
```

不启动理论 gate、不运行 query-driven edge-edit实验。

---

## 4. 其他 Claude 候选

### Non-uniform Degree Allocation

当前不推进。Sparse Navigable Graphs 的 total-edge/minimum-degree优化本身允许不同节点具有不同出度；“现有图全部使用 uniform degree”不是准确理论边界。若只根据 LID/density 分配 `R_i`，很容易退化为参数启发式。

### Amortized Dynamic Maintenance

当前不推进。FreshDiskANN、CleANN 与 signal-triggered repair 已分别覆盖 delta/merge、semi-lazy maintenance 与 repair scheduling。没有明确随机模型、potential function或非平凡 bound前，不再开启新 gate。

### Navigation-Only Poisoning / ACL

按 PZ 的研究偏好继续降级，不作为 FAST/VLDB 主线。

---

## 5. 最终研究线状态

以下方向全部关闭：

- Dynamic Vamana write optimization；
- A0 dynamic architecture recombination；
- B0 repair-bound implementation continuation；
- Page-Cost-Aware Navigability；
- Learned Repair Oracle；
- Self-Improving Graph ANN；
- Lazy Repair recall bound；
- Non-uniform degree allocation；
- amortized repair scheduling；
- ContractANN；
-原 multi-NVMe placement。

M0–M3、A0、B0 与 Page C0 保留为完整的实验、理论和否定性探索记录。

## 6. 下一步原则

不再继续从 Vamana 的：

```text
repair
page layout
degree
beam
cache
query adaptation
```

六个局部轴上枚举变体。

下一阶段应切换到一个独立问题，并先提供：

1. 真实应用或 runtime observation；
2. 明确受影响的 workload；
3. 可复现的问题规模；
4. 与 2024–2026 primary work 的边界；
5. 在提出机制前即可执行的 Kill gate。

本文件完成后保持停止，不自动启动新 brainstorm、实验或代码。
