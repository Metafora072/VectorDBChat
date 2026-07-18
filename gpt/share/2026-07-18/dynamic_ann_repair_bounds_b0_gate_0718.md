# Dynamic ANN Repair Bounds B0：Deletion-Only Feasibility Gate

## 1. 裁决

正式接受 A0 的 `KILL / SWITCH DIRECTION` 结论：

- A0 未留下可继续实现的 Dynamic ANN architecture candidate；
- 未运行实验、未构建索引、未修改代码；
- memory delta、direct page update、localized patch 与 LSM graph 四类架构边界已经闭合；
- 后续不得从 A0 自动恢复任何系统原型。

同时批准一次严格收窄的 **Repair Bounds B0 纯论文/理论审计**。

B0 不是 Dynamic Vamana 写优化的继续实现，也不是对 M2 中 `scheduled − mutated` 的进一步 profiling。其唯一目标是判断：

> 对固定的 graph search algorithm 和单点删除，是否存在比 connectivity/degree 更接近查询成功率的、可局部计算的必要 repair witness；或者能否证明此类 local witness 在一般情形下不存在。

本轮不运行实验，不新增 trace，不实现算法，不自动进入 B1。

## 2. 为什么只批准 deletion-only

原请求同时覆盖 insertion、deletion 和 mixed workload，理论对象过大。

B0 只研究：

```text
single-vertex deletion
```

原因：

- deletion 对现有 search path、random-walk transition 和 in-neighbor connectivity 的破坏更容易明确定义；
- Wolverine、IP-DiskANN、Greator、DEG、CleANN 和 random-walk deletion 都提供了直接边界；
- insertion 的新点可见性、reverse-edge addition 与 placement 是另一问题，不得在 B0 中拼接；
- mixed workload 会引入累积 drift、repair debt 和 scheduling，不适合用于第一个理论门禁。

若 deletion-only 无法建立非平凡结果，整个 repair-bound 方向直接关闭。

## 3. 必须修正的 formal object

不得继续使用：

```text
min over all algorithms A
Recall(G', Dq) >= q*
SearchCost(G', Dq) <= c*
Freshness(G', u) <= f*
```

作为 B0 主对象。该定义同时改变算法、布局与更新语义，无法形成可比较的 repair optimum。

B0 必须固定：

1. metric space 与数据集 `X`；
2. 删除前 graph `G=(V,E)`；
3. 被删除节点 `v`；
4. entry-point distribution `D_s`；
5. query distribution `D_q`；
6. 固定 search procedure `S`：
   - greedy 或固定 beam width；
   - 固定 tie-breaking；
   - 固定 termination rule；
7. fixed degree bound `R`；
8. graph representation仍以 edge mutations为理论单位。

删除后的 repair action 只允许选择：

```text
ΔE- : 删除的旧边
ΔE+ : 新增的 replacement edges
```

理论成本首先定义为：

```text
|ΔE+| + |ΔE-|
number of mutated adjacency records
number of inspected local vertices/edges
```

不得把 4 KiB page writes 直接写入理论下界。页面成本依赖 layout、packing、delta log 和 storage API，只能在未来系统映射阶段讨论。

## 4. 质量指标

B0 不直接以经验 `Recall@k` 作为 theorem 中唯一约束。

至少定义两层对象。

### 4.1 Search-success functional

对固定 `S`：

```text
Success_S(G, q, s)
```

表示从入口 `s` 对查询 `q` 执行固定 search 后，是否返回：

- 真正最近邻；
- top-k 中至少一个指定目标；
- 或距离不超过 `(1+ε)d*` 的结果。

再定义：

```text
P_success(G)
= Pr_{q~Dq, s~Ds}[Success_S(G,q,s)]
```

### 4.2 Structural proxy

候选 witness 可以使用：

- monotonic-search-path preservation；
- query-to-target hitting probability；
- search-trace cut；
- bounded stretch/reachability；
- escape-hardness-like local defect；
- 其他明确 proxy。

但必须证明以下之一：

```text
proxy preservation => lower bound on P_success
```

或：

```text
proxy violation => existence of query set with measurable success loss
```

只有 connectivity、degree或普通 reachability，不能直接声称保证 ANN recall。

## 5. 两条允许的结果路线

### Route I：Impossibility-first

优先尝试证明：

> 对任意只查看删除点 `r`-hop neighborhood 的 local certificate，存在两个全局 graph/query instances，它们具有相同 local view，但维持固定 `P_success` 所需的最小 repair set不同。

若成立，应明确：

- graph family；
- search algorithm；
- local-view半径或信息集合；
- 两个不可区分实例；
- repair necessity 的差异；
- impossibility 对 pre-I/O filtering 的含义。

这是有效的 B0 结论，但它只关闭“纯局部 certificate”，不自动形成系统论文。

### Route II：Restricted constructive result

只有 Route I 在某个受限 graph family 下不成立时，才尝试构造：

- local witness；
- nonzero lower bound；
- repair algorithm；
- approximation/competitive relation。

必须明确限制，例如：

