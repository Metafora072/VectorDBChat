# Dynamic ANN Quality-Constrained Repair Bounds B0：审议请求

**提出时间：** 2026-07-18（UTC+8）  
**性质：** theory/algorithm feasibility gate request；不是实验计划、实现授权或新 idea 宣称  
**建议：** `ALLOW ONE READ-ONLY B0 AUDIT`  
**预算建议：** 1–2 天，新增空间 <1 GiB，无运行实验

## 1. 对 PZ 问题的直接回答

A0 不是因为“研究目标与 prior work 重叠”而 KILL。系统或算法工作完全可以与已有工作追求同一目标，只要新设计具有不同的核心表示/算法、能够解释为什么效果更好，并在 matched semantics、matched quality 和 strongest baselines 下显示稳定优势。

A0 Kill 的是当前三种具体机制：它们分别退化为已有技术组合、普通 cache/LSM，或无法给出可维护的 ANN quality invariant。目标重叠本身不是 Kill 条件。

现有实验与论文仍留下一个较窄但真实的算法问题：

> 在给定 freshness、degree、recall/search-cost 约束下，一次 insertion/deletion 最少必须物化哪些 graph mutations；能否在读取/写入目标 page 之前，以局部可计算的 certificate 逼近这个最小集合？

这不是“少写一些 page”的系统口号，而是一个 quality-constrained minimum repair 问题。只有它能形成非平凡 lower bound、constructive upper bound 或 approximation guarantee，算法方向才可能突破 A0 的组合式 frontier。

## 2. Problem Anchor

- **Bottom-line problem：** 找到 dynamic graph ANN 在 matched search quality 与 freshness 下的最小必要 repair work，并设计接近该下界的算法。
- **Must-solve bottleneck：** 当前算法以 `R`、visited set 或 affected set 产生 repair candidates，但 M2 的 `scheduled → accepted → mutated` 差额不能说明哪些最终 mutations 对质量是必要的。
- **Non-goals：** 不复活 queue coalescing、dirty-page cache、降低 `R`、普通 localized repair、matched-R factorial、ContractANN 或跨论文数字排名；不要求目标与所有 prior work 不重叠。
- **Constraints：** 单机、多 NVMe、无 GPU；必须与 Greator、IP-DiskANN、Wolverine、DEG、CleANN、SPatch/Random-Walk deletion 正面对照；paper 与 artifact 分开。
- **Success condition：** 得到一个非平凡、可局部计算、与 ANN search quality 有明确联系的 repair lower bound/certificate，以及一个不等价于已有 affected-only/少边修复的构造算法；否则在 B0 关闭。

## 3. 为什么现有数字还不是通用上下界

| Existing evidence | 可以支持 | 不能支持 |
|---|---|---|
| 本地 direct-update path 的 target/shared page 为 4096 B/replacement | 在“整页提交、立即物化、当前 layout/API”条件下的精确 floor | 所有 dynamic ANN 的通用 4 KiB 下界；log/packing/delta 可改变物化单位 |
| M3 的 22,522,471 个 page versions 中 pre-submit supersession 为 0 | 固定当前锁、visibility、queue 状态机时，queue coalescing 的可省 bytes 上界为 0 | 跨 completion 改状态机后的安全上界 |
| perfect-future relayout oracle 每次只省 DGAI 0.79、OdinANN 1.11 pages | 当前 write-set constrained relayout family 的收益上界很小 | repair-selection algorithm 的总收益上界 |
| OdinANN `scheduled 96 → accepted 46.6 → mutated 54.3` | candidate/prune/mutation stages 存在明显数量差 | 约 41.7 个 repair 可安全删除；rejected/accepted/mutated 与 quality necessity 不同构 |
| FreshDiskANN 两次全 LTI pass；LSM-VEC 多层 lookup/compaction | 各自 state representation 的结构性 cost | 任意 dynamic graph ANN 都必须支付相同 cost |

因此现有结果给出了多个 **conditional bounds**，但没有给出 quality-constrained repair 的非平凡 lower bound。当前可优化区间不能诚实地写成“baseline bytes − 4096 B”；中间的大部分可能是保持 navigability 所需，也可能含算法冗余，现有聚合数据无法区分。

## 4. 统一理论对象

### 4.1 状态与约束

给定更新前 graph state `G`、更新 `u`、查询分布 `D_q`、degree bound `R` 和目标质量/资源约束：

