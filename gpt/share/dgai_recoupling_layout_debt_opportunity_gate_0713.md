# DGAI Selective Recoupling 与 Layout Debt 联合机会验证

**日期**：2026-07-13
**当前状态**：批准 characterization；不批准完整系统实现
**实验基础**：可运行的 DGAI
**竞争工作定位**：DecoupleVS 作为不可复现的 related work，不作为必须运行的实验 baseline

---

## 1. 研究策略调整

DecoupleVS 与我们的研究定位相关，但其公开 artifact 当前不可获得，因此不能：

* 把论文报告的性能当作已复现事实；
* 在其实现上做增量优化；
* 以“必须击败 DecoupleVS 的公开数字”作为实验门槛；
* 根据论文描述推断其全部运行时行为。

DecoupleVS 可以用于说明社区已经确认：

```text
解耦降低更新成本
但可能损害查询性能
```

我们的实验结论必须建立在可运行的 DGAI 和自行实现的机制上。

下一步不再复现“DGAI 查询比耦合架构慢”这一已知事实，而是验证两个仍未解决的问题：

1. **Selective Recoupling Opportunity**
   解耦索引中是否存在查询频繁、更新较少、拓扑与向量反复共同访问的局部区域，使派生的耦合物化页能够减少 dependent I/O？

2. **Dynamic Layout Debt**
   DGAI 的 similarity-aware layout 是否会在持续插入、删除和图拓扑变化后逐渐偏离当前访问关系，造成查询 I/O 随运行时间退化？

两者共用一套 instrumentation，先看数据，再决定论文主故事。

---

# 2. 候选路线一：Selective Recoupling

## 2.1 问题假设

DGAI 的基础存储将拓扑与向量分离，使更新不需要反复重写完整向量数据。

但查询可能形成：

```text
读取 topology/PQ
    ↓
确定候选节点
    ↓
读取对应 raw vectors
    ↓
精确 rerank
```

如果某些图区域在大量查询中被重复访问，系统可能反复支付相同的跨存储 dependent I/O。

全局重新耦合会失去 DGAI 的更新优势；完全解耦又无法利用局部热点。

因此候选问题为：

> 是否可以保持基础存储完全解耦，仅对查询收益明显、更新相对稳定的局部区域生成可撤销的 coupled query capsules？

---

## 2.2 Query Capsule

基础 DGAI 仍是唯一 source of truth。额外空间只存派生对象：

```text
Query Capsule
├── selected node IDs
├── adjacency/PQ projection
├── selected raw vectors or vector fragments
├── source versions
├── object/page offsets
└── validity metadata
```

查询命中 capsule 后，一次读取可以替代原本来自不同 store 的多个读取。

更新只修改基础层。Capsule 可以：

* 继续有效；
* 通过小型 delta 修正；
* 标记过期后回退基础路径；
* 后台重新构建；
* 失去收益后直接删除。

本轮不实现完整 capsule 系统，只验证机会空间。

---

# 3. 候选路线二：Dynamic Layout Debt

## 3.1 问题假设

DGAI 使用 similarity-aware layout，使相似节点在物理上尽量靠近。

但系统持续更新后：

* 新节点被插入已有页面；
* 删除产生空洞；
* 邻接关系不断变化；
* 图搜索实际共同访问的节点集合发生变化；
* 原布局不会持续保持全局最优。

可以定义布局债务：

```text
Layout Debt =
当前逻辑共同访问关系
与
现有物理共置关系
之间的差距
```

布局债务可能表现为：

* unique pages/query 增加；
* 页面 useful-byte ratio 下降；
* 预取节点被实际使用的比例下降；
* 查询 P99 随更新量增长；
* fresh rebuild 明显优于长期运行索引。

---

## 3.2 候选设计空间

若问题成立，未来系统可能在固定写预算内进行：

* 局部页面重组；
* 节点迁移或交换；
* 空洞回收；
* 热区域 capsule 重建；
* 基于累计收益的维护调度。

但本轮不选择具体维护机制。

---

# 4. C0：统一 Instrumentation

首先在隔离的 DGAI worktree 中加入 measurement-only instrumentation。

每个查询至少记录：

## 4.1 搜索路径

* 访问节点序列；
* expansion 次数；
* 候选进入与退出 heap 的时刻；
* 最终 rerank candidates；
* 查询 recall；
* p50/p95/p99 latency。

