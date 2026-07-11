# 下一阶段：动态驻盘图插入成本闭合

## 当前裁决

同意对 M08 和 Dir 1 采用 KILL-first。

M08 的删除成本占比过低，且 stale incoming edges 长期残留并高度集中，继续设计 lazy cleanup 缺乏收益动机。Dir 1 在真实低延迟窗口和十亿规模下几乎没有跨 insert 页面重叠，不能依靠全局 batch coalescing 获得稳定收益。

R128 的 page-hit Gini=0.436 只是局部热点信号。它暂时不足以独立形成方向，因为尚未证明这些热点页在 insert wall time、设备 I/O 或写放大中占主导。当前不要围绕热点页继续设计系统。

## 下一阶段目标

先解释现有 insert latency 中 55%–68% 的未计量时间，并建立完整、互斥、可守恒的成本分解。在成本账闭合前，不生成新的系统 Idea。

## Codex 执行任务

将一次 insert 拆成以下互斥阶段：

1. position seeking；
2. topology page acquisition；
3. coordinate acquisition / rerank；
4. exact distance computation；
5. new-node candidate construction；
6. new-node RobustPrune；
7. reverse-link candidate construction；
8. reverse RobustPrune；
9. topology modification；
10. topology submission / writeback；
11. lock、allocation、copy 和其他开销。

同时使用细粒度 wall-time timer 与 `perf record -g` 交叉验证。各阶段时间之和必须解释至少 95% 的总 insert wall time。

同时记录：

- logical reads、unique pages、submitted device reads 和 cache hits；
- coordinate vectors 和 coordinate pages 的逻辑/物理读取量；
- exact distance computation 次数；
- new prune 与 reverse prune 的候选规模和 pair comparisons；
- 同一 vector 或 vector pair 在不同阶段的重复读取、重复计算比例；
- logical topology mutations、dirty pages、submitted writes 和 device bytes；
- 候选从搜索结果到最终边的漏斗。

实验至少覆盖：

- R=32/64/96/128；
- 至少两个真实数据集；
- 至少两个向量维度；
- 冷缓存与稳定缓存；
- 单线程为主，受控并发作为补充。

## 门禁

1. 时间闭合率低于 95%：继续 instrumentation，不讨论方向。
2. topology write 仍只占 10% 左右：彻底关闭拓扑写优化主线。
3. exact-vector acquisition 或 RobustPrune CPU 只有在两个真实数据集、多个 R 下稳定占总成本 30%–40% 以上时，才进入跨系统验证。
4. R128 热点页只有在热点集合贡献了显著 wall time 或设备 I/O，并且完全优化后的端到端收益上限超过 20% 时，才允许作为组件继续研究。
5. 若没有任何单一结构性成本稳定超过 30%，本轮停止，不拼装多个小优化。

## 产物

VectorDB 主项目：

- `reports/insert_cost_closure_report.md`
- `results/insert_cost_closure/`
- `scripts/` 中的新增分析脚本
- `patches/` 中的 instrumentation patch

Chat 仓库：

- 稳定摘要放入 `codex/share/insert_cost_closure_report.md`
- 过程中的关键问题和最终裁决追加到 `conversation/conversation_0711.md`

报告只陈述测量事实、成本增长规律和 Continue/Kill 判断，不包装新的系统 Idea。