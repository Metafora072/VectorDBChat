# Insert Search Residual 最终分解报告

## 最终裁决

本轮正式 **Close DGAI 单系统 profiling**。不再拆 timer，不恢复完整 R 矩阵，不围绕 topology write、coordinate access、AIO、PQ、visited 或 heap 生成系统 Idea。

两套 900K stable 数据没有共同的 30% 以上直接测量子阶段。SIFT-128 的最大项是 topology request construction + submit，占 total insert 9.78% [9.68%, 9.87%]；GIST-960 的最大项是 PQ distance computation，占 12.34% [12.23%, 12.45%]。主项不同，且 search wall 被分散到多个小项。新增计时的配对开销 CI 仍无法可靠收敛，也命中 GPT 规定的关闭条件。

## 口径修正与直接 Instrumentation

上一轮名为 `new-node candidate construction` 的字段由完整 search wall 扣除 coordinate rerank 与 exact distance 得到。本轮按 GPT 要求统一改称 `search residual`，并在 `do_rerank_search()` 的真实 search loop 中直接布置互斥 timer，不再用结构计数或总时间相减估算各子阶段。

直接计时覆盖 frontier pop/termination、topology request/submit、completion poll/wait、adjacency decode/expansion、PQ distance computation、visited lookup/update、candidate/frontier heap、search-loop control 和 residual。每条 insert 同时记录 expanded nodes、topology logical/unique pages、host-submitted bytes、PQ evaluations、visited operations、heap operations 与 search iterations。

SIFT 20-insert sanity 和两套 900K formal trace 均满足逐行 `search wall = Σ(substages) + residual`，最大误差为 0 μs。正式尾窗的整体最低 closure 为 SIFT 99.61%、GIST 99.74%。Page-event logging 始终关闭。

## 实验协议

实验固定 SIFT-128、GIST-960、900K base、R=64、L=160、beam=4 和单线程。每套数据在独立 clean source copy 上执行 2,000 次 insert，前 500 次作为 warmup。由于已知 `io_submit()` 状态在序列前段切换，正式统计使用两套数据均已稳定的最后 500 行。

阶段占比按阶段时间总和除以 `total_insert_us` 总和计算，95% CI(Confidence Interval，置信区间)使用 10,000 次 per-insert bootstrap。绝对时间为逐 insert 中位数。

## 直接子阶段结果

| Direct substage | SIFT median | SIFT total share | GIST median | GIST total share |
|---|---:|---:|---:|---:|
| Frontier pop / termination | 105 μs | 2.01% [1.97%, 2.05%] | 297 μs | 5.11% [4.98%, 5.24%] |
| Topology request / submit | 515 μs | 9.78% [9.68%, 9.87%] | 483 μs | 8.42% [8.32%, 8.51%] |
| Topology completion poll / wait | 85 μs | 1.63% [1.61%, 1.65%] | 144 μs | 2.62% [2.57%, 2.68%] |
| Adjacency decode / expansion | 163 μs | 3.05% [3.03%, 3.07%] | 171 μs | 3.11% [3.08%, 3.14%] |
| PQ distance computation | 503 μs | 9.59% [9.47%, 9.70%] | 690 μs | 12.34% [12.23%, 12.45%] |
| Visited lookup / update | 238 μs | 4.55% [4.49%, 4.60%] | 214 μs | 3.93% [3.89%, 3.96%] |
| Candidate / frontier heap | 130 μs | 2.46% [2.44%, 2.49%] | 130 μs | 2.38% [2.36%, 2.41%] |
| Search-loop control | 34 μs | 0.65% [0.64%, 0.66%] | 37 μs | 0.68% [0.66%, 0.69%] |
| Residual | 189 μs | 3.57% [3.52%, 3.62%] | 260 μs | 4.69% [4.65%, 4.73%] |

SIFT 的 total insert latency 中位数为 5.183 ms，直接 search wall 为 1.961 ms，占 total 37.27%。GIST 分别为 5.521 ms 与 2.420 ms，占 total 43.28%。宽 search wall 确实显著，但拆开后没有任何单项达到 total 的 13%，更不存在共同 30% 项。

SIFT 的前三项为 topology request/submit 9.78%、PQ computation 9.59% 和 visited 4.55%；前两项非常接近。GIST 的前三项为 PQ computation 12.34%、topology request/submit 8.42% 和 frontier 5.11%。两套数据的第一项不同，说明宽阶段不能归结为一个跨数据集稳定机制。

## 结构计数与单位成本

