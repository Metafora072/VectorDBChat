# DecoupleVS Residual Characterization Gate

**日期**：2026-07-13
**状态**：批准 characterization 与 faithful reproduction；不批准组合式系统实现
**主线问题**：DecoupleVS 在恢复解耦架构查询性能后，是否仍存在与两阶段 I/O 语义直接相关、且值得独立设计的新瓶颈？

---

## 1. 前序裁决

PageMaxSim residual multi-ball Stage A 的关闭成立。

A0 证明 codeword grouping 后存在更紧的理论 envelope，但 A1 的 outward-safe multi-ball certificate 在所有配置上仍读取全部页面。该结果应准确表述为：

```text
Residual-certified exact PageMaxSim admission 关闭
```

不外推到所有 approximate page admission，但当前方向冻结，不继续堆叠 synopsis。

主线正式转向 DecoupleVS residual。

---

## 2. 对当前讨论的修正

Claude 提出的演进链条是合理的：

```text
DGAI 暴露解耦查询代价
    ↓
DecoupleVS 通过 latency-aware search 与 compression 修复
    ↓
寻找 DecoupleVS 修复后仍存在的 residual
```

但不能直接把 look-ahead、page search 和 intelligent cache 全部迁移到解耦架构。那会成为：

```text
三个已有机制
+ 一个新系统
+ 尚未确认的瓶颈
```

正确顺序是先确定唯一主导 residual，再围绕它形成系统。

Codex 提出“下一基线必须包含 DecoupleVS”原则正确，但 D0 不应强制等待官方 artifact。当前论文只承诺最终版本开源，若源码尚未发布，项目不能无限阻塞。

---

# 3. 当前最值得验证的 residual

## 3.1 首选：Late-Stability Prefetch Gap

DecoupleVS 的 latency-aware search 使用一个明确的阶段边界：

```text
graph traversal
    ↓
连续 B 个候选未替换 K+B heap
    ↓
candidate set 被视为 stable
    ↓
开始向量 prefetch
```

这个策略在普通查询上有效，但困难查询和高 recall 查询可能持续替换 heap，使稳定点很晚出现。

由此可能产生：

```text
traversal 已接近结束
    ↓
vector prefetch 才开始
    ↓
vector I/O 无法与 traversal 充分重叠
    ↓
reranking tail 暴露在关键路径
```

论文自身已经显示，在非常高的 recall 区域，自适应预取的机会缩小，DecoupleVS 与 PipeANN 的 P99 差距趋于收敛。因此该 residual 有明确的论文内证据，不是凭空构造。

潜在问题不是“预取还不够多”，而是：

> DecoupleVS 把 traversal 与 vector fetch 分成两个阶段，但 candidate confidence 实际是连续演化的；固定稳定阈值无法充分利用早期但有价值的候选信号。

如果成立，后续设计空间可能是 continuous dual-frontier execution，而不是简单调小 B。

---

## 3.2 次选：Concurrent-Update Tail

DecoupleVS 在并发更新实验中具有较好的 throughput 和 P50，但 P99 明显落后 OdinANN。该问题真实，但它主要来自 batch merge/update path，而不是 latency-aware search 本身。

可能的故事为：

```text
compressed decoupled storage
+ in-place graph update
+ log-structured vector update
```

但论文已经指出 OdinANN 的 delta-neighbor pruning 可以正交加入。因此若贡献只是移植 OdinANN update mechanism，论文空间较弱。

本轮只记录该现象，不与 search residual 混合。

---

## 3.3 暂不优先：Compression CPU

DecoupleVS 的实验中：

```text
graph decompression + vector decompression
≈ 4.1% average query latency
```

这不足以支撑“现代 NVMe 下解压成为主要瓶颈”的当前叙事。

除非新的高维数据、低延迟 SSD 或更高并发实验显示该比例显著扩大，否则不优先研究。

---

## 3.4 暂不优先：Generic Cache Replacement

DecoupleVS 已通过压缩邻接表和 LRU 获得较高 graph cache hit，并把平均 graph I/O 降至较低水平。

固定 worst-case entry size 确实可能浪费内存，但这首先是 cache capacity efficiency 问题，不等于端到端查询瓶颈。

只有在低 DRAM、热点漂移或多租户 workload 下证明 LRU 明显失效后，才能单独讨论缓存机制。

---

# 4. Artifact 不可用时的执行方案

## R0：构建 DecoupleSearch-R

若官方 DecoupleVS artifact 尚未发布，不等待完整源码，而是在现有 PipeANN/io_uring 基础上实现一个明确标注的 reproduction：

```text
DecoupleSearch-R
```

它不是完整 DecoupleVS，也不能在报告中声称复现官方系统。它只复现 §3.4 latency-aware search 所需的最小机制：

1. 从同一 DiskANN/Vamana index 导出独立 graph 与 vector files；
2. graph traversal 只读取邻接数据；
3. 使用内存 PQ 维护 `K+B` heap；
4. 连续 B 个 expanded candidates 不替换 heap 后触发 prefetch；
5. 使用 `W - inflight_traversal_IO` 作为 vector prefetch budget；
6. 向量分批 rerank；
7. 使用 benefit ratio 决定终止；
8. graph/vector 均使用与 PipeANN 相同的 io_uring backend。

第一阶段不实现：

* Elias-Fano；
* XOR-delta/Huffman；
* segment GC；
* batch update；
* variable-size hierarchy。

