# RAG Document-Group Updates for Disk-Resident Graph ANN：A0 联合评审与 Profiling Gate

**Date:** 2026-07-20

**Repository:** `Metafora072/VectorDBChat`

**Candidate:** Correlated Group Updates in Disk-Resident Graph ANN

**Mode:** Literature closure → trace construction → minimal profiling

**Status:** No system-design authorization

---

## 1. Candidate problem

现有动态图 ANNS 通常把更新表示为独立向量的 insert/delete/replacement。RAG 知识库的真实更新单位通常是一个源文档或文档版本：

```text
source document revision
→ deterministic re-chunking
→ remove old changed chunks
→ insert new changed chunks
```

同一 revision 产生的更新向量可能同时具有：

- 共同来源与版本边界；
- 相近或重叠的文本内容；
- 相近的 embedding 区域；
- 重叠的图搜索路径和 SSD pages；
- 重叠的 reverse-edge / repair targets；
- 对同一 adjacency page 的重复 prune 与写回。

唯一研究问题：

> 与相同规模的随机 batch 和几何相近但跨文档的 batch 相比，真实 document-revision group 是否产生可重复、可利用、且未被普通缓存/批处理机制吸收的图搜索与邻居修复重叠？

本轮不假设答案为是。

---

## 2. Precise cost objects

对一个 group `G={u1,...,ug}`，记录每个独立 update `ui` 的：

- graph-search visited nodes `Vi`；
- candidate nodes `Ci`；
- submitted/read SSD pages `Pi`；
- reverse-edge / affected-node targets `Ai`；
- pruned nodes `Ri`；
- modified adjacency pages `Mi`；
- written pages `Wi`。

定义：

```text
ReadReusePotential(G)
= 1 - |union_i Pi| / sum_i |Pi|
```

```text
RepairTargetReuse(G)
= 1 - |union_i Ai| / sum_i |Ai|
```

```text
ModifiedPageReuse(G)
= 1 - |union_i Mi| / sum_i |Mi|
```

这些只是 union-based upper bounds，不能直接声称可实现收益。

必须另外测量：

```text
actual_serial_cost
serial_with_group-local_perfect-read-cache
existing_batch_or_buffered_baseline
union oracle
measured bookkeeping/cache overhead
```

若普通 group-local page cache 已经捕获几乎全部 read overlap，则 shared search 不构成新机制。

---

## 3. Required prior-work boundary

Claude 与 Codex 必须独立核对 primary papers/code：

- FreshDiskANN；
- IP-DiskANN；
- DGAI；
- OdinANN；
- topology-aware localized/small-batch graph update；
- batch HNSW / dynamic graph ANN；
- multi-query/shared-search ANN；
- graph bulk insertion/deletion；
- transactional or grouped vector updates；
- document-level RAG ingestion/update systems；
- correlated batch processing in graph/database indexes。

必须回答：

1. 现有 batch update 是否已共同定位 affected vertices？
2. 现有实现是否已把同一 page 的重复 read/write 合并？
3. 现有 multi-query ANN 是否已共享 traversal/frontier？
4. 组内一次 combined prune 是否已有算法或等价机制？
5. document identity 是否提供超越 geometric clustering 的信息？

若候选最终只是：

```text
batching
+ page cache
+ delayed writeback
+ one-pass deduplication
```

则 KILL。

---

## 4. Real revision workloads

### 4.1 Sources

至少选择三个公开、可完整复现的 revision sources：

1. 一个大型软件文档 Git 仓库；
2. 一个 API / systems documentation Git 仓库；
3. 一个与前两者结构不同的公开 revision corpus，例如 Wikipedia revision subset 或另一类 Markdown/reStructuredText 文档。

选择标准必须预注册：

- 有足够长的 commit history；
- 能恢复 old/new document content；
- 文档路径和 commit identity 完整；
- license 允许研究使用；
- 不以观察 overlap 后挑选仓库。

### 4.2 Canonical revision unit

一个 revision group 必须由同一 commit 中同一 source document 的 old/new 版本产生。

处理流程：

```text
old document
new document
→ deterministic chunking
→ content-hash exact matching
→ unchanged chunks removed from update set
→ removed / modified / added chunks form the group
```

禁止使用相似度阈值判断 `unchanged`。

### 4.3 Chunking

预注册两种 deterministic chunking policies：

1. structure-aware section/paragraph chunking；
2. fixed-token-window robustness policy。

