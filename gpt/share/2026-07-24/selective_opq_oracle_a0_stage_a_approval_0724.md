# SELECTIVE-OPQ-ORACLE-A0 Stage A Approval

`SELECTIVE-OPQ-ORACLE-A0` Revision 2 已通过审核，批准执行 Stage A only。

当前裁决：

```text
PASS-REVISED-STAGE-A-PLAN
APPROVED-STAGE-A
DO-NOT-ENTER-STAGE-B-AUTOMATICALLY
```

确认 Stage A 范围：

```text
Train:
OPQ40 / OPQ48 / OPQ56

Reuse:
OPQ32 / OPQ64
same GIST1M-960D graph
same queries / GT / training rows

Selectors, independently for each L:
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE

L:
{50,100,200,400,800}
```

Stage A 只评估：

```text
Recall@10
reads/query
comparisons/query
```

dual-dense adapter 的内存、QPS 和延迟不得形成 system claim。

修正失败标签。由于 distance-regret 和 routing-aware 都只是 frozen-trace、
single-node modular surrogate，即使二者全部失败，也不能外推为所有 static
selective OPQ 不可能有效。失败时使用：

```text
KILL-TESTED-STATIC-SELECTORS-ON-GIST-A0
```

并明确限定为：

```text
GIST1M-960D
frozen graph
OPQ32/64
tested per-L selectors
```

任一 routing-relevant selector 出现正面结果时，先给：

```text
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW
```

不得自动运行 Stage B。

结果必须额外报告：

1. 相对 uniform OPQ40/48/56 的 Recall 差值；
2. reads 和 comparisons 的绝对下降与百分比下降；
3. 实际增加或恢复的 top-k 命中数量；
4. 各预算和各 L 下 selected node sets 的重叠率/Jaccard；
5. routing-aware、distance-regret 与 visit-frequency 选择集合的重叠；
6. 每种 selector 的 score 分布和高精度节点访问覆盖率。

严格数值改善可以构成 signal，但如果收益极小，不自动视为值得进入 Stage B。
是否继续由结果审核决定。

资源冻结：

```text
GPU: 0
RAM cap: 48GiB
new NVMe: <=2GiB on /dev/nvme8n1
expected wall: 5–9h
hard wall: 10h
```

达到 hard wall 后停止，不训练 OPQ45/53/61，不实现最终 compact layout，不增加
新的 selector、L 或数据集。

可直接执行 Stage A。
