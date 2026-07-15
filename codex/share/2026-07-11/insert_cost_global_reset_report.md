# Insert Cost 全局重排账报告

## 裁决

本轮不关闭 DGAI 单系统 profiling，但只允许继续一次 `new-node candidate construction` 的最小化分解。除此之外，topology random write、coordinate acquisition、exact-vector access、application-cold `io_submit()` 以及完整 R 矩阵继续保持关闭。

该裁决直接命中 GPT 的自动门禁。SIFT-128 与 GIST-960 在 900K stable tail 中存在同一个 30% 以上一级阶段，即 `new-node candidate construction`。其占比分别为 44.35% [43.80%, 44.90%] 与 38.67% [38.47%, 38.88%]，绝对时间中位数分别为 3.631 ms 与 2.504 ms。该阶段目前仍是宽阶段，不能据此生成系统 Idea，也尚未触发 Claude 的方向判断；下一步只能区分其中的 topology traversal I/O、PQ distance computation、candidate queue/bookkeeping 和 residual，并检查是否为 DGAI 单函数或 AIO 实现偶然性。

## 数据与统计口径

本报告没有新增实验，直接复用 R=64、L=160、beam=4、单线程的四组 stable trace。沿用上一轮经 100-row checkpoint 确认的稳定尾窗，SIFT-100K 与 SIFT-900K 各使用 800 行，GIST-100K 使用 400 行，GIST-900K 使用 1,100 行。

阶段占比按尾窗内阶段时间总和除以 `total_insert_us` 总和计算，95% CI(Confidence Interval，置信区间)使用 10,000 次 per-insert bootstrap。绝对时间报告逐 insert 中位数，避免比例随 total latency 改变而产生误判。四组最小 closure 为 99.41%–99.75%，残差中位数不超过几十微秒，不影响前三阶段排序。

## SIFT-128 一级阶段

表中绝对时间为逐 insert 中位数，括号内为占 total insert 的比例及 95% CI。

| 一级阶段 | 100K stable | 900K stable |
|---|---:|---:|
| Position seeking | 22 μs，0.75% [0.73%, 0.76%] | 42 μs，0.55% [0.54%, 0.56%] |
| Topology acquisition | 38 μs，1.21% [1.20%, 1.22%] | 70 μs，0.84% [0.83%, 0.86%] |
| Coordinate acquisition/rerank | 687 μs，22.56% [22.36%, 22.76%] | 1,111 μs，13.99% [13.80%, 14.19%] |
| Exact distance | 5 μs，0.17% [0.16%, 0.17%] | 7 μs，0.09% [0.08%, 0.09%] |
| New-node candidate construction | 777 μs，25.44% [25.20%, 25.72%] | 3,631 μs，44.35% [43.80%, 44.90%] |
| New-node RobustPrune | 56 μs，1.79% [1.75%, 1.82%] | 64 μs，0.82% [0.80%, 0.84%] |
| Reverse candidate construction | 1,075 μs，33.47% [33.20%, 33.73%] | 2,062 μs，26.01% [25.72%, 26.31%] |
| Reverse RobustPrune | 18 μs，1.48% [1.33%, 1.64%] | 57 μs，2.56% [2.31%, 2.83%] |
| Topology modification | 12 μs，0.44% [0.42%, 0.46%] | 28 μs，0.39% [0.37%, 0.40%] |
| Submission/writeback | 282 μs，9.30% [9.15%, 9.45%] | 679 μs，8.52% [8.39%, 8.66%] |
| Other lock/alloc/copy | 95 μs，3.21% [3.18%, 3.24%] | 139 μs，1.77% [1.74%, 1.79%] |

SIFT 的 total insert latency 中位数从 3.092 ms 增至 7.922 ms，增加 4.831 ms，即 156.3%。其中 `new-node candidate construction` 增加 2.854 ms、增长 367.5%，是总时延增长的主要来源；`reverse candidate construction` 增加 0.987 ms，coordinate acquisition/rerank 增加 0.424 ms。

900K 的前三阶段依次为 `new-node candidate construction` 44.35%、`reverse candidate construction` 26.01% 和 coordinate acquisition/rerank 13.99%。早期 pilot 所见的 coordinate 宽阶段主导没有在更长 stable tail 中保持，原因是上一轮已经确认的 AIO submit 非平稳性；本报告以稳定尾窗结果覆盖早期比例判断。

## GIST-960 一级阶段

