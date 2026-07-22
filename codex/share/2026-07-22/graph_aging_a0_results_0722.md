# ReversibleANN / GraphAging A0 结果

日期：2026-07-22（实验运行时间为 2026-07-21 UTC）  
裁决：**KILL-NO-PROBLEM，同时 KILL-SHADOW-NO-UTILITY**

## 1. 结论先行

本轮观测到了明显的**图结构不可逆**，但没有观测到足以支撑论文问题的**查询性能老化**。

- 官方 DiskANN3 的显式 IP-DiskANN 删除路径运行 100 轮后，Recall@10 变化 −0.006 pp，平均 distance calculations 增长 0.414%，均低于预注册门槛（1 pp / 5%）。
- 任务要求的 PipeANN/FreshDiskANN-style 10% batch、5 update seeds 路径运行 100 轮后，Recall@10 平均变化 +0.004 pp；distance calculations 增长 3.85%；edge Jaccard 降至 0.6621。work 的均值漂移大于 build 波动，但仍低于预注册 5% 门槛。
- A0-2 Path 2 中原先看似显著的约 +9.6% 搜索成本来自终态图多出约 858.7 万条边；统一裁剪到约 64M 边后，5-seed 平均成本相对普通静态构建变成 −0.05%，Recall 差异 −0.006 pp。Path 3（500K→增量到 1.2M→删除 0.2M）也只有 +0.50% comparisons / +0.006 pp Recall。
- Oracle Shadow Replay 可以恢复大量 G0 边，但 Path 2 五种子平均 Recall 仅 +0.042 pp、distance calculations 反而 +3.01%；仅保存缺失 G0 边端点也需 117.5–176.3 MB。

因此，核心链条“历史 → 性能 aging → shadow 恢复有收益”在 A0 中断裂。按照 0722 对话中的明确 gate，停止七历史全矩阵、物理 I/O tracing、真实 shadow 和 semi-coupled 原型。

## 2. 实验口径

### 2.1 数据与参数

- SIFT1M：1,000,000 × 128 float32；10,000 queries；exact top-100 GT。
- PipeANN/Vamana：R=64，Lbuild=Lsearch=96。
- 主要查询指标：Recall@10、per-query recall quantiles、distance calculations、visited nodes。
- 结构指标：edge count、与 identity G0 的 edge Jaccard、missing/added edges、changed owners。
- 所有实验仅使用 CPU 与普通 NVMe；未使用 GPU。

数据文件位于 NVMe bind mount 下：

- base：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin`，SHA256 `8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e`；
- query：同目录 `query.bin`，SHA256 `9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65`；
- GT：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m/gt_cp00`，SHA256 `1df1bff305861bf4b2c02f1c7f59870a31062f8de9f4eb68a97dee53d40c211a`。

正式统计固定取前 1,000 条 query，以满足 4 小时预算；build 使用完整 1M base，Path 3 另生成 200K 临时向量。没有对 base 子采样。

### 2.2 实现版本

- PipeANN/OdinANN-style harness：`PipeANN/tests/graph_aging_a0.cpp`。
- PipeANN 基础 commit：`9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`。
- 官方 Microsoft DiskANN3：commit `028d8d56abce91800bc7205a8115bee1940dbe7f`。
- IP-DiskANN 参数：`VisitedAndTopK(k=20, L=100)`，每个删除点最多 3 个 replacement candidates。

前置 smoke test 先在 10K base / 100 queries 上闭合了 `build → insert → lazy_delete → consolidate → search`，Recall@10=1.0 且无崩溃；随后才放大到 1M。SSD `DynamicSSDIndex::final_merge` 的删除路径需要全量重写，无法在 4 小时内完成 10% × 100 × 5 histories，因此按任务给定 fallback 切到内存 `Index` 路径。由此，动态主实验不包含 SSD I/O，PQ=32 也不适用于该内存实现；所有表中的 distance calculations/visited nodes 来自内存搜索计数器，其中 `n_hops` 作为 expanded/visited nodes。静态 G0 的 identity build 用时 64.83 s、峰值 RSS 1.63 GiB。

