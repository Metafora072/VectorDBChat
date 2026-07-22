# Claude Problem Mining 独立评审与下一步门禁

**日期：** 2026-07-23
**评审对象：**

* `claude/share/2026-07-22/claude_problem_mining_with_codex_checks_0722.md`
* `codex/share/2026-07-22/p01_p07_a0_results_0722.md`
* `claude/share/2026-07-22/p03_p10_p15_a0_tasks_0722.md`

**总体裁决：**

> 只推进 P03 Temporal Connectivity Gap 的现象与 Oracle headroom A0；P10 排在第二位；P15 暂缓。P07、P08、P14 正式关闭；P01、P02 仅保留为 evidence-level backlog；P05 不作为独立方向继续。

---

## 1. 当前候选裁决

| ID  | 方向                                 | 独立裁决                           |
| --- | ---------------------------------- | ------------------------------ |
| P03 | Temporal Connectivity Gap          | **GO-A0，第一优先**                 |
| P10 | PQ Navigation Corridor Drift       | **GO-A0-NEXT，第二优先**            |
| P15 | Approximate Freshness Threshold    | **HOLD-NEEDS-SEMANTIC-ANCHOR** |
| P01 | PQ Codebook Staleness              | **HOLD-NEEDS-REAL-SHIFT**      |
| P02 | Bridge-Node Deletion Fragility     | **HOLD-PRIOR-RISK**            |
| P05 | Stale Entry Point                  | **KILL-AS-STANDALONE**         |
| P07 | Page Bonus                         | **KILL-NO-PROBLEM**            |
| P08 | io_uring Completion-Order Variance | **KILL-GENERIC-EXECUTION**     |
| P14 | NVMe R/W p99 Threshold             | **KILL-GENERIC-STORAGE**       |

Claude 主导的 Problem Mining 流程比此前 Codex 独立生成、独立查重、独立否决的流程更合理。它得到多个 problem seeds，并用低成本 A0 快速验证了 P01 和 P07，没有为了得到 PASS 而强行拼接系统。

但剩余候选仍需避免一个风险：

> 观察到新的结构指标或路径差异后，直接把该差异包装成研究贡献。

对于 P03 和 P10，后续必须建立：

```text
新状态或新现象
→ 可重复的查询伤害
→ Oracle 机制存在恢复空间
```

三段链条缺一不可。

---

# 2. P03 Temporal Connectivity Gap

## 2.1 裁决

```text
GO-A0-PHENOMENON
```

这是当前最值得优先验证的候选。

它研究的问题是：

> 当向量按照时间 cohort 流式插入图索引时，在线插入是否会形成偏向相近时间 cohort 的边，使早期 cohort 与晚期 cohort 之间缺少有效导航通道？

它与普通 GraphAging 的区别是：

* GraphAging 研究相同终态、不同更新历史是否导致整体图质量下降；
* P03 研究特定插入顺序是否形成具有方向性的 cohort connectivity deficit；
* P03 需要进一步证明这种 deficit 会伤害某些 cohort 的查询，而不仅是图边发生变化。

P03 的核心研究对象不应只是一个新的 edge-density metric，而应是：

```text
插入时间顺序
→ 定向导航通道缺失
→ cohort-specific 查询退化
```

---

## 2.2 修改现有 PASS/KILL gate

当前规格使用：

```text
D[C0][C3] < 0.5 × static 才 PASS
矩阵差异小于 20% 则 KILL
```

这两个阈值可以作为描述性门槛，但不应作为唯一研究裁决。

原因是：

* 即使 C0→C3 边减少超过 50%，查询也可能完全不受影响；
* 即使边密度差异只有 15%，也可能集中破坏关键导航通道；
* edge-density 的绝对变化不等价于搜索效用变化。

真正的 PASS 必须同时满足：

1. 结构差异由时间顺序导致；
2. 结构差异造成查询伤害；
3. 修复该结构差异能够恢复查询性能。

---

