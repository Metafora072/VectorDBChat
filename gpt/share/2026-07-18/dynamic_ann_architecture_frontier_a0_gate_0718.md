# Dynamic ANN Architecture Frontier A0：Existing-Work Limitation Audit Gate

## 1. 裁决

PZ 已明确暂停 ContractANN，本轮不执行 C0。

批准一次 **纯纸面的 Dynamic ANN Architecture Frontier A0 审计**，目标不是证明“已有工作有交叠所以不能做”，而是判断：

> 是否存在一个由现有架构约束造成、尚未被解决的明确 trade-off，并且能够由新的状态表示、更新状态机或系统不变量打破，而不只是把已有技术组合到一起。

本轮不得运行实验、构建索引、修改代码、新增 instrumentation 或开始系统原型。

Write Reducibility、Semantic Repair Efficiency、matched-R、multi-NVMe、ContractANN 和 RAG pivot 继续保持停止。

## 2. 对当前 reframing 的必要修正

### 2.1 允许目标重叠，但机制必须形成新边界

系统论文不要求研究目标完全无人涉及。可以与已有工作共同追求 online visibility、低写放大、incremental update、稳定 query latency、小批或流式更新。

但“我们也做这些，并且调得更好”不足以构成贡献。至少需要：

1. 现有架构存在可证明的结构性代价；
2. 新设计有明确的数据结构、状态机或不变量；
3. 该机制不是已有 decoupling、localized repair、direct insert、LSM levels、memory delta、page combining 的并列拼装；
4. 优势来自机制，而不是 `R/L/beam/batch/page size` 参数；
5. 能定义公平语义和强 baseline。

### 2.2 不采用“target / repair / publish 三项严格支配”作为前提

M0–M3 的三组件分解适用于本地 DGAI/OdinANN artifact，但不能直接作为所有系统的同构成本模型：

- FreshDiskANN 的 target update 首先进入内存 TempIndex，长期索引由 StreamingMerge 更新；
- Greator 使用 delete / insertion / patch 小批工作流和页级 `ΔG`；
- LSM-VEC 的成本包含 level insertion、跨层查询和 compaction；
- SVFusion 的成本包含 CPU commit、异步传播和异构层次维护。

因此，A0 可以使用三组件作为辅助观察，但不得据此计算跨论文的伪精确 Pareto 排名。

## 3. 已确认的事实修正

### FreshDiskANN

必须同时记录两件事：

1. 短期更新驻留 DRAM TempIndex，查询同时搜索长期 SSD index 和全部 TempIndex；
2. StreamingMerge 的内存与主要计算依赖 change set，但 Delete/Patch 阶段对长期 SSD index 做两次顺序遍历，并在实验中读写整个 LTI 两遍。

因此其结构性问题可表述为：

> 以 DRAM delta 获得即时 freshness，并通过周期性全索引顺序 pass 控制 delta 大小。

不得简化成“所有成本都与 change set 成比例”，也不得简化成“等同于全量 rebuild”。

### DGAI

paper 与本地 artifact 必须分开：

- 论文描述 direct in-place insertion；
- 论文通过将新节点放入最近邻所在页面，增量维护 similarity-aware locality；
- 论文明确将其与 FreshDiskANN 的 merge overhead 区分。

因此，本地 artifact 的固定 publish/reload 不能直接解释为 DGAI 架构必然要求，也不能用来声称“similarity-aware layout 必须全局重排”。

### Greator

Greator 不应只描述为传统 delete→insert→patch baseline。它已经提供：

- lightweight topology 定位 affected vertices；
- 只更新 affected pages；
- page-aware `ΔG`；
- similarity-aware localized connection；
- 小批 streaming update。

任何“affected-only / effect-proportional repair / incremental patch”候选都必须与 Greator 正面对照。

### OdinANN

OdinANN 已经提供：

- direct insert；
- out-of-place fixed-record update；
- page-level update combining；
- on-path page reuse；
- approximate concurrency control。

普通 direct insert、page combining 或预留空槽不能作为候选 novelty。

### IP-DiskANN

IP-DiskANN 已经以逐操作 in-place insertion/deletion 避免 batch consolidation。任何“取消周期合并、按影响范围即时修复”的候选必须说明与其算法边界不同。

### LSM-VEC

A0 必须新增 LSM-VEC。它通过 hierarchical graph indexing + LSM storage 支持 out-of-place dynamic updates，并明确面向 billion-scale disk-based dynamic vector search。

因此以下口号不能视为空白：

- SSD-resident delta；
- out-of-place update；
- multi-level graph；
- incremental materialization；
- 避免传统 in-place update。

A0 必须核验它为这些能力支付的 query amplification、level maintenance、compaction、memory、recall 和 connectivity 代价。

### SVFusion

SVFusion 只作为异构设计边界：

- CPU–GPU–disk hierarchy；
- versioned/asynchronous propagation；
- dynamic updates and fallback。

不能把其 GPU 依赖简单当成“纯 SSD 版本天然新颖”；必须识别异构状态机中哪些机制已占据一般性设计空间。

## 4. Primary-source 范围

至少覆盖：

1. FreshDiskANN；
2. Greator；
3. DGAI paper；
4. DGAI frozen artifact；
5. OdinANN paper；
6. OdinANN frozen artifact；
7. IP-DiskANN；
8. LSM-VEC；
9. SVFusion；
10. Disk-Resident Graph ANN Experimental Evaluation。

