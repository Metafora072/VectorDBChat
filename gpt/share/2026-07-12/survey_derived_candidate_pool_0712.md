# Survey-Derived Vector Search Candidate Pool

## 1. 目的与边界

本文重新回到《Survey of Vector Database Management Systems》中提出的开放问题，从以下五类方向出发：

1. similarity function selection；
2. hybrid vector–scalar query；
3. incremental search；
4. multi-vector search；
5. security and privacy。

本文不把 Survey 中的 open problem 直接视为 novelty，也不将候选直接包装成论文 Idea。其目标是按照：

```text
Background
    ↓
Unresolved system problem
    ↓
Motivation
    ↓
Why existing abstractions are insufficient
    ↓
System challenges
    ↓
Minimal Kill gate
```

形成一个新的候选池。

结合 VectorDBChat 此前连续多轮 Kill 的经验，所有候选都必须遵循：

* 先查最新直接 prior art，再讨论机制；
* 先验证真实 workload 是否存在，再设计系统；
* 优先寻找新的系统对象、执行语义或资源矛盾；
* 不以“换一种启发式”“增加一个 score”“改用 io_uring”作为核心贡献；
* 不因问题来自 Survey 就降低 novelty 和系统贡献标准；
* 当前只允许最多两个候选进入优先审计，其余候选冻结。

---

# 2. Candidate A：SetPageANN

## 2.1 Background

传统 ANN 索引通常假设：

```text
one object = one vector
```

但 late-interaction、token-level retrieval 和多模态检索中，一个逻辑对象可能由一组向量表示：

```text
document = {token vector 1, token vector 2, ...}
image = {patch vector 1, patch vector 2, ...}
video = {frame vector 1, frame vector 2, ...}
```

对象级得分可能采用 MaxSim 或其他 set-to-set aggregation：

```text
Score(Q, D) = Σ_i max_j sim(q_i, d_j)
```

现有 multi-vector 方法主要优化：

* 候选生成；
* token pruning；
* centroid probing；
* vector-set graph；
* compression；
* CPU/GPU MaxSim 计算。

ESPN 和 ColBERT-serve 已经证明 multi-vector embeddings 可以驻盘，因此“尚无驻盘 multi-vector system”不是有效 novelty claim。

## 2.2 Problem

一个 multi-vector object 经常横跨多个 SSD page。对象进入 refinement 阶段后，系统通常需要读取它的大量甚至全部 token embeddings，才能计算精确对象得分。

这带来一种传统 single-vector ANN 中不存在的 I/O 决策：

> 系统不是决定“是否读取某个向量”，而是决定“一个逻辑对象的哪些 token pages 还值得继续读取”。

现有方案通常以对象或 tensor 为读写单位。即使数据驻盘，也没有充分回答：

* 是否必须读完对象的全部 token pages；
* 哪些 token page 最可能改变对象最终得分；
* 读到一部分 token 后，是否可以安全终止 refinement；
* 如何在多个候选对象之间调度 token-page reads；
* 对象长度不均匀时，如何避免长对象垄断 I/O；
* synopsis、compressed tokens 和 full tokens 应如何分层布局。

## 2.3 Motivation

假设一个查询有 1,000 个候选对象，每个对象占用 1–5 个页面。即使候选生成完全在内存中完成，refinement 也可能触发数千次随机页面访问。

传统优化通常只能：

```text
减少候选对象数量
或
压缩每个对象
```

但存在第三种可能：

```text
候选对象不变，
只读取每个对象中真正影响最终 MaxSim 的页面。
```

这要求存储引擎把对象得分视为一个可渐进求值的函数，而不是一次性 materialization。

## 2.4 Core Hypothesis

构建两级对象表示：

```text
Object synopsis
    +
Token-page groups
```

synopsis 可能包含：

* token cluster centroids；
* 每组 token 的 similarity upper bound；
* query token 可覆盖范围；
* compressed local representatives；
* token group norm/radius；
* MaxSim contribution bounds。

查询过程为：

```text
1. 使用已有方法生成候选对象；
2. 根据 synopsis 计算对象得分上下界；
3. 选择最可能改变 top-k 边界的对象和 token page；
4. 读取页面并更新对象得分区间；
5. 当对象上界低于当前 top-k 下界时停止读取；
6. 当 top-k 排名被证明稳定时结束 refinement。
```

这不是一个新的候选生成 ANN，而是一个：

> page-granular progressive multi-vector evaluation engine。

## 2.5 Potential System Contributions

候选贡献需要至少形成以下三者中的两个：

### A. 可证明的渐进求值

