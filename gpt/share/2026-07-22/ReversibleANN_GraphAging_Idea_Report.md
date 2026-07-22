# ReversibleANN / GraphAging：动态驻盘图索引的历史老化、更新可逆性与半耦合存储

**日期：** 2026-07-22  
**当前状态：** `GO A0`，仅批准现象验证，不批准直接实现完整系统  
**目标领域：** 向量数据库、动态 ANNS、SSD 驻盘图索引  
**潜在投稿方向：** FAST / EuroSys / USENIX ATC / SIGMOD / PVLDB / ICDE  
**硬件约束：** 单机 CPU、大内存、普通多 NVMe SSD；不依赖 GPU、ZNS 或分布式集群

---

## 0. 执行摘要

现有驻盘图索引通常同时绑定了四个对象：

1. 向量数据对象；
2. 图导航节点；
3. 磁盘记录或磁盘页；
4. 更新与剪枝单元。

这种绑定带来两个长期存在、但通常被分别处理的问题：

- **动态图更新具有历史不可逆性。**  
  新节点插入会触发邻居剪枝，被淘汰的旧边及其淘汰原因通常不会被保留。之后删除该新节点时，系统无法恢复原有导航结构，只能重新发现候选并再次修复。即使最终活跃向量集合恢复原状，图结构、查询路径和 I/O 成本也可能无法恢复。

- **耦合式存储产生冗余 I/O。**  
  邻接表只改变少量边时，系统仍可能读取和重写包含完整向量的节点记录或磁盘页。完全解耦虽然降低更新写放大，却可能使查询额外读取拓扑与向量，损失局部性。

本报告提出一个待验证的研究方向：

> **ReversibleANN：通过保留 ANN 剪枝决策的反向依赖，并使用“不可变读优化基础记录 + 追加式拓扑增量”，同时降低图老化和耦合更新 I/O。**

核心机制包括：

- 不可变或低频重写的 `BaseRecord`；
- 小粒度追加式 `EdgeDelta`；
- 记录“哪条新边淘汰了哪条旧边”的 `Shadow Edge / Edge-Displacement Dependency`；
- 删除节点时，将历史被淘汰边重新加入局部候选集并进行条件恢复；
- 使用明确的成本平衡决定何时将 delta 合并为新基座。

该 idea 的生死线并不在于设计是否看起来合理，而在于以下现象是否真实存在：

> **相同最终向量集合经过不同更新历史后，驻盘图索引是否会产生超过构建随机性的持续查询退化；保存被剪枝候选是否能以低成本显著恢复导航结构。**

因此，当前只建议建立 `GraphAging` A0 探索项目，先验证问题，不应直接进入完整系统开发。

---

## 1. 背景与问题来源

### 1.1 驻盘图索引仍然高度依赖磁盘页

DiskANN、Starling、PipeANN、PageANN 等系统将图节点或节点集合布局到 SSD 上，并围绕磁盘页访问优化搜索。

磁盘页带来的优势包括：

- 合并多个节点访问；
- 降低 I/O 命令数；
- 利用 SSD 顺序与并行能力；
- 将查询路径映射成可管理的块访问。

但它也会带来以下问题：

1. 查询实际只使用页内少数节点或少数边，剩余字节形成无效读取；
2. 页成为更新边界，修改少量拓扑信息也可能导致整页处理；
3. 动态插入后，新节点难以持续保持原有页面局部性；
4. 节点记录扩张会引起 relocation、碎片化或间接寻址；
5. 页面布局往往针对某个静态图优化，更新后查询访问模式逐渐偏离布局假设。

2026 年对驻盘图 ANN 的统一实验研究报告称，现有布局的有效 I/O 利用率通常很低，并指出页面大小、维度、布局和更新方式之间存在明显权衡。这说明“页对齐”仍是重要优化方向，但当前页级抽象并没有消除有效数据利用率和动态维护问题。[1]

本方向不主张普通 NVMe 上的物理 I/O可以真正脱离块粒度，而是挑战：

> **为什么磁盘页必须同时成为逻辑节点、版本边界和拓扑更新边界？**

