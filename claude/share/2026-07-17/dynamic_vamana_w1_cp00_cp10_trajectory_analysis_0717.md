# Dynamic Vamana W1 CP00→CP10 Trajectory Analysis

> **状态说明（CP20 终审后补充，2026-07-17）**
> 本文是 CP20 完成前形成的中间分析，仅用于保留当时的证据解释与研究判断。CP20 最终轨迹已经推翻其中关于 OdinANN 查询性能随 churn 持续碎片化、DiskANN stale Recall 超线性退化及损失加速的机制性表述。本文不得再作为最终结论引用；最终裁决以 `codex/share/2026-07-17/dynamic_vamana_w1_final_five_point_review_0717.md` 为准。

## 1. Recall 退化轨迹

### 动态系统（matched-Recall L 点）

| System | L | CP00 | CP01 (1%) | CP05 (5%) | CP10 (10%) | 总变化 |
|---|---:|---:|---:|---:|---:|---:|
| DGAI | 64 | 0.9515 | 0.9513 | 0.9499 | 0.9478 | −0.0037 (−0.39%) |
| DGAI | 128 | 0.9801 | 0.9801 | 0.9785 | 0.9777 | −0.0024 (−0.24%) |
| OdinANN | 29 | 0.9508 | 0.9502 | 0.9466 | 0.9461 | −0.0047 (−0.49%) |
| OdinANN | 46 | 0.9799 | 0.9792 | 0.9782 | 0.9768 | −0.0031 (−0.32%) |

两系统在 10% 累计替换后 Recall 仅下降 0.24–0.49%，退化速率基本线性，无突变。这表明 Vamana 图结构在部分更新下具有足够的局部修复能力。

### DiskANN stale-static negative control

| L | CP00 | CP01 (1%) | CP05 (5%) | CP10 (10%) | 总变化 |
|---:|---:|---:|---:|---:|---:|
| 29 | 0.9516 | 0.9360 | 0.8801 | 0.8190 | −0.1326 (−13.9%) |
| 53 | 0.9800 | 0.9628 | 0.9026 | 0.8382 | −0.1418 (−14.5%) |

逐段退化速率：

| 区间 | ΔRecall(L29) | 替换比例 |
|---|---:|---:|
| CP00→CP01 | −0.0156 | 1% |
| CP01→CP05 | −0.0559 | +4% |
| CP05→CP10 | −0.0611 | +5% |

DiskANN stale 退化明显**超线性**——每新增百分点 churn 造成的 Recall 损失在加速。10% churn 后 L53 仅 0.8382，接近无法使用的水平。这证实了 static index 在持续更新负载下的根本缺陷：不更新图结构会使过期邻居比例逐步累积，且这种累积是 compounding 的（已删除节点的邻居也可能指向其他已删除节点）。

**关键对比**：两个动态系统在 10% churn 后 Recall 仅损失 ~0.3%，DiskANN stale 损失 ~14%。这是 Dynamic Vamana 主题最直接的量化论据之一。

## 2. QPS 演化：架构差异的浮现

| System | L | CP00 QPS | CP05 QPS | CP10 QPS | CP00→CP10 变化 |
|---|---:|---:|---:|---:|---:|
| DGAI | 64 | 1260.8 | 1245.8 | 1270.5 | +0.8% |
| DGAI | 128 | 874.5 | 849.8 | 832.2 | −4.8% |
| OdinANN | 29 | 1609.0 | 1666.8 | 1267.6 | **−21.2%** |
| OdinANN | 46 | 1345.4 | 1315.5 | 1168.7 | **−13.1%** |

这是本轮最重要的新发现：

- **DGAI QPS 基本持平**。merge/rebuild 操作虽然昂贵（离线时间），但每次都重建干净的图结构，因此查询路径不会积累碎片。
- **OdinANN CP05→CP10 出现显著 QPS 衰减**。CP00→CP05 阶段 OdinANN L29 QPS 甚至轻微上升（1609→1667），但 CP10 突降至 1268，跌幅 24%。这暗示 OdinANN 的 in-place 图维护在较低 churn 下可以保持结构质量，但累计 10% 替换后开始出现图碎片效应——入度分布退化、热点路径变长。

