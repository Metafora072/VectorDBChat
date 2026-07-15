# E1–E3 快速 prior-art 扫描：RAG、Learned ANNS 与 LLM 推理

日期：2026-07-12

## 执行摘要

PZ 将目标会议从 FAST/VLDB 扩展至 NeurIPS、ICML、ICLR、KDD、WWW、MLSys 等 AI/ML 会议，这确实允许算法—系统混合贡献，但不会降低 novelty 门槛。对 Claude 提出的 E1–E3 各核验至少五个直接或强相邻竞争者后，结论如下：

| 方向 | 竞争密度 | 裁决 | 仍可验证的最窄问题 |
|---|---:|---|---|
| E1 RAG 向量索引层 | 中高 | **REVISE / Continue-to-problem-validation** | 可变文档在 re-chunk/re-embed 时的原子版本切换，以及以 downstream answer quality 定义的 freshness SLO |
| E2 learned ANNS components | 高 | **KILL generic direction** | learned routing、entry、termination 已逐项覆盖；没有新 workload/guarantee 时不再发散 |
| E3 LLM inference ANN | 极高 | **KILL generic direction** | KV retrieval、retrieval-based speculative decoding、semantic cache 已形成三个拥挤子赛道 |

E1 是唯一值得继续做问题验证的方向，但不能以“RAG 需要 freshness”直接立项。普通增量 ETL、vector upsert、timestamp rerank 和重新 embedding 都是工程常识；论文问题必须收紧为：**一次 source edit 改变 chunk boundaries 并产生一组新增、失效和替换向量时，如何让读者只观察到完整的旧知识快照或完整的新知识快照，并以 answer-affecting staleness 而非单条 vector visibility 作为 SLO。** 这属于 RAG lifecycle 与 DB-native ANN 的交叉，而不是新的 ANN search kernel。

## 1. E1：RAG 系统的向量索引层

### 1.1 Top-5 直接/强相邻竞争者

