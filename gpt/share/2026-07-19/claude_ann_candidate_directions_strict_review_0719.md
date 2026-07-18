# Claude Disk-Resident ANN 候选方向严格总评

**日期**：2026-07-19  
**范围**：Claude `/idea-discovery` Phase 2 合并报告中的 10 个 finalist，以及合并阶段淘汰的候选。  
**评审标准**：问题真实性、机制新颖性、系统深度、实验可行性、用户毕业工作匹配度。  
**硬约束**：单机、多 NVMe、无 GPU/分布式依赖；不能依靠参数调优、任意阈值或跨系统不公平比较形成贡献。

---

## 一、总裁决

Claude 的 pipeline 在“扩大搜索面”上有价值，但其 novelty 分数普遍偏高，主要存在三类系统性误判：

1. 将“没有直接使用完全相同标题的论文”视为机制空白；
2. 将 characterization 或 diagnostic 自动视为可独立投稿的系统贡献；
3. 低估 2025–2026 年 KV retrieval、filtered ANN、quantization–graph co-design 等方向的拥挤程度。

最终分档如下。

### 第一档：只允许受限门禁，不允许直接实现

1. **ANN-on-ZNS Feasibility Frontier**  
   已单独裁决：只执行 Z0 trace/model validity gate。

2. **Ambiguity-Monotone Graph**  
   最强非 ZNS 备选。只值得做一次 formal-object / nearest-work 门禁；当前不能启动实验。

3. **PageTxn-ANN**  
   问题真实、系统工作量足，但当前机制仍接近“给图索引加 WAL”。只值得做 graph-specific crash-state uniqueness gate。

### 第二档：可作为其他论文中的实验维度或负结果，不独立立项

4. **Selectivity Is Not Enough**  
   可成为 filtered ANN 论文的 workload dimension，但不再是独立新问题。

5. **AttentionLoop-SSD**  
   可成为 KV retrieval 系统的 evaluation methodology，但不能独立成为当前毕业主线。

6. **Block-Probe Navigability / Summary-Bit Probe Lower Bound**  
   仅适合作为长期理论问题；不符合当前系统型毕业约束。

### 第三档：当前形式直接 Kill

7. **ZoneEpoch-ANN 当前机制**  
   ZNS 方向可保留，但“navigability certificate 决定 zone reset”的机制不闭合；只能等待 Z0 产生真实 ANN-specific design lever。

8. **FreshCert**  
   证书只能排除 pending delta 中更近的新点，无法证明 stale graph 对旧数据的搜索结果正确；实用版本又退化为搜索 delta。

9. **GraphKV**  
   已被 RetrievalAttention、RetroInfer、KVDrive、ParisKV、Tutti 等直接压缩；“把现有索引换成 graph ANN”不足以形成贡献。

---

## 二、统一评分

评分采用 10 分制。`机制新颖性`评当前方案，不评未来可能完全重构后的新方案。

| 排名 | 方向 | 问题意义 | 机制新颖性 | 系统深度 | 可行性 | 毕业匹配 | 裁决 |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Ambiguity-Monotone Graph | 7 | 5 | 7 | 4 | 6 | HOLD：纸面门禁 |
| 2 | PageTxn-ANN | 7 | 4 | 8 | 5 | 6 | HOLD：唯一性门禁 |
| 3 | ANN-on-ZNS Feasibility | 6 | 5 | 3 | 6 | 5 | Z0 only |
| 4 | ZoneEpoch-ANN | 7 | 3 | 8 | 2 | 5 | 当前机制 Kill，等待 Z0 |
| 5 | Selectivity Is Not Enough | 7 | 3 | 3 | 7 | 4 | 不独立立项 |
| 6 | AttentionLoop-SSD | 7 | 3 | 3 | 2 | 2 | 仅作评测维度 |
| 7 | FreshCert | 6 | 3 | 4 | 4 | 3 | Kill |
| 8 | Block-Probe Navigability | 6 | 4 | 7（理论） | 2 | 2 | Kill 主线 |
| 9 | Summary-Bit/Probe LB | 6 | 4 | 7（理论） | 2 | 2 | Kill 主线 |
| 10 | GraphKV | 9 | 1 | 6 | 2 | 2 | Kill |

这里没有任何方向达到“直接实现”门槛。

