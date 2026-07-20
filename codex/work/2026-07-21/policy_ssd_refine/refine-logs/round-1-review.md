# Round 1 Review

<details>
<summary>Raw reviewer response</summary>

# 外部方法评审：Page-Addressed Permission Maintenance for SSD Graph ANN

## 总体判断

该 proposal 的 Problem Anchor 清晰，能够准确区分两类正确性要求：

1. grant 的 stale-negative 会造成授权对象不可发现；
2. revoke 的 stale-positive 可以由最终精确验证兜底。

这是目前方案最扎实的部分。proposal 也主动排除了 Bloom、MVCC、WAL、lazy revoke 等伪贡献，并设置了明确的 kill gate，研究纪律较好。

但当前核心方法尚未越过顶会系统论文的“自然组合”反证。把 PipeANN-Filter 的 approximate/exact filtering 接口、Curator 的 stale-positive revoke、Zanzibar/RocksDB 的 snapshot/WAL/LSM，以及一个按 `graph_page` 排序的 RocksDB column family 组合起来，就已经可以自然得到：

```text
base summary
OR WAL-backed page-prefix grant delta
-> exact snapshot authorization
-> background compaction
```

目前所谓 `page-addressed grant delta` 与这个强组合之间的实质差别，主要仍是 key layout、cache locality 和查询时机，而不是一个已被具体定义的新数据结构、协议或算法。因此，若直接执行当前计划，即使测到明显性能收益，也很容易被审稿人解释为“把普通 LSM delta 的 key 从 node 改成 graph page”。

我的结论不是 Problem Anchor 应该被放弃，而是：**当前机制级新意尚未成立，必须先完成最强自然组合等价性反证，再决定是收紧方法还是 KILL。**

## 评分

| 维度 | 权重 | 分数 | 加权分 |
|---|---:|---:|---:|
| Problem Fidelity | 15% | 8.5/10 | 1.275 |
| Method Specificity | 25% | 6.0/10 | 1.500 |
| Contribution Quality | 25% | 4.0/10 | 1.000 |
| Frontier Leverage | 15% | 8.5/10 | 1.275 |
| Feasibility | 10% | 6.5/10 | 0.650 |
| Validation Focus | 5% | 7.0/10 | 0.350 |
| Venue Readiness | 5% | 4.5/10 | 0.225 |
| **OVERALL** | **100%** | **6.275/10** | **6.3/10** |

**Verdict: RETHINK**

这里的 RETHINK 针对核心机制和 novelty framing，不是要求更换 Problem Anchor。当前方案不应进入完整实现或大规模实验；应先做源码/API 级等价性审计和最小机制 preflight。

---

## 1. Problem Fidelity：8.5/10

### 优点

- grant recall 与 revoke safety 被正确拆开。
- 方案持续围绕“动态权限下 SSD ANN routing 的可达性”展开，没有漂移成通用 ACL 服务或通用复合查询系统。
- 不强行加入 LLM、RL 或 learned planner 是正确选择。这里的瓶颈是存储可见性和快照一致性，而不是学习问题。
- 使用 fresh synchronous-summary 作为 recall 参照，比直接对 exact top-k 宣称绝对 ANN recall 更合理。

### 尚存问题

Problem Anchor 中的“动态 RBAC/ACL”比实际 page-addressed 机制覆盖的更新类型更宽：

- `direct-principal -> object` grant 和 `role -> object` grant 会改变对象侧 summary，确实需要 grant delta。
- `user -> role` grant 通常只改变查询侧 atom closure；如果对象 base summary 已包含该 role atom，它不需要更新 graph page。
- role hierarchy edge 更新也可能通过查询侧角色闭包处理，而不是产生 page-addressed object delta。

因此，当前方法并不统一解决所有 RBAC/ACL 更新，只解决“改变对象侧 policy atom 集合”的更新。

### 建议

将方法适用域明确收紧为：

> object-side permission grants whose committed visibility changes the approximate predicate attached to SSD graph records.

用户角色成员关系和角色继承可以保留为 workload 维度或已有 PolicyStore 功能，但不要把它们表述成 page-addressed delta 的贡献对象。

---

## 2. Method Specificity：6.0/10

### 具体弱点

#### A. `GrantPageDirectory` 同时被称为 directory 和 cache，正确性语义不清

搜索 invariant 要求 committed grant 不可因目录 miss 而消失。如果该结构是可驱逐 cache，则 cache miss 后必须有一个不会产生 false negative 的权威 SSD 索引；如果它是完整 directory，则必须给出在 1B scale、64 GiB cap 下的内存公式。

