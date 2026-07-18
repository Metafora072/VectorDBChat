> 该文件属于中间分析，其中相关机制解释已被M2/M3运行时证据推翻。

# Dynamic Vamana W1 最终五点轨迹审议报告

## 审议结论

R13 composed closure 已正式接受，Dynamic Vamana W1 的 `CP00→CP01→CP05→CP10→CP20` 五点轨迹至此闭合。现有数据支持两类动态索引在累计 20% replacement 后维持较稳定的 Recall，也支持 stale-static index 在不更新图结构时发生持续且严重的 Recall 下降。数据不支持 OdinANN 查询性能随 churn 单调碎片化，也不支持 DiskANN stale Recall 损失随 churn 加速或 compounding 的旧判断。

当前最稳定的系统权衡是 online visibility 与持久化写入量之间的冲突。DGAI 不提供 publish 前的 online visibility，但 CP20 的端到端写入量较低；OdinANN 提供 online visibility，但 CP20 的端到端 write bytes/replacement 是 DGAI 的约 `4.26` 倍。该观察是候选研究问题，不是已经完成机制归因的论文结论。

本阶段不再增加 churn checkpoint，也不自动启动实验。下一步仅允许设计机制归因与 novelty 审查；是否进入 profiling，等待 Gpt 后续裁决。

## 审议范围与证据边界

实验对象为 SIFT10M 上的 W1 replacement 轨迹。累计 checkpoint 为 CP00、CP01、CP05、CP10 和 CP20，分别对应 0%、1%、5%、10% 和 20% replacement。动态查询每个参数点执行 3 次，表中使用中位数。QPS(Queries Per Second，每秒查询数)用于表示查询吞吐，I/O(Input/Output，输入/输出)用于表示存储访问。DiskANN 使用已接受的 CP00 静态索引查询各 checkpoint 的 ground truth，作为 stale-static negative control，不参与动态更新吞吐排名。

