# SELECTIVE-OPQ-ORACLE-A0 Plan Response

## Status

```text
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```

本轮只完成源码兼容性、表示布局、数学目标与资源预算审计。没有 coding、训练、
trace generation 或 search。

## 1. OPQ40/48/56 兼容性

当前 `generate_pq` 实际调用 native `generate_opq_pivots()` 与
`generate_pq_data_from_pivots()`，不经过要求 `dim % chunks == 0` 的
`*_simplified` helper。native pivots 文件保存显式 `chunk_offsets`，encoder 与
ADC search 均按 offsets 工作，因此：

```text
OPQ40: 40 × 24D
OPQ48: 48 × 20D
OPQ56: 8 × 18D + 48 × 17D
```

OPQ56 不补零、不丢维，属于 DiskANN native uneven-chunk path。正式 artifact gate
必须验证 57 个 offsets、前 8 个 chunk 宽 18、后 48 个宽 17、总宽 960。三个
uniform baseline 都独立训练 rotation/codebook。

## 2. Mixed layout 与精确内存

使用 compact two-array layout：

```text
low_codes[(N-H)][32]
high_codes[H][64]
high_tag[ceil(N/64)]                 // bitset
rank1_prefix[ceil(N/64)+1]           // uint32 per 64-node word
```

由 tag、word-prefix 和一次 popcount 得到 node ID 在 low/high dense array 中的
rank，O(1) random access；不存在为 low node 预留 64B 的空洞。

在 `N=1,000,000` 时，tag+rank 包含 64B alignment/padding 后为 187,584B。
OPQ32 与 OPQ64 的独立 codebook、centroid、rotation、offset arrays 共
9,347,072B。因此三档 mixed 实际 allocation 为：

| Payload mix | Total bytes | Effective bytes/vector |
|---|---:|---:|
| 75% OPQ32 + 25% OPQ64 | 49,534,656 | 49.534656 |
| 50% OPQ32 + 50% OPQ64 | 57,534,656 | 57.534656 |
| 25% OPQ32 + 75% OPQ64 | 65,534,656 | 65.534656 |

OPQ40/48/56 的实际 allocation 分别只有 44.673472/52.673536/60.673536
B/vector，所以它们只是同 payload 对照。最终 no-free-memory gate 必须增加最近的
更强 uniform OPQ45/53/61，其实际占用为
49.673472/57.673536/65.673536 B/vector。

当前 native loader 同时保留 row-major 与 transposed codebook。正式实现必须让
uniform/mixed 共同只保留一个在线 transposed copy，或把重复 allocation 对所有方法
如实计费；不能只优化 selective 一侧。最终同时报告 serialized bytes 和 allocator
capacity，以较大实测值为准。

## 3. 双 query preprocessing

OPQ32/64 是独立模型，mixed search 每个 query 必须执行两次 centering、两次
960×960 V1 rotation，并生成 256×32 与 256×64 两张 ADC table。两张 ADC table
需 98,304B scratch，两份 query buffer 需 7,680B。已测 V1 rotation-only
`~123.15us`，所以两次 rotation 的最低经验估计约 246us；这不包含 ADC，也不能
代替正式的 in-search 计时。最终 QPS、p50、p99 必须包含完整双 preprocessing。

## 4. Selection objective

对每个 official test query 与每个 frozen L，取 deterministic OPQ32 和 OPQ64
search 的 node-distance event union；同一 `(q,L,node)` 去重。令 `d*` 为 exact
squared-L2，`d32/d64` 为两套 ADC estimate：

```text
delta(q,L,v) = (d32-d*)^2 - (d64-d*)^2
s_v          = sum delta(q,L,v)
J(S)         = sum_{v in S} s_v,  |S|=H
```

无阈值、无中心性权重、无调参系数。`J` 是 modular objective，因此 top-H
`s_v` 是该目标的精确最优解；交换任一 selected low-score node 与 unselected
high-score node 不会降低目标。ties 在运行前固定按 node ID 升序。