编译配置为 GCC 13.3、CMake 3.28.3、Release、Linux AIO；环境缺少 tcmalloc，故关闭 tcmalloc。机器为双路 Intel Xeon Gold 6348（112 logical CPUs），Linux 6.8。除实验 harness、统计脚本与兼容构建项外，没有修改 PipeANN 核心更新算法。

一个重要口径修正：DiskANN3 的 `replace` API 直接覆盖 slot，不调用 IP deletion。因此 replacement 循环只作为控制；正式 IP baseline 使用显式 `delete → maintenance → insert → delete → maintenance → reinsert`。

### 2.3 预注册门槛

- Recall@10 下降至少 1 percentage point；或
- search work 增长至少 5%；且
- 效应超过普通 build-seed variance。

官方 IP-DiskANN 无明显 aging 时立即 KILL。

## 3. G0 与普通构建方差

五个随机插入顺序的静态构建结果：

| 指标 | mean | std | 95% CI | min–max |
|---|---:|---:|---:|---:|
| Recall@10 | 0.81592 | 0.000432 | ±0.000537 | 0.8154–0.8164 |
| distance calculations | 3614.93 | 3.55 | ±4.40 | 3610.83–3618.67 |
| edge Jaccard vs identity G0 | 0.43683 | 0.000157 | — | 0.43662–0.43701 |

后一个结果很关键：仅改变普通 build history，就会使超过一半边不同，但查询性能基本相同。因此 edge Jaccard 下降本身不能作为 GraphAging 成立的证据。

## 4. A0-1：同终态可逆循环

### 4.1 官方 IP-DiskANN：显式原地删除

每轮删除 1,000 个原对象、插入 1,000 个临时对象，再删除临时对象并重新插回原对象；每轮结束活跃 tag/vector 集合与 G0 相同。100 轮共执行 200K 个显式 in-place deletes。为能立即回收 slot，maintenance threshold 设为 0.05%；该配置偏向强 baseline，并完整执行 IP deletion 与 dangling-edge cleanup。

| checkpoint | Recall@10 | Δ Recall (pp) | mean comparisons | Δ comparisons | mean hops |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.79502 | 0 | 3324.30 | 0 | 101.0552 |
| 1 | 0.79499 | −0.003 | 3330.75 | +0.194% | 100.9750 |
| 10 | 0.79500 | −0.002 | 3325.70 | +0.042% | 100.9893 |
| 100 | 0.79496 | **−0.006** | 3338.06 | **+0.414%** | 101.0372 |

结论：命中强 baseline KILL gate。100 轮后的变化远低于门槛，说明 IP-DiskANN 已足以消除本轮假设的 aging。

### 4.2 DiskANN3 replacement 控制

同终态 replacement 100 轮后，Recall 变化 +0.003 pp，distance calculations 变化 −0.073%。这不是 IP-delete 证据，但进一步表明 slot replacement 本身没有造成 aging。

### 4.3 PipeANN / FreshDiskANN-style repair

五个 update seeds、每轮 10% batch 的结果：

| checkpoint | Recall@10 mean ±95% CI | comparisons mean ±95% CI | visited mean；p50/p95/p99 | edge Jaccard ±95% CI |
|---:|---:|---:|---:|---:|
| 1 | 0.81624 ±0.00019 | 3687.68 ±1.29 | 100.000；100/102/102.8 | 0.70560±0.00052 |
| 10 | 0.81624 ±0.00026 | 3698.83 ±2.40 | 99.975；100/102/103 | 0.68657±0.00052 |
| 100 | 0.81624 ±0.00014 | 3722.18 ±2.46 | 99.962；100/102/102.8 | 0.66209±0.00078 |

identity G0 为 Recall 0.8162、comparisons 3584.27。因此第 100 轮是 **+0.004 pp Recall / +3.85% comparisons**。visited nodes mean 从 100.018 变为 99.962，基本不变。查询工作的 p50/p95/p99 从 3751/4559/4771 变为五 seed 均值 3864.8/4632.8/4856.8。

