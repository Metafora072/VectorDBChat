# DGAI Update-Induced Graph Quality Degradation 归因门禁

**日期**：2026-07-13
**状态**：批准一次 measurement-only attribution gate
**不批准**：完整 repair system、论文立项或继续枚举 DGAI I/O residual

---

## 1. 对上一轮结果的裁决

C0–C4 的两条原始路线正式关闭。

### Selective Recoupling

在 10% 空间预算下：

* SIFT capsule oracle 仅减少约 9.48% pages/query；
* GIST capsule oracle 仅减少约 8.16%；
* 普通 LRU 与 vector-hot baseline 均取得更高页面收益；
* skewed workload 下，普通缓存优势进一步扩大；
* 1% 更新后，绝大多数 capsule pages 已受到影响。

因此，现有数据不支持：

> topology/vector 跨 store 共置存在普通缓存和热点向量复制无法覆盖的独立价值。

即使未来优化 capsule validation，静态 oracle 本身也没有形成足够强的新 Pareto，因此不实现 capsule protocol、rent-or-buy controller 或后台 rebuild。

### Dynamic Layout Debt

在持续 delete–reinsert 更新后：

* current layout 与 same-graph fresh layout 几乎没有差异；
* adjacency relayout 的收益在初始索引中已经存在，并随更新比例增加而缩小；
* clustered update 同样没有表现出不断增长的 fresh-layout gap。

因此，这不是随更新积累的 layout debt，而是一个初始布局的静态排列机会。当前不实现在线 layout maintenance。

---

# 2. 新 observation

上一轮出现了一个独立于物理布局的现象：

```text
持续 delete–reinsert
        ↓
逻辑数据集合恢复不变
        ↓
Recall 持续下降
```

在 uniform refresh 中，Recall@10 从约：

```text
0.9970 → 0.9632
```

clustered refresh 的下降更明显。

同一逻辑查询轨迹在不同物理 layout replay 下得到相同 recall，说明该变化不能归因于：

* topology page placement；
* vector page placement；
* page occupancy；
* adjacency physical relayout。

目前最合理的候选原因是：

```text
graph topology / navigability degradation
```

但这仍只是 observation，不是 idea。

---

# 3. 为什么不能直接开发 graph repair

动态 graph ANN 的 recall maintenance 已有直接工作：

* FreshDiskANN 通过累积删除并周期性 consolidation 修复图；
* IP-DiskANN 通过原地处理插入与删除维持长期稳定 recall；
* topology-aware localized update 已研究 affected-vertex 定位与相似邻居替换；
* repair timing 和 navigability-triggered repair 也已有近期研究。

因此不能声称：

* 首个发现 churn 导致 recall 下降；
* 首个局部修复；
* 首个按信号触发 repair；
* 首个避免 full rebuild；
* 首个稳定 dynamic graph recall。

下一轮唯一值得验证的独立系统问题是：

> DGAI 的 topology/vector 解耦是否降低了高质量 graph repair 的物理成本，使系统能够在相同 I/O 和写预算内执行更充分的 repair？

换言之，候选贡献不是新的 repair algorithm 本身，而可能是：

```text
decoupled topology-only storage
        +
repair-cost accounting
        +
budgeted repair execution
```

---

# 4. 核心研究问题

## Q1：Recall 下降是否真实且可复现？

需要首先排除：

* ground-truth 计算错误；
* tag/internal-ID 映射错误；
* instrumentation 引入行为变化；
* delete–reinsert harness 语义错误；
* PQ code 未正确恢复；
* update completion 尚未持久化；
* query 参数相对更新后图不足。

## Q2：哪种 update primitive 导致退化？

必须分离：

* insert-only；
* delete-only；
* delete 后重新插入相同向量；
* delete 后插入不同向量；
* uniform churn；
* clustered churn。

## Q3：图的哪个结构性质发生退化？

候选包括：

* deleted-edge residue；
* in-neighbor 路径丢失；
* 平均或尾部入度下降；
* hub 节点被替换后未恢复；
* entry-point reachability 下降；
* greedy monotonic path 变长；
* affected region 与其余图连接减弱；
* 插入产生的边质量低于原始 build；
* pruning 在重复更新中逐渐丢失 bridge edges。

## Q4：现有 repair baseline 能否直接恢复？