## 4.2 页面访问

* topology logical reads；
* topology unique physical pages；
* vector logical reads；
* vector unique physical pages；
* 同一查询内重复页面；
* 跨查询页面复用；
* useful bytes/read bytes；
* topology→vector dependent read pairs。

## 4.3 更新行为

* insert/delete/update 节点；
* 被修改邻接表；
* 被影响页面；
* 实际写入 bytes；
* 页面空洞；
* layout 变化；
* capsule 假想失效范围。

## 4.4 区域统计

对节点、页面和局部图区域记录：

* query frequency；
* update frequency；
* topology/vector co-access frequency；
* co-access set 稳定性；
* query hotspot 与 update hotspot 的重合度。

所有原始 trace 存放于项目 NVMe，系统盘仅保存脚本与摘要。

---

# 5. C1：Selective Recoupling Oracle

## 5.1 Oracle 目标

从训练查询 trace 中识别频繁共同访问的：

```text
topology pages
+
vector records/pages
```

在额外空间预算下，构造理想 capsule，计算它理论上可以消除多少：

* unique page reads；
* dependent I/O rounds；
* bytes/query；
* rerank coordinate I/O；
* p95/p99 路径长度。

预算至少覆盖多个点，例如：

```text
1%、5%、10% 基础索引空间
```

这些预算只用于画 Pareto 曲线，不作为人为通过阈值。

---

## 5.2 必须使用 held-out queries

不能在同一批查询上训练和评估 capsule。

流程：

```text
training queries
    ↓
生成 capsule packing

held-out queries
    ↓
评估真实复用
```

同时需要比较：

* 相同查询分布；
* hotspot shift；
* uniform queries；
* skewed queries。

如果收益只在训练查询上存在，说明 capsule 只是 trace overfitting。

---

## 5.3 更新生命周期

在更新流中记录每个 capsule：

* 首次受影响时间；
* 有效寿命；
* 被修改节点比例；
* 增量修正 bytes；
* 完整重建 bytes；
* 查询收益累计值；
* 维护成本累计值。

需要回答：

> capsule 在兑现足够查询收益前，是否已经因更新失效？

---

# 6. C2：Selective Recoupling 强 Baselines

至少比较以下方案。

## B0：原始 DGAI

不增加额外派生布局。

## B1：普通 LRU 页面缓存

分别缓存原始 topology pages 和 vector pages。

该 baseline 判断收益是否只是普通缓存命中。

## B2：Vector-only 热点缓存

相同 DRAM/SSD 空间预算，只复制热点 raw vectors，不重组拓扑。

该 baseline判断跨 store 共置是否必要。

## B3：简单预取

根据当前 candidate heap 提前读取 raw vectors，不改变布局。

该 baseline 判断 capsule 收益是否只是 prefetch。

## B4：静态热点复制

根据训练访问频率复制热点节点完整记录，但不按 co-access grouping 装页。

该 baseline判断共同访问 packing 是否必要。

## B5：Offline Co-access Capsule Oracle

理想化 capsule，用于给出理论上界，不作为可部署方案。

未来可行机制必须超越 B1–B4，而不是只接近 oracle。

---

# 7. C3：Layout Debt 实验

## 7.1 更新阶段

从同一个初始索引开始，执行真实或可解释的更新序列：

```text
0%
1%
5%
10%
20%
```

更新比例不是通过门槛，而是观察连续退化趋势的采样点。

至少覆盖：

* uniform inserts；
* clustered inserts；
* deletes；
* insert/delete mixed；
* query hotspot 与 update hotspot 重合；
* query hotspot 与 update hotspot 分离。

---

## 7.2 两个索引视图

在每个更新检查点比较：

### Long-running Index

持续在线更新形成的 DGAI 索引。

### Fresh-layout Reference

使用相同逻辑节点和相同图拓扑，重新执行离线 layout/rebuild。

两者必须保持：

* 相同数据；
* 相同图边；
* 相同 PQ；
* 相同查询参数；
* 相同 recall。

因此性能差异主要反映物理布局债务，而不是图质量变化。

---

## 7.3 Layout Debt 指标

报告：

* unique topology pages/query；
* unique vector pages/query；
* nodes used per fetched page；
* page useful-byte ratio；
* page occupancy；
* graph-neighbor co-location；
* query co-access co-location；
* P50/P95/P99；
* rebuild write bytes；
* incremental update write bytes；
* layout gap 随更新时间的变化。

