# Dynamic Vamana P2-B Pareto Analysis — W0 Query Frontier

**日期**：2026-07-15
**上游数据**：`codex/share/2026-07-15/dynamic_vamana_p2b_matched_recall_w0_results_0715.md`

---

## 1. 总览

P2-B 在五个 Recall floor（0.93/0.95/0.97/0.98/0.99）上完成了 DiskANN、DGAI、OdinANN 的严格 matched-Recall 比较。每个 floor 选择满足 `R ≤ median Recall ≤ R+0.005` 的最小实测整数 L，Tq=1 和 Tq=16 均有效。以下分析基于这些 matched point。

---

## 2. Tq=1 Query Frontier

| Recall floor | DiskANN | DGAI | OdinANN |
|---|---|---|---|
| **L（搜索广度）** | 22 / 29 / 42 / 53 / 79 | 46 / 64 / 95 / 128 / 200 | 24 / 29 / 38 / 46 / 65 |
| **QPS @ 0.93** | 524.5 | 1452.0 | **1806.9** |
| **QPS @ 0.95** | 497.4 | 1254.8 | **1726.0** |
| **QPS @ 0.97** | 366.1 | 1056.9 | **1612.7** |
| **QPS @ 0.98** | 278.0 | 849.4 | **1563.8** |
| **QPS @ 0.99** | 204.9 | 639.3 | **1329.5** |

### OdinANN 的 Tq=1 优势来源

OdinANN 在所有 floor 上 QPS 最高、P99 最低。关键指标对比（R=0.99）：

| 指标 | DiskANN | DGAI | OdinANN |
|---|---|---|---|
| L | 79 | 200 | 65 |
| Mean I/O | 93.37 | 224.79 | 84.55 |
| P99 (μs) | 10619 | 1880 | 888 |
| QPS | 204.9 | 639.3 | 1329.5 |

- **OdinANN vs DiskANN**：I/O 数接近（85 vs 93），但 QPS 差 6.5 倍、P99 差 12 倍。差异不在图质量或搜索广度，而在 I/O 执行效率——OdinANN 使用 io_uring + pipeline，DiskANN 使用同步 libaio。Per-I/O latency 是 DiskANN 的根本瓶颈。
- **OdinANN vs DGAI**：DGAI 需要 2.66 倍的 I/O（225 vs 85）才达到相同 Recall，因为 R32 图的搜索路径更长。但 DGAI 的 per-I/O 效率高于 DiskANN（同样多的 I/O 下 DGAI 更快），因为 DGAI 只读 topology + PQ 而非完整向量。

### DiskANN 的异常表现

DiskANN 作为 static index（无需维护动态结构）、R64（介于 DGAI R32 和 OdinANN R96 之间），理论上不应比两个 dynamic 系统都差。其 P99 在高 Recall 区间超过 10ms，是 OdinANN 的 12 倍。这强烈暗示差异来自 I/O 子系统实现（同步 vs 异步、pipeline depth）而非算法或图质量。这是一个可以在 paper 中量化讨论的发现：**static graph advantage 可以被 I/O execution gap 完全抵消**。

---

## 3. Tq=16 Scaling 与 Crossover

| Recall floor | DiskANN QPS | DGAI QPS | OdinANN QPS |
|---|---|---|---|
| 0.93 | 6990.5 | **14319.8** | 13226.0 |
| 0.95 | 5415.6 | 12489.8 | **12704.9** |
| 0.97 | 5769.6 | 10113.5 | **11777.4** |
| 0.98 | 4359.9 | 4623.3 | **11075.1** |
| 0.99 | 2722.4 | 5909.8 | **9111.2** |

### DGAI 的低 Recall 并发优势

DGAI 在 R=0.93 以 14320 QPS 领先 OdinANN 的 13226（+8.3%）。这个 crossover 值得解释：