这构成了一对架构 trade-off：

| 维度 | DGAI (decoupled merge) | OdinANN (coupled in-place) |
|---|---|---|
| 更新时 QPS 稳定性 | 高（每次 merge 重建） | 随 churn 累积退化 |
| Online visibility | 无（需 merge+reload） | 即时 |
| Update 吞吐 | ~1000 repl/s | ~1600 repl/s |
| Write amplification | 低 (49 KB/repl @ CP10) | 高 (207 KB/repl @ CP10) |

CP20（20% churn）将进一步检验：OdinANN 的 QPS 衰减是否继续加速，是否存在需要 consolidation 才能恢复的临界点。

## 3. 更新吞吐与 I/O 成本

### Ingest throughput 轨迹

| System | CP01 (80K) | CP05 (320K) | CP10 (400K) | 趋势 |
|---|---:|---:|---:|---|
| DGAI repl/s | 991 | 1003 | ~1037 | 稳定偏升 |
| OdinANN repl/s | 1566 | 1721 | ~1592 | 稳定 ~1.6x DGAI |

OdinANN 的 ingest 吞吐约为 DGAI 的 1.6 倍，并且两者在不同 batch size 下保持稳定。这说明 ingest 吞吐主要受单次 insert/delete 的算法成本控制，与累计 churn 量基本无关。

### Write amplification per replacement

| System | CP10 e2e write GiB | Replacements | KB/replacement |
|---|---:|---:|---:|
| DGAI | 19.677 | 400,000 | **49.2** |
| OdinANN | 82.602 | 400,000 | **206.5** |

OdinANN 在 CP10 的每替换写入量是 DGAI 的 **4.2 倍**。这反映了 in-place 图修复的代价：OdinANN 每次 insert/delete 都需要修改多跳邻居的邻接表并立即持久化到 NVMe，而 DGAI 在 ingest 阶段写入较少（仅 append），大部分写入集中在 publish 阶段的批量 merge。

对于 NVMe 寿命和写入带宽受限的部署场景，这是一个显著的成本差异。

### Persistent growth

两系统在 CP10 的 apparent/allocated growth 均为 **0**。这证实了 replace-new 操作保持了 index 文件的 cardinality 不变——每个 delete 释放的空间被对应的 insert 填充。

## 4. 基础设施成熟度

0717 的 R02–R10 基础设施 saga 暴露了十余类控制面缺陷（NVMe I/O baseline cgroup 延迟、permission 传播、schema 命名、路径硬编码等），但有两个正面信号：

1. **每次 fail-closed 都在任何指标被污染之前停止**。R02–R09 没有一次产生了被误接受的虚假性能数据。
2. **PZ 的效率干预（01:51:18）转折了节奏**。Gpt 在 14:44 后授权 Codex 对控制面问题自行修复并继续，不再逐次等待审议。这使 R10 从"每个权限错误等审批"变成了"36 分钟跑完两系统完整 CP00→CP05"。

后续 R12 也体现了这种效率：首次因 unit 命名停止后，Codex 自行修复并在 continuation 中完成了完整 CP10，总实际运行约 30 分钟。

## 5. CP20 预期

基于 CP00→CP10 的趋势外推：

- **Recall**：两系统在 20% churn 后预计仍保持 >0.97（L128/L46），退化约 0.5–0.6%
- **OdinANN QPS**：如果碎片效应继续，CP20 的 L29 QPS 可能降至 1000 以下，意味着 DGAI 与 OdinANN 的 QPS 差距将基本消失
- **DiskANN stale**：L53 Recall 可能降至 0.75–0.78 区间，几乎丧失实用价值
- **DGAI QPS**：预计继续持平，因为 merge/rebuild 每次重建干净图
- **Write amplification**：OdinANN 的 KB/replacement 可能进一步上升，因为更多邻接表需要修改