\[
\operatorname{Recall}(G',D_q) \ge q^*,\qquad
\operatorname{SearchCost}(G',D_q) \le c^*,\qquad
\operatorname{Freshness}(G',u) \le f^*.
\]

令 `F(G,u;q*,c*,f*,R)` 为满足上述约束的所有更新后 graph states。该集合才是跨算法比较的 invariant object；`scheduled repairs`、`mutated records` 和 `written pages` 都只是某个实现的 proxy。

### 4.2 单指标 constrained optimum

不能把 write、read、query latency、DRAM 与 recall 直接加成一个伪精确 scalar。以 write pages 为例，在其他指标作为约束时定义：

\[
\mathrm{OPT}_{w}(G,u)
=
\min_{A:\,A(G,u)\in\mathcal F}
\mathbb E[\mathrm{WritePages}(A,G,u)].
\]

同理可以定义 `OPT_r` 或 `OPT_update-latency`。对 strongest baseline `A_b`，只有在找到有效 `LB_w` 后，才存在 certified opportunity：

\[
0 \le
\underbrace{\mathrm{Cost}_w(A_b)-\mathrm{OPT}_w}_{\text{真实但未知的优化空间}}
\le
\underbrace{\mathrm{Cost}_w(A_b)-LB_w}_{\text{可证明的机会窗口}}.
\]

如果 `LB_w=0`，这个窗口没有决策价值；如果 `LB_w` 需要先完整运行全局 ANN workload 才能计算，也不能指导 pre-I/O repair。

### 4.3 需要建立的结果类型

B0 不预设必须得到某个 theorem。只接受以下三种结果之一：

1. **Lower bound：** 任意满足明确 graph/search invariant 的更新算法至少要修改/检查某个局部 cut、path witness 或 edge set；
2. **Constructive upper bound：** 一个算法用可计算 witness 产生 repair set，并保证 cost 不超过 lower bound 的常数或可解释因子；
3. **Impossibility boundary：** 证明 local certificate 不能约束 recall/navigability，因而 effect-proportional pre-I/O repair 在当前语义下不可成立。

第三种结果会诚实地关闭算法方向，而不是强行进入实现。

## 5. 两条候选理论路线

### Route A：Local navigability witness

从 deletion/insertion 影响的局部 search paths 或 cuts 出发，定义只有在 witness 失效时才必须 repair 的最小集合。

- **优点：** 直接连接 M2 的 repair fanout/mutation observations；可能在 page I/O 前计算。
- **主要风险：** connectivity、degree 和局部 monotonic path 并不等于 recall；Wolverine、DEG、CleANN、SPatch 已覆盖大量相邻边界。
- **B0 关键问题：** 是否存在比这些工作更强、又无需全图维护的 witness。

### Route B：Query-distribution-aware repair value

把一条 repair edge 对 `D_q` 下 search success/hitting probability 的边际贡献作为状态，求满足质量约束的最小 repair subset。

- **优点：** 与实际 recall/search cost 更直接，可能得到 submodular/approximation 形式。
- **主要风险：** 需要 workload statistics；边际贡献随 graph 和 query path 相互作用，可能非局部、非平稳；容易退化为 threshold/edge utility heuristic。
- **B0 关键问题：** 是否能证明结构性质或误差界，而不是只提出 learned/ranked heuristic。

当前推荐先审 Route A，再以 Route B 作为反证/替代；不得把两者拼成大系统。

## 6. Primary-work boundary

B0 至少应核验：

- Greator：affected vertices/pages、localized connection、page-aware `ΔG`；
- IP-DiskANN：approximate in-neighbors、`O(cR)` replacement edges、in-place delete；
- Wolverine：monotonic-path repair；
- Dynamic Exploration Graph：even-regular replacement、connectivity、continuous refinement；
- CleANN：workload-aware linking、query-adaptive consolidation；
- Graph-Based Nearest Neighbors with Dynamic Updates via Random Walk / SPatch：hitting-time-preserving deletion；
- FreshDiskANN、LSM-VEC：作为 materialization cost 边界，而不是算法同构 baseline。

需要回答的是“这些算法保证了什么、没有保证什么”，而不是“目标已经有人做所以 Kill”。

## 7. B0 pass/kill gate

### PASS 仅当同时满足

1. 明确固定 continuous insert、delete 或 mixed workload 中的一种；
2. 定义一个比 degree/connectivity 更接近 ANN quality 的 invariant；
3. 得到非零、非 `R` 参数重述的 lower bound，或一个有正式 approximation/competitive claim 的算法；
4. certificate 能在读取/写入大部分 candidate pages 之前计算；
5. 与 Greator/IP-DiskANN/Wolverine/DEG/CleANN/SPatch 的机制差异成立；
6. 可以在 matched recall、search cost、freshness 下构造 strongest baseline；
7. 不需要先实现完整系统才能说明问题。

### 任一出现即 KILL

- lower bound 只能是 `0`、target record 或 degree bound；
- 把 `scheduled−mutated` 直接当可省 repair；
- invariant 只保证 connectivity，却声称保证 recall；
- certificate 要扫描全图、跑完整 query workload 或维护全局 all-pairs state；
- 算法只是调 `R`、edge rank threshold、dirty bit 或 affected-only patch；
- Route B 最终只是无保证的 learned heuristic；
- closest prior 已给出等价 witness/guarantee；
- strongest baseline 无法获得或构造等价版本；
- 现有 M2/M3 聚合 trace 不足，而新增 trace 前也无法提出明确可证伪 claim。

## 8. 请求 Gpt 审议

建议 Gpt 只裁决是否允许一个 **1–2 天、<1 GiB、纯论文/理论的 B0 feasibility audit**。B0 输出应为：formal object、assumptions、prior guarantee matrix、至少一条完整 derivation 或 impossibility argument、可计算性分析，以及 `PASS/KILL`。

本请求不授权：

- 新实验或 trace；
- matched-R；
- instrumentation；
- prototype；
- solver/oracle 大规模运行；
- 自动进入 B1。

如果 Gpt 不认可存在形成非平凡 bound 的可能，应直接接受 A0 closure 并换方向。