---

# 三、逐项评审

## 1. ZoneEpoch-ANN

### Claude 的核心主张

将稳定导航核心与 append-only adjacency versions 分离，通过“navigability certificate”决定何时可以 reset zone，从而降低 ZNS GC 写放大。

### 正面价值

- ZNS 与动态 graph ANN 的接口冲突是真实问题；
- 若能找到 graph semantics 与 zone lifecycle 之间独有的状态机，系统深度可能足够；
- 用户已有动态 ANN 写入生命周期数据，可作为问题发现起点。

### 致命问题

#### 1. certificate 与 zone reset 的安全性不是同一问题

reset 一个 zone 的直接正确性条件是：

```text
zone 中不存在仍被当前逻辑版本引用的数据
```

只要将所有 live records 迁移并原子更新映射，图 navigability 并不决定 zone 是否可 reset。反过来，即使某些旧边对当前查询“不重要”，也不能仅凭近似查询质量证书直接删除其唯一持久版本。

因此当前设计把两个问题混在一起：

- storage liveness / version reachability；
- graph quality / navigability。

#### 2. 已有机制容易覆盖其技术组件

如果设计最终变成：

```text
append adjacency versions
维护 logical-to-physical map
迁移 live records
reset victim zone
```

它本质上是普通 log-structured / ZNS object store 上承载 graph records。ANN-specific novelty必须来自新的 zone placement、version grouping 或 reclaim invariant，而不是“图也能放到 ZNS”。

#### 3. 依赖尚未成立的前置结论

Claude 直接预测 `3–5×` GC WA reduction 和 `≥1.5×` throughput，但目前：

- 没有 host-managed reclaim模型；
- 没有稳态多轮 GC；
- 没有 read locality成本；
- 没有真实 ZNS hardware；
- 没有能够计算的 navigability certificate。

### 裁决

```text
当前 ZoneEpoch mechanism：KILL
ZNS broader direction：HOLD，完全依赖 Z0
```

只有 Z0 证明存在 generic overwrite trace无法复现的 ANN-specific zone invalidity结构，并找到超出普通 hot/cold separation 的 design lever，才重新定义系统。

---

## 2. ANN-on-ZNS Feasibility Frontier

已在独立 Z0 门禁中详细裁决。

### 核心评价

问题可研究，但当前贡献只是：

```text
两套实现 × 一个数据集 × write-only trace × host-GC simulation
```

这不足以自动成为 FAST/EuroSys 论文。

当前计划中的 `ρ`、Gini、`WA=3` 和线性 `ρ*` 均不是可靠的 GC feasibility模型。尤其是：

- 相同 `ρ/Gini` 可以有完全不同的 temporal locality 与 HostWA；
- finite batch 的重复页比例不等于 steady-state GC phase transition；
- host relocation WA 与 device-level WA必须分开；
- 256 次模拟不会自动弥补模型假设错误。

### 裁决

```text
Z0 only
```

通过 Z0 后才能讨论 Z1；失败则整个 ZNS-ANN方向关闭。

---

## 3. Block-Probe Navigability

### Claude 的核心主张

为 navigable graph ANN 建立 SSD block-probe / I/O lower bound。

### 现有边界

PODS 2020 的 *On the I/O Complexity of the k-Nearest Neighbors Problem* 已经给出静态 external-memory k-NN 的 block-read lower bounds，包括高维 Hamming 和部分近似设置。

因此“首次 ANN I/O lower bound”已经不成立。剩余空间只能是：

```text
对受限 graph-navigation algorithm family 的 probe lower bound
```

### 研究风险

- 需要先精确定义 algorithm class、memory summary、adaptive probes、graph construction与approximation guarantee；
- 若模型过强，下界通常是已有 k-NN lower bound 的直接推论；
- 若模型过窄，只能得到针对某个搜索实现的技术性结论；
- 很可能需要高强度 cell-probe / communication-complexity理论能力；
- 即使成功，也难形成用户要求的完整存储系统毕业工作。

### 裁决

```text
KILL 当前主线
```

可作为长期理论合作题，不值得投入当前实验服务器和毕业周期。

---

## 4. Summary-Bit / Probe Lower Bound

### Claude 的核心主张

