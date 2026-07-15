# Dynamic Vamana P2-B Matched-Recall Slim W0 结果

## 结论

`pilot3_sift10m_p2b` 已完成并停止。P2-M(Matched-point refinement，匹配点细化) 为五个 Recall floor 都找到了三个系统的最小实测整数 L，且每个 Tq=1 median Recall 均位于 `[R,R+0.005]`。随后 P2-B 在同一 L 的 Tq=16 下完成三次独立有效重复，所有 median Recall 仍位于对应区间。因此本轮获得五个严格 matched-Recall 工作点，而不是由插值或低于 floor 的配置形成的近似比较。

P2-M 共保留 202 个 raw query point，其中 DGAI 的 `R=0.99` 候选因单次 Recall 横跨阈值补至 5 次；P2-B Tq=16 共 45 个 raw point。所有正式 raw run 均有效，没有 fatal、EBADF、负 CQE、I/O error、cgroup OOM 或零 NVMe 读取。P2-B 到此停止，未启动 W1、churn、DEEP/GIST、W2 或其它负载。

## Tq=1 最小匹配 L 与性能

| Recall floor | DiskANN：L / Recall / QPS / P99 / I/O | DGAI：L / Recall / QPS / P99 / I/O | OdinANN：L / Recall / QPS / P99 / I/O |
| ---: | --- | --- | --- |
| 0.93 | 22 / 0.9329 / 524.5 / 5239 / 39.11 | 46 / 0.9308 / 1452.0 / 1074 / 79.74 | 24 / 0.9325 / 1806.9 / 727 / 48.53 |
| 0.95 | 29 / 0.9516 / 497.4 / 5834 / 45.45 | 64 / 0.9514 / 1254.8 / 1174 / 95.59 | 29 / 0.9523 / 1726.0 / 737 / 52.72 |
| 0.97 | 42 / 0.9707 / 366.1 / 6837 / 57.57 | 95 / 0.9702 / 1056.9 / 1307 / 123.73 | 38 / 0.9713 / 1612.7 / 789 / 60.28 |
| 0.98 | 53 / 0.9800 / 278.0 / 8164 / 68.16 | 128 / 0.9801 / 849.4 / 1538 / 155.44 | 46 / 0.9805 / 1563.8 / 802 / 67.05 |
| 0.99 | 79 / 0.9900 / 204.9 / 10619 / 93.37 | 200 / 0.9900 / 639.3 / 1880 / 224.79 | 65 / 0.9902 / 1329.5 / 888 / 84.55 |

表中 QPS 为 driver-reported median QPS，P99 单位为微秒，I/O 为 driver-reported mean I/Os。所有横向比较均使用实际 median Recall，而不是名义 floor。OdinANN 在五个 matched 点的 Tq=1 QPS 和 P99 均优于其余两个完整 artifact。DGAI 的 QPS 位于 DiskANN 与 OdinANN 之间，但达到相同 floor 所需的 L 和 mean I/O 显著更高；这描述当前冻结 artifact 的 query frontier，不足以归因为架构机制本身。

## Tq=16 伸缩

| Recall floor | DiskANN：Recall / QPS | DGAI：Recall / QPS | OdinANN：Recall / QPS |
| ---: | --- | --- | --- |
| 0.93 | 0.9329 / 6990.5 | 0.9329 / 14319.8 | 0.9311 / 13226.0 |
| 0.95 | 0.9516 / 5415.6 | 0.9537 / 12489.8 | 0.9515 / 12704.9 |
| 0.97 | 0.9707 / 5769.6 | 0.9715 / 10113.5 | 0.9713 / 11777.4 |
| 0.98 | 0.9800 / 4359.9 | 0.9807 / 4623.3 | 0.9805 / 11075.1 |
| 0.99 | 0.9900 / 2722.4 | 0.9901 / 5909.8 | 0.9901 / 9111.2 |

Tq=16 使用与 Tq=1 相同的 selected L，且所有三次 median 均落入 Recall floor 区间，因此没有触发相邻 L 的并发局部 refinement。该结果可用于当前 artifact 的查询伸缩比较；driver QPS 与 external QPS 的计时边界分别保留，未混用为同一吞吐指标。

## 可复核工件

机器可读结果位于 `VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_p2b/`。其中 `refinement_raw.tsv`、`tq1_raw_runs.tsv` 和 `tq16_raw_runs.tsv` 保留逐次点；`selected_matched_points.tsv`、`matched_recall_summary.tsv`、`timing_scope.tsv` 和 `resource_summary.tsv` 给出中位数、最小值、最大值与计时/资源口径。`figures/` 包含 Recall–QPS、Recall–P99、Recall–mean-I/O、两种并发的 matched QPS、matched P99、matched I/O、serving DRAM、计时 reconciliation 与 selected L 图；每个图由实际 Recall 数据绘制。

## 解释边界与后续裁决

这些数据支持对当前三套完整索引 artifact 的 matched-Recall query frontier、I/O 代价、尾延迟和 Tq=1 至 Tq=16 伸缩进行比较。它们不证明解耦机制的普遍优劣，不涉及动态更新、churn 稳定性或完整 `Vq–Vm` frontier。是否进入 W1 或先开展 query-path 归因，应由 Gpt 基于本轮实际 frontier gap 单独裁决。
