# SnapCursor prior-art、需求真实性与 baseline 审计

**日期**：2026-07-12  
**范围**：只做独立文献、产品文档与公开实现审计；未运行实验  
**裁决**：**KILL**

## 1. 执行结论

没有发现已发表论文完整实现“动态 ANN graph 的 versioned frontier continuation”，因此这个交集不是被单篇论文直接占领；但候选仍应 Kill，因为它的两个必要前提分别被削弱：

1. **需求不足**：没有找到公开 search/RAG/agent trace 表明用户会在同一 query vector 上跨时间持续请求 page 2/3，并且要求跨 insert/delete 的固定 snapshot。Iterative RAG 通常会 reformulate query、加入新上下文或改检索目标，旧 ANN frontier 不能复用。
2. **语义已有低成本强 baseline**：Milvus SearchIterator 已固定 MVCC timestamp 并分页返回 ANN 结果；Elasticsearch/OpenSearch 可用 PIT 固定 index view；immutable segment pinning 同样直接提供 snapshot。剩余贡献只是在这些语义上保存 HNSW/DiskANN frontier 来减少重复工作。

公开系统也清楚显示，产品需要的通常是 API pagination，而非 graph-state continuation：Qdrant、Vespa、Weaviate vector pagination 都重新执行更大的/带 offset 的 ANN；Databricks Vector Search 提供 opaque `next_page_token`，但未公开 graph frontier/version机制。缺乏 workload 证明时，不能把“现有实现会重搜”自动升级成研究问题。

最终候选会退化为：

```text
generic MVCC / PIT / immutable segments
    + serialized ANN heap and visited set
    + cursor timeout / GC
```

这正中 gate 的 Kill 条件“最终贡献只剩把 MVCC 用到 ANN”。

## 2. 生产系统机制审计