若 IP-DiskANN/TALS/FreshDiskANN 风格的简单已知机制已经恢复全部 recall，就不存在新的机制空间。

## Q5：解耦是否产生新的 repair-cost Pareto？

只有当更强 repair 的主要成本是 topology I/O，而 coupled storage 会被迫携带大量无用 vector bytes，DGAI 的解耦才可能形成独立系统优势。

---

# 5. G0：正确性与复现

使用隔离的 clean DGAI commit，保留 instrumentation patch，但不得复用已经经历更新的索引副本。

至少执行：

* SIFT-900K；
* GIST-900K；
* 三个随机种子；
* 多个 query subsets；
* 更新检查点 0%、1%、5%、10%、20% operations。

## 5.1 Ground Truth

### Delete–reinsert 相同向量

由于最终逻辑数据集合未变化，原始 tag-level ground truth 可以复用，但必须验证：

* 每个 reinserted tag 唯一存在；
* old internal node 不再可见；
* new internal node 正确映射回原 tag；
* exact scan 的 top-k tag 集合与原始 ground truth 一致。

### Delete-only / insert-only

必须重新计算相应逻辑数据集合的 ground truth，禁止通过简单过滤旧 top-k 近似代替。

## 5.2 Search Budget Sweep

在每个更新检查点扫描：

* candidate-list size；
* beam width；
* rerank candidate 数。

需要判断：

> Recall 下降是图真的失去 navigability，还是旧查询预算不足以搜索更新后的图？

如果增大普通 search budget 即可低成本恢复，应将其作为最强 baseline，而不是立刻开发 repair。

---

# 6. G1：Update Primitive Isolation

## U0：No-op Control

不执行更新，只重复加载、查询和 checkpoint，确认 measurement drift 为零。

## U1：Insert-only

从较小初始集合开始，持续插入 held-out vectors。

记录：

* Recall；
* 插入边质量；
* reverse-edge 成功率；
* query path length；
* update I/O。

## U2：Delete-only

逐步删除数据并使用重新计算的 remaining-set ground truth。

记录：

* 指向已删除节点的残余边；
* affected in-neighbor 数；
* repair coverage；
* reachable active nodes。

## U3：Delete–reinsert Same Vector

删除后重新插入完全相同的向量和 tag。

该 workload 的理想结果应接近初始索引，因为逻辑数据集合未变化。它最适合测量纯 graph-maintenance drift。

## U4：Replace with New Vector

删除旧对象并插入不同分布的新对象，用于区分：

* graph maintenance failure；
* 合法 distribution drift。

每个 update primitive 分别执行 uniform 和 clustered 版本，不在第一轮混合所有 workload。

---

# 7. G2：Topology Attribution

在每个 checkpoint 导出逻辑图快照，不只记录物理位置。

## 7.1 节点级指标

* active outdegree；
* estimated/exact indegree；
* 邻居距离分布；
* neighbor overlap with fresh-build graph；
* repeated-refresh nodes 的边质量；
* updated 与 untouched nodes 的差异；
* 指向 tombstone/invalid node 的边比例。

## 7.2 路径级指标

对固定查询记录：

* visited nodes；
* expanded nodes；
* first-hit true-neighbor depth；
* greedy path length；
* dead-end 次数；
* 搜索是否进入 ground-truth 邻域；
* 失败 query 的路径断点；
* entry node 到 true-neighbor region 的 reachability。

## 7.3 区域级指标

* strongly/weakly connected components；
* bridge-node loss；
* hub indegree changes；
* updated region 与其余图之间的 cut edges；
* affected-query tail recall；
* mean recall 与 worst-query recall。

不能只报告全局平均度数，因为少量 bridge/hub 损失即可显著影响一部分查询。

---

# 8. G3：Repair Baselines 与 Oracles

## R0：Current DGAI

当前 lazy deletion、batch deletion trigger 和 insertion 流程。

## R1：Search-Budget-Only

不修改图，只提高 query search budget。

用于判断 repair 是否必要。

## R2：Full Fresh Rebuild

相同逻辑数据集合重新离线建图，作为质量上界。

若 fresh rebuild 也无法恢复，则问题可能来自 PQ、参数或 ground truth，而不是 dynamic repair。

## R3：Exact Local Repair Oracle

离线知道被删除节点的真实 in-neighbors 与 out-neighbors，并在受影响局部区域中执行高质量重连。

该 oracle 不要求可部署，用于判断：