建立 token-group synopsis，使得：

* 未读取页面有安全的贡献上界；
* 已读取页面给出得分下界；
* 系统可以在不读完整对象时安全淘汰候选。

若只能使用经验 score 猜测哪些页面重要，则容易退化为 learned/heuristic prefetch。

### B. I/O-aware cross-object scheduler

调度单位不是单一 object，而是：

```text
(object, token-page group)
```

调度器根据：

* top-k 边界；
* score uncertainty；
* page cost；
* object fairness；
* concurrent query page sharing；

选择下一批读取。

### C. Multi-vector-specific physical layout

页面布局围绕渐进求值而设计，例如：

* 高贡献代表 token 与普通 token 分层；
* query-token coverage-aware grouping；
* shared centroid/residual separation；
* variable-length object packing；
* synopsis 与 token page 的共置或解耦。

## 2.6 Strongest Rejection Arguments

1. ESPN 已实现 multi-vector SSD reranking 和 I/O/compute overlap。
2. ColBERT-serve 已用 mmap 使主体索引驻盘。
3. PLAID/WARP 已通过 pruning 大幅减少参与 MaxSim 的 token。
4. GEM、MV-HNSW 等原生 multi-vector index 可能已经改变候选/refinement 边界。
5. 若普通 document-contiguous layout 已接近最优，则无需新系统。
6. 若 CPU MaxSim 计算主导端到端时间，页面优化价值有限。
7. 若得分上界不够紧，系统最终仍需读取绝大多数页面。
8. 若 synopsis 大到接近 compressed token storage，则只是存储转移。

## 2.7 Relationship to Killed DiskColBERT Direction

SetPageANN 不能复活此前已经 Kill 的 DiskColBERT。

已 Kill 的原始方向是：

```text
为 ColBERT 构建一个 SSD 驻盘引擎，
替代 mmap 并优化候选对象读取。
```

SetPageANN 只有在以下条件成立时才是不同问题：

```text
即使采用最强现有 candidate generation、
compression 和 document-contiguous storage，

对象内部仍存在显著的、
可通过渐进 page evaluation 回收的 I/O。
```

因此，不能把：

* custom async I/O；
* prefetch；
* mmap replacement；
* object packing；

单独作为贡献。

## 2.8 Minimal Kill Gate

第一阶段只做 trace/oracle，不实现系统。

### Datasets

至少包含：

* MS MARCO 或等价 ColBERT workload；
* 一个 BEIR 数据集；
* 对象长度分布明显不同的数据集。

### Baselines

* 当前 PLAID/WARP candidate and token pruning；
* document-contiguous layout；
* compressed tensor mmap；
* object-level full refinement；
* strongest available ESPN/ColBERT-serve-equivalent execution model。

### Measurements

对每个候选对象记录：

* token 数量；
* 实际读取页面；
* 各 token 对 MaxSim 的贡献；
* 读取前缀长度与最终 score 的关系；
* top-k 边界稳定时间；
* CPU refinement 时间；
* unique page reads；
* p50/p99 latency；
* cold/warm cache；
* concurrency 1/8/32。

### Oracle

允许 oracle 预知每个 token 对最终得分的实际贡献，计算：

```text
在保持完全相同最终 top-k 的条件下，
最少需要读取多少 token pages。
```

### Kill Conditions

满足任意一项即 Kill：

1. page oracle 相对 document-contiguous full refinement 的 I/O 收益不显著；
2. oracle 收益主要来自进一步 token pruning，而不是 page-level evaluation；
3. 普通“代表 token 优先 + 连续读取”已接近 oracle；
4. synopsis metadata 接近或超过节省的 page bytes；
5. CPU MaxSim 明显主导，减少页面不能改善端到端性能；
6. 收益只存在于一个数据集或高度 aligned query；
7. 现有 ESPN、ColBERT-serve 或最新工作已经实现等价 progressive page refinement。

## 2.9 Current Status

```text
Status: PRIOR-ART / REQUIREMENT AUDIT
Priority: 1
Implementation: NOT APPROVED
Experiment: NOT APPROVED
```

---

# 3. Candidate B：SnapCursor

## 3.1 Background

Survey 提出的 incremental search 是指：

```text
第一次返回 top-20
第二次继续返回 21–40
第三次继续返回 41–60
```

而不是每次重新执行一个更大的 top-k 查询。

对静态 ANN 图，可以保存：

* candidate heap；
* expanded set；
* visited set；
* current frontier；

并在下一次请求时继续图遍历。

已有生产系统已经展示过 paginated ANN，因此：