---

### 1.2 动态图的导航性可能随更新历史变化

动态图 ANN 已经出现多种解决方案：

- IP-DiskANN 逐条原地处理插入和删除，目标是长时间更新后的稳定 recall；[2]
- OdinANN 使用直接插入降低批量 merge 对前台查询的干扰；[3]
- 随机游走删除方法尝试保持删除前后的 hitting-time 统计；[4]
- navigability-signal repair 根据导航退化信号触发局部修复，重点保护 tail recall。[5]

这些工作证明动态图维护是一个真实问题，但它们主要评价：

- 连续更新期间 recall 是否稳定；
- 更新吞吐和查询吞吐；
- 删除或修复的成本；
- 何时触发 repair。

本报告希望验证一个更强的问题：

> **最终活跃数据完全相同时，索引性能是否仍依赖到达该状态的更新历史？**

给定两个更新序列 \(\sigma_1,\sigma_2\)，如果：

\[
V_{\sigma_1}=V_{\sigma_2},
\]

是否仍可能有：

\[
G_{\sigma_1}\neq G_{\sigma_2},
\]

并进一步导致：

\[
C(q,G_{\sigma_1})\neq C(q,G_{\sigma_2})?
\]

其中 \(C\) 可以表示：

- Recall@k；
- p1 / p50 / p99 query recall；
- distance computations；
- visited nodes；
- SSD page reads；
- 查询路径长度；
- p95 / p99 latency。

这类差异可称为：

> **History-Induced Graph Aging：历史诱发的图老化。**

---

### 1.3 耦合式节点记录产生更新读写放大

传统耦合式驻盘图常将以下信息共同存放：

```text
NodeRecord =
    full vector
  + adjacency list
  + metadata
  + alignment / padding
```

更新只改变几十字节的邻接信息，却可能读取和重写包含完整向量的记录或页面。

DGAI 已经明确指出耦合存储会在图更新时造成冗余向量读写，并通过拓扑与向量解耦降低插入和删除成本；与此同时，它必须为查询设计额外的分阶段过滤和增量页面重排，以弥补解耦带来的查询损失。[6]

DecoupleVS 同样从存储空间、查询读取和更新写放大角度分析向量数据与索引元数据共置的问题，并提出解耦存储框架。[7]

因此，本工作不能再次把“拓扑与向量解耦”当成新贡献。真正的研究空间在于：

> **能否保留 coupled layout 的常规查询局部性，同时让拓扑更新不重写完整基础记录，并使更新具有部分可逆性？**

---

## 2. 核心观察：ANN 剪枝是破坏性的

考虑节点 \(u\) 的邻接表：

\[
N(u)=\{a,b,c,d\}.
\]

插入节点 \(x\) 后，候选集合执行有界度剪枝：

\[
N'(u)=\{a,b,x,d\}.
\]

边 \((u,c)\) 被淘汰。

之后删除 \(x\)，大多数动态图索引无法直接恢复：

\[
N(u)=\{a,b,c,d\}.
\]

原因在于系统通常没有保存：

- \(c\) 曾经是 \(u\) 的活跃邻居；
- \(c\) 在哪一次剪枝中被淘汰；
- 哪个候选导致 \(c\) 被淘汰；
- 当该候选消失后，\(c\) 是否仍值得恢复；
- 当时剪枝的候选集合和 witness。

系统只能重新搜索局部邻域，最终可能得到：

\[
N''(u)=\{a,b,e,d\}.
\]

因此：

\[
\operatorname{Delete}_x
\left(
\operatorname{Insert}_x(G)
\right)
\neq G.
\]

这种不可逆性可能不断积累：

```text
插入
→ 邻接表超限
→ 破坏性剪枝
→ 旧边及淘汰原因丢失
→ 后续删除重新发现候选
→ 图结构偏离原始状态
→ 查询路径和物理布局逐渐老化
```

本方向的关键判断是：

> 动态图的长期问题可能不只来自“删除节点后缺边”，还来自“过去每次剪枝都不可逆地忘记了被覆盖的导航选择”。

---

## 3. 研究问题