| Structure metric，median per insert | SIFT | GIST |
|---|---:|---:|
| Expanded nodes | 168 | 182 |
| Topology logical pages | 169 | 183 |
| Topology unique pages | 106 | 156 |
| Host-submitted topology bytes | 323,584 B | 974,848 B |
| PQ evaluations | 4,576 | 9,808 |
| Visited lookups | 10,752 | 11,073 |
| Visited inserts | 4,576 | 9,808 |
| Heap pushes | 959 | 1,119 |
| Heap pops | 337 | 366 |
| Heap updates | 789 | 929 |
| Search iterations | 195 | 522 |

GIST 的 PQ evaluations 约为 SIFT 的 2.14 倍，解释了 PQ computation 绝对时间从 503 μs 增至 690 μs。单位 evaluation 成本反而从 SIFT 的 0.109 μs 降至 GIST 的 0.070 μs，因此该差异来自工作量而非单次 PQ 运算异常。PQ 在 GIST 中仍只占 total 12.34%，不能形成系统方向。

Topology submit 的单位成本为每 logical page 3.05 μs（SIFT）和 2.52 μs（GIST）。GIST 的 unique pages 与 host-submitted bytes 更高，但该阶段 total share 反而更低，未呈现一个随页数稳定放大的共同瓶颈。它还包含 DGAI 的 request mapping、cache lookup 和 Linux AIO submit 路径，不满足非实现偶然性条件。

Adjacency expansion 的单位成本约为每 expanded node 0.96/0.94 μs，跨数据集基本一致，但 total share 仅约 3.1%。Visited 单位 operation 为 0.0156/0.0104 μs，heap 单位 operation 为 0.0622/0.0541 μs；两者均没有容器级异常，也没有足够占比。Frontier 的单位 iteration 成本约为 0.54 μs，但 GIST iterations 更多，因此其 share 上升至 5.11%，仍远低于门禁。

## Instrumentation Overhead

小型开销对照采用 SIFT-100K clean source、1,500 inserts、9 组 base/profile 交错配对。全部 trial 成功，paired median overhead 为 4.55%，但 95% bootstrap CI 为 [-7.95%, 73.36%]。宽 CI 来自此前已确认的 AIO 状态切换，无法给出可靠的 overhead 上界。

该不确定性足以改变 SIFT 中 topology submit 与 PQ 两个接近项的排序，因此不能选择其中任一项做方向判断。即使暂时忽略 overhead，所有直接子阶段仍低于 13%，距离 30% 门禁很远；开销结果不会把失败门禁变成通过，只会进一步强化 Close 裁决。

## 已关闭的假设

M08 stable-ID refresh 已因删除占比和 stale-edge 证据关闭。Deferred topology write coalescing 已因 billion-scale 外推失效关闭。Topology random write、append-only adjacency 与 topology modification 优化已因稳定占比不足关闭。Coordinate acquisition、exact-vector access 与 application-cold AIO 已因 stable 份额不足、双峰和实现特异性关闭。

本轮进一步关闭 search residual 方向。直接分解证明它不是单一 candidate construction 机制，而是 topology request、PQ、frontier、visited、heap、decode 和 control 的组合；没有共同 30% 子项，且最大项因数据集而异。

## 保留下来的事实

DGAI insert 在 900K stable 下仍有约 37%–43% 时间位于 search loop，但该成本是多个小项的合计。GIST 更高的 PQ 绝对时间可由 evaluation 数解释，frontier 时间可由 iteration 数解释；未发现异常单位成本。Topology write 和 coordinate path 仍是 DGAI 布局 tradeoff 的组成部分，但都不是当前数据下的共同主导机制。

这些事实可以作为 DGAI 工程诊断和后续系统比较的背景资料，但不足以生成论文级系统 Idea。若未来研究其他 direct-insert 驻盘图系统，应从跨系统问题重新立项，而不是继续在本 DGAI trace 上逐层拆计时器。

## 结束状态

按照 GPT 最终门禁，本轮之后停止 DGAI 单系统 profiling。无需提交 Claude 做方向审查，因为没有直接测量子阶段通过 30% 条件。下一步应由 PZ 与 GPT 决定是重新选题，还是启动独立的跨系统问题发现流程；Codex 不再自行扩展本分支。

机器可读结果位于主项目 `reports/insert_search_residual_final.json`，分析脚本为 `scripts/analyze_insert_search_residual_final.py`，原始 formal runs 位于 NVMe 的 `VectorDB/data/VectorDB/runs/insert_search_residual_final/formal/`。