> “ANN 不支持分页”不是有效的问题声明。

真正尚需审查的是动态索引上的版本语义。

## 3.2 Problem

考虑：

```text
t1：查询 q 开始，返回 page 1
t2：插入新对象 x
t3：删除 page 1 中的对象 y
t4：图拓扑被更新
t5：用户请求 page 2
```

系统需要决定：

* page 2 是否可以返回 x；
* y 是否仍参与游标的剩余排序；
* 已保存 frontier 引用的旧邻接表是否仍可使用；
* visited set 对新图是否有效；
* 如何避免 page 1 与 page 2 重复；
* 更新后的节点 ID/location 是否仍然可恢复；
* cursor 是否看到固定 snapshot，还是每页看到最新版本。

简单保存 candidate heap 无法解决这些语义。

## 3.3 Motivation

该问题不仅对应搜索翻页，也对应：

* RAG 在证据不足时逐步请求更多文档；
* Agent 按预算扩大 memory retrieval；
* interactive retrieval；
* streaming search；
* progressive top-k；
* fixed-latency anytime retrieval。

如果每次从头执行 top-40、top-60：

* 重复读取相同 SSD pages；
* 重复计算相同距离；
* 重复遍历相同图区域；
* 结果可能因索引更新而抖动；
* 客户端难以判断重复和遗漏。

## 3.4 Core Hypothesis

设计 versioned ANN cursor：

```text
Cursor =
    query identity
  + visibility epoch
  + compact search frontier
  + result boundary
  + visited summary
  + topology recovery metadata
```

系统提供两种显式模式：

### Snapshot Cursor

所有分页结果属于查询开始时的逻辑版本：

```text
page 1, page 2, ... page n
```

均观察同一 corpus/index snapshot。

### Fresh Cursor

允许后续页面观察新数据，但必须定义：

* 是否允许新对象插入已有排名区间；
* 如何去重；
* 如何避免排名回退；
* 是否只保证“未返回结果中的近似 top-k”。

## 3.5 Potential System Architecture

### A. Epoch-versioned topology

图记录或邻接表携带 epoch。更新采用：

* append-only adjacency delta；
* copy-on-write graph records；
* bounded old-version retention；
* tombstone visibility interval。

cursor 固定一个 read epoch。

### B. Compact continuation state

完整 visited set 可能很大，需要：

* exact hot frontier；
* compressed visited summary；
* range/segment bitmap；
* Bloom/cuckoo summary 加 selective replay；
* server-side state + compact client token；
* cursor checkpoint compaction。

### C. Bounded topology replay

若 cursor 引用的旧 graph page 已被回收：

```text
current graph
    +
bounded update log
    →
reconstruct necessary old adjacency
```

系统不保存完整历史索引，而只保留活跃 cursor 所需的最小版本窗口。

### D. Cursor-aware garbage collection

GC 需要同时考虑：

* 最老 active cursor epoch；
* cursor timeout；
* old adjacency bytes；
* update log size；
* reconstruction cost；
* forced cursor invalidation。

## 3.6 System Contribution Boundary

SnapCursor 不能只贡献：

* 序列化 candidate heap；
* 保存 visited nodes；
* continuation token；
* 普通 MVCC；
* 对每个查询复制图；
* “旧版本文件不删除”。

论文贡献必须回答：

> 如何在动态 ANN 图上，以有界状态和有界版本保留，继续近似搜索，并给出明确的跨页可见性、重复和遗漏语义。

## 3.7 Main Challenges

### Challenge 1：近似分页语义

精确数据库分页可以定义稳定排序，但 ANN 本身没有完整扫描全部对象。

需要定义：

* page-level recall；
* cumulative recall；
* no-duplicate property；
* snapshot consistency；
* approximate no-omission 的具体边界。

### Challenge 2：Visited Set Compression

visited set 可能包含数千到数万个节点。

过度压缩可能导致：

* 重复 expansion；
* 错误判断已访问；
* recall 损失；
* replay I/O。

### Challenge 3：Topology Mutation

更新后：

* 节点邻居改变；
* 旧路径消失；
* 新路径出现；
* location mapping 改变；
* 节点被合并或 GC。

cursor 必须继续基于旧语义执行，或者安全转入新版本。

### Challenge 4：Version Retention Cost

若大量 cursor 长期存活，旧 graph pages 可能无法回收。

系统需要把：

```text
cursor state cost
old-version storage cost
replay cost
restart cost
```

统一考虑。

## 3.8 Strongest Rejection Arguments