> 局部 repair 是否足以恢复，还是必须全局 rebuild？

## R4：Approximate In-neighbor Repair

实现或复用 IP-DiskANN 风格的近似 affected-neighbor 定位与替换策略。

## R5：Localized Replacement

实现最小的 topology-aware similar-neighbor replacement baseline。

R4/R5 的目标不是声称新贡献，而是确定已知 repair 是否已经覆盖 observation。

---

# 9. 必须测量的成本

每种 repair 必须同时报告：

## Quality

* mean Recall@10；
* P5/min query recall；
* failed-query count；
* path/reachability recovery。

## Update Cost

* topology pages read；
* vector pages read；
* topology bytes written；
* vector bytes written；
* pruning CPU；
* update latency；
* background repair burst；
* query P99 interference。

## Storage

* reverse-neighbor metadata；
* affected-node index；
* repair log；
* temporary candidate state。

只报告 recall 恢复而不报告 repair 成本，没有系统意义。

---

# 10. Decoupling-Specific Opportunity

最终需要比较两个物理成本模型。

## Coupled Repair

修改邻接表时，node record 同时包含：

```text
topology + vector
```

即使 repair 只需要 topology，也可能读取或写回完整 record。

## Decoupled Repair

repair 只读取和修改：

```text
compact topology records
```

raw vectors仅在候选距离验证真正需要时读取。

需要回答：

1. 在相同 repair algorithm 下，解耦减少多少无效 vector read/write？
2. 节省的 I/O 是否足以执行更多 affected-node repair？
3. 在相同 update-I/O budget 下，解耦能否保持更高 recall？
4. 在相同 recall 目标下，解耦能否降低 update latency 或 tail interference？

若成立，潜在系统故事是：

> 解耦不只降低普通更新成本，还可以将节省的 I/O 预算重新投资于更强的图质量维护。

这比“再设计一个 repair algorithm”更符合 storage-systems 定位。

---

# 11. 与近期工作的边界

本方向不研究：

* 什么时候触发 repair；
* 用什么通用信号预测 recall；
* 普通 local repair；
* 普通 in-neighbor discovery；
* 单纯避免 batch consolidation。

这些问题已经有直接工作。

本方向只在以下条件下继续：

```text
更高质量 repair 确实有用
        +
其成本主要由物理 topology/vector coupling 决定
        +
decoupling 形成新的 repair-budget Pareto
```

若 repair 收益与存储架构无关，则该问题属于 graph algorithm，不进入当前主线。

---

# 12. 决策

## Continue

同时满足以下事实时，才进入系统设计：

1. Recall degradation 在两个数据集和多个种子上稳定复现；
2. 不能仅靠轻微增加 search budget 恢复；
3. exact/local repair oracle 可以显著恢复；
4. 当前 DGAI repair 与已知简单 repair 之间仍有明显空间；
5. repair 成本主要受 topology/vector I/O coupling 影响；
6. 在相同 I/O budget 下，decoupled repair 形成新的 recall–update–query Pareto。

届时再讨论暂定的：

```text
Budgeted Topology Repair for Decoupled ANN
```

## Close DGAI

满足任一情况，就退出 DGAI 主线：

* observation 来自 harness、ground truth 或实现错误；
* search-budget-only 已低成本恢复；
* IP-DiskANN/TALS 风格 baseline 已完全解决；
* 只有 full rebuild 能恢复；
* repair opportunity 与 decoupled storage 无关；
* 改善只来自新的 graph pruning algorithm；
* 第二个数据集无法复现。

---

# 13. Codex 下一任务

执行 G0–G3，但按阶段早停。

输出：

```text
codex/share/dgai_update_quality_attribution_g0_g3_0713.md
```

交付内容：

1. 正确性审计；
2. 四类 update primitive；
3. search-budget sweep；
4. topology/path attribution；
5. full rebuild 与 local-repair oracle；
6. 已知 repair baselines；
7. coupled/decoupled repair-I/O accounting；
8. Continue 或 Exit DGAI。

本轮不实现：

* 自适应 repair scheduler；
* repair controller；
* reverse graph production system；
* 新 pruning algorithm；
* 完整后台维护框架。

如果 G0 证明 observation 不可靠，应立即停止；如果 G2/G3 证明问题纯属 graph algorithm，也应退出，不为了保留 DGAI 而强行包装。
