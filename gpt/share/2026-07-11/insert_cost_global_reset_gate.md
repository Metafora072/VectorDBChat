# Insert Cost 全局重置门禁

## 当前裁决

关闭以下方向：

* topology random write 优化；
* append-only adjacency version；
* coordinate acquisition / exact-vector access 优化；
* 围绕 application-cold `io_submit()` 双峰生成系统 Idea。

`io_submit()` 的非平稳停留目前只应视为 DGAI/Linux AIO 实现诊断问题，不进入论文方向，也不进入跨系统验证。

## 最后一步：全局成本重排账

不新增大规模实验，不运行完整 R 矩阵。请直接使用现有 900K、R64、stable-tail 数据，重新汇总完整的 11 个一级阶段。

对 SIFT-128 和 GIST-960 分别报告：

* 各阶段绝对时间中位数；
* 各阶段占 total insert 的比例及 95% CI；
* total insert latency；
* 前三大阶段；
* 100K 到 900K 的绝对时间变化；
* topology write、coordinate path 和 CPU prune 的最终占比。

需要特别区分：

```text
position seeking
coordinate acquisition/rerank
new-node candidate construction
new-node RobustPrune
reverse candidate construction
reverse RobustPrune
topology modification
submission/writeback
other
```

不要只报告 share，还要报告绝对微秒或毫秒，避免 total latency 变化造成比例误导。

## 最终门禁

1. 如果同一个一级阶段在两套 900K 数据上稳定占 30% 以上，并且绝对时间也显著，则允许再做一次该阶段的最小化分解。
2. 如果两套数据的主导阶段不同，或没有任何共同阶段超过 30%，则停止 DGAI 单系统 profiling。
3. 如果主导项只是单个函数、锁、内存分配或 AIO 实现异常，则记录为工程问题，不生成系统 Idea。
4. 不再为寻找方向继续逐层拆计时器；本轮必须给出明确的 Continue 或 Close profiling 裁决。

## 产物

发布：

```text
codex/share/insert_cost_global_reset_report.md
```

这份报告应尽量由已有数据生成。只有发现现有 CSV 缺失关键一级字段时，才允许补一个很小的 sanity run，不允许重新铺设实验矩阵。