### RQ1：更新历史是否导致可测量的图老化？

在活跃向量集合相同的前提下，不同更新历史是否导致显著不同的：

- 图结构；
- 搜索路径；
- 查询 recall；
- page reads；
- tail latency？

这种差异是否显著超过：

- 构建随机种子；
- 插入顺序；
- 查询线程调度；
- 缓存状态；

产生的自然波动？

---

### RQ2：被剪枝边是否仍有可恢复价值？

当节点 \(x\) 被删除时，被 \(x\) 或相关更新淘汰的历史边能否：

- 作为高质量局部 repair candidates；
- 减少重新搜索范围；
- 降低修复距离计算与随机 I/O；
- 使最终图更接近更新前状态；
- 改善查询 I/O 或 tail recall？

---

### RQ3：半耦合 base/delta 能否同时改善查询与更新？

能否设计：

```text
读取时：
    大多数节点只读一个紧凑 BaseRecord

更新时：
    只追加小型 topology delta
    不重写 full vector 或整页基础记录
```

并在总体上超过：

- coupled in-place；
- fully decoupled；
- out-of-place / LSM-style update；

之间的传统权衡？

---

## 4. 核心设计：ReversibleANN

### 4.1 不可变向量基座

完整向量独立存储：

```text
VectorStore:
    vector_id → immutable full-precision vector
```

向量首次写入后不因邻接变化而重写。

这避免 topology update 携带完整向量写入，但单独这一点不构成创新，因为 DGAI 和 DecoupleVS 已经探索了解耦。

---

### 4.2 读优化的 BaseRecord

每个节点在构建或 compaction 时生成基础记录：

```text
BaseRecord(u):
    compact vector / PQ code
    base adjacency
    full-vector pointer
    base epoch
```

设计目标：

- 常规查询读取一个基础记录即可获得导航所需的压缩距离信息和大部分邻接；
- 未发生更新的节点不产生额外 topology I/O；
- 完整向量只在必要精排阶段读取；
- 基础记录可以按现有 page-aware layout 聚合。

因此，ReversibleANN 并非完全解耦，而是：

> **保留读路径所需的压缩向量与基础邻接耦合，将频繁变化的拓扑增量从基础记录中分离。**

---

### 4.3 追加式 EdgeDelta

邻接变化不直接覆盖 BaseRecord，而追加：

```text
EdgeDelta:
    node_id
    add_edges
    deactivate_edges
    version / epoch
    dependency metadata
```

当前邻接为：

\[
N_t(u)
=
N_{\text{base}}(u)
\oplus
\Delta_1(u)
\oplus
\Delta_2(u)
\oplus\cdots
\oplus
\Delta_t(u).
\]

潜在实现：

- 热点 delta overlay 保存在内存；
- 冷 delta 以紧凑 append log 存储；
- 同页节点的 delta 可聚合；
- 查询仅对有活跃 delta 的节点执行 merge；
- compaction 生成新的 BaseRecord 并清理旧 delta。

---

### 4.4 Shadow Edge / Edge-Displacement Dependency

当插入 \(x\) 导致边 \((u,c)\) 被剪枝时，不直接忘记 \(c\)，而记录：

```text
ShadowEdge:
    owner_node = u
    displaced_edge = (u, c)
    displaced_by = x
    prune_epoch
    optional prune witness
```

形成反向依赖：

\[
x
\longrightarrow
\{
(u,c)\mid (u,c)\text{ was displaced due to }x
\}.
\]

删除 \(x\) 时，不必从整个邻域重新发现候选，而是优先取出其 shadow candidates。

---

### 4.5 条件恢复，而非简单回滚

旧边不能无条件恢复，因为数据和邻域在 \(x\) 存活期间可能继续变化。

删除 \(x\) 后：

\[
C_x(u)
=
N_t(u)\setminus\{x\}
\cup
S_x(u),
\]

其中 \(S_x(u)\) 是与 \(x\) 相关的 shadow candidates。

然后执行当前版本的确定性局部剪枝：

\[
N_{t+1}(u)
=
\operatorname{Prune}(C_x(u)).
\]

