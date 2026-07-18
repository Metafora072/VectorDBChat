# Page-Cost-Aware Navigability C0：Joint Graph–Packing Theory Gate

## 1. 裁决

本轮不优先推进以下候选：

- `Navigation-Only Poisoning`：问题可能真实，但研究重心明显偏安全，与当前 FAST/VLDB 存储系统主线不匹配；
- `ACL / Deletion Navigation Non-Interference`：继续 HOLD；
- `Lazy Repair with Recall Degradation Bounds`：当前表述 HOLD，不得与 page-aware graph 拼成大系统。

批准一次严格收窄的 **Page-Cost-Aware Navigability C0 纯论文/理论门禁**。

本轮只判断：

> 在固定 ANN 搜索语义、page capacity 和 graph space/degree budget 下，联合选择 graph topology 与 page packing，是否能获得任何 post-hoc layout 无法达到的非平凡 page-I/O 优势；以及该问题是否存在新的 approximation、hardness 或 constructive guarantee。

本轮不运行系统实验、不构建大索引、不修改代码、不实现 page-aware RobustPrune，不自动进入 C1。

---

## 2. 必须纠正的当前叙述

### 2.1 PageANN 不是“只在标准 Vamana 后做普通 layout”

PageANN 已经：

- 从高质量 vector-level graph 出发；
- 把多个向量聚成 page node；
- 聚合跨 page 的 vector-level edges；
- 删除 page 内部冗余边；
- 让 logical page node 与 physical SSD page 一一对应；
- 使用 page-node graph 执行查询。

因此不得再声称：

```text
图 ANN 从未出现 page-native graph；
PageANN 只做 post-hoc page shuffle；
我们的贡献只是首次让 graph structure 感知 page。
```

PageANN 已占据 page-node graph、逻辑粒度改变与物理 page 对齐的系统设计空间。

仍可能存在的空白只能是：

```text
PageANN 的构造是由既有 vector graph 派生的 heuristic；
尚未发现一个以 page-read objective 为核心、
同时对 navigability/search quality 给出正式保证的
joint graph–packing optimization。
```

### 2.2 OctopusANN 已经有 page-level cost model

OctopusANN 已把：

- average degree；
- search path length；
- records per page；
- page overlap/locality

共同放入 page-read complexity model，并联合 disk layout 与 page search。

因此不得把“edge/node cost 与 page cost 不一致”单独写成 novelty。

新对象必须超出：

- overlap ratio characterization；
- page shuffle；
- in-page search；
- dynamic beam/width；
- layout/search 技术组合。

### 2.3 B-tree 类比只能作为动机

“从 binary tree 到 B-tree”的类比直观，但不能替代技术差异。

只有证明：

1. layout-only class 存在不可消除的 page-cost lower bound；
2. 改变 graph structure 后能突破该 bound；
3. 同时保持 matched navigability、space 和 degree；

才能成立“page-native topology”故事。

---

## 3. 固定模型

C0 必须先固定以下对象。

### 3.1 数据与图

给定：

```text
finite metric space (P, d)
alpha >= 1
directed graph G=(P,E)
maximum out-degree bound R
total edge budget M
page capacity B
```

Graph quality 至少使用以下之一：

- `alpha`-navigability；
- sorted `alpha`-reachability；
- 明确定义且与固定 beam/best-first search 对应的更强条件。

不得仅使用：

- connectivity；
- graph diameter；
- average degree；
- empirical Recall@k。

### 3.2 Page packing

定义：

```text
pi : P -> {physical pages}
```

满足每个 page 最多容纳 `B` 条完整 node record。

必须明确 node record 包含：

- vector / compressed vector；
- adjacency list；
- neighbor IDs；
- metadata。

如果理论中假设 adjacency 与 vector 分开存储，必须单独建模，不得在结论中再按“一次 page read获得全部信息”解释。

### 3.3 固定查询执行

必须固定一个 page-aware search procedure `S_page`，例如：

- deterministic greedy；
- fixed-width beam/best-first；
- fixed tie-breaking；
- fixed termination；
- 是否对已读 page 内所有 vertices 做 free in-page evaluation。