给定每个节点或全局 `b` bit 内存摘要，证明查询至少需要多少次 SSD probes，由此刻画“quantization quality何时足够”。

### 正面价值

它比纯 block lower bound 更接近 DiskANN 的 PQ-in-memory / full-vector-on-SSD 架构。

### 致命问题

- 需要定义 summary 是 per-vector、global、randomized 还是 data-dependent；
- PQ code 本身包含距离近似信息，允许 adaptive graph traversal，模型极难封闭；
- 很容易退化为一般 cell-probe / information-theoretic ANN lower bound；
- 即使证明某个 worst-case下界，也未必解释真实数据上的 read count；
- 没有可实现的系统机制，难满足系统论文工作量与评测要求。

### 裁决

```text
KILL 当前主线
```

理论价值可能存在，但不符合用户当前毕业目标。

---

## 5. FreshCert

### Claude 的核心主张

在 stale base graph 和 pending update delta 并存时，使用 stale query 的 kth-distance margin与delta的量化距离下界，证明该查询无需 graph repair即可继续返回正确 top-k。

### 根本逻辑缺口

该证书最多证明：

```text
pending inserted vectors中，没有点比当前第k名更近
```

它无法证明：

1. stale graph search 已经找到 base dataset 的真实 top-k；
2. 新边不会改变到旧点的搜索路径；
3. 删除没有使当前结果失效；
4. PQ envelope 是严格、可组合的保守下界。

所以它不是“top-k correctness certificate”，只能是：

```text
conditional delta non-interference certificate
```

前提是 base result本来就是正确的。

### 实用性困境

为了证明 delta 中不存在更近点，需要计算：

```text
min_{x in delta} lower_bound_distance(q, x)
```

若逐点扫描 delta，成本随delta增长；若为delta构建 ANN/quantized index，系统已经在查询delta，这正是 FreshDiskANN 的基本思路。

因此证书要么：

- 和直接搜索delta成本接近；
- 要么使用松下界，coverage很低；
- 要么依赖强假设，只能形成理论小题。

INSQ 等 safe-region 工作也已经覆盖“当前近邻在更新/移动下何时保持有效”的一般范式。FreshDiskANN 与 IP-DiskANN则已经直接解决实时更新可见性。

### 裁决

```text
KILL
```

它不应与 ZNS 或动态写优化再次组合。

---

## 6. Ambiguity-Monotone Graph

### Claude 的核心主张

构造图，使量化距离不确定区间沿搜索路径单调收缩；只有区间与当前 top-k boundary重叠时才读取SSD全精度向量。

### 为什么它仍值得保留

这是 10 个方向中，除新介质问题外最接近独立算法机制的候选：

- 目标不是普通 page layout；
- 直接连接 quantization error、graph topology 与 SSD exact-read decision；
- 若能建立严格的 uncertainty invariant，可能形成新的 pruning / graph-construction规则；
- 可在单机 DiskANN 基线上完成。

### 强 prior pressure

近邻工作已经覆盖大量空间：

- **SymphonyQG**：联合 graph 与 quantization，并调整graph以适配量化批处理；
- **QuIVer**：直接在2-bit量化度量中完成edge selection、pruning与navigation；
- **δ-EMG / δ-EMQG**：monotonic graph、量化搜索与近似保证；
- DiskANN系工作已经使用内存压缩表示指导候选探索。

因此不能把贡献写成：

```text
首次联合quantization与graph
首次monotonic quantized graph
```

### 最难的技术问题

#### 1. “区间沿路径收缩”未必可构造

量化误差是 query-dependent。一个节点对查询 `q1` 的区间很窄，对 `q2` 可能很宽。离线构图很难同时保证任意查询上的单调性。

#### 2. exact-read语义需要先核对

必须精确说明基线在什么时候读取：

- adjacency page；
- compressed code；
- full vector；
- final reranking candidate。

如果一次读取邻接记录时已经获得full vector，那么“跳过exact read”可能同时意味着跳过扩展该节点，直接影响navigability，而不是单独省一次rerank I/O。

#### 3. 容易退化成启发式评分

若最终机制只是：

```text
prune_score = distance + lambda * uncertainty
```

或同页/低误差tie-breaking，它只是参数启发式，无法通过 novelty gate。

### 保留条件

只允许一次纸面门禁，必须证明至少一个对象：