因此：

- shadow edge 是历史候选证据；
- 不是直接 redo/undo；
- 恢复遵循当前图约束；
- 系统保留的是“被覆盖的选择空间”，而非强制恢复旧状态。

---

### 4.6 成本驱动的 compaction

不能使用任意 delta 长度阈值。

应比较：

\[
C_{\text{keep-delta}}
=
C_{\text{future query merge}}
+
C_{\text{delta I/O}}
+
C_{\text{delta memory}}
\]

与：

\[
C_{\text{compact}}
=
C_{\text{new base write}}
+
C_{\text{metadata update}}.
\]

当预期保留 delta 的成本高于生成新 BaseRecord 时才 compact。

所需统计可以包括：

- 节点近期访问频率；
- delta 链长度和字节数；
- 查询访问该节点时的额外 CPU/I/O；
- 基础页重写成本；
- 当前 SSD 写压力。

该成本模型属于后续系统设计，不属于 A0 必须完成的内容。

---

## 5. 新性质与形式化目标

### 5.1 更新可逆性

定义：

\[
\mathcal R_x(G)
=
\operatorname{Delete}_x
\left(
\operatorname{Insert}_x(G)
\right).
\]

完全可逆：

\[
\mathcal R_x(G)=G.
\]

实际动态图通常无法保证完全一致，因此定义近似可逆性：

\[
d_G(\mathcal R_x(G),G)\le \epsilon.
\]

\(d_G\) 可分别使用：

- edge symmetric difference；
- 邻接 Jaccard 距离；
- reachable-set difference；
- greedy path difference；
- query recall–cost curve distance；
- page-access distribution distance。

---

### 5.2 更新历史敏感度

对于最终活跃集合相同的两个序列：

\[
H(\sigma_1,\sigma_2)
=
d_G(G_{\sigma_1},G_{\sigma_2}).
\]

进一步定义性能历史敏感度：

\[
H_C(\sigma_1,\sigma_2)
=
\mathbb E_q
\left[
\left|
C(q,G_{\sigma_1})
-
C(q,G_{\sigma_2})
\right|
\right].
\]

论文需要证明的不是“图必然不同”，而是：

> 不同更新历史会造成稳定、可复现且超过正常构建方差的查询性能差异。

---

### 5.3 导航债务

每次破坏性剪枝产生潜在未来修复负担：

\[
D_t
=
\sum_{e\in E_{\text{shadow}}} w(e).
\]

\(w(e)\) 可表示：

- 该边是否跨越稀疏区域；
- 历史搜索使用频率；
- gateway 价值；
- 恢复成本；
- 活跃 displacer 数。

“导航债务”适合作为解释和分析指标，但不应在早期直接变成启发式 repair scheduler。

---

## 6. 与现有工作的边界

### 6.1 IP-DiskANN

IP-DiskANN 关注逐条原地插入和删除，以及长时间更新后的稳定 recall。[2]

ReversibleANN 必须证明：

- IP-DiskANN 虽能维持平均 recall，仍可能存在 history-dependent page reads、tail recall、repair I/O 或 write amplification；
- shadow candidate 能在公平更新预算下提供额外收益；
- 贡献不只是另一种删除补边算法。

若 IP-DiskANN 在同终态实验中没有明显老化，本方向应被 KILL。

---

### 6.2 OdinANN

OdinANN 通过 direct insert 避免内存缓冲和批量 merge 对前台搜索造成阶段性干扰，目标是持续插入期间的稳定性能。[3]

ReversibleANN 不研究 merge interference，核心应是：

- 破坏性剪枝的历史依赖；
- 插入—删除循环后的结构恢复；
- topology delta 与基础记录的物理组织。

---

### 6.3 DGAI / DecoupleVS

DGAI 和 DecoupleVS 已经建立：

> 向量数据与索引元数据共置会造成冗余读写，解耦可以改善更新和空间效率。[6][7]

因此 ReversibleANN 不应声称首次发现 coupled write amplification，也不能把“拓扑与向量分开”写成主要 novelty。

差异必须落在：