不得观察结果后改变窗口、overlap 或 section merge 规则。

### 4.4 Embeddings

至少使用两个 CPU-compatible frozen embedding models，或一个模型加一个公开预计算 embedding corpus。

要求：

- model revision/hash 固定；
- normalization 与 distance metric 固定；
- no LLM/API；
- no GPU requirement；
- embedding generation cost 不计入 ANN update speed，但必须单独报告。

---

## 5. Matched controls

对每一个真实 revision group，生成三个 paired controls。

### Control A：Random batch

从同一 active corpus 随机选取相同数量的 old/new vectors。

匹配：

- group size；
- insert/delete ratio；
- chunk-length distribution；
- active-set checkpoint。

### Control B：Geometrically clustered cross-document batch

从不同 source documents 中选择一组向量，使其：

- group size 相同；
- pairwise-distance / centroid-distance distribution 尽量匹配真实 group；
- document IDs 全部不同；
- insert/delete ratio 匹配。

该控制用于区分：

```text
收益来自 embedding geometry
vs
收益来自 document/version identity
```

### Control C：Same-document unrelated revision control

从同一文档的不同、非连续 revision 中构造匹配 group，或打乱 old/new lineage，使 document identity 保留但真实版本关系被破坏。

用于判断收益是否来自真实 revision lineage，而非只来自“同文档”。

所有控制必须在看 update trace 前生成并冻结。

---

## 6. Index baselines

至少使用两个当前已有 disk-resident dynamic index paths：

```text
DGAI-style
OdinANN-style
```

可加入 IP-DiskANN 或 topology-aware localized update 作为第三边界，但不得以安装新系统为 A0 必要条件。

每个 group 从完全相同的 frozen index state fork：

```text
hash(index_A) == hash(index_B) == ...
```

必须比较：

1. **Serial-cold**
   - 独立逐向量更新；
   - 每个 update 不继承专用 group cache。

2. **Serial-group-cache**
   - 算法完全不变；
   - 只允许普通、精确的 group-local page cache；
   - 不共享候选队列，不改变 prune 语义。

3. **Existing batch/buffered path**
   - 若系统已有公开 batch path，按其原始语义运行；
   - 禁止人为做弱 baseline。

4. **Union oracle**
   - 只用于上界；
   - 不能作为实现结果；
   - 假设每个 distinct page 在 group 内至多读取/写入一次，但保留全部逻辑工作。

---

## 7. Trace and provenance closure

每个 update 记录：

```text
dataset / document / commit / revision identity
chunk identity and content hash
embedding hash
group ID and member ordinal
graph node ID
visited node IDs
candidate node IDs
page IDs and file roles
I/O issue/completion timestamps
affected/reverse-edge targets
RobustPrune inputs and outputs
modified page IDs
submitted write page IDs
logical and physical bytes
query-visible checkpoint
```

要求闭合：

```text
application page events
= I/O-engine submitted events
= device/cgroup completed bytes
```

允许显式的 merge/cache explanation，但不得保留 unexplained residual。

源码、binary、config、dataset manifest 和 raw trace 必须哈希绑定。

---

## 8. Key confound checks

### 8.1 Page cache dominance

若 `Serial-group-cache` 已达到 union oracle 的主要收益，则：

```text
shared graph traversal novelty = absent
```

不能继续包装 shared search。

### 8.2 Geometry-only explanation

若真实 revision group 与几何相近跨文档控制没有差异，则 document identity 不提供新的索引信号。

这不一定 Kill 所有 correlated-batch 方向，但会 Kill `RAG document group` 作为独立动机。

### 8.3 Existing batch dominance

若现有 batch/localized-update baseline 已共同定位 affected nodes、去重 prune 或合并写回，则新方向必须在其后仍有剩余空间。

### 8.4 Sequential semantics

组合处理不得默认等价于逐点插入。

记录：

- final graph digest；
- per-node adjacency difference；
- Recall/QPS；
- active-set visibility。

A0 中 union oracle 只估计成本，不允许声称 combined prune 可保持相同 final graph。

### 8.5 Group-size artifact

必须按真实 group size 分层，并使用 matched controls。不得把大 group 与单点 update 直接比较。

### 8.6 Unchanged chunk inflation

完全相同的 chunks 不属于更新集。不得通过重复删除/插入 unchanged chunks 制造 overlap。

---

## 9. Required statistical analysis

对每个真实 group 与其 paired controls，计算：

