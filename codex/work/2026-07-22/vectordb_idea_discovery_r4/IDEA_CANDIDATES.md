# R4 Phenomenon Cards and Open Pool

本轮共生成 27 张 workload-first 卡。下表只在“机制同构”或“纯工程”时概念期 KILL；其余允许进入 A-1。

| ID | 背景 -> 可观察现象 -> 正式问题 | 最小机制 / 理论抓手 | Phase-0 |
|---|---|---|---|
| P01 | kNN 图被 spectral clustering/UMAP/label propagation 消费；相同 edge recall 的错误位置可能造成完全不同 cut/eigenspace 误差；在距离预算 B 下最小化下游结构误差。 | 从低预算图估计 cut/spectral uncertainty，只扩展可能改变低-conductance cut 的邻域；Laplacian/eigenspace perturbation bound。 | OPEN |
| P02 | 同数据不同种子/插入序得到不同 top-k；在 matched recall/latency 下最小化跨构建 replacement。 | stable anchors/canonical fringe；near-tie 下 epsilon-indifference 最少替换。 | OPEN |
| P03 | 推荐画像/聚合特征在同一空间频繁小幅运动；delete+insert 忽略 \(||Delta_i||<=r_i\)。 | frozen base + displacement layer + region envelope；工作量由决策边界带质量控制。 | OPEN |
| P04 | 统一 PQ/LVQ 给所有对象同样 bits；固定总字节下，排名边界附近对象的误差价值更高。 | 估计 per-object/region inversion-risk 的离散收益曲线，以 water-filling/greedy 分配 residual precision。 | OPEN |
| P05 | 文本 token/语音帧持续到达，最终 query 尚未形成；此前计算可用于最终搜索。 | 若 \(||q^*-q_t||<=rho_t\)，转移距离区间并只重开失效区域；工作量依赖路径长度与最终 margin。 | OPEN |
| P06 | 一次出现一包相近 queries；普通 batch 仍重复对象-query distance。 | query cover + pivot distance bounds + boundary split；复杂度依赖 query-packet cover number。 | OPEN |
| P07 | sharded ANN 的 local average recall 不是 coordinator 可组合契约。 | 每 shard 返回 candidate + missing-best bound，只有仍可能击败 global kth 的 shard 深化。 | OPEN |
| P08 | 两个随机化 replica 的分歧集中在 hard queries。 | 低预算双 probe + capture-recapture omission estimate，再分配追加搜索。 | OPEN（高 prior 风险） |
| P09 | near-tie 使 exact top-k 定义本身脆弱。 | certified core + epsilon fringe，在合法集合中最小化 churn。 | OPEN |
| P10 | ANN 得到 ID 后还需 NVMe/object-store payload；最终赢家常在搜索结束前出现。 | candidate survival hazard 下的异步 payload 读取调度；优化 payload-complete time 与 wasted bytes。 | OPEN |
| P11 | ANN 仅为下游 vote/action 服务；低 ID recall 不一定改变决策。 | decision certificate：只有 unseen 邻居仍可能翻转 f(Sk) 时深化。 | OPEN（高 prior 风险） |
| P12 | 一个字段希望支持 cosine/IP/L2，独立索引占三份空间。 | angular cover + norm shells 的共享索引。 | HOLD：multi-metric/reduction 先例强、场景一般。 |
| P13 | 建索引数小时内仍需服务；最大化 build horizon 的 area-under-utility。 | partial index + fallback + marginal coverage scheduling。 | HOLD：PANENE/progressive indexing 直接相邻。 |
| P14 | 对离群 query 不应强制返回结果。 | local null-distance significance + selective deepening。 | HOLD：selective/conformal retrieval 很近。 |
| P15 | 多向量实体会占满 top-k。 | entity aggregate / distinct top-k。 | KILL：MaxSim、MV-HNSW、Milvus 直接覆盖。 |
| P16 | 语义邻域 COUNT/SUM/GROUP BY。 | near head + sampled tail。 | KILL：CANDE/KDE 同构。 |
| P17 | 语料预算下只索引部分 chunk。 | submodular/query-coverage pruning。 | KILL：static passage pruning 与 2026 chunk filtering 直接覆盖。 |
| P18 | query-time metric weights 改变。 | weight-space anchors。 | KILL：multiple weighted-lp ANN/WLSH 已直接研究。 |
| P19 | query distribution shift 后 retarget index。 | hot-region maintenance。 | KILL：Quake/DQF/workload-aware maintenance。 |
| P20 | 多相关 queries 共享 entry/cache。 | traversal reuse。 | KILL：MQO/QVCache/CABANA。 |
| P21 | 逐渐增大 k / 加载更多。 | 保存 best-first frontier。 | KILL：anytime search 自然支持。 |
| P22 | 二阶段昂贵 reranker score。 | upper/lower-bound top-k。 | KILL：Threshold Algorithm/cascade/AdaCUR。 |
| P23 | 不确定向量 fresh-world top-k。 | ordered UCB enumeration。 | KILL：R3 A0 已证明 tight/sound oracle 退化。 |
| P24 | similarity-proportional sampling。 | head-tail proposal correction。 | KILL：Gumbel-MIPS/RF/MIDX/LSH sampler。 |
| P25 | capacity-constrained collective retrieval。 | Hall-deficiency expansion。 | KILL：SIGMOD 2008/STOC 2014 同构。 |
| P26 | similarity join/range/multi-k/reverse。 | 新 primitive。 | KILL：SimJoin/DiskJoin/Range Retrieval/OMEGA。 |
| P27 | 少量 exact probes 监控 recall regression。 | stratified sequential audit。 | KILL：偏监控/抽样，没有 ANN-specific 机制。 |

