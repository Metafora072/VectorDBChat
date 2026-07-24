# PQ-RP-HIGHDIM-DISCOVERY 独立评审与下一步门禁

## 1. 独立裁决

接受本轮：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

该裁决严格限定为：

> 在 GIST1M-960D、固定全精度图、普通 PQ 和本轮搜索参数范围内，提高统一导航码精度可以用显著额外 DRAM 换取更优的 Recall–I/O–Latency 前沿。

本轮不支持 mixed precision 已可行、精度收益具有节点/查询选择性、高维普遍性或论文级系统优势。

## 2. 关键证据

完整 1K queries 上：

```text
PQ32 L800:
Recall@10 94.83%
reads/query 809.73
comparisons/query 75,496.57
QPS 20.62
p99 75.28 ms
DRAM 32 B/vector

PQ64 L400:
Recall@10 96.82%
reads/query 410.64
comparisons/query 40,561.57
QPS 37.92
p99 40.95 ms
DRAM 64 B/vector
```

因此 PQ64 L400 相对 PQ32 L800：

- Recall 高 1.99pp；
- reads 减少 49.29%；
- comparisons 减少 46.27%；
- QPS 提升 1.839×；
- p99 降低 45.60%；
- 代价为额外 32B/vector。

paired-query audit 中，PQ64 L400 相对 PQ32 L800 为 231 个 query 获胜、667 个持平、102 个退化；10,000 次 bootstrap 的 Recall@10 增益 95% CI 为 `[+1.50,+2.48]pp`。

该比较是 no-lower-Recall Pareto 对照，并非严格 equal-recall。不过 PQ32 在本轮最大 `L=800` 时仍低于 PQ64 L400，因此粗粒度比较已经足够证明统一精度存在显著前沿移动。当前无需为了 discovery 继续补中间 `L`。

## 3. 这轮真正建立的问题

当前问题已经从：

```text
PQ 导航误差能否由 larger-L 修复？
```

收敛为：

```text
统一增加 PQ 码长能够减少达到高 Recall 所需的图扩展，
但其 DRAM 成本在大规模下很高。
能否在相同平均内存预算下，只把额外精度分配给真正关键的对象或决策？
```

PQ32→PQ64 的额外内存为：

```text
1M:   +32 MB
100M: +3.2 GB
1B:   +32 GB
```

这构成 mixed-precision candidate 的动机，但尚未构成机制。

## 4. 当前最大风险：强平行工作可能直接消灭动机

普通 PQ64 只与普通 PQ32 比较。下一阶段必须先检查相同或更低内存下的强表示方法：

- OPQ；
- RPQ（Routing-Guided Learned PQ，直接优化图路由）；
- RaBitQ；
- LVQ / LeanVec；
- TurboQuant；
- QuIVer；
- residual / multi-stage PQ；
- per-vector adaptive bit allocation；
- ANNS-AMP 等 adaptive mixed-precision 工作。

特别需要区分：

1. 改善量化表示本身；
2. 针对图路由训练量化器；
3. 改变图拓扑；
4. 查询期动态提高精度；
5. 节点静态分配不同码长；
6. CPU/SSD 系统设计与专用硬件 accelerator。

若某个统一 32B 或更低内存的强 baseline 已经达到普通 PQ64 的前沿，当前 mixed-precision 动机应直接 KILL，不能通过换指标续命。

## 5. 下一步门禁一：Novelty / Prior Kill Map

由 Claude 主导，Codex 协助核对代码与可复现性，完成：

```text
MIXED-PRECISION-QUANTIZATION-KILL-MAP
```

每项工作至少整理：

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector / per-subspace / per-cluster / per-query |
| 精度分配 | uniform / static adaptive / runtime adaptive |
| 图关系 | 固定图导航 / routing-aware training / quantized graph construction |
| 内存预算 | bits/vector 与额外 metadata |
| 查询成本 | ADC/SIMD/bitwise/extra fetch |
| 存储场景 | in-memory / SSD graph / accelerator |
| 结果指标 | Recall–QPS–memory、构建成本 |
| 代码状态 | 可否接入当前 frozen graph harness |
| Novelty 威胁 | 与候选机制的重合位置 |
| Kill 条件 | 是否在相同内存下已解决当前问题 |

Kill Map 完成前，不实现 mixed precision。

## 6. 下一步门禁二：强统一 baseline 计划

Codex 只准备计划，不立即运行：

```text
UNIFORM-QUANTIZER-BASELINE-A0
```

优先级：

```text
第一层：OPQ32 / OPQ64
第二层：RPQ 或 routing-aware quantizer
第三层：RaBitQ / LeanVec 等可复现方法
```

统一要求：

- 尽可能复用 byte-identical full-precision graph；
- 相同 query、GT、W、K 和 I/O 路径；
- 同时报告 bytes/vector；
- 比较完整 Recall–reads–QPS–p99–DRAM 前沿；
- 禁止只比较固定 `L`；
- 禁止把 native implementation 与当前 harness 的差异隐藏在结果中。

先回复实现兼容性、代码来源、预计工作量和最小实验矩阵，等待审核。

## 7. 下一步门禁三：Selectivity Oracle

只有 Kill Map 未直接杀死方向后，才设计：

```text
MIXED-PRECISION-SELECTIVITY-ORACLE-A0
```

该门禁不先发明 selector，而是回答：

> 在相同平均 bytes/vector 下，选择性精度分配能否严格优于统一码长？

避免使用任意阈值。建议比较平均预算：

```text
40B / 48B / 56B per vector
```

每个预算同时构造：

1. uniform PQ40/PQ48/PQ56；
2. PQ32 base + selective residual/high-precision codes；
3. random allocation control；
4. held-out query Oracle upper bound。

真正的 PASS 条件应是：

> 在相同平均内存预算下，选择性 Oracle 在 held-out queries 上严格 Pareto 优于 uniform code：Recall 更高且 reads 不增加，或 reads 更低且 Recall 不下降。

若选择性结果只落在 PQ32 与 PQ64 的普通连续前沿上，说明没有系统机制空间，应 KILL。

## 8. 当前任务拆分

```text
Claude:
完成 MIXED-PRECISION-QUANTIZATION-KILL-MAP。

Codex:
只准备 UNIFORM-QUANTIZER-BASELINE-A0 的兼容性与成本计划；
不运行实验，不实现 mixed precision。

Gpt:
Kill Map 和 baseline 计划回来后，独立判断是否值得进入 Selectivity Oracle。
```

## 9. 当前禁止项

在上述门禁完成前，禁止：

- 实现 per-node mixed precision；
- 设计启发式 selector；
- 使用 residual 大小直接选节点；
- 根据当前 GIST query 结果后验挑选节点；
- 扩大到 100M/1B；
- 宣称论文方向成立。

当前最合理状态：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
HOLD-MIXED-PRECISION-CANDIDATE
NEXT: PRIOR KILL MAP + STRONG UNIFORM BASELINE PLAN
```