1. 实际用户很少对 ANN 执行深分页。
2. RAG 通常重新查询，而不是保持 cursor。
3. top-40 从头重搜可能足够便宜。
4. Azure/Cosmos DB 等系统可能已有 continuation state。
5. 通用 MVCC + immutable segment 已足以提供 snapshot。
6. cursor 状态可以简单保存在服务器内存中。
7. 更新期间返回 slightly inconsistent results 对 ANN 应用可接受。
8. 活跃 cursor 数量少，旧版本 retention 不是问题。
9. 若需要严格 snapshot，不如直接固定旧 index segment。

## 3.9 Minimal Kill Gate

第一阶段只验证需求和成本，不设计新协议。

### Workloads

至少覆盖：

* interactive top-k expansion；
* RAG progressive retrieval；
* search pagination；
* Agent memory expansion。

若无法找到真实或公开 trace，需要明确说明，只能使用代表性 workload，不得声称普遍需求。

### Systems

至少考察：

* 静态 DiskANN-style graph；
* 一个动态 graph index；
* 一个 segment/LSM-style vector index。

### Experiments

比较：

```text
A. 一次 top-40
B. 两次独立 top-20/top-40
C. 保存 search state 后连续两个 top-20
```

测量：

* repeated node expansions；
* repeated page reads；
* continuation state size；
* visited set size；
* p50/p99 latency；
* cumulative recall；
* duplicate count；
* insert/delete 期间的异常结果；
* 每个 cursor 阻止 GC 的旧版本 bytes；
* cursor lifetime 对 version-retention cost 的影响。

### Strong Baselines

* stateless re-search；
* server-side full cursor state；
* immutable snapshot segment；
* generic MVCC；
* shadow copy / copy-on-write；
* current production continuation token mechanism。

### Kill Conditions

满足任意一项即 Kill：

1. stateful continuation 相对 re-search 节省很小；
2. continuation state 天然只有少量 KB，不需要新压缩机制；
3. immutable segment/MVCC 已以很低成本解决版本语义；
4. 真实 workload 不需要跨更新的一致分页；
5. snapshot retention 成本可忽略；
6. fresh pagination 的宽松语义已经足够；
7. 现有生产或论文系统已实现等价的 dynamic versioned cursor；
8. 最终贡献只剩“把 MVCC 用到 ANN”。

## 3.10 Current Status

```text
Status: PRIOR-ART / REQUIREMENT AUDIT
Priority: 2
Implementation: NOT APPROVED
Experiment: NOT APPROVED
```

---

# 4. Candidate C：SLO-ANN

## 4.1 Background

Hybrid vector–scalar query 已形成大量执行策略：

* pre-filter；
* post-filter；
* inline filter；
* per-label graph；
* partitioned index；
* adaptive candidate expansion；
* exact scan fallback。

现有优化器开始根据：

* selectivity；
* correlation；
* query features；
* history；

选择执行计划。

## 4.2 Problem

传统 optimizer 在等价计划之间选择，选错主要损失性能。

ANN optimizer 选择的计划可能具有不同 recall。用户真正希望表达的是：

```text
Recall@k ≥ target
P99 latency ≤ target
I/O ≤ budget
```

但系统通常只能基于离线模型猜测参数，无法在运行时确认当前 query 是否达到质量目标。

## 4.3 Candidate Idea

建立 progressive recall-SLO execution：

```text
cheap initial plan
    ↓
online quality-risk estimation
    ↓
continue / expand / switch / exact fallback
```

候选贡献必须是运行时质量控制与状态复用，而不是新的 learned router。

## 4.4 Main Risks

* 无 ground truth 时无法在线估 recall；
* validation 成本可能接近 exact search；
* filtered-ANN optimizer 赛道已经拥挤；
* query difficulty prediction 已有大量工作；
* 容易退化成调参系统。

## 4.5 Status

```text
Status: FROZEN
Priority: 3
```

只有 SetPageANN 和 SnapCursor 均被 Kill 后，才考虑展开。

---

# 5. Candidate D：BridgeIndex

## 5.1 Background

Embedding model 升级会使：

```text
old corpus vectors ∈ E_old
new queries/vectors ∈ E_new
```

现有方案包括：

* 全量重编码和重建；
* 双索引；
* query adapter；
* shadow build；
* background migration。

此前 VectorDBChat 已验证旧 Vamana topology 对同家族模型升级具有很强鲁棒性，因而简单 topology repair 已被 Kill。

## 5.2 Problem

仍可能存在一个更宽的 lifecycle 问题：

```text
部分对象只有旧向量
部分对象已有新向量
新写入对象只有新向量
```