方差分解如下：普通 build seeds 的 Recall sample variance 为 1.87e−7；history seeds 在 checkpoint 1/10/100 分别为 2.30e−8、4.30e−8、1.30e−8，即 build variance 的 0.123×、0.230×、0.070×。所以 Recall 没有超过普通构建随机性。comparisons 的均值偏移虽可重复、超过其 build-seed std，但 100 轮仍只有 3.85%，低于预注册的 5% search-work 门槛；同时官方 IP-DiskANN 更低。

第 3 节五个静态 build seeds 即 static-rebuild reference。受 wall/RSS 限制，本轮用“5 个独立 build seeds + identity G0 上 5 个独立 update seeds”的一因素分解，而不是完整 5×5=25 个交叉组合；因此上述方差比可分离两类随机性，但不能估计 build×history interaction。

另做一个 1% batch、100 轮敏感性检查：

| checkpoint | Recall@10 | mean comparisons | Jaccard vs G0 | missing G0 edges |
|---:|---:|---:|---:|---:|
| 1 | 0.8161 | 3606.66 | 0.94381 | 1,850,076 |
| 10 | 0.8161 | 3609.34 | 0.94111 | 1,941,816 |
| 100 | 0.8161 | 3617.65 | 0.93314 | 2,213,490 |

相对 identity G0，1% 路径 100 轮为 −0.01 pp / +0.93%。per-query recall quantiles 在 checkpoint 1/10/100 均保持 p01=0.3、p10=0.6、p50=0.9、p90=1.0。

解释：结构继续漂移，但性能没有随结构漂移明显恶化。

## 5. A0-2：相同终态，不同构建历史

比较三条到达同一 SIFT1M 终态的路径，每条使用 seeds 11/22/33/44/55：

1. Path 1：一次性静态构建（输入物理顺序由 build seed 排列）；
2. Path 2：先 build 随机 500K，再按 10 批、每批 50K 插入其余 500K；
3. Path 3：先 build 500K，增量插入至 1.2M，再删除额外的 200K，恢复同一原始 1M tag/vector 集合。

下表均为 5-seed mean ±95% CI。`post-prune` 对所有路径统一执行 R=64 final prune；Path 3 的 consolidation 已使 degree 基本满足 R，因此 pre/post 数字相同。

| 路径 | edges | Recall@10 | mean calcs | calcs p50/p95/p99 | visited mean；p50/p95/p99 | Jaccard vs G0 |
|---|---:|---:|---:|---:|---:|---:|
| Path 1 static | 64.000M | 0.81592±0.00054 | 3614.93±4.40 | 3785.2/4578.4/4788.4 | 100.015；100/102/102.8 | 0.43683±0.00019 |
| Path 2 pre-prune | 72.587M | 0.81600±0.00036 | 3963.31±4.06 | 4156.8/5085.8/5374.8 | 99.710；100/101/102.2 | 0.41398±0.00061 |
| Path 2 post-prune | 64.000M | 0.81586±0.00052 | 3613.21±3.91 | 3781.2/4578.0/4814.2 | 99.980；100/102/102.6 | 0.43619±0.00059 |
| Path 3 post-prune | 63.999M | 0.81598±0.00010 | 3633.17±8.43 | 3796.6/4594.2/4823.0 | 100.149；100/102/103 | 0.43307±0.00047 |

相对 Path 1 五-seed均值，Path 2 post-prune 是 −0.006 pp Recall / −0.05% mean calcs；Path 3 是 +0.006 pp Recall / +0.50% mean calcs。两者都远小于预注册门槛，Recall 分布也完全落在普通 build-seed 区间内。

Path 2 裁剪前看似存在约 +9.6% 搜索成本，但它平均多出 8.587M 条边，源于 incremental insert 暂时允许约 1.3R degree slack，不是可归因于 history 的 equal-degree aging。统一边预算后差异消失，Jaccard 也回到普通 build-history 的约 0.437。

可选 sliding-window Path 4 未跑：Path 1–3、完整 10%×100 histories 和官方 IP-DiskANN 已触发 KILL gate，继续扩展到七历史矩阵不符合预注册 early-stop 原则。

