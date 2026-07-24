# SELECTIVE-OPQ-ORACLE-A0 Plan Review

`SELECTIVE-OPQ-ORACLE-A0` 的 compatibility、compact layout、双 preprocessing
和正确性审计通过，但当前完整计划暂不批准运行。

当前裁决：

```text
PASS-COMPATIBILITY-AND-LAYOUT-AUDIT
NEEDS-REVISION-ON-ORACLE-AND-DECISION-LOGIC
PLAN-ONLY
```

需要修正以下问题。

第一，当前

```text
delta(q,L,v) = (d32-d*)² - (d64-d*)²
s_v = Σ delta(q,L,v)
```

的 top-H 只对该 modular surrogate 精确最优。计划已经明确它不优化 mixed
search 改变后的非加性轨迹，因此它不是 selective OPQ 的全局 oracle。

所以：

```text
该 selector 失败
→ KILL-DISTANCE-REGRET-SELECTOR
```

不能直接：

```text
→ KILL-SELECTIVE-OPQ
```

若需要对整条 candidate 给出 KILL，必须增加更强的乐观门禁，或至少同时验证多种
独立的 routing-relevant selector。

第二，增加每个 `L` 独立的 score：

```text
s_v^(50), s_v^(100), s_v^(200), s_v^(400), s_v^(800)
```

当前直接汇总五个 L 会重复计算嵌套轨迹，并隐含等权 workload 假设。跨 L 综合
selector 可以保留，但只能作为附加结果。

第三，除了 exact-distance regret，至少增加一个 routing-aware surrogate，例如
frozen candidate/beam boundary 上的 ranking-inversion correction score。最终对照
应至少包括：

```text
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE
```

第四，内存比较必须分两种口径：

```text
1M actual resident:
mixed40/48/56 vs OPQ45/53/61

scale-normalized / variable bytes:
mixed40/48/56 vs OPQ40/48/56
```

双 rotation/codebook 的约 9.35MB 是固定开销。在 1M 上约为
9.35B/vector，在 1B 上约为 0.009B/vector。若只输给 OPQ45/53/61，但超过
OPQ40/48/56，应判为 `HOLD-SCALE-DEPENDENT`，不能直接 KILL。

第五，将门禁拆成：

```text
ALGORITHMIC-SELECTIVITY:
same memory, no-lower Recall, strictly lower reads/comparisons

SYSTEM-PARETO:
QPS/p50/p99 including dual preprocessing and compact accessor
```

QPS 和 p99 的两个 raw repeats 可用于强 PASS，但不得作为单独的方向级 KILL
依据。

执行改成两阶段。

Stage A 只训练：

```text
OPQ40 / OPQ48 / OPQ56
```

复用 OPQ32/64，完成 per-L selectors、routing-aware selector 和 algorithmic
Recall–reads gate。暂不训练 OPQ45/53/61。

只有 Stage A 出现明确选择性，才进入 Stage B：

```text
train OPQ45/53/61
implement final compact layout
run actual-memory and end-to-end system gate
```

请更新计划、决策标签、阶段预算和 hard wall 后回复。收到再次批准前不得运行。
