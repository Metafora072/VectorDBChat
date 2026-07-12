# SetPageANN prior-art、需求真实性与 baseline 审计

**日期**：2026-07-12  
**范围**：只做独立文献、公开实现与需求审计；未运行实验  
**裁决**：**PROVISIONAL，但仅保留 multi-page visual late interaction 分支**

## 1. 执行结论

原始表述需要大幅收紧。2026 年预印本 [Col-Bandit](https://arxiv.org/abs/2602.02827) 已经把 late-interaction reranking 建模为 finite-population top-k identification，维护部分 document score 的不确定性界，并按需揭示 `(document, query-token)` MaxSim 项；它在 BEIR 与 REAL-MM-RAG 上报告最高约 5–8× MaxSim FLOP reduction 和较高 top-k overlap。因而以下声称已经不能使用：

> 首个渐进求值 MaxSim、首个跨候选 uncertainty scheduler、首个根据 top-k boundary 跳过 late-interaction 工作。

仍未发现直接工作同时覆盖以下交集：

```text
SSD-resident multi-page multi-vector object
        +
physical token-page groups and synopsis
        +
page-safe score bounds
        +
cross-object page-read scheduling
        +
I/O / metadata / ranking-fidelity joint accounting
```

不过，这个空白对普通 text ColBERT 很可能不成立。ESPN 实测每个 BOW embedding 约 2–10 KiB，即通常只有 1–3 个 4 KiB pages；PLAID、WARP、EMVB、SPLATE、IGP 又在进入 full refinement 前减少 document 或 token 工作。真正具有多页内部选择空间的是 ColPali/ColQwen 一类 visual document retrieval：一个 page 常有约 1,024 个 patch embeddings，Col-Bandit 也已在 REAL-MM-RAG 上证实其中存在 query-time interaction redundancy。

因此只给出窄 **PROVISIONAL**：下一 problem gate 必须围绕“multi-page visual object 的 page-aware I/O”，并把 Col-Bandit 作为第一算法 baseline。若回到 text-only ColBERT、只做 token pruning、只把 mmap 换成 async I/O，或只把 Col-Bandit 的计算顺序映射到页，均应 Kill。

## 2. 最接近的 prior art

| 工作 | 状态 | 已覆盖内容 | 对 SetPageANN 的影响 |
|---|---|---|---|
| [Col-Bandit](https://arxiv.org/abs/2602.02827) | 2026 preprint | query-time partial MaxSim、uncertainty-aware top-k identification、跨 document 调度、BEIR + REAL-MM-RAG、最高约 5–8× FLOP reduction | **最强直接竞争者**；吃掉 progressive evaluation 与 uncertainty scheduler 的算法 novelty |
| [ESPN](https://arxiv.org/abs/2312.05417) | ISMM 2024 | multi-vector table 驻 SSD、GDS async I/O、ANN-guided prefetch、early rerank、top-64/128 object partial rerank | 吃掉 disk residency、prefetch、I/O overlap 与 object-level progressive baseline |
| [PLAID](https://arxiv.org/abs/2205.09707) | CIKM 2022 | centroid interaction/pruning、分阶段 candidate elimination、最终 residual decompression + exact MaxSim | page oracle 必须在 PLAID pruning 后计算，不能从 vanilla full corpus 起算 |
| [WARP](https://arxiv.org/abs/2501.17788) | SIGIR 2025 | selected-cluster token retrieval、missing-similarity imputation、implicit decompression、two-stage reduction | 已避免 gathering complete document representation；page method 必须证明比 selected-token execution 更优 |
| [EMVB](https://arxiv.org/abs/2404.02805) | 2024 | bit-vector prefilter、PQ direct scoring、per-document term filtering | 已在最终阶段减少至少约 30% scored terms 且不降低 MRR@10；是 token pruning 强 baseline |
| [DESSERT](https://arxiv.org/abs/2210.15748) | NeurIPS 2023 | vector-set search、hash/inverted candidate generation、概率保证 | 覆盖 set-search algorithm，不覆盖 page I/O |
| [IGP](https://www4.comp.polyu.edu.hk/~csmlyiu/conf/SIGIR25_IGP.pdf) | SIGIR 2025 | proximity-graph multi-vector candidate generation | 进一步压缩 refinement candidate 数，削弱绝对 page-read 需求 |
| [SPLATE](https://arxiv.org/abs/2404.13950) | 2024 preprint | sparse first stage；约 50 candidates 即可匹配 PLAID effectiveness | 构成少候选 rerank baseline |
| [ColBERT-serve](https://arxiv.org/abs/2504.14903) | ECIR 2025 | compressed tensors mmap、top-200 first stage、低内存并发 serving | 覆盖 CPU/mmap 驻盘路径；不是 intra-object progressive page evaluation |
| [LEMUR](https://arxiv.org/abs/2601.21853) / [MUVERA](https://arxiv.org/abs/2405.19504) | 2026 preprint / NeurIPS 2024 | multi-vector → single/fixed-dimensional representation | 是绕过 full multi-vector I/O 的 representation baseline |

### 2.1 Col-Bandit 与候选的精确边界

Col-Bandit 与 SetPageANN 的共同核心是：在候选对象之间选择下一份 MaxSim 工作，根据 score uncertainty 判断 top-k 是否稳定。区别只剩：

- Col-Bandit 的 revealed unit 是 `(document, query-token)` MaxSim entry，而非物理 token page；
- 它优化计算覆盖率/FLOPs，数据默认已可访问，未联合 SSD page placement 与 read amplification；
- 它使用带可调 relaxation 的统计 decision bounds，未提供“相同 exact top-k”的确定性 page synopsis；
- 它不研究 synopsis bytes、4 KiB useful-byte ratio、cold/warm cache、并发 I/O。

这意味着 SetPageANN 不再是独立的新算法，而只能是一个 storage-aware co-design 问题。论文必须证明，物理 page coupling 使直接执行 Col-Bandit 次序明显次优，并由此需要新的 synopsis/layout/scheduler；否则就是 Col-Bandit + SSD engineering。

### 2.2 ESPN 已经覆盖的 page/block 边界

ESPN 不只做 object-level SSD offload。其论文明确：

- 对齐 CLS/BOW embedding，使小于 I/O block 的对象从两次 block read 降为一次；
- 数据集中 BOW embedding 约 2–10 KiB；稍超过 I/O limit 会为少量尾部读取额外 block；
- 4 KiB GDS I/O 难以跑满带宽，并建议更大 block 和 packing；
- top-64/128 partial rerank 可用约 0.3–0.7% quality loss换 8–16× bandwidth reduction。

所以“发现跨页尾部浪费”“对齐/packing”“更大 I/O”“减少 object 数”都不是 novelty。唯一未覆盖的是**对象内部 query-dependent page skipping**。

## 3. 需求真实性

### 3.1 Text ColBERT：需求偏弱

ESPN 的 2–10 KiB/object 意味着多数对象只有少量 pages。即使存在 token contribution skew，page scheduler 也只有 1–3 次离散决策；再叠加以下 reduction：

- PLAID centroid stages 只把少量 candidate 送入 residual decompression；
- WARP/XTR 不收集完整 document representation，而只处理 selected clusters/tokens；
- EMVB 在 per-document final scoring 前继续过滤 terms；
- SPLATE 可把 exact MaxSim rerank candidate 压到约 50；
- ESPN object-level partial rerank 把 1000 降至 64–128。

因此不能以“1000 objects × 1–5 pages”作为默认 workload。对 text branch，最可能结果是 candidate/token pruning 已经拿走主要收益，page 层只回收尾页碎片。

### 3.2 Visual late interaction：需求真实但未被系统化

Visual document models 常把整页编码为约 1,024 patch vectors；即使量化后，一个逻辑 page/object 也会跨很多 4 KiB storage pages。此时：

- 对象内确实存在十几到几十个物理读取决策；
- query 只关心页面中特定区域/patch，贡献分布天然稀疏；
- Col-Bandit 在 REAL-MM-RAG 上的结果独立证明了 multimodal MaxSim interaction 存在显著 query-time redundancy；
- 但当前结果只证明 FLOP redundancy，不证明 page-locality、safe bound 紧度或端到端 I/O criticality。

这是 PROVISIONAL 的唯一需求基础。候选名称也不应再默认等同 DiskColBERT；更准确的工作对象是 **page-resident visual multi-vector object refinement**。

## 4. 最强 baseline 审计

未来若 Gpt 批准 problem gate，缺少任一项都不能立项：

1. **Full object**：document-contiguous compressed tensor + exact Full-MaxSim。
2. **现有 SSD**：ESPN exact GDS path、ANN prefetch、top-64/128 partial rerank；CPU 环境至少构造语义等价 direct-I/O model。
3. **Candidate pruning**：PLAID、WARP/XTR、SPLATE/IGP 级 candidate sets，而非自造宽松 candidates。
4. **Token/interaction pruning**：EMVB per-document filtering、token pooling/pruning。
5. **最强直接算法**：Col-Bandit 在相同 candidate、相同 ranking-fidelity 下的 revealed entries、FLOPs 与按现有 layout 映射后的 page reads。
6. **Representation alternatives**：MUVERA/LEMUR/constant-space representation 在相同 quality 下的 bytes/latency。
7. **Oracle**：预知 token contributions 的 page oracle；同时给出不受 physical grouping 限制的 interaction oracle，以分离“算法可跳过”与“page layout 能兑现”的收益。
8. **Simple layout/schedule**：document contiguous、spatial contiguous、centroid-grouped、representative-first sequential、Col-Bandit order + ordinary page cache。

关键公平性是：所有 baseline 必须在同一 compressed representation、同一 candidate set、同一 cache budget 和同一 top-k fidelity 下比较。不能把 exact page method 与有损 token/object baseline混成一个 Pareto 点。

## 5. Requirement gate 前必须回答的问题

当前不批准实验，但下一 gate 的问题应固定为：

1. 在 PLAID/WARP/Col-Bandit 后，**每个候选实际触达多少 distinct 4 KiB pages**？不是原始 token 数。
2. page oracle 相对 `Col-Bandit + document/spatial contiguous layout` 还有多少额外可回收 I/O？
3. safe bound 是否在读少量 pages 后足够紧；若必须读大多数页，立即 Kill。
4. synopsis、offset、scheduler state、alignment padding 是否计入总 bytes 和 cache budget？
5. 减少 page reads 后，cold/warm/concurrency 1/8/32 的 P95/P99 是否真的受益，还是 CPU MaxSim/解压主导？
6. 结果能否同时出现在至少一个 text benchmark 和一个 visual benchmark？若 text 分支失败，只能将 claim 明确收窄为 visual-document retrieval。

## 6. 最终裁决

```text
Status: PROVISIONAL / PROBLEM GATE ONLY
Approved scope: multi-page visual late-interaction page I/O
Not approved: implementation, experiment, advisor, generic DiskColBERT revival
Primary threat: Col-Bandit (2026)
```

保留理由不是“没有人做渐进 MaxSim”，而是：已有渐进计算方法尚未回答怎样在 SSD page granularity 上兑现 savings，并且 visual multi-vector object 确实跨越足够多页面。若 Gpt 认为这一 storage delta 不足以和 Col-Bandit 区分，应在 problem gate 前直接 Kill。