如何在迁移窗口中控制：

* query quality；
* 双份存储；
* build cost；
* migration scheduling；
* cross-space candidate coverage。

## 5.3 Main Risk

* 容易成为普通 shadow migration；
* Drift-Adapter 等工作直接攻击 novelty；
* 需要真实 paired embeddings；
* 可能只是工程运维框架；
* topology reuse 已被实验证明并非明显问题。

## 5.4 Status

```text
Status: FROZEN
Priority: 4
```

---

# 6. Candidate E：MetricOverlay

## 6.1 Background

一个 corpus 可能需要多个 similarity metric：

* cosine；
* inner product；
* L2；
* weighted composite metric。

每个 metric 建一个完整索引会造成存储和更新放大。

## 6.2 Candidate Idea

设计：

```text
shared backbone graph
    +
metric-specific sparse overlays
```

在总边预算下共同服务多个 metric。

## 6.3 Main Risk

* 多 metric 邻域可能重合很低；
* 已有 multi-metric ANN 可能直接覆盖；
* 更像图算法和 edge-selection objective；
* SSD 系统贡献不明确；
* overlay 最终可能退化成多个完整索引。

## 6.4 Status

```text
Status: FROZEN
Priority: 5
```

---

# 7. Candidate F：QuarantineANN

## 7.1 Background

向量投毒可以利用 embedding geometry，使少量恶意向量成为大量查询的高频近邻或 graph hub。

动态向量数据库通常默认：

```text
new vector = ordinary trusted record
```

但一个向量的插入可能影响：

* 大量查询结果；
* 反向邻居；
* 图结构；
* 导航路径；
* 多租户数据安全。

## 7.2 Candidate Idea

两阶段接纳：

```text
new vectors
    ↓
quarantine index
    ↓
retrieval influence evaluation
    ↓
main index admission
```

新向量在进入主图前，评估：

* retrieval coverage；
* reverse-neighbor pressure；
* local density；
* hubness；
* sampled-query influence。

## 7.3 Main Risk

* 正常热门对象也可能是 hub；
* influence score 天然依赖 workload；
* 阈值容易缺乏依据；
* 攻击者可缓慢分散插入；
* 更偏安全算法，系统机制不够；
* 可能被普通 anomaly detection 攻击。

## 7.4 Status

```text
Status: FROZEN
Priority: 6
```

---

# 8. Unified Priority Decision

当前只允许以下两个候选进入独立审计：

```text
Priority 1: SetPageANN
Priority 2: SnapCursor
```

原因：

## SetPageANN

它可能引入一个传统 single-vector ANN 不存在的新系统对象：

```text
a progressively evaluable vector set spanning multiple pages
```

若成立，可形成：

* 新页面布局；
* 新渐进执行模型；
* 新 I/O 调度单位；
* multi-vector-specific storage abstraction。

但必须首先证明它不是已经 Kill 的 DiskColBERT 换名。

## SnapCursor

它可能引入一个传统 ANN serving 中尚未充分定义的新系统语义：

```text
versioned continuation of approximate graph traversal
```

若成立，可形成：

* ANN cursor semantics；
* bounded version retention；
* compact state；
* update-aware traversal continuation；
* cursor-aware GC。

但必须首先证明普通 MVCC、immutable segment 和 server-side state 不足。

---

# 9. Required Codex Audit

Codex 下一步只做文献和需求审计，不运行实验。

每个候选分别提交：

```text
codex/share/setpageann_prior_art_requirement_audit_0712.md
codex/share/snapcursor_prior_art_requirement_audit_0712.md
```

每份审计必须包括：

1. 2024–2026 直接竞争工作；
2. 每项最接近工作的实际机制；
3. 当前候选哪些部分已被覆盖；
4. 剩余 delta 是否是新的系统抽象；
5. 最强简单 baseline；
6. 真实 workload 和公开数据是否存在；
7. 当前环境是否可执行；
8. 一周内最小 Kill gate；
9. 最强拒稿意见；
10. 最终裁决：

```text
KILL
REVISE
PROVISIONAL
```

若两个候选都未达到 `PROVISIONAL`：

* 不立即生成 Round 2 机制；
* 不通过更换名称复活；
* 回到 Survey 其他 open problems 或更广泛 vector workload；
* 继续保持先 prior art、后实验、再 architecture 的流程。

若至少一个候选达到 `PROVISIONAL`：

* Gpt 统一审查 gate；
* 只批准 trace/problem validation；
* 在真实问题成立前不设计完整系统；
* 只有 problem gate 通过后才请 Claude 介入 architecture review。