1. 可构造的 query-independent uncertainty dominance关系；
2. 对固定quantizer的安全SSD-read skipping条件；
3. 不读取full vector时仍保持的search invariant；
4. 与δ-EMQG、QuIVer和SymphonyQG不等价的正式目标；
5. 可证伪预测：matched recall与graph bytes下显著减少full-vector page reads。

### 裁决

```text
HOLD：最强非ZNS备选
不启动实验，先做formal/nearest-work gate
```

如果无法写出query-independent invariant，立即Kill。

---

## 7. GraphKV

### Claude 的核心主张

在SSD上为KV cache建立graph ANN，以每个decode step检索约1%重要tokens。

### 已被直接压缩

近期工作已经形成完整技术链：

- **RetrievalAttention**：用ANNS检索注意力相关KV，并处理query/key OOD；
- **RetroInfer**：把KV cache重构为vector storage，设计wave index；
- **KVDrive**：GPU–DRAM–SSD多层KV管理；
- **ParisKV**：drift-robust top-k KV retrieval；
- **Tutti**：SSD-backed KV cache I/O系统；
- **Louver**：将稀疏attention建模为range search，并提供critical-key zero-false-negative保证。

因此“将KV存到SSD并使用向量索引选择性读取”已经不是空白。

把现有centroid、collision或wave index替换为Vamana，只能算组件替换。还需要GPU、LLM serving stack与长上下文质量评测，偏离当前无GPU依赖约束。

### 裁决

```text
KILL
```

只有发现现有KV retrieval index存在一个graph特有、可独立证明的新问题时，才能重新提出；不能以“graph通常更快”立项。

---

## 8. PageTxn-ANN

### Claude 的核心主张

为一次涉及vector page、target adjacency和多个neighbor adjacency的更新提供multi-page crash atomicity，并保证恢复后graph navigability。

### 为什么问题真实

动态graph ANN的一次逻辑update可能跨许多非连续records。崩溃可能留下：

- vector存在但target adjacency缺失；
- target已连接但reverse edges部分完成；
- 删除标记与replacement edges不同步；
- metadata/publish状态与数据页不一致。

这确实比单record update复杂。

### 为什么当前 novelty 仍低

标准 WAL / redo logging 已能表达：

```text
operation intent
pageLSN / operation ID
redo idempotence
commit marker
recovery replay
```

“一个事务修改很多页”不是graph ANN独有，数据库、文件系统和LSM compaction都长期处理该问题。

真正可能的新贡献必须是：

> 即使所有数据结构在字节层面可恢复，哪些部分提交状态仍会使近似图的搜索质量或navigability发生静默退化；如何以比完整原子事务更低成本维持一个query-safe intermediate state。

### 值得做的唯一性门禁

在实现前必须证明：

1. generic WAL / copy-on-write / shadow paging不能以可接受成本直接解决；
2. 存在字节一致但query semantics不安全的partial update state；
3. 可以定义一个比“全部页原子提交”更弱、但足以保证搜索安全的不变量；
4. 新协议利用图结构降低log/write/barrier成本；
5. failure model包含torn record、write reorder、volatile cache和重复redo，而非只有`kill -9`；
6. 与生产vector DB已有WAL/recovery机制有明确区别。

### 风险

- 容易最终变成普通redo log工程；
- 要做可信fault injection与持久化barrier验证，工作量高；
- “navigability”本身难在crash后快速验证；
- 若直接全事务化，性能结论缺少ANN-specific novelty。

### 裁决

```text
HOLD：第二备选
只批准graph-specific crash-state uniqueness gate
```

如果找不到比generic WAL更弱且有效的query-safe invariant，直接Kill。

---

## 9. Selectivity Is Not Enough

### Claude 的核心主张

构造相同selectivity、但label fragmentation与churn不同的filtered ANN workloads，使最优query plan相反，证明selectivity-only planner失效。

### 已有工作直接逼近

2026年的 *Filtered Approximate Nearest Neighbor Search in Vector Databases: System Design and Performance Analysis* 已经：

- 分析vector DB中的filtered execution；
- 提出Global-Local Selectivity（GLS）度量；
- 展示pgvector cost-based optimizer会选择次优plan；
- 说明原始selectivity不能完整预测执行效果。