名称固定为 `TRACE-CONDITIONED-SELECTOR`，不称 global oracle：它没有优化 mixed
search 改变后产生的非加性后续轨迹，而且显式使用 test queries 与 exact distance。
其 PASS 只能支持 hindsight selectivity。

同预算加入：

```text
RANDOM-NODE(seed=20260724)
VISIT-FREQUENCY(top-H on the same trace)
TRACE-CONDITIONED-SELECTOR(top-H by s_v)
```

trace generation、exact-distance evaluation、selection/sort 与 online search
时间分开报告。

## 5. 实现范围

收到批准后，预计只改：

- `include/pq_flash_index.h`、`src/pq_flash_index.cpp`：双表、compact accessor、
  trace hook、mixed distance dispatch；
- `include/pq_scratch.h`：双 query/ADC scratch；
- `include/pq.h`、`src/pq.cpp`：compact table ownership 与 preprocessing 计时；
- `include/percentile_stats.h`、`apps/search_disk_index.cpp`：双 preprocessing
  与实际 bytes 输出；
- `codex/work/2026-07-24/selective_opq_oracle_a0/` 下新增 work-local
  train/pack/trace/audit/run/analyze 脚本。

不实现新图、完整 VectorDB、SSD redesign、deployable selector、RPQ 或 structured
OPQ。

## 6. 正确性门禁

1. graph/query/GT/training-row SHA 全部复核；
2. 所有 uniform chunk offsets、rotation orthogonality、codes shape 通过；
3. 对 1M node 穷举验证 tag/rank、slot 唯一性和 low/high cardinality；
4. all-low mixed 与 OPQ32、all-high mixed 与 OPQ64 的 ADC 和 search 完全对齐；
5. 抽样 mixed node distance 与对应 standalone model 的 absolute error ≤ `1e-5`；
6. 双 rotation/ADC 必须位于 query timer 内；
7. actual allocated capacity 与 layout model 对账；
8. selector score 可从 raw trace 重算，top-H 与 tie-break 完全确定；
9. full performance 恰好两个 interleaved repeats，报告 raw repeats，不补第三次。

任何 hidden dense 64B allocation、内存计费不一致、endpoint parity 失败、遗漏双
preprocessing 或 frozen artifact mismatch，均标记 `INVALID`，不能判 PASS。

## 7. Search matrix 与生死门

Uniform：

```text
OPQ32/40/45/48/53/56/61/64
× L={50,100,200,400,800}
× 1K queries × exactly 2 interleaved repeats
```

Mixed：

```text
3 payload budgets
× {random, visit-frequency, trace-conditioned}
× L={50,100,200,400,800}
× 1K queries × exactly 2 interleaved repeats
```

至少一个 budget 必须在两个 raw repeats 中都相对 actual-memory guard
OPQ45/53/61 达成：Recall 不低、reads 严格更低、QPS 严格更高、p99 严格更低。
均值不能挽救某一次失败。否则：

```text
KILL-SELECTIVE-OPQ
```

通过时也只给：

```text
PASS-HINDSIGHT-SELECTIVITY
HOLD-DEPLOYABLE-SELECTOR
```

## 8. 资源与 hard wall

```text
GPU: 0
CPU: OPQ build 最多 3-way parallel × 24 threads；search 1 thread
RAM: 预计 ~13GiB/build，并发 cap 48GiB
NVMe: 在 /dev/nvme8n1 预留 2GiB；禁止大文件写 system LV
expected wall: 7–13h
hard wall: 16h
```

当前主机为 112 logical CPUs、242GiB available RAM，data NVMe 约 1.4TiB
available。达到 hard wall 即停在当前 phase，不增加模型、L 或 repeat。

详细计划与 tracker：

- `codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_PLAN.md`
- `codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_TRACKER.md`

```text
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```