| 一级阶段 | 100K stable | 900K stable |
|---|---:|---:|
| Position seeking | 64 μs，0.83% [0.82%, 0.85%] | 41 μs，0.66% [0.65%, 0.68%] |
| Topology acquisition | 142 μs，1.85% [1.82%, 1.88%] | 70 μs，1.10% [1.09%, 1.11%] |
| Coordinate acquisition/rerank | 1,438 μs，19.00% [18.72%, 19.29%] | 856 μs，13.52% [13.43%, 13.61%] |
| Exact distance | 28 μs，0.37% [0.36%, 0.38%] | 19 μs，0.30% [0.30%, 0.31%] |
| New-node candidate construction | 1,934 μs，25.82% [25.40%, 26.28%] | 2,504 μs，38.67% [38.47%, 38.88%] |
| New-node RobustPrune | 103 μs，1.69% [1.58%, 1.81%] | 102 μs，1.87% [1.80%, 1.94%] |
| Reverse candidate construction | 1,873 μs，24.19% [23.85%, 24.53%] | 1,435 μs，22.33% [22.18%, 22.49%] |
| Reverse RobustPrune | 414 μs，8.84% [8.04%, 9.65%] | 375 μs，8.79% [8.37%, 9.22%] |
| Topology modification | 26 μs，0.37% [0.36%, 0.38%] | 18 μs，0.30% [0.29%, 0.32%] |
| Submission/writeback | 713 μs，9.06% [8.84%, 9.26%] | 398 μs，6.25% [6.20%, 6.30%] |
| Other lock/alloc/copy | 587 μs，7.86% [7.74%, 7.98%] | 388 μs，6.11% [6.06%, 6.15%] |

GIST 的 total insert latency 中位数从 7.594 ms 降至 6.321 ms，减少 1.274 ms，即 16.8%。尽管 total latency 下降，`new-node candidate construction` 的绝对时间仍从 1.934 ms 增至 2.504 ms，增加 570 μs、增长 29.4%；其余主要阶段多为下降。因此，该阶段是唯一在两套数据从 100K 扩至 900K 时都出现绝对增长的共同主要项。

900K 的前三阶段依次为 `new-node candidate construction` 38.67%、`reverse candidate construction` 22.33% 和 coordinate acquisition/rerank 13.52%。这与 SIFT 的前三阶段完全一致，且排序一致。

## Topology write、coordinate path 与 CPU prune

| Dataset/base | Topology write | Coordinate path，含 exact | CPU prune，new + reverse |
|---|---:|---:|---:|
| SIFT 100K | 253 μs，8.07% | 691 μs，22.73% | 83 μs，3.26% |
| SIFT 900K | 480 μs，6.10% | 1,117 μs，14.08% | 124 μs，3.38% |
| GIST 100K | 550 μs，6.87% | 1,464 μs，19.37% | 535 μs，10.53% |
| GIST 900K | 362 μs，5.70% | 875 μs，13.82% | 498 μs，10.66% |

Topology write 在两套 900K 数据上仅占 5.70%–6.10%，topology modification CPU 低于 0.4%，继续否定 topology random write 与 append-only adjacency 方向。Coordinate path 在两套 900K 数据上均约 14%，没有达到 30% 门禁，也支持 Claude 关于 decoupled layout 代价不应包装为跨系统共性瓶颈的判断。CPU prune 分别占 3.38% 与 10.66%，同样不是共同主导项。

## 前三阶段与机制边界

900K 的共同前三阶段为 new-node candidate construction、reverse candidate construction 和 coordinate acquisition/rerank。只有第一项在两套数据中同时超过 30%，且从 100K 到 900K 的绝对中位时间均增长。因此，本轮不能直接 Close profiling。

不过，`stage_new_candidate_us` 当前由完整 search wall time 扣除 coordinate rerank 与 exact distance 得到，本质上仍是一个差分宽阶段。它可能同时包含 topology traversal I/O、PQ distance lookup、candidate heap/visited-set 操作以及未单独计量的控制流。现有结果只能证明该宽阶段值得最后拆一次，不能证明其中存在论文级机制。

## 下一步授权范围

按照 GPT 的全局重置门禁，下一步直接推进一次最小化分解，不需要再次等待 GPT 批准。分解只允许覆盖 `new-node candidate construction`，目标是形成互斥的 topology traversal I/O、PQ distance computation、candidate queue/visited bookkeeping 和 residual，并继续使用 SIFT/GIST 900K、R64、stable 条件。优先复用现有 `QueryStats`；只有字段无法映射时才补小规模 sanity，不重新铺设矩阵。

若分解后没有共同 30% 以上子项，或主导项落在单个函数、容器、锁或 AIO 实现，则正式 Close DGAI profiling。只有出现两套数据共同、绝对时间显著且非实现偶然性的明确子项，才把结果提交给 GPT 和 Claude 做方向判断。

机器可读结果位于主项目 `reports/insert_cost_global_reset.json`，分析脚本为 `scripts/analyze_insert_cost_global_reset.py`。