- 单层图；
- 特定 monotonicity property；
- bounded doubling dimension；
- 固定 entry set；
- 固定 query distribution family；
- 特定 deletion位置。

不得把受限 theorem 外推到一般 Vamana/HNSW。

## 6. Prior-work guarantee matrix

B0 至少覆盖以下 primary works。

### Greator

核验 affected vertices/pages、similarity-aware localized replacement，以及它提供的是 empirical matched-quality，还是 formal necessity/approximation guarantee。

### IP-DiskANN

核验 approximate in-neighbor search、replacement-edge数量与复杂度，以及 stable recall 是 empirical result还是 formal invariant。

### Wolverine

核验 monotonic search path 的精确定义、Wolverine/Wolverine+修复哪些被破坏路径、2-hop restriction提供何种保证，以及是否已经形成等价 local witness。

### Dynamic Exploration Graph

核验 even-regular structure、deletion connectivity guarantee、continuous refinement，以及 connectivity 与 ANN search quality之间是否有 formal link。

### CleANN

核验 workload-aware linking、query-adaptive consolidation、semi-lazy cleaning，以及是否存在 query-distribution-aware repair value 的正式性质，还是经验策略。

### Random-Walk / SPatch

核验 preserved hitting-time statistics 的精确定义、randomized deletion与deterministic algorithm、hitting-time preservation与 ANN quality 的理论/经验连接，以及它是否已经占据 Route B 的核心对象。

### Static graph-ANN theory

至少核验 Graph-based NNS from Practice to Theory 等工作，明确静态 search guarantee 依赖哪些数据与图分布假设，能否用于动态 repair lower bound。

### 新近相邻威胁

核验 Dynamically Detect and Fix Hardness、navigability-signal-triggered repair，以及其他直接使用 query distribution、hardness或repair signal 的工作。调度“何时修”与选择“必须修哪些边”应严格区分。

## 7. 关键问题

报告必须回答：

1. 在固定 search algorithm 下，最小 repair 是否可以写成 well-defined combinatorial optimization？
2. 即使给定 `D_q`，该 optimum 是否需要全局 query/path information？
3. local neighborhood是否足以产生非零 necessary lower bound？
4. monotonic path、hitting time与 ANN success之间已有何种正式关系？
5. 是否存在两个 local-view identical、global-necessity different 的反例？
6. 若只能在强假设下建立 witness，这些假设是否仍覆盖实际 Vamana/DiskANN？
7. theoretical edge bound 能否在未来映射为 SSD I/O收益，还是会被page granularity完全吞没？
8. strongest prior是否已经提供相同 witness或更强 guarantee？

## 8. PASS 条件

B0 仅在以下两类结果之一成立时 PASS。

### PASS-A：非平凡 constructive result

同时满足：

- 单点删除；
- 固定 search algorithm；
- invariant 比 connectivity/degree 更接近 search success；
- lower bound严格大于0，并非 `target record`、`R`或affected-set重述；
- certificate无需全图scan或完整query replay；
- 给出 approximation/competitive或明确upper/lower关系；
- 与 Wolverine、random-walk deletion、Greator等机制不等价；
- 假设范围仍足以覆盖至少一种实际图ANN family。

### PASS-B：强 impossibility result

同时满足：

- 给出完整不可区分实例构造；
- 证明一般 local certificate无法约束 minimum quality-preserving repair；
- 明确哪些额外全局状态是必要的；
- 结论可以直接 Kill 一类看似可行的 pre-I/O repair算法；
- 不只是“recall是全局的”这一口头判断。

PASS 只表示值得继续理论推导或小型离线验证，不授权系统实现。

## 9. KILL 条件

出现任一情况立即关闭：

- lower bound只能是0、删除目标或degree bound；
- 只重新命名 affected vertices、monotonic path或hitting time；
- 以 connectivity保证替代 search quality；
- 必须扫描全图、保存所有query traces或运行完整 workload才能计算 certificate；
- 把 `scheduled−accepted` 或 `scheduled−mutated` 当作可省repair；
- Route B退化为 edge utility threshold、learned ranking或无保证heuristic；
- theorem只适用于与Vamana/HNSW无关的特殊图；
- 页面I/O收益无法从edge bound中产生可证伪预测；
- random-walk deletion、Wolverine或已有理论已经给出等价/更强结果；
- 只能产出研究计划，没有完整 derivation或counterexample。

## 10. 输出与停止点

输出：

```text
codex/share/2026-07-18/
dynamic_ann_repair_bounds_b0_0718.md
```

报告必须包含：

- fixed formal model；
- prior guarantee matrix；
- 至少一个完整证明草图；
- constructive derivation或impossibility construction；
- assumptions与适用范围；
- edge-bound到page-cost的可行性边界；
- PASS/KILL；
- 独立反方审稿评分。

资源边界：

- 时间上限：1–2天；
- 新增空间：<1 GiB；
- 只读论文、代码和数学推导。

完成后停止，不自动运行实验、生成新trace、matched-R、instrumentation、prototype、B1，或恢复A0已Kill的系统候选。