## 6. A0-3：耦合式更新账本（部分完成）

在内存 harness 中增加了 changed-owner 与 edge-difference 账本，并计算两个反事实逻辑写量：

\[
W_{coupled}=N_{changed-owner}(512\text{B vector}+256\text{B adjacency}),
\]

\[
W_{topology}=N_{changed-owner}(256\text{B adjacency}).
\]

| 场景 | changed owners | coupled bytes | topology-only bytes | ratio |
|---|---:|---:|---:|---:|
| 1% cycle，checkpoint 100 | 412,007 | 316,421,376 | 105,473,792 | 3.0× |
| A0-2 Path 2 post-prune（5-seed mean） | 999,967 | 767,974,656 | 255,991,552 | 3.0× |
| A0-2 Path 3 post-prune（5-seed mean） | 999,974 | 767,979,725 | 255,993,242 | 3.0× |

这只是“若把终态发生变化的 owner 各重写一次”的 snapshot counterfactual，不是累计 application/filesystem/block 写量。它确认了 128d full vector 与 R=64 adjacency 耦合会产生约 3× 的逻辑写差，但这一点不足以单独构成新 ANN 论文，而且核心 aging gate 已失败。因此没有继续做 WAL/filesystem/block tracing；将该结果冒充完整 A0-3 会过度陈述。

## 7. A0-4：Oracle Shadow Replay（上界式部分验证）

本实验使用“G0 中存在、当前图缺失”的边作为 Oracle shadow candidates，再执行同一 robust prune。这比只保存历史淘汰边的真实 shadow 更直接地提供目标结构候选；若该 Oracle replay 仍无收益，则真实 shadow 很难在同一目标上获得更强收益。

| 场景 | candidates | replay accepted | acceptance | Jaccard before→after | Recall before→after | comparisons before→after |
|---|---:|---:|---:|---:|---:|---:|
| 1% cycles，100 轮 | 2,213,490 | 4,480 | 0.202% | 0.93314→0.93322 | 0.8161→0.8161 | 3617.65→3616.89 |
| Path 2 incremental post-prune（5 seeds） | 25,124,829 | 14,329,712 | 57.03% | 0.43619→0.62662 | 0.81586→0.81628 | 3613.21→3721.86 |
| Path 3 insert-delete post-prune（5 seeds） | 25,318,751 | 14,224,651 | 56.18% | 0.43307→0.62094 | 0.81598→0.81614 | 3633.17→3730.87 |

Path 2 中 Oracle replay 恢复了大量结构，但 Recall 只增加 0.042 pp，仍处于普通 build-seed range 内，同时 comparisons **增加 3.01%**；Path 3 则为 +0.016 pp / +2.69%。这说明“更像 G0”不等于更好的搜索性能。

Shadow 原始存储预算（仅 edge endpoints，不含 provenance metadata/index）：

- 1% cycles：8-byte encoding 17.7 MB；12-byte encoding 26.6 MB。
- Path 2 五种子平均：8-byte encoding 117.5 MB；12-byte encoding 176.3 MB，相当于 256 MB 基础 adjacency 的 45.9%–68.9%。
- Path 3 五种子平均：8-byte encoding 119.7 MB；12-byte encoding 179.6 MB，相当于 256 MB 基础 adjacency 的 46.8%–70.2%。

这里的存储预算只计算 Oracle replay 前相对 G0 缺失的边端点；`candidates` 还包含当前邻居，因此不能直接把 candidates × endpoint bytes 当作 shadow 存储量。该 replay 没有实现逐次 `(owner, displaced_edge, displaced_by, epoch)` 日志，也不是可部署 Shadow 原型。

因此 A0-4 命中 `KILL-SHADOW-NO-UTILITY`：即使给出 Oracle 候选，查询指标也没有实质收益，且候选存储膨胀明显。

## 8. 资源与复现

### 8.1 实测资源