当前“fixed-budget DRAM directory/cache”混淆了两种完全不同的结构。

**修复：CRITICAL**

明确拆成：

- correctness-critical locator：任何 committed page delta 都必须可定位，不能因 eviction 丢失；
- optional DRAM cache：只影响 I/O，不影响可达性。

需要给出 key、value、查找步骤、false-positive/false-negative 语义、每 page/record 字节数及 1B 规模预算。

#### B. 查询路径没有精确定义 summary 在何处剪枝

必须明确 approximate predicate 用于：

- 是否展开 graph node；
- 是否读取 vector/PQ/full vector；
- 是否进入 candidate heap；
- 还是仅用于最终结果资格判断。

如果底层 traversal 允许通过未授权节点 tunneling，那么 stale-negative 可能只影响 candidate admission，而不是“永久剪断 graph routing”。若该失败点没有源码级 witness，整个 Problem Anchor 的 ANN-specific 部分会减弱。

**修复：CRITICAL**

用一段确定的伪代码描述 PipeANN-Filter-style traversal，并给出一个最小反例：

```text
fresh summary 能发现授权 top-k
stale-negative summary 在具体哪一行丢弃它
exact recheck 为什么无法恢复
```

该反例必须建立在实际准备复用的代码路径上。

#### C. grant commit 跨 PolicyStore、GrantLog 和内存可见性的原子性不足

“one commit intent; fsync; install directory visibility; publish CSN”仍不足以实现：

```text
ACK grant => every q_csn >= grant_csn can route to it
```

缺少以下定义：

- PolicyStore 与 GrantLog 是否共用 WAL；
- 两个独立 fsync 之间崩溃如何处理；
- commit marker 和 published high-watermark 位于何处；
- 查询如何原子读取 stable `q_csn` 与 delta generation；
- recovery 如何区分 committed/uncommitted intent；
- rebuild directory 时系统是否完全停止服务；
- recovery 工作量是否随全部历史 grant 增长。

**修复：CRITICAL**

给出一个单一协议。最简单的路线是复用一个 durable commit record，并将“policy tuple durable”和“routing delta durable”绑定到同一 CSN；查询只取得已经越过 routing-visible watermark 的快照。不要同时保留多个模糊替代协议。

#### D. merge 对旧快照的语义不完整

“visible grants - expired exact permissions”可能破坏仍在运行的旧快照。对于 `q_csn < end_csn` 的查询，被 revoke 的权限在其快照上仍然有效。

**修复：CRITICAL**

明确：

- merge 生成的是哪个 `base_csn` 的 summary；
- 可回收版本的条件；
- `oldest_active_snapshot` 或 snapshot retention window；
- manifest 切换前后查询如何选择 base generation 和 delta range；
- page ID 是否在系统生命周期内稳定。

#### E. exact verifier 后的 top-k 补齐未定义

精确验证剔除 candidate 后，结果可能不足 k。仅写“return exact-allowed top-k”不等于实现 authorized top-k。

**修复：IMPORTANT**

定义 continuation/refill 规则：exact verifier 失败后，搜索是否继续扩大 frontier、每轮扩大多少、何时终止，以及与 fresh-summary baseline 对齐的 search budget。

---

## 3. Contribution Quality：4.0/10

### 核心阻塞

当前 strongest generic baseline 定义得不够强。proposal 使用“generic node-keyed delta”作为主要对照，但一个熟悉 RocksDB 的工程师会自然实现：

```text
key = (graph_page, policy_atom, begin_csn, node_id)
value = normalized permission payload
```

再配合：

- prefix Bloom；
- block cache；
- WAL/WriteBatch；
- page-prefix iterator 或 MultiGet；
- touched-page 批处理；
- background compaction。

这已经具备 proposal 中 page addressing、append-only grant、page-local fetch、cache 和 merge 的大部分行为。Curator 再提供 lazy revoke 的先例，PipeANN-Filter 提供 approximate/exact split，Zanzibar 提供 snapshot authorization，组合路径非常直接。

因此，当前“ANN-specific novelty”还没有显示为：

- 新的抽象；
- 新的数据结构；
- 新的 correctness protocol；
- 新的 I/O scheduling guarantee；
- 或此前组合无法得到的复杂度边界。

只有测出 `2x` 写字节或 `1.5x` p99，并不能自动把 key-layout 优化变成机制贡献。

### 具体修复：CRITICAL

首先建立一个真正最强的自然组合 baseline：