1. read-optimized semi-coupled base；
2. append-only topology overlay；
3. edge-displacement dependency；
4. conditional reactivation；
5. query aging 与 write amplification 的联合优化。

---

### 6.4 Random-Walk Deletion / Signal-Triggered Repair

随机游走删除试图保持删除前后的 hitting-time 统计；signal-triggered repair 研究何时修复以保护 tail recall。[4][5]

ReversibleANN 研究的是：

- 候选从哪里来；
- 为什么动态剪枝不可逆；
- 如何利用剪枝历史减少 repair search；
- 如何减少物理更新 I/O。

如果最终机制只是根据一个 debt signal 决定何时 repair，将与已有方向重合。

---

### 6.5 PageANN 与页面布局研究

PageANN 将逻辑图节点与 SSD page 对齐，以缩短 I/O 路径和提高扩展效率。[8]

本工作不应主张“页面抽象错误”或“完全 page-free”。更准确的目标是：

> **磁盘页可以继续作为物理传输和布局单元，但不再承担每次拓扑更新的逻辑版本边界。**

---

## 7. 为什么不单独做 Page-Free ANN

“每个邻接表是几百字节变长记录，只读取实际需要的字节”看起来可以减少无效读取，但存在硬伤：

1. NVMe 和底层 NAND 仍按块处理；
2. 小记录随机读取会增加 I/O 命令数；
3. 变长记录更新会造成 relocation、碎片和 GC；
4. 多个小请求可能不如一次聚合页读取；
5. 最终容易重新发明 slotted page、extent allocator 或 LSM record store；
6. PageANN、Starling、BAMG 等工作已经在优化块级局部性。

因此，本方向只将 `page-oblivious logical update` 作为系统属性，而不把物理 page-free 作为论文主张。

---

## 8. A0：GraphAging 生死实验

### 8.1 A0 目标

只回答两个问题：

1. 同一最终向量集合经过不同更新历史后，查询性能是否持续偏离静态基线？
2. 保存被剪枝候选是否能低成本改善恢复？

A0 暂不实现：

- 新磁盘格式；
- delta compaction；
- 完整半耦合查询路径；
- 多 NVMe 并行；
- 复杂调度策略。

---

### 8.2 A0-1：插入—删除可逆循环

从静态图 \(G_0\) 开始：

```text
insert batch B
delete the same batch B
```

循环次数：

\[
1,\ 10,\ 100,\ 1000.
\]

每轮结束后，活跃数据集都与 \(G_0\) 相同。

比较：

- static rebuild；
- 原始动态图方法；
- IP-DiskANN；
- OdinANN 可用更新路径；
- HNSW dynamic baseline。

指标：

- Recall@10 / Recall@100；
- per-query recall 分布；
- distance calculations；
- visited nodes；
- distinct SSD pages；
- p50 / p95 / p99 latency；
- edge Jaccard；
- 入度与出度分布；
- SCC / reachable coverage；
- gateway edge disappearance；
- update logical bytes、application bytes、block bytes。

---

### 8.3 A0-2：同终态不同历史

固定最终活跃集合，构造：

1. 顺序插入；
2. 随机插入；
3. cluster burst；
4. sliding-window expiration；
5. insert-delete churn；
6. delete-reinsert；
7. hot-cluster 高 churn、cold-cluster 静态。

对每种历史使用多个 build/update seeds。

必须分离：

\[
\text{history variance}
\]

与：

\[
\text{ordinary build-seed variance}.
\]

---

### 8.4 A0-3：耦合式更新 I/O 账本

对每次 topology update 记录：

\[
W_{\text{logical edge}},
W_{\text{application}},
W_{\text{filesystem}},
W_{\text{block}}.
\]

至少区分：

- 新向量写入；
- 邻接修改；
- full-vector 重写；
- page rewrite；
- WAL / journal；
- compaction；
- repair search read；
- repair write。

目标不是再次证明“解耦更好”，而是确认：

> 在当前 coupled baseline 中，多少写入来自与本次 topology change 无关的不可变向量和基础记录。

---

### 8.5 A0-4：Oracle Shadow Replay