**Curator** 也明确把低selectivity时qualifying vectors在graph中的fragmentation / connectivity breakdown作为核心问题。

GateANN、PipeANN-Filter和大量FANNS工作进一步覆盖filter与SSD I/O的执行选择。

因此 Claude 的核心结论“selectivity不够”已被直接占据。

### 剩余的 churn 角度

动态churn是否导致：

```text
相同GLS/selectivity下，fragmentation随时间变化并引起plan drift
```

可能仍可研究，但它更像：

- benchmark extension；
- optimizer feature engineering；
- filtered ANN系统的一组实验。

缺少新的执行机制或优化器状态机时，不能形成独立系统论文。

### 裁决

```text
不独立立项
```

可作为未来filtered ANN工作中的workload dimension。

---

## 10. AttentionLoop-SSD

### Claude 的核心主张

比较fixed-trace retrieval与closed-loop autoregressive generation，判断SSD KV retrieval错误是否随生成累积。

### 问题真实性

问题真实：错误检索可能改变当前token，进而改变之后的query向量和注意力分布。近期工作已经关注：

- distribution drift；
- long-generation quality；
- critical KV miss造成的sharp error；
- zero-false-negative retrieval。

ParisKV专门强调drift robustness；Louver指出遗漏一个critical key可能造成明显错误，尤其在长推理任务中。

### 为什么不足以独立立项

- “closed-loop评测优于fixed trace”属于evaluation methodology；
- 没有新的index、scheduler或correctness机制；
- 需要完整LLM serving、GPU和长上下文benchmark；
- 若发现误差不累积，论文贡献更弱；
- 若发现累积，最自然的下一步是提高retrieval recall或提供critical-key guarantee，已被现有工作直接研究。

### 裁决

```text
KILL 独立方向
```

可作为任何KV retrieval论文必须包含的评测维度，但不应单独作为当前毕业工作。

---

# 四、合并阶段已淘汰候选

## Write-Deferred

与 FreshDiskANN delta、lazy/batch update、LSM-VEC和此前已关闭的amortized maintenance高度重叠。保持KILL。

## I/O Attribution

M0–M3已经证明其characterization价值，但没有机制时不足以独立投稿。保持归档，不立项。

## Deadline-Wave

依赖GraphKV / SSD KV serving主系统，且deadline-aware prefetch与I/O scheduling已是拥挤系统组件。随着GraphKV被Kill，该方向一并关闭。

## Maintenance-Bandwidth Lower Bound

理论对象过宽，容易与FreshCert、动态索引amortization和external-memory lower bound重叠；缺乏可实现系统。保持KILL。

## CrashANN

已合并到PageTxn-ANN，不重复立项。

---

# 五、推荐执行顺序

当前不能并行开启多个候选。

## 1. 继续执行已批准的 ZNS Z0

Z0只验证问题与模型，不承诺后续系统。

## 2. Z0完成前，不启动其他实验

纸面上仅保留两个备选：

### Backup A：Ambiguity-Monotone Graph

通过条件：找到query-independent uncertainty invariant或安全read-skipping条件，并明确超出SymphonyQG、QuIVer、δ-EMQG。

### Backup B：PageTxn-ANN

通过条件：找到generic WAL无法低成本提供的graph-specific query-safe intermediate invariant。

## 3. 其余候选正式关闭

不得再将FreshCert、GraphKV、Selectivity diagnostic、AttentionLoop或两类lower bound与ZNS方向拼装成“大系统”。

---

# 六、最终结论

Claude 的 10 个 finalist 中：

```text
直接实现：0
受限实验门禁：1（ZNS Z0）
纸面备选门禁：2（Ambiguity-Monotone、PageTxn）
仅作子实验/长期理论：4
直接Kill：其余
```

从毕业工作的角度，最重要的不是保留更多候选，而是防止再次进入“每个方向先做数周实验，最后因机制不新而关闭”的循环。

当前最合理的策略是：

1. 用极小成本完成 Z0；
2. Z0若PASS，再判断能否形成ANN-specific ZNS状态机；
3. Z0若KILL，只在Ambiguity-Monotone与PageTxn中选择一个做纸面唯一性门禁；
4. 两者都失败后，应离开当前DiskANN内部构图/更新语义，而不是继续枚举新名字。