还需要给出区域分布，而不只报告全局平均值：

```text
哪些页面债务高？
债务是否集中？
高债务页面是否具有共同特征？
```

若债务高度集中，局部维护有机会；若均匀分布，可能只能全局 rebuild。

---

# 8. C4：简单维护 Baselines

若 layout debt 存在，先比较简单方案：

## M0：不维护

持续使用 long-running index。

## M1：固定周期 full rebuild

给出最直接的性能—写放大上界。

## M2：页面利用率触发整理

只根据空洞或 occupancy 做局部 compact。

## M3：图邻居共置整理

按当前 adjacency 重组局部页面。

## M4：查询 co-access oracle

按未来 held-out query trace 的共同访问关系重组，仅作为上界。

如果 M1 或 M2 已经取得近似最优结果，就不需要复杂 layout-debt 系统。

---

# 9. 联合决策逻辑

本轮不使用统一的 2×、20% 或 30% 固定门槛。

## 9.1 路线一成立

若观察到：

* topology/vector co-access 在 held-out queries 中稳定；
* capsule oracle 形成普通 LRU、vector cache、prefetch 无法达到的新 Pareto 点；
* 查询收益能够在 capsule 失效前覆盖构建与维护成本；
* 收益集中在可解释的 workload domain；

则主线进入 Selective Recoupling。

可能的论文核心为：

> 面向动态解耦 ANN 的局部、派生、可撤销的物理重耦合。

---

## 9.2 路线二成立

若观察到：

* long-running index 相对 fresh-layout reference 持续退化；
* 退化不是图 recall 或 PQ 质量变化造成；
* layout debt 集中在部分页面或区域；
* 简单 full rebuild 写成本高；
* 局部维护存在明显空间；

则主线进入 Layout Debt Management。

可能的论文核心为：

> 在固定写预算下维护动态 ANN 的查询局部性。

---

## 9.3 两者同时成立

若热点 capsule 收益与 layout debt 同时显著，二者可能合并：

```text
基础解耦布局
    +
查询驱动 capsule
    +
更新驱动债务管理
```

但是否合并必须由数据决定。不能因为两个问题都存在，就默认把所有机制放进一篇论文。

---

## 9.4 两者都弱

如果：

* 普通 LRU/prefetch 已达到 capsule oracle；
* co-access 跨查询不稳定；
* capsule 很快失效；
* fresh rebuild 与 long-running index 差异很小；
* 简单 compact 已恢复全部性能；

则不强行设计系统。

这说明 DGAI 在这些维度上已经足够稳健，而不是实验失败。

---

# 10. 与 DecoupleVS 的关系

DecoupleVS 在论文中作为同题竞争工作讨论，但实验表述必须保持克制：

可以说：

* 它报告了解耦存储上的 compression 和 latency-aware search；
* 它从另一角度修复查询性能；
* 本工作不依赖其 artifact；
* 本工作研究的是局部物化与长期布局退化。

不能说：

* 已经复现其性能；
* 我们必然快于它；
* 其性能报告不可信；
* 某个未实测 residual 一定存在。

若未来 artifact 发布，再追加实验对比，不阻塞当前研究。

---

# 11. Codex 下一任务

执行：

```text
C0：DGAI measurement-only instrumentation
C1：Selective Recoupling oracle
C2：LRU / vector cache / prefetch / static replication baselines
C3：Layout Debt update progression
C4：fresh rebuild 与简单维护 baselines
```

第一轮优先使用已有 SIFT-900K 环境完成流程闭环；随后至少增加一个更高维或分布不同的数据集验证趋势。

输出：

```text
codex/share/dgai_recoupling_layout_debt_characterization_r1_0713.md
```

必须包含：

1. trace 与 instrumentation 说明；
2. recoupling oracle；
3. 简单强 baseline；
4. capsule lifetime 与更新成本；
5. layout-debt 连续退化曲线；
6. fresh-layout reference；
7. 区域异质性分析；
8. 推荐路线一、路线二、统一路线或两者均不成立。

本轮不实现：

* 在线 rent-or-buy controller；
* capsule version protocol；
* 后台重组系统；
* 新缓存算法；
* 新 PQ；
* DecoupleVS reproduction；
* 完整论文架构。

完成 characterization 后停止，由 Gpt/PZ 决定正式系统方向。