R13 首次 execution 在 DGAI CP20 stage 完整 PASS 后因 query launcher 的 capability 变量名不匹配而 fail-closed；后续 continuation 绑定首次 execution，只补充 DGAI query/freeze，并完成 fresh OdinANN 与 DiskANN control。该组合没有重做 DGAI 的 800K update。机器汇总位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_cp20_trajectory_r13/summary.json`，其 `status` 为 `pass`。

## 原始结果

### 动态查询五点轨迹

| 系统 | Checkpoint | L | Recall@10 | QPS | P99（μs） | Mean I/O |
|---|---|---:|---:|---:|---:|---:|
| DGAI | CP00 | 64 | 0.95146 | 1260.75 | 1014 | 96.359 |
| DGAI | CP01 | 64 | 0.95128 | 1253.25 | 1010 | 97.417 |
| DGAI | CP05 | 64 | 0.94994 | 1245.81 | 1022 | 98.319 |
| DGAI | CP10 | 64 | 0.94781 | 1270.51 | 1001 | 97.732 |
| DGAI | CP20 | 64 | 0.94613 | 1235.72 | 1013 | 98.432 |
| DGAI | CP00 | 128 | 0.98015 | 874.52 | 1331 | 155.400 |
| DGAI | CP01 | 128 | 0.98009 | 835.75 | 1371 | 154.234 |
| DGAI | CP05 | 128 | 0.97851 | 849.83 | 1381 | 156.992 |
| DGAI | CP10 | 128 | 0.97768 | 832.20 | 1385 | 155.003 |
| DGAI | CP20 | 128 | 0.97634 | 827.91 | 1397 | 155.516 |
| OdinANN | CP00 | 29 | 0.95085 | 1609.04 | 817 | 51.325 |
| OdinANN | CP01 | 29 | 0.95024 | 1628.83 | 802 | 51.440 |
| OdinANN | CP05 | 29 | 0.94662 | 1666.78 | 780 | 51.575 |
| OdinANN | CP10 | 29 | 0.94605 | 1267.56 | 1013 | 51.580 |
| OdinANN | CP20 | 29 | 0.94255 | 1712.27 | 742 | 51.400 |
| OdinANN | CP00 | 46 | 0.97991 | 1345.38 | 956 | 65.897 |
| OdinANN | CP01 | 46 | 0.97924 | 1420.91 | 936 | 65.365 |
| OdinANN | CP05 | 46 | 0.97819 | 1315.53 | 968 | 66.231 |
| OdinANN | CP10 | 46 | 0.97682 | 1168.69 | 1069 | 65.737 |
| OdinANN | CP20 | 46 | 0.97431 | 1226.82 | 1044 | 65.837 |

DGAI 从 CP00 到 CP20 的 Recall 绝对下降在 `0.00381–0.00533` 之间，OdinANN 在 `0.00560–0.00830` 之间；相对下降均小于 `0.9%`。OdinANN 的 L29 QPS 在 CP10 降至 `1267.56` 后，于 CP20 恢复至 `1712.27`，较 CP10 上升约 `35.08%`。L46 QPS 同期恢复约 `4.97%`。因此 CP10 的局部下降不是单调轨迹。

### 动态更新成本轨迹

| 系统 | Checkpoint | Stage replacements | Ingest replacements/s | E2E(End-to-End，端到端) replacements/s | E2E read bytes/replacement | E2E write bytes/replacement |
|---|---|---:|---:|---:|---:|---:|
| DGAI | CP01 | 80K | 990.894 | 766.066 | 678519.4 | 97007.0 |
| DGAI | CP05 | 320K | 1002.963 | 841.515 | 557115.7 | 55193.3 |
| DGAI | CP10 | 400K | 1037.142 | 874.544 | 550875.8 | 52818.8 |
| DGAI | CP20 | 800K | 1041.441 | 926.155 | 533866.6 | 48042.6 |
| OdinANN | CP01 | 80K | 1565.601 | 529.012 | 979744.4 | 356773.8 |
| OdinANN | CP05 | 320K | 1721.295 | 865.601 | 682291.4 | 229931.3 |
| OdinANN | CP10 | 400K | 1591.862 | 850.899 | 661892.4 | 221734.0 |
| OdinANN | CP20 | 800K | 1728.372 | 1109.026 | 617965.5 | 204618.4 |

CP01、CP05、CP10 和 CP20 的单段 stage size 分别为 80K、320K、400K 和 800K。吞吐与 bytes/replacement 同时受 batch size 和固定 publish 成本摊销影响，不能把表中的变化直接解释为累计 churn 的因果效应。跨 DGAI 与 OdinANN 的绝对 QPS 和吞吐比较也只具有描述性，因为两者的构建布局、I/O engine 和 visibility semantics 不同。

在相同的 CP20 stage size 下，OdinANN 的端到端 write bytes/replacement 为 `204618.4`，DGAI 为 `48042.6`，比值约为 `4.26`。DGAI 在 publish 前不支持 online visibility；OdinANN 的 online visibility 与 fresh visibility 均通过验证。这是当前证据中最稳定、最值得进一步归因的系统权衡。

### DiskANN stale-static 轨迹

| Checkpoint | L29 Recall@10 | L53 Recall@10 | L29 单位百分点 replacement 损失 | L53 单位百分点 replacement 损失 |
|---|---:|---:|---:|---:|
| CP00 | 0.9516 | 0.9800 | — | — |
| CP01 | 0.9360 | 0.9628 | 0.01560 | 0.01720 |
| CP05 | 0.8801 | 0.9026 | 0.01398 | 0.01505 |
| CP10 | 0.8190 | 0.8382 | 0.01222 | 0.01288 |
| CP20 | 0.7110 | 0.7258 | 0.01080 | 0.01124 |

从 CP00 到 CP20，DiskANN stale 的 Recall 绝对下降分别为 `0.2406` 和 `0.2542`，持续且严重，足以证明静态索引与演化 active set 之间的失配会积累。然而，按各段新增 replacement 百分点归一化后，L29 的损失从 `0.01560` 逐段降至 `0.01080`，L53 从 `0.01720` 逐段降至 `0.01124`。单位 churn 损失是略微下降而非加速，因此不得使用“超线性退化”“损失加速”或“compounding”描述该轨迹。

## 数据支持的结论

第一，DGAI 与 OdinANN 在 20% replacement 后的 Recall 仅温和下降。现有证据不支持动态索引质量在该范围内快速崩溃。

第二，OdinANN QPS 不随 churn 单调下降。CP10 的下降在 CP20 明显恢复，不能将 CP10 单点解释为确定的图碎片、搜索路径变长或 consolidation 临界点。

第三，DiskANN stale Recall 随 replacement 持续严重下降，说明不更新的静态索引无法维持对新 active set 的查询质量。但单位 churn 的 Recall 损失逐段略降，证据不支持损失加速。

第四，当前最稳定的系统权衡是 DGAI 的无 online visibility、较低写入量，与 OdinANN 的 online visibility、较高写入量之间的冲突。CP20 相同 stage size 下，OdinANN 的端到端 write bytes/replacement 约为 DGAI 的 `4.26` 倍。

第五，更新成本轨迹存在 batch-size 混杂。各 checkpoint 的 stage size 不同，不能把吞吐提升或每 replacement 成本下降直接归因于累计 churn。

第六，跨系统绝对性能只能作为描述性结果。当前实验没有控制 DGAI 与 OdinANN 在构建布局、I/O engine 和可见性语义上的差异，因而不支持严格的因果排名。

## 被 CP20 推翻的旧判断

`claude/share/2026-07-17/dynamic_vamana_w1_cp00_cp10_trajectory_analysis_0717.md` 是 CP20 前的中间分析。其关于 OdinANN 在累计 10% replacement 后开始发生图碎片、入度退化和路径变长的解释，被 CP20 的 QPS 恢复推翻。数据只能证明 CP10 出现局部性能下降，不能说明下降机制，更不能外推为持续趋势。

该中间分析将 DiskANN stale 轨迹描述为超线性、损失加速和 compounding。加入 CP20 并按每段 replacement 百分点归一化后，两个 L 点的单位损失均逐段略降，因此这些措辞不再成立。DiskANN stale 的严重绝对退化仍然成立，但其曲线形状必须改写为持续下降且边际损失略降。

该中间分析还将不同 checkpoint 的吞吐和 bytes/replacement 变化解释为累计 churn 效应。由于 stage size 从 80K 变化到 800K，固定成本摊销没有被隔离，此类机制解释亦不成立。

## 尚未验证的机制

现有证据没有定位 OdinANN 较高写入量来自哪些具体文件、更新步骤或邻接表修复，也没有区分固定 publish 成本与每 replacement 边际成本。将高写入归因于多跳邻居修复或即时持久化，在当前阶段仍是假设。

现有证据也没有解释 DGAI 较低写入量为什么必须以 publish/reload 和无 online visibility 为代价。DGAI 是否存在可在线查询的 delta state、该状态能否在不承担 OdinANN 同等级写放大的前提下暴露，以及 reload 的一致性约束是什么，均尚未验证。

OdinANN CP10 QPS 下降的原因同样未知。缓存状态、系统噪声、索引局部结构、运行时条件或其他实现因素都没有被当前实验排除，因此不得选择性地归因于图结构碎片。

## 有效性限制

五点轨迹来自一个数据集和一类 W1 replacement 工作负载，能够回答当前实验范围内的演化趋势，但不足以直接外推到其他数据分布、索引规模或更新模式。每个查询点使用 3 次重复的中位数，能够降低偶发噪声影响，但不是跨机器、跨 seed 的可重复性证据。

DiskANN 是 stale-static negative control，其查询质量变化可用于说明不更新索引的后果，但不能用于与动态系统进行 update throughput 排名。DGAI 与 OdinANN 的接口语义和实现路径不同，绝对性能差异中同时包含算法与工程实现因素。

## 下一阶段研究裁决

不再把 churn 导致查询性能持续碎片化作为核心问题，也不继续增加 churn checkpoint。主要候选问题调整为 online visibility 与持久化写放大的冲突。

若 Gpt 授权进入机制 profiling，首先应定位 OdinANN 高写入涉及的文件、更新步骤与邻接表修复，分别测量固定 publish 成本和每 replacement 边际成本。对照侧应分析 DGAI 低写入为何依赖 publish/reload，并确认是否存在可在线查询的 delta state。上述工作只用于机制归因和问题真实性判断，随后还需要 novelty 审查；当前不实现新系统，也不把候选问题包装为已成立的贡献。

最终裁决是接受 R13 composed closure，结束当前五点轨迹实验阶段，并等待 Gpt 决定是否进入机制 profiling。