先只在内存 instrumentation 中记录：

```text
inserted node x
owner node u
edge c displaced during prune
prune epoch
```

当删除 \(x\) 时比较：

1. baseline repair；
2. 从图中重新搜索候选；
3. shadow candidates + current prune；
4. oracle original-neighbor replay；
5. static rebuild reference。

衡量：

- repair candidate discovery cost；
- repair distance computations；
- repair SSD reads；
- restored-edge acceptance ratio；
- final graph distance from \(G_0\)；
- post-repair query cost；
- shadow metadata size。

---

## 9. A0 机械裁决

### PASS

必须同时满足：

1. 活跃数据集恢复原状后，查询性能仍随更新循环持续退化或产生显著历史方差；
2. 老化不仅体现在平均 recall，还体现在 page reads、tail recall、distance computations 或 tail latency中的至少一项；
3. history-induced difference 明显超过 build seed 和 update seed 的自然波动；
4. coupled update 的物理写入中存在显著的不可变数据重写；
5. shadow candidate 相比 baseline repair 显著减少候选发现成本，或更接近静态重建性能；
6. 现象在 Vamana/DiskANN 和至少一种 HNSW 系实现中出现；
7. shadow metadata 没有立即膨胀到与完整候选图同量级。

### HOLD

出现以下情况之一：

- 图结构变化明显，但查询性能变化较小；
- 只有弱删除 baseline 老化，IP-DiskANN 基本不老化；
- shadow candidates 有价值，但存储膨胀很快；
- 只在极端 churn 或单一数据集出现；
- 只改善 repair CPU，不改善 I/O 或查询性能。

### KILL

出现以下任一情况：

1. IP-DiskANN/OdinANN 在相同终态下没有超过随机方差的老化；
2. insert-delete 后查询性能自然恢复；
3. 图结构差异不影响查询性能；
4. shadow candidates 与普通局部搜索效果相同；
5. shadow metadata 或验证成本过高；
6. delta 查询额外开销抵消更新收益；
7. 主要收益已被 DGAI/DecoupleVS 的普通解耦覆盖；
8. 只有人为、极端或不现实的 churn 才能得到正结果。

---

## 10. 主要反方攻击

### 攻击 1：图不同并不代表图更差

不同更新历史产生不同图是预期现象。只有查询性能产生稳定单向退化，或性能方差显著扩大，才构成研究问题。

### 攻击 2：Shadow edge 可能无限增长

持续 churn 会产生大量历史候选。必须量化：

- shadow edges / active edges；
- 每次插入平均新增 shadow 数；
- active displacer 引用计数；
- compaction 后可回收比例。

如果 shadow storage 接近完整候选图，设计不成立。

### 攻击 3：旧边不再是好边

历史边只能重新进入候选集，不能直接恢复。若每次仍需读取大量向量并运行完整 RobustPrune，收益可能很小。

### 攻击 4：IP-DiskANN 已解决长期稳定 recall

如果更强 baseline 已经稳定维持 recall、page reads 和 tail latency，则“可逆性”只是结构美学，不是系统需求。

### 攻击 5：Base + Delta 是通用 LSM/MVCC 包装

实现形式确实类似常见日志结构。论文价值必须来自 ANN-specific 的 displacement dependency 和 conditional reactivation，而不是 append log。

### 攻击 6：半耦合查询可能退化为双 I/O

如果大量被访问节点都有 delta，查询将同时读取 base 和 delta，重新接近完全解耦的访问放大。

### 攻击 7：删除并非插入的逆操作

动态图中的其他更新使严格恢复原图不合理。因此论文必须强调“近似可逆性和历史敏感度降低”，不能过度声称完全回滚。

### 攻击 8：物理写放大可能主要来自文件系统和 WAL

必须做分层账本，不能把 journal、metadata、allocator 和 topology record 混为一谈。

---

## 11. 预期贡献形态

若 A0 PASS，完整论文可能包含：

1. **新现象：**  
   首次系统性量化相同终态下的 history-induced graph aging。

2. **新形式对象：**  
   更新可逆性、历史敏感度与 edge-displacement dependency。