## 2.3 三组严格控制

所有实验必须保持：

* 相同 active vector set；
* 相同 `R`；
* 相同 build/search `L`；
* 相同 `alpha`；
* 相同构建线程数；
* 相同最终 degree budget；
* 相同查询和 ground truth。

比较三组图：

### STATIC

对最终 active set 一次性静态构建。

### STREAM-TIME

按照：

```text
C0 → C1 → C2 → C3
```

顺序流式插入。

### STREAM-SHUFFLE

保持：

* 每个 batch 大小相同；
* 每个 cohort 的向量数量相同；
* 插入总量相同；

但打乱 cohort 插入顺序。

`STREAM-SHUFFLE` 是最重要的控制。

若 `STREAM-TIME` 和 `STREAM-SHUFFLE` 的结构、查询结果基本相同，观察到的问题更可能来自普通在线构建，而非时间顺序。

---

## 2.4 第一阶段：结构验证

先只验证是否存在 Temporal Connectivity Gap。

必须报告：

* 完整的 4×4 directed edge-density matrix；
* 每个 cohort 的 outgoing cross-cohort edge mass；
* 每个 cohort 的 incoming cross-cohort edge mass；
* degree-normalized edge mass；
* same-cohort 与 cross-cohort edge ratio；
* cohort 间可达率；
* cohort 间最短导航路径长度；
* 强连通分量情况；
* 多个 build/update seeds。

不能只报告：

```text
D[C0][C3]
```

因为缺失的导航通道可能通过 C1/C2 间接补偿。

### 第一阶段裁决

```text
KILL-P03-NO-TEMPORAL-EFFECT
```

适用于：

* TIME 与 SHUFFLE 没有稳定差异；
* 所有差异均落入 seed variance；
* 差异只来自 cohort 数据分布，不来自插入顺序。

```text
GO-P03-QUERY-EFFECT
```

适用于：

* TIME 相对 STATIC 存在稳定的 directional deficit；
* 该 deficit 明显强于 SHUFFLE；
* 不同 seeds 下方向一致。

只有通过这一阶段，才继续查询实验。

---

## 2.5 第二阶段：查询影响

查询必须按其 GT 1-NN 所属 cohort 分组。

例如：

```text
Q-C0：真实最近邻位于 C0
Q-C1：真实最近邻位于 C1
Q-C2：真实最近邻位于 C2
Q-C3：真实最近邻位于 C3
```

每组报告：

* Recall@10；
* visited nodes；
* distance comparisons；
* first-hit cohort；
* first-entry-to-target-cohort expansion；
* 搜索路径 cohort transition matrix；
* 若使用真实 SSD 路径，再报告 distinct graph pages/query。

重点不是平均 Recall，而是：

> 缺失的 cohort 通道是否只伤害特定查询组，并被整体平均值掩盖。

### 第二阶段裁决

```text
HOLD-P03-STRUCTURE-ONLY
```

适用于：

* edge matrix 明显不同；
* 但各 cohort Recall、visited nodes 和 comparisons 基本稳定。

这种结果说明结构现象存在，但尚不能形成系统问题。

```text
GO-P03-ORACLE
```

适用于：

* 至少一个 query cohort 出现稳定查询退化；
* 退化与对应 cross-cohort deficit 一致；
* SHUFFLE control 不出现相同退化。

---

## 2.6 第三阶段：Degree-Matched Oracle Repair

不能在查询伤害出现后立即实现 temporal pruning 或 cross-cohort repair。

先做 Oracle headroom。

Oracle 方案：

1. 从 `STREAM-TIME` 图开始；
2. 找出相对 STATIC 缺失的 cross-cohort edges；
3. 用 STATIC 中对应的 cross-cohort edges 替换等量 cohort-local edges；
4. 每个节点 degree 保持不变；
5. 总边数保持不变；
6. 不允许通过增加 degree 获得收益。

也可以实现最小 edge injection Oracle，但需要同时给出 degree-matched 版本，排除 degree inflation。