| 工作 | Venue / 状态 | 已覆盖问题 | 对 E1 的边界 |
|---|---|---|---|
| [RAPTOR](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html) | ICLR 2024，peer-reviewed | 递归 embedding、clustering、summarization，形成多层 tree retrieval | paragraph/sentence/summary 多粒度索引不是空白 |
| [PipeRAG](https://www.amazon.science/publications/piperag-fast-retrieval-augmented-generation-via-adaptive-pipeline-parallelism) | KDD 2025，peer-reviewed | retrieval 与 generation pipeline parallelism、动态 retrieval interval、质量—延迟模型 | index/search 与 generation 的 algorithm-system co-design 已有直接先例 |
| [RAGO](https://people.csail.mit.edu/suvinay/pubs/2025.rago.isca.pdf) | ISCA 2025，peer-reviewed | RAGSchema、跨 RAG variant characterization、自动 schedule optimization | “端到端而非只看 recall”的 system optimizer 已被覆盖 |
| [RAGCache](https://dl.acm.org/doi/10.1145/3768628) | ACM TOCS 2026，peer-reviewed | knowledge-tree KV states、GPU/host multi-level cache、RAG-aware replacement、retrieval/inference overlap | RAG-aware cache/storage hierarchy 已被覆盖 |
| [KET-RAG](https://arxiv.org/abs/2502.09304) | 2025 preprint | KG skeleton + text，cost-efficient multi-granular indexing，联合报告 index cost、retrieval、generation quality | “多粒度 + token/cost aware”已有直接竞争者，但尚非正式发表 |

补充边界：

- [Cache-Craft, SIGMOD 2025](https://dl.acm.org/doi/10.1145/3725273) 已处理任意位置/上下文下的 RAG chunk KV reuse，说明 chunk-level serving cache 也不是空白。
- [E²-RAG, COLM 2025](https://openreview.net/forum?id=ZZ4tcxJvux) 直接讨论 INSERT/DELETE/UPDATE knowledge，并编辑压缩 KV cache；它不等价于 vector-index atomic refresh，但会攻击“RAG knowledge update 首次被研究”的表述。
- [HoH, ACL 2025](https://aclanthology.org/2025.acl-long.301/) 证明 outdated information 即使与新信息共存也会降低回答质量，给 freshness 问题提供了高质量 benchmark 和真实性证据。
- [Streaming RAG](https://arxiv.org/abs/2508.05662) 已提出 streaming prototypes、incremental upsert 与有限内存；虽为 preprint，但会攻击“首次实时 RAG index”叙事。
- [CRUD-RAG](https://arxiv.org/abs/2401.17043) 是 benchmark 而非 index system，但已系统评估 knowledge-base construction、retriever、context length 与 generation。

### 1.2 Claude 初始五个需求的覆盖情况

| 初始需求 | 覆盖判断 | 说明 |
|---|---|---|
| Freshness SLA | **部分覆盖，仍有窄空格** | benchmark、streaming upsert、KV editing 都存在；缺少的不是 update API，而是 multi-vector chunk replacement 的原子可见性与 answer-level SLO |
| 多粒度索引 | **已覆盖** | RAPTOR、KET-RAG 及大量 Graph-RAG 工作直接覆盖 |
| 上下文相关检索 | **高度活跃** | Self-RAG、iterative/agentic RAG、PipeRAG 等已学习何时及如何再次 retrieval |
| downstream generation quality | **已覆盖为评价轴** | PipeRAG、KET-RAG、RAGO、CRUD-RAG 已不只报告 recall |
| token 成本意识 | **部分覆盖且快速升温** | adaptive retrieval budget、context compression、RAGO/KET-RAG 已显式优化 cost；固定 k 的批评不新 |

### 1.3 唯一建议保留的 E1-F 问题

**问题定义。** 一个 source document 的小编辑可能改变后续 chunk boundaries，导致不是“一条旧向量换一条新向量”，而是一个 document version 对应的一组 vector insert/delete/replace。若系统逐条 upsert，查询可能同时检出旧版本和新版本的 chunks；HoH 已表明过时信息与新信息并存会伤害回答。E1-F 研究的是：在 continuous ingestion 下，以 document-version 为原子单位发布向量集合，同时控制 embedding/re-index cost、search availability 与 answer-affecting staleness。

**与普通 MVCC/ETL 的区别必须证明。** 普通 shadow index、outbox、snapshot pointer 和 batch commit 已能提供原子切换。RAG-specific 贡献必须来自至少一个不可被这些基线消去的约束，例如：chunk-boundary cascade、多个粒度/多个 retriever 的跨索引一致发布、generation quality 对短暂 mixed-version results 的非线性敏感性，或在 freshness deadline 下的选择性 materialization。

**下一步仅做需求/证据门禁，不实现系统。**

1. 选择带真实 version history 的 corpus（Wikipedia revision、software docs 或 policy docs），重放 edits 与 query trace。
2. 比较 whole-document rebuild、text-diff incremental chunks、content-defined/stable chunking 三种策略，测每次 edit 引起的 changed-vector fanout。
3. 构造 mixed-version exposure，测 retrieval stale-hit 与 downstream answer quality，而非只测 index freshness latency。
4. 基线必须包含 document-level shadow generation + atomic pointer flip；如果它已经同时满足 freshness、availability 和成本，立即 Kill。

**预注册 Kill。** 中位 edit 只影响极少 chunks，普通 diff-upsert 足够；mixed-version exposure 对 answer quality 无显著影响；shadow-index/pointer-flip 的额外空间与延迟可接受；或问题仅在一个特制 corpus 上成立。通过这些门禁前，E1-F 只能标记为 `Problem-to-validate`。

## 2. E2：向量搜索的学习化组件

### 2.1 Top-5 直接竞争者

| 工作 | Venue / 状态 | 已覆盖组件 |
|---|---|---|
| [Learning to Route in Similarity Graphs](https://proceedings.mlr.press/v97/baranchuk19a) | ICML 2019 | 学习 vertex representations 与 routing function，缓解 graph local minima |
| [Learned Adaptive Early Termination](https://dl.acm.org/doi/10.1145/3318464.3380600) | SIGMOD 2020 | 根据 query/search state 预测何时终止 ANN search |
| [Adaptive Entry Point Selection](https://arxiv.org/abs/2402.04713) | 2024 preprint | query-adaptive graph entry point 的理论上界与实证 |
| [Probabilistic Routing](https://proceedings.mlr.press/v235/lu24l.html) | ICML 2024 | 用带概率保证的 PEOs 决定哪些邻居需要 exact distance；HNSW/NSSG 上直接验证 |
| [GATE](https://arxiv.org/abs/2506.15986) | 2025 preprint | 学习 optimal entry point，增强 proximity graph 的 adaptive awareness |

此外，RoarGraph 已针对 OOD query 设计 query-aware heterogeneous graph，Quake 已根据 workload 动态调整 partition，PAG/PEOs 等继续挤压 routing/pruning 空间。

### 2.2 裁决

Claude 列出的 learned beam width、learned entry、learned pruning/routing、learned termination 四项已经逐项存在直接 prior art。因此 **E2 作为 generic direction 直接 Kill**。把 loss、classifier 或 GNN 换一种并不足以形成 AI 会议 novelty。

若未来重审，必须先给出传统工作没有的约束，例如可验证 recall/SLO、强 distribution drift 下的 safe fallback、持续插入下无需 retraining，或 GPU/SSD I/O cost 被纳入 decision objective；而且要先证明普通 analytical/adaptive policy 无法达到相同 frontier。当前不建议继续搜索或做 pilot。

## 3. E3：面向 LLM 推理的近似搜索

E3 实际包含三个不同赛道，不能合并成一个 idea。

### 3.1 KV cache / sparse attention retrieval

| 工作 | Venue / 状态 | 核心覆盖 |
|---|---|---|
| [Quest](https://arxiv.org/abs/2406.10774) | ICML 2024 | query-aware Top-K KV pages；page min/max metadata |
| [InfiniGen](https://www.usenix.org/conference/osdi24/presentation/lee) | OSDI 2024 | 从 host memory 只预取推测为 critical 的 KV entries |
| [MagicPIG](https://arxiv.org/abs/2410.16179) | ICLR 2025 | LSH sampling + CPU/GPU heterogeneous attention approximation |
| [RetrievalAttention](https://proceedings.neurips.cc/paper_files/paper/2025/file/4e36d4049fb0fea195a8267c8dcd0824-Paper-Conference.pdf) | NeurIPS 2025 | 在 CPU KV vectors 上建立 attention-aware ANNS index，并在生成时 vector retrieval |
| [RetroInfer](https://www.microsoft.com/en-us/research/publication/retroinfer-a-vector-storage-engine-for-scalable-long-context-llm-inference/) | 2025 preprint / Microsoft Research | 直接把 KV cache 重述为 vector storage engine；WAVE index、accuracy-bound estimation、segmented clustering |

强相邻工作还有 [PQCache](https://arxiv.org/abs/2407.12820) 的 product-quantized KV retrieval，以及 2026 的 [ParisKV](https://arxiv.org/abs/2602.07721) 对 drift-robust GPU-native retrieval 的直接优化。由此，“用 ANN 检索重要 KV”已经是明确且拥挤的赛道，不是开放命题。

### 3.2 Retrieval-based speculative decoding

- [REST](https://aclanthology.org/2024.naacl-long.88/)（NAACL 2024）使用字符串/datastore retrieval 生成 draft tokens。
- [NEST](https://proceedings.neurips.cc/paper_files/paper/2024/hash/93c099bb4cde51b724eaa6d6d4a4b5e4-Abstract-Conference.html)（NeurIPS 2024）直接使用 nearest-neighbor datastore 支持 generation 与 attribution。
- [DReSD](https://arxiv.org/abs/2502.15572)（ACL Findings 2025）已经以 contextualized token embeddings + ANN 替代 sparse retrieval，并报告 acceptance 与 generation speed。

因此，“speculative decoding 的 candidate 用 embedding ANN”已被 DReSD 直接覆盖。

### 3.3 Semantic prompt/response cache

MeanCache、vCache、VectorQ、QVCache 及 continuous semantic caching 已分别研究 semantic equivalence threshold、online boundary、bounded error 与 cache admission。这里的核心风险不是缺少 ANN，而是语义等价性、invalidations 和错误复用。若只把 prompt embedding 放入 HNSW，贡献不足。

### 3.4 裁决

**E3 作为 generic direction Kill，且不建议作为 PZ 的优先赛道。** 它的竞争密度比驻盘 ANN 更高，实验通常需要多种 LLM、GPU kernels 与 end-to-end serving stack，和 PZ 当前存储系统资产的复用度低。未来若有非常具体的 storage/lifecycle 问题可单独审查，但不应从“LLM serving 很热”反推 idea。

## 4. 综合排序与下一步

1. **E1-F：RAG document-version atomic refresh** — 唯一保留，状态为 `Problem-to-validate`。先做 workload/quality evidence，不实现系统。
2. **E2：generic learned components** — Kill。已有 ICML/SIGMOD/ICML 直接工作覆盖 routing、termination、entry 与 pruning。
3. **E3：generic LLM inference ANN** — Kill。KV retrieval、speculative decoding 与 semantic cache 三个子赛道均已有强竞争者。

建议把下一轮问题交给 Claude/Gpt 的不是“E1 能否设计系统”，而是两个更严格的问题：

1. mixed-version chunks 是否在真实 revision trace 上造成可测量的 answer-level harm？
2. document-level shadow build + atomic pointer flip 是否已是足够强且廉价的答案？

只有第一个为 yes、第二个为 no，E1-F 才值得设计 G0；否则扩展到 AI 会议也不改变 Kill。