原因是论文 ablation 已经把 `DecoupleSearch` 与 compression 分开。对首选 residual 而言，复现 latency-aware search 即可，不需要先复制完整 19K LoC 系统。

---

# 5. R0 正确性检查

DecoupleSearch-R 不要求精确匹配论文绝对性能，但必须重现以下定性关系：

```text
naive decoupling
    → 因额外 vector I/O 明显退化

latency-aware search
    → vector I/O 从 traversal 关键路径移出
    → 相比 naive decoupling 明显恢复
```

必须使用：

* 同一个 base graph；
* 同一个 PQ；
* 同一个 vector representation；
* 同一个 io_uring backend；
* 同一 recall；
* 同一缓存预算；
* 同一 NVMe。

若无法重现这种基本趋势，应优先审计实现，不进入 residual 结论。

---

# 6. R1：Late-Stability Characterization

逐 query 记录：

## Traversal evolution

* explored candidate 数；
* 总 traversal rounds；
* 每轮 heap replacements；
* `K+B` heap 首次填满时刻；
* 连续无替换长度；
* stability trigger 时刻；
* trigger 后剩余 traversal 比例。

## Prefetch behavior

* 每个 vector prefetch 的 issue/complete 时刻；
* prefetch 与 traversal overlap；
* traversal 完成时尚未完成的 vector I/O；
* prefetched vectors 最终是否参与有效 rerank；
* wasted prefetch 数与 bytes；
* rerank batch 数；
* benefit ratio 变化。

## Query tail

* p50/p95/p99；
* traversal critical path；
* exposed vector-fetch tail；
* PQ compute；
* exact rerank；
* device queue wait。

---

# 7. 实验轴

## Recall

不能只测论文默认点，需要从中等 recall 扫描到非常高 recall，以观察稳定点是否系统性后移。

## Query difficulty

不预先用人工标签划分困难查询。使用执行特征定义：

* visited nodes；
* traversal rounds；
* heap replacement 次数；
* stability position；
* baseline latency。

报告这些连续变量与 exposed vector-fetch tail 的关系。

## Parameters

扫描：

* candidate list size L；
* beam width W；
* rerank batch B。

B 的扫描首先用于判断：

> 当前问题能否仅通过调参解决？

若每个 workload 只需选择一个固定 B 即可达到最佳 frontier，则方法空间较弱；若最优 B 在 query 之间显著变化，才支持 query-adaptive design。

---

# 8. R2：互斥上界

## Oracle A：Final-Candidate Prefetch Oracle

离线知道最终需要 rerank 的 candidates，并在其首次进入活跃 frontier 时立即发起 vector read。

回答：

```text
当前稳定触发规则损失了多少可重叠窗口？
```

## Oracle B：Earliest-Safe Stability Oracle

离线找到不会再改变最终 rerank 集合的最早时刻。

回答：

```text
固定 B 连续无替换，相比真正稳定点晚了多少？
```

## Oracle C：Bandwidth-Allocation Oracle

在每轮固定总 I/O budget 下，离线分配：

```text
traversal I/O
vs.
vector-prefetch I/O
```

回答：

```text
当前 W - inflight traversal 的剩余带宽规则是否次优？
```

Cache 和 compression oracle 暂不进入第一轮，避免同时打开三个机制方向。

---

# 9. 判断标准

本轮不采用固定的“30% residual”或“20% oracle improvement”作为机械 Kill 阈值。

进入设计需要同时观察到：

1. late stability 与 query difficulty／高 recall 存在稳定关系；
2. exposed vector-fetch tail 对 p95/p99 有可解释贡献；
3. oracle 能形成当前固定 B 调参无法达到的新 latency–I/O–recall Pareto 点；
4. 改善不是单纯增加总 I/O 或牺牲 recall；
5. 至少在两个性质不同的数据集上出现相同机制趋势。

若 residual 存在但固定 B sweep 已能解决，则论文可以保留 characterization finding，但不立即开发复杂系统。

若 residual 主要出现在极端 recall，仍不自动否定；需要判断该 recall 区域是否对应真实高质量检索需求。

---

# 10. 可能的设计方向

只有 R1/R2 支持后才进入设计。

可能的系统抽象为：

```text
Continuous Dual-Frontier Search
```

同时维护：

```text
Traversal frontier
Vector-fetch frontier
```

vector fetch 不再等待离散 stable 状态，而根据候选持续存活、PQ rank persistence、剩余 traversal budget 和设备 I/O budget连续推进。

潜在贡献不是“给 DecoupleVS 加 look-ahead”，而是：

> 将 decoupled graph search 从 phase-separated execution 改为 jointly scheduled dual-frontier execution。

该机制必须正面对比：

* DecoupleVS fixed stability；
* tuned per-workload B；
* LAANN-style look-ahead；
* simple earlier-prefetch；
* unlimited speculative prefetch。

---

# 11. Codex 下一任务

执行顺序：

```text
R0：DecoupleSearch-R reproduction
R1：late-stability characterization
R2：三个 prefetch-specific oracles
```

输出：

```text
codex/share/decouplevs_late_stability_characterization_r0_r2_0713.md
```

若官方 artifact 在执行期间发布，优先追加官方系统验证，但不阻塞 R0。

本轮不实现：

* cache replacement；
* compression redesign；
* page layout；
* update mechanism；
* complete dual-frontier system。

完成 R2 后停止，由 Gpt 根据数据决定是否进入设计。