3. **新算法机制：**  
   shadow candidate 保留和 conditional edge reactivation。

4. **新存储架构：**  
   read-optimized semi-coupled base + append-only reversible topology delta。

5. **联合收益：**  
   在相同 recall 下减少 update write amplification、repair I/O 和查询老化。

6. **边界结论：**  
   指出何种 churn、图稀疏度、维度和查询分布下可逆维护有效，何时应回退到重建或普通 repair。

---

## 12. 给 Claude 的严格审议问题

请重点攻击以下问题：

1. **问题是否真实：**  
   IP-DiskANN、OdinANN 或其他强 baseline 是否已经使同终态历史老化几乎不可观测？

2. **最近工作是否直接覆盖：**  
   是否已有工作保存被剪枝邻居、prune provenance、undo edge 或 reversible adjacency？

3. **Shadow edge 是否有信息价值：**  
   被淘汰边相比删除时重新搜索得到的候选，是否真的更优？

4. **机制是否只是工程组合：**  
   `base + delta + old edge log` 是否会被审稿人概括为 WAL/LSM/MVCC 包装？

5. **可逆目标是否合理：**  
   动态数据分布变化后，恢复旧邻居是否可能反而降低图质量？

6. **存储是否可控：**  
   shadow dependency 的空间是否会随 churn 无界增长？

7. **查询路径是否受损：**  
   topology delta overlay 是否把 coupled query 退化成 decoupled query？

8. **理论是否足够：**  
   update reversibility 和 history sensitivity 是否只是指标定义，能否产生有意义的性质或界？

9. **A0 是否公平：**  
   insert-delete 循环是否代表真实工作负载，还是人为制造对称终态？

10. **论文身份：**  
    该工作更适合 FAST/EuroSys，还是会被认为应投数据库或 ANN 算法会议？

请给出明确裁决：

```text
PASS-A0
HOLD-NEEDS-PAPER-GATE
KILL-PRIOR
KILL-NO-PROBLEM
KILL-GENERIC-STORAGE
```

---

## 13. 当前建议

当前不应以 `ReversibleANN` 名义直接启动完整系统。

建议先建立：

```text
GraphAging/
    instrumentation/
    workloads/
    baselines/
    shadow_oracle/
    reports/
```

第一阶段只完成：

- 同终态不同历史；
- 插入—删除循环；
- 分层 I/O 账本；
- shadow candidate oracle。

若 A0 PASS，再正式冻结 ReversibleANN 的系统设计；若 IP-DiskANN 等强 baseline 无明显老化，立即停止，不通过加入缓存、调度或其他模块强行续命。

---

## 参考工作

[1] Xiaoyu Chen et al. **Disk-Resident Graph ANN Search: An Experimental Evaluation.** arXiv:2603.01779, 2026.  
[2] Haike Xu et al. **In-Place Updates of a Graph Index for Streaming Approximate Nearest Neighbor Search.** arXiv:2502.13826, 2025.  
[3] Hao Guo and Youyou Lu. **OdinANN: Direct Insert for Consistently Stable Performance in Billion-Scale Graph-Based Vector Search.** FAST 2026.  
[4] Nina Mishra et al. **Graph-based Nearest Neighbors with Dynamic Updates via Random Walks.** arXiv:2512.18060, 2025.  
[5] Madhulatha Mandarapu and Sandeep Kunkunuru. **When to Repair a Graph ANN Index: Navigability-Signal-Triggered Local Repair Protects Tail Recall Under Bursty Churn.** arXiv:2607.00728, 2026.  
[6] Jiahao Lou et al. **DGAI: Decoupled On-Disk Graph-Based ANN Index for Efficient Updates and Queries.** arXiv:2510.25401, 2025.  
[7] Yuanming Ren et al. **Decoupling Vector Data and Index Storage for Space Efficiency.** arXiv:2604.09173, 2026.  
[8] Dingyi Kang et al. **Scalable Disk-Based Approximate Nearest Neighbor Search with Page-Aligned Graph.** arXiv:2509.25487, 2025.