## A-1 shortlist

优先执行六个彼此正交的必要现象实验：

1. **P04 Ranking-Risk Precision Allocation**：先做 oracle workload-risk 分配上限；若 matched-byte 不胜 uniform/MSE，KILL。
2. **P05 Query-in-Flight ANN**：真实文本 prefixes 的最终 top-k 覆盖与可认证半径；若直到最后 token 才收紧，KILL。
3. **P03 Motion-Bounded ANN**：边界包络候选膨胀；若接近全库，KILL。
4. **P02/P09 Stable Top-k**：跨构建 churn 的 near-tie 分解；若 fixed seed/canonical tie-break 已解决，KILL。
5. **P10 Speculative Payload Materialization**：candidate survival vs wasted-byte frontier；若 winner 出现太晚，KILL。
6. **P01 Downstream-Structural kNNG**：相同 edge recall 下 spectral/cut damage 是否相差显著，以及简单 risk refinement 是否有 oracle headroom。

P07 shard certificate 暂列第七：先做更深查新和 bound 可行性，不与六个 A-1 同时消耗实现预算。

## Post-experiment / independent-review ledger

| ID | 最终证据状态 | 本轮动作 |
|---|---|---|
| P01 | A−1 phenomenon PASS；fully-connected kernel graph prior 极近，但非严格同构；缺 critical-missing-edge discovery algorithm | HOLD backlog，不是 finalist |
| P02/P09 | 高 ef 下 mean churn 小；未做 fixed seed/order 单独对照，near-tie 现象仍在 | HOLD low-priority |
| P03 | oracle affected set 可小；4,096-cell sound enumeration p95 64,047 distances、4.15× flat | KILL current spherical-cell mechanism；唯一 finalist 出局 |
| P04 | test-oracle PASS；current train-risk estimator 不泛化 | HOLD backlog；KILL current estimator |
| P05 | oracle drift-ball 在 final query 前仍不能认证，prefix tail coverage 低 | KILL current mechanism |
| P06 | query-cover/pivot-bound/split 与 dual-tree batch NN 同构 | KILL novelty |
| P07 | sound local-ANN missing bound 尚未实验，最近工作不完全同构 | HOLD backlog，不是 finalist |
| P08 | 无 A−1；two-probe cost/error correlation 风险高 | HOLD evidence-only |
| P10 | walker recall 太低，probe 无效；current form 只有 generic prefetch | KILL current form |
| P11 | 无 A−1；只有 narrow vote-margin certificate | HOLD evidence-only |

最终 `PASS=0, retained finalist=0`。以上 HOLD 只是 backlog 证据状态，不因“尚未被杀”自动进入下一轮。

## Gate policy

- A-1 只判断必要现象与 oracle headroom，不要求 paper-ready mechanism。
- A-1 正且无同构先例，才进入 A0；A0 后恢复 R2/R3 的强 KILL。
- 最终最多保留 3 个候选，不拼装多个弱机制。