```text
read-reuse potential
actual read-byte saving from ordinary group cache
affected-node multiplicity
prune-target multiplicity
modified-page multiplicity
write-byte overlap
update wall time
foreground query p99 under update
Recall
```

使用 paired bootstrap 或 paired permutation analysis。

不能使用任意“提升超过 10%”阈值。

进入下一阶段需满足：

```text
LCB(real-group benefit over both controls)
>
UCB(measured group bookkeeping/runtime overhead)
```

并且收益在：

- 至少两个 revision sources；
- 两种 chunking policies；
- 至少两个 index paths 或一个 index path 加一个独立 update algorithm；
- 多个 group-size strata；

上保持方向一致。

---

## 10. Claude deliverable

Claude 先产出：

```text
claude/share/2026-07-20/
rag_document_group_update_landscape_and_trace_design_0720.md
```

必须包含：

1. RAG document revision workload 的证据；
2. 15 个以内最接近 prior works；
3. document-group 与 ordinary batch 的严格区别；
4. 三个可被实验否定的假设；
5. 数据源、chunking、embedding 和 paired controls；
6. 最强 novelty objections；
7. 是否值得进入 profiling 的初判。

Claude 不得提出系统名称或直接设计机制。

---

## 11. Codex prelaunch deliverable

Codex 独立审查 Claude 后，先只产出：

```text
codex/share/2026-07-20/
rag_document_group_update_a0_prelaunch_0720.md
```

必须完成：

- primary-source novelty audit；
- 数据源可复现性检查；
- frozen group/control generator；
- exact unchanged-chunk matching；
- embedding/config hashes；
- index fork closure；
- trace schema；
- I/O accounting plan；
- resource budget；
- fail-stop conditions。

只有 prelaunch 得到：

```text
PASS-PRELAUNCH
```

才允许运行 profiling。

---

## 12. Resource bounds

A0 限制：

```text
GPU = 0
LLM/API = 0
distributed cluster = 0
NVMe allocation <= 80 GiB
peak RSS <= 32 GiB
wall clock per formal attempt <= 8 hours
source repositories <= 3
revision groups <= preregistered fixed count
```

优先复用现有 Dynamic Vamana instrumentation，但 RAG revision vectors 必须建立独立的小型 canonical index，不能将文档 vectors 强行映射到 SIFT IDs。

---

## 13. Final labels

最终只允许以下标签。

### `PASS-DOCUMENT-GROUP-OVERLAP`

要求全部成立：

1. 真实 revision groups 相比 random controls 有显著更高的 read/repair/page overlap；
2. 相比 geometrically matched cross-document controls 仍有剩余差异，或明确证明 geometry 本身就是可利用的稳定对象；
3. 普通 group-local page cache 未捕获全部主要收益；
4. 现有 batch/localized update 未捕获全部主要收益；
5. 可实现收益置信下界高于 bookkeeping/runtime overhead 上界；
6. Recall、active set 和 visibility closure 通过；
7. 至少两个数据源、两种 chunking policy 和两个系统/算法边界复现。

PASS 仅授权后续设计 gate，不代表论文成立。

### `HOLD-GEOMETRIC-CORRELATION-ONLY`

真实 group 有重叠，但与几何相近跨文档控制无差异。

此时 document identity 作为动机被否定，只允许另行审查 `correlated geometric batch update`，不得直接实现。

### `KILL-CACHE-OR-BATCH-ABSORBS-GAIN`

普通 group-local page cache或现有 batch/localized update 已吸收几乎全部可实现收益。

### `KILL-NO-GROUP-OVERLAP`

真实 revision groups 相比 matched random batches 没有稳定的 search/repair/page overlap 优势。

### `KILL-GENERIC-BATCH-REPACKAGING`

即使存在 overlap，剩余机制只等价于 batching、dedup、page cache、delayed writeback 或普通 bulk graph processing。

### `FAIL-WORKLOAD-OR-TRACE-CLOSURE`

数据 lineage、chunk identity、fork、I/O 账、源码或统计协议无法闭合。

---

## 14. Stop line

A0 完成后必须停止。

禁止自动：

- 实现 shared frontier；
- 实现 combined prune；
- 改 DGAI/OdinANN；
- 做 document-level transaction；
- 扩大到 multi-NVMe；
- 加入版本、过滤、Agent 或 embedding migration；
- 将 positive overlap 直接写成论文贡献。

下一阶段必须由 Gpt 单独审阅并给出设计 gate。