| 系统 | 对外能力 | 实际/公开机制 | 对 SnapCursor 的影响 |
|---|---|---|---|
| [Qdrant](https://qdrant.tech/documentation/concepts/search/#pagination) | vector `offset + limit` | 官方明确说明内部检索 `offset + limit`，HNSW 不适合分页；不同请求可能重复/遗漏 | 不是 stateful continuation；同时说明产品接受 re-search/client materialization |
| [Vespa](https://docs.vespa.ai/en/querying/approximate-nn-hnsw.html) | `hits + offset` | 官方明确“pagination requests 之间不缓存结果”，更高 offset 会重新搜索 | 不是 stateful continuation；是强 stateless baseline |
| [Weaviate](https://docs.weaviate.io/weaviate/api/graphql/additional-operators#cursor-with-after) | `after` cursor；vector offset | `after` 只支持按 object ID 的 list query，不兼容 near-vector/BM25/hybrid；vector query 使用 offset | “Weaviate cursor”不能作为已有 vector continuation 证据 |
| [Milvus basic pagination](https://milvus.io/docs/single-vector-search.md) | limit/offset | 每页独立 search，`limit+offset < 16384` | stateless deepening baseline |
| [Milvus SearchIterator](https://milvus.io/docs/with-iterators.md) | ANN iterator，可返回 >16,384 | PyMilvus 源码固定 `guarantee_timestamp`，然后以 tail distance 为 `range_filter/radius` 重复 range search，并过滤同距离 IDs；客户端缓存页面 | 已覆盖 snapshot ANN pagination 语义，但**不复用 graph frontier** |
| [Databricks Vector Search](https://learn.microsoft.com/en-us/azure/databricks/ai-search/query-ai-search#paginate-through-results) | `next_page_token` + `query-next-page` | opaque token；公开文档未披露是否 materialize、range resume 或保存 ANN state | API claim 已占；不能声称首个 vector continuation token |
| [Elasticsearch kNN + search_after](https://discuss.elastic.co/t/does-k-nearest-neighbor-knn-search-supports-search-after-pagination/315222) | 对预先设置的大 `k` 结果分页 | approximate kNN 先产生 k matches，再对其 `search_after`；不能无限按距离继续 ANN | snapshot/materialized-result baseline |
| [OpenSearch PIT](https://docs.opensearch.org/latest/search-plugins/point-in-time/) | PIT + search_after | 固定索引视图并按 sort value 续页 | generic snapshot baseline，不保存 ANN frontier |

### 2.1 Milvus SearchIterator 是最强 baseline

公开 PyMilvus `SearchIterator` 源码提供了关键事实：

- 初始化第一页后读取 `session_ts`，后续请求把它设为 `guarantee_timestamp`；
- 保存 tail distance 和一个自适应 width；
- 下一页通过 `radius/range_filter` 搜索新的距离环；
- 对边界同分 IDs 显式过滤，避免跨页重复；
- 页面在 client-side iterator cache 中保存；
- 它没有保存 HNSW candidate heap、expanded set 或 visited set。

所以 SnapCursor 不能再以“没人定义 ANN snapshot pagination”立项。准确的 gap 只是：

> 相比 Milvus 的 MVCC-pinned repeated range search，保存底层 graph traversal state 是否在真实跨页 workload 中显著省 I/O/距离计算，同时值得承担 version retention？

这是性能优化假设，不是新的查询语义。

## 3. 需求真实性审计

### 3.1 Search pagination 存在，但 deep ANN continuation 不是主流需求

Qdrant、Milvus、Vespa、Weaviate、Elastic 和 Databricks 都暴露某种分页形式，证明 UI/API pagination 不是虚构需求。但它们的共同做法是：

- 预取一个较大的 top-k 后在结果内分页；
- offset + re-search；
- range-based iterator；
- client/server materialized result + token。

Qdrant 甚至直接建议一次取较大 batch 后由客户端分页，以避免 approximate ranking 跨请求抖动。生产系统愿意接受这些方案，说明“必须保存图搜索状态”的需求尚未成立。

### 3.2 RAG/agent 并不能自动提供 workload

已知 iterative retrieval 路线（FLARE、IRCoT、Iter-RetGen、query expansion、multi-hop retrieval）通常在每轮：

- 根据生成中的不确定内容构造新 query；
- 加入上一轮 evidence；
- 改变 filter、budget 或 retrieval target；
- 从 document retrieval 转到 graph/entity retrieval。

这不是同一 query 的 top-20 → 21–40。查询向量变化后，旧 frontier、visited set 与 score boundary 均不再有效。2026 年名为“Progressive Searching for Retrieval in RAG”的工作也指低维到高维的分层搜索，而非分页 continuation。

本轮未找到公开 agent memory trace 同时包含：相同 query identity、连续 top-k expansion、跨 index update、严格 no-duplicate/snapshot 要求。没有这四项，不能把 agent 热度当需求证据。

### 3.3 动态版本语义已有普通解法

Milvus iterator 的 MVCC timestamp、OpenSearch/Elastic PIT、immutable segment pinning 都能给 page 1/2 同一逻辑可见性。若需要 fresh semantics，现有系统通常允许 eventual/bounded/session consistency，而不是维护旧 graph adjacency。

SnapCursor 的 epoch adjacency、update log replay、cursor-aware GC 只有在“保存 frontier 的收益很大，且 immutable segment/MVCC retention 很贵”时才必要。本轮没有需求或公开成本数据支持这两个条件。

## 4. 学术 prior art 与缺口

Survey 所说 incremental search 确实是一个未完全解决的接口问题；HNSW、NSG/Vamana、DiskANN 的内部 beam/heap 理论上可暂停。但本轮没有找到同行评审工作同时提供：

- dynamic graph snapshot cursor；
- bounded visited/frontier state；
- versioned adjacency retention/replay；
- cursor-aware graph GC；
- 跨页 recall/no-duplicate 语义。

这个“没人完整做过”不足以推翻 Kill。其组件分别是标准 graph-search state serialization、MVCC/copy-on-write、snapshot retention 和 GC。缺少真实 workload 或不可由 baseline 达到的性能/状态矛盾时，只是已知机制组合。

## 5. 最强 baseline 审计

任何未来复议都必须先击败以下 baseline；当前不批准实验：

1. 一次性 top-40/top-100 后 client pagination；
2. Qdrant/Vespa-style `offset+limit` re-search；
3. Milvus SearchIterator 的 MVCC timestamp + distance-ring range searches；
4. server-side materialized full result/heap；
5. immutable segment snapshot / PIT + search_after；
6. copy-on-write/shadow index snapshot；
7. 保存完整 ANN frontier + exact visited set，不做压缩；
8. cursor 超时后直接 restart。

尤其不能先设计 Bloom visited set、replay log 或 cursor GC。只有完整 frontier baseline 的状态真的大、Milvus-style range search 重复成本真的高、snapshot segment retention 真的贵，才有机制空间。

## 6. Kill 原因

| Gate 条件 | 本轮证据 | 结果 |
|---|---|---|
| 真实 workload 需要跨更新一致分页 | 未找到公开 trace；iterative RAG 多为 query reformulation | 失败 |
| snapshot 语义尚未解决 | Milvus MVCC iterator、PIT、immutable segment 已覆盖 | 失败 |
| stateful continuation 有独特系统语义 | 剩余差异仅 graph frontier reuse | 失败 |
| 现有 API 尚无 vector continuation | Milvus SearchIterator、Databricks token 已存在 | 失败 |
| 贡献不是 MVCC + saved heap | 当前无法越过该组合 | 失败 |

最终裁决：

```text
Status: KILL
Reason: requirement not demonstrated; snapshot semantics already have low-cost baselines;
        remaining novelty is graph-frontier reuse without a public workload.
Experiment: NOT APPROVED
```

若未来出现公开 agent/search trace，证明同一 vector query 会多次扩展、持续跨更新且 re-search I/O 占主导，可重新提出一个**纯 requirement gate**；在此之前不保留为 active candidate。