| 实验 | wall time | max RSS | GPU |
|---|---:|---:|---:|
| 官方 DiskANN3 replacement 100 cycles | 2m05s | 1.94 GiB | 0 |
| 官方 IP-DiskANN explicit-delete 100 cycles | 1m58s | 1.92 GiB | 0 |
| PipeANN 1% ×100 cycles + Oracle replay | 10m40s | 2.98 GiB | 0 |
| PipeANN A0-2 500K+500K + prune + Oracle replay | 20m45s | 2.68 GiB | 0 |
| PipeANN 10% ×100 cycles，单 seed | 76–87m | 约 3.8 GiB | 0 |
| PipeANN Path 3，单 seed | 约 20m | 未单独采集 | 0 |

- 工作目录约 1.2 GB；A0 准备数据约 7.2 GB。
- 10% ×100 的五个 update seeds 并行执行，任务聚合 RSS 峰值约 19 GiB，未超过 24 GiB；五个静态 seed 的平均 build time 186.95 s。所有大文件在 NVMe，工作目录约 1.2 GB，A0 准备数据约 7.2 GB，均未超过 10 GiB data-disk 限制。

### 8.2 简化与未完成项

- 采用内存 `Index` fallback，故没有 PQ=32/SSD page-cache/I/O 口径；不能把本报告外推为驻盘 I/O 结论。
- 每个配置用 1,000/10,000 queries；base 为完整 SIFT1M。A0-1 做了 5 build + 5 update seeds，但没有跑 25 个全交叉组合。
- A0-2 完成 Path 1–3 各五种子；可选 sliding-window Path 4 在 KILL gate 后停止。
- A0-3 只有 logical snapshot counterfactual，没有实际 application/filesystem/block I/O tracing。
- A0-4 没有实现逐 epoch provenance 日志或“重新搜索候选”的 baseline，只做了 Oracle G0-diff replay。

### 8.3 关键产物

- 原始/汇总结果：`chat/codex/work/2026-07-22/graph_aging_a0/results/`
- 机器可读总表：`results/final_summary.json`
- 实验代码：`PipeANN/tests/graph_aging_a0.cpp`
- 官方 baseline 配置与 runbook：`baselines/ip_diskann_a0/`
- 固定的官方源码：`baselines/DiskANN3/`
- Tracker：`EXPERIMENT_TRACKER.md`

## 9. 最强反方审稿与回应

**反方 1：只测均匀 SIFT 与低比例 IP deletion，hot-cluster / adversarial history 可能仍 aging。** 这是真的，也是本轮边界。但原 proposal 的强 claim 是一般性 history-induced aging，并明确规定 IP-DiskANN 无 aging 即 KILL。现在没有资格在 gate 失败后，用尚未测的 workload 猜测来保住原 idea。若未来发现具体 adversarial construction，应作为新的、形式化的最坏情况问题重新 A0，而不是本 idea 的补实验。

**反方 2：IP-DiskANN 的 maintenance threshold 过于积极。** 是的，但本轮 gate 明确要求强 baseline；既然强 baseline 下 100 轮无老化，原问题不能靠削弱 baseline 来保留。

**反方 3：Oracle replay 不是真实 shadow。** 成立，但 Oracle 直接提供 G0 缺失边，已是面向“恢复原结构”目标的强候选来源；它仍没有查询收益，因此没有理由继续实现更复杂的 provenance 机制。

## 10. 最终裁决与 venue fit

最终裁决：**KILL-NO-PROBLEM，同时 KILL-SHADOW-NO-UTILITY**。

- A0-1：强 baseline 100 轮后无 gate-level performance aging。
- A0-2：degree inflation 混杂被移除后差异消失。
- A0-3：只确认已知式 coupling write opportunity，不能独立支撑 AAAI/IJCAI/NeurIPS/ICML 算法贡献。
- A0-4：Oracle replay 无实质查询收益且候选端点存储达基础 adjacency 的约 46%–70%。

当前形态不具备 AAAI/IJCAI/NeurIPS/ICML fit，也不建议继续补实验。只有找到可形式化、可构造、强 baseline 仍失败的 adversarial/hot-history family，并给出非启发式算法机制与界，才值得以新问题重启。
