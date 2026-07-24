# SELECTIVE-OPQ-ORACLE-A0 Revised Plan Response

## Status

```text
PASS-COMPATIBILITY-AND-LAYOUT-AUDIT
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```

已按评审修订 oracle 边界、per-L selector、决策逻辑、内存口径与阶段预算。本轮
没有 coding、训练、trace generation 或 search。

## 1. Oracle 边界与 per-L score

Distance-regret 仍定义为：

```text
delta_DR(q,L,v) = (d32-d*)² - (d64-d*)²
s_DR,L(v)       = Σ delta_DR(q,L,v)
```

但现在为五个 `L` 分别构造 `s_DR,L`。top-H 只对这个 modular surrogate 精确，
不再视为 selective OPQ 全局 oracle。因此它单独失败时只判：

```text
KILL-DISTANCE-REGRET-SELECTOR
```

Primary gate 禁止直接汇总五个嵌套 trace。可选 aggregate-L 只作为显式
uniform-over-L workload 的附加诊断，不改变任何裁决。

## 2. Routing-aware selector

每个 `L` 独立记录 frozen OPQ32/64 candidate-list boundary event union。
对事件 `e=(q,L,a,b)`，`a` 是 incoming/evaluated candidate，`b` 是当前最差
retained candidate：

```text
y_e    = 1[d*(a) < d*(b)]
y_0    = 1[d32(a) < d32(b)]
y_a    = 1[d64(a) < d32(b)]
y_b    = 1[d32(a) < d64(b)]

delta_RA(e,a) = 1[y_0 != y_e] - 1[y_a != y_e]
delta_RA(e,b) = 1[y_0 != y_e] - 1[y_b != y_e]
s_RA,L(v)     = Σ delta_RA(e,v)
```

它直接衡量单节点升精度能否纠正 frozen beam-boundary ranking inversion，与
squared distance-regret 独立。top-H 对这个 single-node modular
counterfactual 精确，但仍不称 global oracle。单独失败只判：

```text
KILL-ROUTING-AWARE-SELECTOR
```

每个 L、每档预算的完整 selector 对照为：

```text
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE
```

## 3. 两种内存口径

### 1M actual resident

```text
mixed40 vs OPQ45
mixed48 vs OPQ53
mixed56 vs OPQ61
```

三档 mixed 实际为 49.534656/57.534656/65.534656 B/vector。

### Scale-normalized / variable bytes

```text
mixed40 vs OPQ40
mixed48 vs OPQ48
mixed56 vs OPQ56
```

这称为 matched-code-payload diagnostic，不声称 total bytes 完全相等。一般形式：

```text
B_mix(N,c) =
  c + aligned_tag_rank(N)/N + 9,347,072/N
```

在 1B nodes 上，两模型固定开销约 0.009347 B/vector，但 tag+rank 仍约
0.1875 B/vector，所以 mixed40 实际约 40.196847 B/vector。所有报告保留这部分，
不把它四舍五入为 40。

若只超过 OPQ40/48/56、但输给 1M actual-memory OPQ45/53/61：

```text
HOLD-SCALE-DEPENDENT
```

不能直接 KILL。

## 4. 拆分后的门禁

### ALGORITHMIC-SELECTIVITY

```text
no-lower Recall
strictly lower reads/query
strictly lower comparisons/query
```

Stage A 只使用这三个确定性指标；每点一个完整 run，不用性能重复决定算法门禁。

### SYSTEM-PARETO

```text
QPS
p50
p99
dual preprocessing time
compact accessor time
actual allocated bytes/vector
```

只在 Stage B 使用最终 compact layout，恰好两个 interleaved raw repeats，不补
第三次。两个 repeat 同方向可支持强 PASS；系统性能失败只能产生
`HOLD-SYSTEM-OVERHEAD` 或 `KILL-CURRENT-SYSTEM-REALIZATION`，不能单独 KILL
算法选择性或方向。

## 5. Stage A

只训练：

```text
OPQ40 / OPQ48 / OPQ56
```

复用 audited OPQ32/64，不训练 OPQ45/53/61，不实现最终 compact layout。允许
dual-dense experimental adapter 只用于正确 dispatch OPQ32/64 distance；其内存
和 QPS 不形成 claim。

矩阵：

```text
OPQ40/48/56 × 5 L × full 1K queries

3 payload budgets
× 4 per-L selectors
× 5 L
× full 1K queries
```

决策：

- 任一 routing-relevant selector 在任一预算/L 通过：

  ```text
  PASS-ALGORITHMIC-SELECTIVITY-SCALE
  GO-STAGE-B
  ```

- distance-regret 单独失败：`KILL-DISTANCE-REGRET-SELECTOR`。
- routing-aware 单独失败：`KILL-ROUTING-AWARE-SELECTOR`。
- 两个独立 routing-relevant selector 在全部三个预算和五个 per-L hindsight
  gates 都失败：

  ```text
  KILL-SELECTIVE-OPQ-STATIC-NODE-A0
  ```

  该 KILL 仅限 frozen GIST1M graph 上的 static OPQ32/64 node allocation。
- 只有 random/visit-frequency 为正：

  ```text
  HOLD-HOTNESS-ONLY
  ```

Stage A 预算：

```text
GPU: 0
CPU: 最多 3 concurrent builds × 24 threads；search 1 thread
RAM cap: 48GiB
new NVMe: ≤2GiB on /dev/nvme8n1
expected wall: 5–9h
hard wall: 10h
```

达到 hard wall 即停，不训练 OPQ45/53/61，不自动进入 Stage B。

## 6. Stage B

Stage B 只有在 Stage A 为正且再次获得 GPT 批准后才执行：

```text
train OPQ45/53/61
implement accepted compact low/high/tag/rank layout
run 1M actual-memory algorithmic gate
run exactly two end-to-end system repeats
```

只携带 Stage-A-positive selector/budget/L 配置。

裁决：

```text
scale pass + actual-memory fail
→ HOLD-SCALE-DEPENDENT

actual-memory algorithmic pass + system fail
→ PASS-ALGORITHMIC-SELECTIVITY
  HOLD-SYSTEM-OVERHEAD

actual-memory algorithmic pass + both raw system repeats favorable
→ PASS-HINDSIGHT-SELECTIVITY
  HOLD-DEPLOYABLE-SELECTOR
```

Stage B 预算：

```text
GPU: 0
CPU: 最多 3 concurrent builds × 24 threads；search 1 thread
RAM cap: 48GiB
additional NVMe: ≤2GiB on /dev/nvme8n1
expected wall: 6–10h
hard wall: 11h
combined maximum after two separate approvals: 21h
```

## 7. 正确性与实施边界

保留此前全部 frozen hash、OPQ offsets/orthogonality、endpoint parity、ADC
`abs error ≤1e-5`、1M tag/rank 穷举和 allocator-capacity 门禁，并新增：

- 每个 L 使用独立 raw trace/score 文件；
- distance-regret 和 boundary-inversion score 均可从 raw event 重算；
- Stage A dual-dense adapter 不得产生 system/memory claim；
- Stage B 双 rotation/ADC 与 compact accessor 必须位于 query timer 内；
- Stage B 只有两个完整 performance repeats。

详细修订计划与 tracker：

- `codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_PLAN.md`
- `codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_TRACKER.md`

```text
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```