读取一个 page 后可复用其中已加载内容；查询成本定义为：

```text
PageCost(G, pi, q, s)
= number of distinct physical pages read by S_page
```

再选择一种主目标：

```text
worst-case over (q,s)
```

或：

```text
expected cost under fixed D_q, D_s
```

两者不得混用。

---

## 4. 三个优化对象

### 4.1 Fixed-graph best layout

对固定 graph `G0`：

```text
PostLayout(G0)
= min_pi PageCost(G0, pi)
```

这是最强 post-hoc layout oracle，不是某个具体 partition heuristic。

### 4.2 Edge-sparsity-optimal family

定义：

```text
OPT_edge
= minimum |E| among alpha-navigable graphs
```

并定义所有 edge-optimal graph 中最好的 page cost：

```text
SparsePageOPT
= min_{G,pi}
  PageCost(G,pi)
  s.t. G is alpha-navigable
       |E| = OPT_edge
       max_degree <= R
```

这避免选择一个刻意差的固定 graph 来制造 separation。

### 4.3 Joint page-cost optimum

定义：

```text
PageOPT_c
= min_{G,pi}
  PageCost(G,pi)
  s.t. G is alpha-navigable
       |E| <= c * OPT_edge
       max_degree <= R'
       page capacity = B
```

`c` 与 `R'` 必须是明确常数或函数。

C0 要判断：

> 允许有限的 edge/degree slack，是否能换取 asymptotically 更低的 page reads？

若只在无限增加 edges 或把整个数据放一页时成立，则没有意义。

---

## 5. C0 的首要理论任务：Separation

必须优先尝试构造一个显式 metric family，证明以下至少一种 separation。

### Separation A：Sparse topology 与 page topology 的 Pareto gap

证明：

```text
SparsePageOPT / PageOPT_c = Omega(f(n,B))
```

其中 `f(n,B)` 非常数。

要求：

- 所有 edge-optimal graph，即使使用最优 packing，也存在 page-read lower bound；
- 另一个仅使用常数倍 edges/degree 的 graph + packing 达到更低 page cost；
- 两者满足同一 `alpha`-navigability；
- 使用同一 `S_page`；
- gap 不是由更换 entry point、beam width 或 page search语义造成。

### Separation B：Post-layout 无法弥合固定构图的损失

针对一个明确且重要的 graph family，例如：

- SlowDiskANN；
- sorted-alpha construction；
- practical Vamana abstraction；

证明：

```text
PostLayout(G_A) / PageOPT_c = Omega(f(n,B))
```

但 Separation B 单独成立时研究价值低于 A，因为它可能只说明构图算法较差。

### Separation C：Hardness / approximation boundary

若无法形成 separation，可以证明 joint graph–packing 问题：

- NP-hard / Set-Cover-hard；
- 存在非平凡 approximation；
- 或给出 bicriteria approximation。

只有“显然 NP-hard”且没有 constructive result，不能 PASS。

---

## 6. Constructive algorithm 门槛

只有 separation 或 hardness 成立后，才检查是否存在构造算法。

候选算法必须输出：

```text
(G, pi)
```

而不只是：

- 对 Vamana edges 做 same-page tie breaking；
- 先建图再运行 graph partitioner；
- 调整 `R/alpha`；
- 提高 intra-page edge比例；
- 把 PageANN grouping换一个 heuristic。

必须至少保留一种正式性质：

- `alpha`-navigability；
- sorted reachability；
- bounded approximation factor；
- bicriteria edge/page guarantee；
- 明确 worst-case/expected page-cost upper bound。

如果算法只在 empirical recall 上工作，则不属于 C0 的理论突破。

---

## 7. Primary-work 边界

C0 至少逐项核验：

### PageANN

必须回答：

- page-node graph 与 vector-node graph 的关系；
- grouping 是否改变 graph logical granularity；
- page connections 如何从原图聚合；
- 是否存在 formal navigability或page-I/O guarantee；
- 新候选与其区别是 theory、objective，还是仅不同 heuristic。

### OctopusANN / I/O DSE

必须回答：