比较：

* Recall；
* visited nodes；
* comparisons；
* cohort transition；
* edge density；
* SSD page reads。

### 最终 P03 裁决

```text
PASS-P03-PHENOMENON
```

必须同时满足：

1. TIME 相对 STATIC 有稳定的 directional cross-cohort deficit；
2. deficit 明显强于 SHUFFLE control；
3. 至少一个 query cohort 出现可重复的 Recall 或搜索成本退化；
4. degree-matched Oracle repair 能恢复部分查询性能。

```text
KILL-P03-NO-TEMPORAL-EFFECT
```

TIME 与 SHUFFLE 没有稳定区别。

```text
HOLD-P03-STRUCTURE-ONLY
```

结构差异存在，但查询影响弱。

```text
KILL-P03-NO-UTILITY
```

结构和查询差异存在，但 Oracle 修复不能改善查询。

只有 `PASS-P03-PHENOMENON` 才允许进入机制设计。

禁止：

* 仅凭 edge-density metric 建立项目；
* 在 Oracle 通过前实现 cross-cohort repair；
* 增加 cache、scheduler、threshold 或 background maintenance 续命。

---

# 3. P10 PQ Navigation Corridor Drift

## 3.1 裁决

```text
GO-A0-NEXT
```

P10 是 P03 之后最值得验证的候选。

它研究的不是普通的“PQ 降低距离精度”，而是：

> PQ 误差是否在图搜索早期将 beam 引入不同的导航走廊，使后续即使进行全精度重排序，也无法找回未被访问的真实邻居？

这里可能存在一个重要区分：

```text
候选分数误差
```

与：

```text
搜索路径误差
```

最终 rerank 可以修正已经被访问的候选分数，却无法修复从未被发现的节点。

---

## 3.2 A0 对照

使用：

* 同一张图；
* 同一入口；
* 同一 beam/search-L；
* 同一查询；
* 同一停止条件。

比较：

### EXACT-NAV

导航阶段全程使用全精度距离。

### PQ-NAV

使用 DiskANN 风格 PQ 距离导航。

### EARLY-EXACT(h)

前 `h` 个 expansion blocks 使用全精度距离，随后恢复 PQ。

### LATE-EXACT

导航始终使用 PQ，只在传统最终候选阶段做精确 rerank。

---

## 3.3 指标

必须报告：

* PQ 与 exact 路径第一次分叉的位置；
* visited-set Jaccard；
* expansion order Jaccard；
* PQ 路径是否重新进入 exact corridor；
* Recall@10；
* visited nodes；
* comparisons；
* SSD page reads；
* early exact 额外读取的完整向量数量；
* 按 PQ residual 和 top-k margin 分组的结果。

---

## 3.4 Gate

```text
PASS-P10-CORRIDOR
```

要求：

1. early corridor divergence 稳定预测最终 Recall miss 或额外 I/O；
2. `EARLY-EXACT(h)` 用少量完整向量访问获得明显 Oracle headroom；
3. matched-cost beam enlargement 无法达到同样收益；
4. 标准 final rerank 无法修复该问题。

```text
KILL-P10-NO-CONSEQUENCE
```

路径显著不同，但 Recall 和 I/O 基本不受影响。

```text
KILL-P10-BEAM-SOLVES
```

简单增大 beam/search-L 以相同成本解决。

```text
KILL-P10-EXACT-TOO-EXPENSIVE
```

需要大量 early exact reads 才产生收益，最终退化为全精度导航。

A0 阶段禁止实现：

* corridor predictor；
* learned uncertainty；
* selective exact-fetch policy；
* 新的 graph layout；
* 多级 cache。

---

# 4. P15 Approximate Freshness Threshold

## 裁决

```text
HOLD-NEEDS-SEMANTIC-ANCHOR
```

当前问题表述存在三种语义混淆。

### 情况一：新向量完全没有进入索引

新向量无法被发现是确定结果，不构成新的 ANN 现象。