> PipeANN-Filter + Curator semantics + Zanzibar/RocksDB MVCC，其中 RocksDB delta 同样按 graph page prefix 排序、使用相同 cache budget、相同 WAL durability、相同 batched touched-page fetch 和相同 compaction资源。

然后回答：

> proposal 中还有哪一行机制是这个 baseline 无法通过 schema、comparator、prefix extractor 和 cache 配置获得的？

如果答案为“没有”，应立即执行 `KILL-RENAME-MVCC-LSM`。

如果仍有差异，只允许选择一个机制作为 dominant contribution，例如：

- 一个具有明确无 false-negative 性质和有界 DRAM 成本的 page grant locator；
- 一个将 grant durability 与 routing visibility 原子绑定的 grant-visibility fence；
- 一个能将 delta lookup 与 graph page I/O 合并、并给出额外 I/O 上界的 physical sidecar layout。

不要同时添加三个机制来“堆出新意”。最终论文必须能用一句话指出唯一不可由普通 page-keyed RocksDB 获得的性质。

---

## 4. Frontier Leverage：8.5/10

系统论文不需要为了“现代”引入 foundation model。当前选择是正确的：

- io_uring/异步 SSD pipeline；
- snapshot/MVCC；
- WAL/LSM；
- conservative approximate predicate；
- exact verification。

这些已经是与问题匹配的现代系统原语。

**Modernization Opportunities: NONE**

LLM/VLM/RL 不会提升方法合理性，加入它们反而会导致 drift。需要更新的是存储机制的精确程度，而不是模型组件。

---

## 5. Feasibility：6.5/10

### 具体弱点

- PipeANN-Filter artifact 是否允许在目标代码路径插入 page-local overlay，尚未有 API 级证据。
- 1M 数据很可能被 OS page cache 或 DRAM 吸收，不能自然代表 SSD-resident routing 行为。
- exact MVCC verifier 可能成为主要 query I/O；若每批 graph candidate 都要随机访问权限关系，page delta 的收益会被掩盖。
- hierarchical RBAC 的 snapshot evaluation 与 batched verification 成本没有预算。
- recovery 需要重建所有 `base_csn` 后 grant；若没有 checkpointed directory，其重启时长可能不可接受。
- page address 作为 durable key 要求 graph packing 在 policy lifetime 内稳定，或存在 graph generation/version 映射。

### 具体修复：IMPORTANT

在任何完整实现前，只做三个低成本闭环：

1. **源码 witness**：确认 predicate 的真实剪枝点及 page ID 稳定性。
2. **equivalence prototype**：使用 RocksDB page-prefix schema 实现最强自然组合，不修改 ANN 主体。
3. **I/O accounting microbenchmark**：在显式冷缓存或超出有效 cache 的工作集上，测一次 graph-page touch 对应的 delta lookup 次数和额外物理 I/O。

如果这三项不能显示 proposal 具有强 baseline 不具备的行为，不应进入 100M/1B。

---

## 6. Validation Focus：7.0/10

### 优点

- 两个 claim block 足够集中。
- 有 correctness 与 performance 两条独立证据链。
- kill gate 明确，不回避 negative result。
- 明确要求 logical/physical bytes、query I/O、compaction duty cycle，而非只报吞吐。

### 需要收紧之处

1. “generic node-keyed delta”必须替换成同样按 page prefix 排序的最强 RocksDB baseline。
2. 两类 permission model 不能代替核心 locality 变量。page-addressing 的收益高度依赖 grant 在 graph pages 上的分布。
3. 需要显式 sweep：

   - grants/page；
   - update-to-page entropy；
   - tenant/role atom density；
   - hot/cold page skew；
   - delta lifetime；
   - exact verifier cache hit rate。

4. crash test 需要验证线性化点和 recovery contract，而不是把“1M”当作 correctness 强度。
5. 增加：

   - recovery time；
   - directory rebuild bytes；
   - policy-plane DRAM；
   - merge write amplification；
   - query result不足 k 的比例和 continuation cost。

6. `2x`、`1.5x`、`15%` 目前是人为阈值。应先通过设备级 cost model 推导“普通 page-keyed LSM 理应达到什么”，再冻结门槛。

---

## 7. Venue Readiness：4.5/10

目前可以形成一个严谨的系统问题和一项有价值的工程观察，但还不能形成顶会级机制贡献。审稿人最可能给出的拒稿意见是：

> The proposed page-addressed delta appears to be a conventional WAL-backed LSM overlay keyed by physical graph pages, combined with existing approximate filtering, lazy revocation, and exact authorization checks. The paper does not establish which capability cannot be obtained by a straightforward RocksDB schema and cache configuration.