- DGAI 的 decoupled record 更小（topology + PQ only，不含 full vector），因此同一 NVMe bandwidth 下能服务更多并发 read request
- 在低 Recall（L 小 → I/O 总量少）时，这个 per-I/O size advantage 主导，因为设备尚未被 I/O 数量而是 bandwidth 饱和
- 在高 Recall（L 大 → I/O 总量高）时，DGAI 2-3x 的 I/O 数量超过了 per-I/O size 的节省，OdinANN 重新主导

### Scaling Ratio（Tq=16 / Tq=1）

| Recall floor | DiskANN | DGAI | OdinANN |
|---|---|---|---|
| 0.93 | 13.3× | 9.9× | 7.3× |
| 0.95 | 10.9× | 10.0× | 7.4× |
| 0.97 | 15.8× | 9.6× | 7.3× |
| 0.98 | 15.7× | 5.4× | 7.1× |
| 0.99 | 13.3× | 9.2× | 6.9× |

DiskANN 的 scaling ratio 最高（~13-16x），因为 Tq=1 的 per-query latency 极高（同步 I/O），并发时有大量 CPU idle time 可利用。OdinANN 的 scaling ratio 最低（~7x），因为 Tq=1 已经很高效，并发的边际收益较小。DGAI 的 0.98 下降到 5.4× 可能与 L=128 时大量随机读导致 NVMe queue depth 饱和有关。

---

## 4. I/O Pattern 与架构映射

三系统的 I/O 模式反映了各自的存储架构：

| 特征 | DiskANN | DGAI | OdinANN |
|---|---|---|---|
| Record layout | 耦合：vector + neighbors in one sector | 解耦：topology/PQ 与 coordinates 分离 | 耦合：vector + neighbors in one record |
| R（degree） | 64 | 32 | 96 |
| Per-I/O size | 大（含 full vector） | 小（只读 topology + PQ） | 大（含 full vector） |
| I/O subsystem | 同步 libaio | io_uring | io_uring + pipeline |
| Mean I/O @ R=0.99 | 93.37 | 224.79 | 84.55 |

DGAI 的 I/O 效率悖论：它做了最多的 I/O，但在 Tq=1 下仍比 DiskANN 快 3 倍。这说明 per-I/O latency（取决于 I/O size 和 submission 效率）比 I/O count 更重要。在 NVMe random 4K read 下，小 record + 异步 submission 的延迟显著低于大 record + 同步 submission。

---

## 5. W0 结论与 W1 预期

### W0 Query Frontier 排序

- **Tq=1 全域**：OdinANN >> DGAI >> DiskANN
- **Tq=16 低 Recall（≤0.93）**：DGAI ≥ OdinANN >> DiskANN
- **Tq=16 高 Recall（≥0.97）**：OdinANN >> DGAI > DiskANN

### W1 1% Canary 的关键问题

W0 是纯 query frontier，W1 引入 update 维度后 Pareto 图可能发生位移：

1. **DGAI 的 update cost**：merge + reload + publish 是重量级操作，如果 restart-visible throughput 远低于 OdinANN 的 online-visible throughput，DGAI 在 Vq-Vm 二维 Pareto 上可能落后
2. **OdinANN 的 online visibility**：如果 insert/delete 后无需额外操作即可查询，OdinANN 的 update latency 可能接近于零（仅 API 调用时间），这是耦合动态架构的核心优势
3. **Recall stability under churn**：1% replace-new 后，使用 W0 固定 L 的 Recall 是否保持稳定？如果某系统的 Recall 下降显著，说明其动态图维护质量有问题
4. **Write amplification**：DGAI 的 merge 可能产生大量设备写入（重写整个 PQ/topology segment），OdinANN 的 consolidation 同样如此——device_write_bytes / inserted_vector_payload_bytes 的差异将直接影响 I/O-bound workload 的可持续性

这些问题就是 W1 canary 要回答的。Gpt 的 gate 已经覆盖了所有关键指标，Codex 按 gate 准备基础设施即可。