### 情况二：新向量进入 delta/memory layer

这接近：

* FreshDiskANN；
* SPFresh；
* OdinANN；
* base + delta 跨层查询。

需要非常清楚地区分已有更新可见性问题。

### 情况三：backlog 增加后 Recall 非线性崩溃

仍需排除：

* 查询命中新数据比例提高；
* 未索引比例本身增加；
* 新旧数据分布不同；
* 普通跨层搜索预算不足。

P15 只有在提出更具体的语义后才能恢复，例如：

> 在相同 pending ratio 下，pending vectors 的空间集中度、导航位置或查询相关性导致可发现性出现显著不同。

在此之前不执行 A0，不与 P03/P10 并行。

---

# 5. Backlog 与 KILL 项

## P01 PQ Codebook Staleness

当前结果只能说明：

> SIFT1M 同分布切分没有触发明显 codebook staleness。

不能据此永久 KILL。

保留条件：

* 真实时间切分；
* 不同业务域；
* 自然 embedding model drift；
* 新数据落入旧训练集未覆盖区域。

禁止通过任意旋转、平移、加噪人为制造 shift。

当前状态：

```text
HOLD-NEEDS-REAL-SHIFT
```

---

## P02 Bridge-Node Deletion Fragility

有两个风险：

1. 按中心性删除容易成为 adversarial workload；
2. 删除修复已被 Wolverine、IP-DiskANN、FreshDiskANN 等高度研究。

只有当真实 workload 显示：

```text
删除概率与导航中心性存在相关性
```

或业务天然删除某类 bridge nodes 时，才值得恢复。

当前状态：

```text
HOLD-PRIOR-RISK
```

---

## P05 Stale Entry Point

入口点过时是真实但偏薄的问题。

自然解决方案包括：

* 周期性重算 medoid；
* 多入口；
* HNSW upper layers；
* query-aware entry selection。

很难形成足够强的独立系统核心。

当前状态：

```text
KILL-AS-STANDALONE
```

可作为 P03 或真实 distribution shift 实验中的控制变量。

---

## P07 Page Bonus

A0 显示：

* co-resident 节点落入 GT-100 的比例约 0.03%；
* 理论 I/O 节省约 1.29%。

没有足够问题规模。

```text
KILL-NO-PROBLEM
```

不再通过更大 page、人工布局或扩大候选集合续命。

---

## P08 io_uring Completion-Order Variance

异步完成顺序可能影响 tie-breaking 或实现确定性，但当前核心属于通用异步执行问题。

除非证明：

* 相同查询；
* 相同 I/O 集合；
* 相同计算预算；
* 仅完成顺序差异就稳定造成显著 Recall 风险；

并需要新的 ANN correctness abstraction，否则不值得推进。

```text
KILL-GENERIC-EXECUTION
```

---

## P14 NVMe R/W p99 Threshold

NVMe FTL GC 和读写竞争是真实系统问题，但：

* ANN 只是受害 workload；
* 机制大概率是 QoS、限速、优先级或调度；
* 缺少 ANN-specific 状态与核心 primitive。

```text
KILL-GENERIC-STORAGE
```

---

# 6. 执行顺序

```text
Step 1：P03 structure + shuffled control
Step 2：只有结构信号存在，才测 grouped-query effect
Step 3：只有查询伤害存在，才做 degree-matched Oracle repair
Step 4：P03 PASS 后设计机制；P03 FAIL 后转 P10
Step 5：P10 完成前不启动 P15
```

时间预算：

```text
P03 结构阶段：2–4 小时
P03 查询 + Oracle：额外 2–4 小时
P03 A0 总 hard wall：1 个工作日
```

最终纪律：

> 放宽 discovery gate，不等于放宽 A0 后的证据标准。P03 和 P10 都必须证明“新状态差异、查询伤害、Oracle 可恢复”三段链条。缺少查询影响时只能 HOLD，Oracle 无收益时必须 KILL。