- page-read complexity model 的精确定义；
- overlap ratio、path length与degree如何进入模型；
- page shuffle与page search覆盖哪些设计；
- joint graph construction是否仍为空白。

### DiskANN++ / Starling

核验 layout、page search、entry routing 与 page utilization，避免把已有 I/O optimization重新包装。

### Sparse Navigable Graphs

核验：

- `alpha`-navigability；
- minimum total edges / maximum degree；
- Set Cover equivalence；
- approximation与hardness。

新问题若只是把每条 edge换成一个固定 page weight，可能直接退化为已有 weighted Set Cover，必须明确判断。

### Sort Before You Prune

核验 sorted `alpha`-reachability与beam-search guarantee，判断 page-aware construction是否破坏理论前提。

### Disk-resident experimental evaluation

核验 page size、layout、I/O utilization和dimension sensitivity，作为系统意义证据，不作为 formal novelty。

---

## 8. 对 Lazy Repair 的当前裁决

`Lazy Repair with Recall Degradation Bounds` 本轮不批准。

原因：

1. 一般图中一次关键 insertion/deletion就可能改变桥接路径，无法仅由 `k,n,R,alpha` 得到有实用价值的统一 recall 上界；
2. 若加入随机数据、随机更新和分布假设，问题会变成另一条独立理论线；
3. FreshDiskANN通过搜索 delta保证 freshness，并非依赖主图 recall缓慢下降；
4. Wolverine、CleANN、Greator与近期 repair scheduling 已覆盖 repair、lazy cleaning、tail recall与何时repair的大量空间；
5. 将它与 page-native graph拼接，会形成两个尚未验证的核心机制，而非单一系统贡献。

只有 Page C0 关闭后，且能先给出非平凡反例边界或明确随机模型时，才允许单独重提。

---

## 9. PASS 条件

C0 仅在同时满足以下条件时 PASS：

1. 形成严谨的 joint graph–packing formal object；
2. PageANN 与 OctopusANN 没有等价 theorem/objective；
3. 得到至少一个非平凡、非恒定的 separation，或 hardness + constructive approximation；
4. separation 使用最强 post-layout oracle，而不是弱 heuristic baseline；
5. graph、packing、search语义和page record内容完全固定；
6. 保持 matched navigability 与受控 edge/degree budget；
7. 能推出至少一个可证伪系统预测，例如：
   - 在相同 recall/graph bytes 下减少 distinct pages/query；
   - gain随 page capacity `B`按某个方向变化；
   - layout-only oracle仍无法达到 joint design；
8. 独立反方评分同时达到：
   - problem significance >= 7/10；
   - formal novelty >= 6/10；
   - system relevance >= 7/10；
   - implementation feasibility >= 7/10。

任何一项不足均为 KILL。

---

## 10. KILL 条件

出现任一情况立即关闭：

- 只能证明常数 `1 page` 或 toy gap；
- 最优 post-hoc packing可以完全消除gap；
- 需要无限增大degree/edges才能降低page cost；
- formal objective与真实best-first/page-search I/O不一致；
- PageANN已实现等价page-node construction；
- OctopusANN模型已包含等价优化对象；
- 问题直接退化为weighted Set Cover且没有新结构；
- page-aware RobustPrune无法保持navigability guarantee；
- 只能得到same-page tie-breaking heuristic；
- 只在不匹配的 recall、entry、beam或memory配置下有效；
- strongest baseline无法实现或构造；
- 最终故事仍是“提高overlap ratio，所以少读page”。

---

## 11. 输出与资源

输出：

```text
codex/share/2026-07-18/
page_cost_aware_navigability_c0_0718.md
```

资源边界：

- 2–3天；
- 新增空间 <1 GiB；
- 只读论文、公式推导与证明；
- 不运行完整数据集实验；
- 不构建索引；
- 不修改 Vamana/PageANN；
- 不生成新 trace。

报告必须包含：

- PageANN事实纠正；
- formal page model；
- 三个优化对象；
- strongest post-layout baseline；
- separation/hardness推导；
- prior-work matrix；
- PASS/KILL；
- 若PASS，仅给出C1最小 proof-of-concept预算，不执行。

完成后停止，不自动进入 C1。