可补充 SPFresh、Wolverine 或其他直接相关工作，但不得用二手摘要替代核心论据。

## 5. 统一审计框架

对每个系统分别回答以下问题。

### 5.1 Freshness path

- 新点在何处首次可查询？
- 查询是否需要同时搜索 delta / levels / fallback？
- 删除何时对查询生效？
- 稳态 freshness 受什么后台阶段限制？

### 5.2 Materialization unit

- 更新写入 record、page、segment、level 还是完整 index？
- 哪些工作与 active-set size `N` 相关？
- 哪些工作与 change set `Δ` 相关？
- 是否存在周期性全索引 scan/rewrite？
- 是否存在 compaction / merge debt？

### 5.3 Repair semantics

- scheduled repair 与 actual mutated vertices/edges 的关系；
- repair 是 affected-only、localized、search-derived、in-neighbor-derived 还是固定 fanout；
- 插入与删除是否使用不同机制；
- 是否需要 global quality restoration。

### 5.4 Query tax

- delta/levels 是否增加额外搜索；
- 是否产生跨层候选合并；
- 是否损失页面局部性；
- 是否增加 random I/O、distance computation 或 cache footprint；
- 后台维护是否干扰前台查询。

### 5.5 Resource and stability tax

- DRAM 增长；
- SSD space amplification；
- write amplification；
- merge/compaction backlog；
- 长 churn 下 recall 与 latency 稳定性；
- failure/recovery 只记录明确承诺，不扩展为 ContractANN。

## 6. 架构家族，而非论文逐个拼装

至少形成四个 architecture family：

### Family A：Memory delta + periodic global merge

代表：FreshDiskANN。

### Family B：Direct in-place / out-of-place page update

代表：DGAI、OdinANN、IP-DiskANN。

### Family C：Localized small-batch patch

代表：Greator。

### Family D：Out-of-place multi-level / LSM graph

代表：LSM-VEC。

SVFusion作为异构层次参照。

对每个家族必须给出：

```text
immediate benefit
unavoidable/structural cost
cost source in algorithm or data structure
whether a local patch can remove it
what new cost that patch introduces
```

“unavoidable”必须由论文算法、数据结构或复杂度支持。代码没有实现、作者没有评测、默认参数较差，均不等于结构性限制。

## 7. 候选新 Pareto 点的严格门禁

A0 最多保留一个候选。候选必须同时满足：

1. 有明确目标 workload，例如持续 insert、insert/delete 混合、小 batch 或 billion-scale steady state，不得泛化为所有动态负载；
2. 指出至少两个 architecture family 的结构性代价；
3. 给出一个新的核心状态表示或状态机，而非技术列表；
4. 写出至少三个系统不变量，例如：
   - 查询必须覆盖哪些版本/层；
   - repair debt 如何被有界；
   - graph connectivity 如何保持；
   - 后台 materialization 如何不需要全索引 pass；
   - compaction 后旧状态何时可回收；
5. 不依赖人工阈值作为核心正确性条件；
6. 说明为什么给已有系统增加一个普通模块不能得到同样机制；
7. 明确最接近的两个 prior works 和本质差异；
8. 定义至少一个可证伪预测；
9. 能在用户的单机、多 NVMe、无 GPU约束下实现；
10. 工程量能够形成完整毕业工作，但不是六个月无边界重写全部系统。

## 8. 自然 Kill 条件

出现任一项即关闭该候选并建议换方向：

- 所谓空白已被 LSM-VEC、Greator、DGAI、OdinANN 或 IP-DiskANN 直接覆盖；
- 候选等价于 `memory delta + localized repair + LSM` 的组合；
- 只需给现有系统增加 dirty-page tracking、减小 R、改 batch 或换 page size；
- 无法写出新的状态机和正确性/质量不变量；
- 优势只能通过跨论文数字或不匹配参数证明；
- 必须依赖“严格支配所有现有系统”才能成立；
- 只对本地 artifact bug或缺失 publish path有效；
- strongest baseline 没有可运行实现且无法构造等价 baseline；
- 论文故事最终仍是“少写一点、少读一点”；
- 需要先做大量实验才能说清问题是什么。

## 9. A0 通过条件

只有同时满足以下条件，才申请下一步最小 profiling：

1. 找到一个未被上述工作直接覆盖的结构性 trade-off；
2. 该 trade-off 与 M0–M3 至少一项直接观测有关，但不继承已被推翻的因果解释；
3. 提出一个非组合式核心机制；
4. 至少一个现有架构无法通过局部扩展实现该机制；
5. 可以设计同一数据集、同一更新语义、matched index-quality 下的公平 baseline；
6. 独立反方审稿评分达到：
   - problem significance ≥ 7/10；
   - mechanism novelty ≥ 6/10；
   - system depth ≥ 7/10；
   - evaluation feasibility ≥ 7/10。

任何一项不足均为 Kill，不通过平均分补偿。

## 10. 输出与资源

输出：

```text
codex/share/2026-07-18/
dynamic_ann_architecture_frontier_a0_0718.md
```

时间上限：2–3天只读审计。  
新增磁盘：小于1 GiB，仅论文、源码文本和报告。  
不得启动任何实验、构建或 instrumentation。

报告必须给出：

- primary-source evidence matrix；
- 四个 architecture family；
- 每个所谓结构性限制的证明与反证；
- LSM-VEC专项边界；
- 最多一个 surviving candidate；
- PASS/KILL；
- 若 PASS，仅给出最小 profiling 假设与预算，不执行。

完成后停止。