若没有回答这一点，更多实现细节和更大规模实验不会解决 venue-readiness 问题。

---

## Drift Warning

**PARTIAL**

Problem Anchor 本身保持良好，但有两处隐性漂移风险：

1. 从“固定 policy-plane DRAM”漂移到一个未定量、可能需要完整驻留的 `GrantPageDirectory`。
2. 从“动态 RBAC/ACL”泛化到所有权限更新，而实际 page delta 主要解决 object-side atom grant；user-role/hierarchy 更新可能走查询侧 closure。

应收紧适用域和预算，不应更换底层问题。

---

## Simplification Opportunities

1. **删除 supporting contribution 的论文贡献地位。** Lazy revoke + exact verification 是 correctness plumbing，应作为复用设计，不应占据第二贡献。
2. **把核心动态更新限制为 object-side grants/revokes。** user-role 与 hierarchy update 由 PolicyStore/query atom compilation 处理，只作为兼容性说明。
3. **删除不能检验核心 novelty 的次要 ablation。** materialized user×document ACL 是已知弱设计，不应成为主 baseline；“no batched exact verify”也只验证工程常识。
4. **只保留一个新机制。** locator、visibility fence、sidecar layout 中至多选择一个；其余使用标准 RocksDB/MVCC 组件。

---

## Modernization Opportunities

**NONE**

该问题不需要学习组件。应把精力放在强系统 baseline、接口定义、原子发布和 I/O 上界，而不是引入 foundation-model-era 模块。

---

## 按优先级的修改项

### P0 / CRITICAL

1. **建立自然组合等价表。** 逐项列出 proposal 组件与 PipeANN-Filter、Curator、Zanzibar/RocksDB 的对应关系，明确唯一不能通过组合获得的机制。
2. **升级 strongest baseline。** 必须允许 generic RocksDB delta 使用相同 graph-page key、cache、WAL、batching 与 compaction；禁止用 node-keyed 弱 baseline 制造优势。
3. **确认真实剪枝点。** 在目标 ANN 代码中证明 stale-negative 在哪一步造成不可恢复的 authorized recall 损失。
4. **定义唯一的新接口。** 给出输入、输出、持久状态、内存状态、查询步骤、更新步骤和复杂度；不能继续使用“directory/cache”模糊称呼。
5. **补全线性化与恢复协议。** 明确 grant/revoke ACK 点、routing-visible watermark、旧快照、manifest generation 和 GC 条件。
6. **执行 KILL 判断。** 若 page-prefix RocksDB baseline 已实现相同 invariant 和 I/O 行为，停止该路线，不进入完整实验。

### P1 / IMPORTANT

7. 收紧为 object-side policy atom maintenance，分离 query-side RBAC closure。
8. 定义 exact-verification 失败后的 top-k continuation。
9. 给出 1B scale 的 DRAM 与 SSD 元数据公式，包括 locator、delta、cache 和 recovery checkpoint。
10. 用 locality/entropy sweep 代替“两个 permission model 即可证明普适性”。
11. 在最小 preflight 中测真实物理 I/O、write amplification、recovery cost，而不只测 RocksDB logical bytes。

### P2 / MINOR

12. 将“ANN-specific reachability obligation absent from ordinary secondary indexes”改弱。普通二级索引同样有 committed visibility obligation；真正可能特殊的是 graph traversal 的 page-touch 顺序和额外 I/O 约束。
13. 区分 policy-induced recall delta、ANN intrinsic recall 和结果不足 k 三个指标。
14. 明确 `graph_page` 是否包含 graph generation，避免 rebuild/repack 后 durable delta 指向失效页面。

---

## 最终结论

**OVERALL: 6.3/10**

**Verdict: RETHINK**

- Problem Anchor：基本保持，值得继续审计。
- 方法具体性：已有良好骨架，但 correctness-critical locator、commit protocol、snapshot merge 和 query continuation 尚未闭合。
- 核心贡献：当前尚不能证明超出 PipeANN-Filter + Curator + Zanzibar/RocksDB 的自然组合。
- 最合理的下一步：不是扩展系统或跑大实验，而是完成 page-prefix RocksDB 强基线等价性审计和源码级 stale-negative witness。
- READY 条件：必须找到一个强自然组合无法提供的、单一且可形式化的 ANN-specific 机制；否则应按 proposal 自己的规则执行 `KILL-RENAME-MVCC-LSM`。

</details>
