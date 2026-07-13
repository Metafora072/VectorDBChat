# DGAI Selective Recoupling / Layout Debt Characterization R1

**日期**：2026-07-13
**Gate**：`gpt/share/dgai_recoupling_layout_debt_opportunity_gate_0713.md`
**结论**：Selective Recoupling 与 Dynamic Layout Debt 两条路线均不成立，停止在 characterization，不进入系统设计。

## 1. 结论摘要

本轮得到两个方向一致的否定性结果。

第一，DGAI 的查询访问确实存在可复用局部性，但它不是 topology/vector 共同装页独有的机会。在相同额外空间预算下，SIFT-900K 的 10% offline co-access capsule oracle 只减少 9.48% 的 unique pages/query，弱于 LRU 的 14.19% 和 vector-only 热点缓存的 18.18%；GIST-900K 上 capsule 只减少 8.16%，同样弱于 LRU 的 21.87% 和 vector cache 的 18.01%。skewed workload 下差距更大：SIFT/GIST 的 LRU 分别减少 69.42%/87.32%，capsule 只有 6.99%/4.28%。因此 capsule 没有形成强基线达不到的新 Pareto 点。

第二，持续更新没有积累可由 fresh layout 恢复的物理布局债务。SIFT uniform mixed update 到 20% 时，当前布局为 175.405 pages/query；恢复初始 tag 布局的 same-graph fresh reference 为 175.705，反而差 0.17%；occupancy compaction 为 181.105，反而差 3.25%。邻接 BFS 重排在 20% 可减少 8.26%，但 0% 时已经能减少 14.97%，收益随更新缩小而不是增长。clustered mixed update 的 aligned/separate 区域在 20% 时 fresh reference 也分别差 1.13%/0.326%。这排除了“更新使原布局持续偏离、fresh layout 可恢复”的核心前提。

更新后 recall 的确下降：uniform mixed 的全体查询均值从 0.9970 降至 0.9632，clustered mixed 的 aligned 区域从 0.9970 降至 0.9467。但 C4 在完全相同的逻辑查询路径上只重放物理布局，所有 layout view 的 recall 按构造相同，因此该下降属于 graph/search-quality 现象，不能归因于 layout debt。

独立 result-to-claim 审阅给出：`claim_supported=no`、`confidence=high`、`recommended_action=kill`。若继续追查 recall 下降，必须作为新的 graph maintenance 问题重新立 gate，不能沿用本轮两个叙事。

## 2. 实验边界与证据类型

### 2.1 可执行基础

- DGAI source commit：`a0179b876a4bd453336dc2893b46ae890f680555`，保留此前 measurement instrumentation，不提交或覆盖用户工作树。
- 正式索引策略：DGAI 官方脚本使用的 strategy 23；SIFT 初次 strategy 1 运行只作为错误口径控制，不进入主结论。
- SIFT-900K：128 维，正式 C0 使用 10,000 queries、top-10、L=100。
- GIST-900K：960 维，正式 C0 使用 1,000 queries、top-10、L=400、beam width 32。
- 所有 build、索引视图、layout snapshot 和原始 trace 均位于项目 NVMe：`/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_recoupling_layout_debt`。
- 完成时系统盘占用 45%，项目 NVMe 占用 15%；没有在系统盘创建大索引或原始 trace。

### 2.2 三类证据必须分开解释

1. **直接实测**：C0 查询 latency/recall/搜索轨迹；C3 当前 long-running index 查询；真实 delete+reinsert 更新、插入 latency 和 host I/O counters。
2. **page-exact trace replay**：C1/C2 的 B1/B2/B4/B5 和 C4 的 M1--M3。在固定逻辑访问序列上替换物理 page mapping，计算 logical unique page demand；这不是完整在线系统的端到端实测。
3. **不可实现 oracle**：B5 使用训练 trace 构造并在 held-out queries 评估；M4 直接使用 future held-out co-access，只表示页面数上界，未建立 latency 模型。

B3 是最小 next-page prefetch 对照。它不改变 demand path，却几乎没有 useful prefetch（SIFT/GIST 每查询约 0.02/0.03 pages），并使计入 speculative read 的页面数近乎翻倍；只说明这种简单预测器无效，不代表所有 prefetch 都无效。

## 3. C0：统一 trace 与正确性

measurement-only patch 记录 topology node/page 序列、expanded nodes、rerank node/page 序列、heap events、latency、recall 和更新 RMW/page events。正式 trace 均可逐行解析。

| 数据集 | Queries | Mean recall@10 | P50 / P95 / P99 latency | 轨迹一致性 |
|---|---:|---:|---:|---|
| SIFT-900K | 10,000 | 0.99779 | 2.201 / 2.592 / 2.840 ms | topology trace=stat 1,096,291；coordinate trace=stat 1,000,000；true |
| GIST-900K | 1,000 | 0.9794 | 8.492 / 10.696 / 12.735 ms | true |

这里的 topology/vector page 序列是由 DGAI 当前 location mapping 得到的逻辑物理位置；不能把所有 logical page demand 都写成块设备实际提交次数。C1--C4 因而统一使用 unique page demand 比较布局，不宣称 device I/O latency 已被直接复现。

## 4. C1/C2：Selective Recoupling 与强基线

训练与 held-out query IDs 对每种 workload 均不重合。预算按 active topology+vector store 大小计算：SIFT 为 777,643,804 B，GIST 为 4,008,494,876 B。比较 1%/5%/10% 三个预算点；下表给出最有利的 10% 点，括号为相对 B0 的 unique pages/query 降幅。

| 数据集 / workload | B0 | B1 LRU | B2 vector-hot | B4 static full record | B5 coaccess capsule oracle |
|---|---:|---:|---:|---:|---:|
| SIFT same/uniform | 175.786 | 150.842 (-14.19%) | 143.828 (-18.18%) | 163.198 (-7.16%) | 159.117 (-9.48%) |
| SIFT hotspot shift | 176.526 | 150.920 (-14.51%) | 149.620 (-15.24%) | 166.168 (-5.87%) | 163.030 (-7.65%) |
| SIFT skewed | 177.592 | 54.316 (-69.42%) | 160.222 (-9.78%) | 168.288 (-5.24%) | 165.175 (-6.99%) |
| GIST same/uniform | 719.348 | 562.015 (-21.87%) | 589.783 (-18.01%) | 660.645 (-8.16%) | 660.663 (-8.16%) |
| GIST hotspot shift | 714.265 | 547.524 (-23.34%) | 616.994 (-13.62%) | 669.253 (-6.30%) | 669.188 (-6.31%) |
| GIST skewed | 719.213 | 91.185 (-87.32%) | 676.935 (-5.88%) | 688.410 (-4.28%) | 688.410 (-4.28%) |

结论不是“没有访问局部性”，而是最可利用的局部性已被普通 LRU 或 vector-only hotspot capture。co-access packing 相对 static full-record 的增益很小，在 GIST 10% 点甚至完全相同；跨 store 共置不是必要条件。

区域异质性同样没有救回 capsule：SIFT topology page 的 top-1% access share 为 9.11%、Gini 0.371；vector page 分别为 4.28%/0.330。热点存在但不极端，而且普通缓存更直接地兑现了热点。

## 5. Capsule lifetime 与维护成本

SIFT 10% capsule 包含 100,731 nodes、22,496 capsule pages；在 held-out queries 上理论减少 68,274 B/query。将真实 mixed update 的 target 和 insert 实际触及 topology pages 映射到 capsule：

| Update checkpoint | 仅 target 节点页失效 | target + actual insert-page 失效 | 全 topology page-version 保守失效 | 乐观 rebuild / break-even |
|---:|---:|---:|---:|---:|
| 1% | 2.25% | 99.54% | 100% | 91.7 MB / 1,343 queries |
| 5% | 10.58% | 100% | 100% | 92.1 MB / 1,350 queries |
| 10% | 20.70% | 100% | 100% | 92.1 MB / 1,350 queries |
| 20% | 37.45% | 100% | 100% | 92.1 MB / 1,350 queries |

删除路径在每个 checkpoint 扫描并重写全部 topology pages，因此页面级 source-version 会立即使 capsule 全失效。`target + actual insert-page` 是偏乐观下界，因为 deletion 导致的邻居表逻辑修改没有逐项 trace；“全失效”是页面版本协议的保守上界。即使使用乐观口径，1% 时已失效 99.54%，且要约 1.3k 后续查询才能摊销一次重建，生命周期不成立。

## 6. C3：真实更新进程与布局状态

SIFT 从同一 900k active-record index 出发，在 1/5/10/20% checkpoint 执行 delete+reinsert 同一 tag/vector 的真实 mixed refresh；20% 对应累计 90k refresh（180k delete/insert operations）。全程 insertion failure 为 0，active records 始终 900k，因而没有把数据量变化混入比较。

| Checkpoint | Mean recall@10（全体 query） | Topology mean occupancy | Topology pages <50% | Vector occupancy |
|---:|---:|---:|---:|---:|
| 0% | 0.9970 | 0.7757 | 8.31% | 1.0000 |
| 1% | 0.9961 | 0.7757 | 8.34% | 1.0000 |
| 5% | 0.9908 | 0.7757 | 8.44% | 1.0000 |
| 10% | 0.9832 | 0.7757 | 8.74% | 1.0000 |
| 20% | 0.9632 | 0.7757 | 9.10% | 1.0000 |

occupancy 仅出现很小的低占用尾部增长，没有全局恶化。写成本却很高：各阶段 insert host I/O 为 0.885/3.533/4.397/8.778 GB，insert P50 为 4.706/4.628/4.715/4.841 ms，P95 为 6.829/5.460/7.281/7.682 ms；每个 delete checkpoint 还写约 316.85 MB topology。它说明全局重建/频繁 capsule rebuild 不便宜，但本轮没有找到值得支付该成本的布局收益。

## 7. C4：same-graph fresh/simple maintenance

C4 固定每个 query 的逻辑 node/page demand 和 recall，只改变物理映射。实际 current-index latency 仅用于校准；M1--M3 latency 是模型值，主判断使用 page counts。M4 不建 latency 模型。

| Checkpoint | M0 current | M1 restored initial/fresh | M2 compact | M3 adjacency | M4 future coaccess oracle |
|---:|---:|---:|---:|---:|---:|
| 0% | 174.350 | 174.350 | 179.608 | 148.255 (-14.97%) | 29.560 |
| 1% | 175.180 | 175.200 | 180.525 | 未运行 | 未运行 |
| 5% | 175.665 | 175.703 | 180.880 | 未运行 | 未运行 |
| 10% | 175.680 | 175.788 | 181.145 | 未运行 | 未运行 |
| 20% | 175.405 | 175.705 (+0.17%) | 181.105 (+3.25%) | 160.915 (-8.26%) | 30.363 |

M1 在任何非零 checkpoint 都没有优于 M0，因此不存在随时间增长、可由 fresh layout 恢复的 debt。M2 说明 occupancy-only compact 还会破坏当前共同访问。M3 证明“按 adjacency 做更好的静态布局”有机会，但 0% 的 14.97% 明显大于 20% 的 8.26%，不能包装成动态债务管理。M4 的 82.69% 页面上界依赖未来 evaluation trace，表明页面排列的离线极限很高，但不提供可部署信号。

### Clustered updates 与区域异质性

额外 clustered mixed stream 将 update IDs 集中到前 1,500 个 query 的 GT 区域，并分别测 aligned（qid 0--999）与 separate（qid 2000--2999）区域：

| 20% region | Current pages | Fresh same-graph pages | Fresh improvement | Recall@10 |
|---|---:|---:|---:|---:|
| aligned | 175.289 | 177.273 | -1.13% | 0.9467 |
| separate | 177.714 | 178.293 | -0.326% | 0.9590 |

即使更新和查询热点对齐，fresh layout 仍没有恢复 page locality。recall 在 aligned 区域下降更多，进一步指向动态图维护质量，而不是物理布局债务。

## 8. Gate 完整性与早停

直接执行了两组真实 mixed update stream：uniform mixed 与 clustered mixed，二者都包含 delete+reinsert，并覆盖 aligned/separate query regions。没有再单独运行 insert-only 和 delete-only 的完整 checkpoint stream；GIST 也只完成 C0--C2，没有复制 C3--C4。原因是 SIFT 的两种更新分布已经在 0--20% 全曲线上给出 same-graph fresh 反证，而 GIST 又独立复现了 selective recoupling 输给强基线。按 gate 的“两者都弱则不强行设计系统”早停，这些缺项登记为外部有效性限制，不伪装为已完成。

DecoupleVS 只作为 related work；没有使用、复现或推断其不可获得的 artifact。

## 9. Result-to-claim 与最终路线

### 支持的窄结论

- DGAI 存在普通页面热点，LRU/vector-hot 能利用。
- DGAI 的初始静态物理排列不是 adjacency page locality 的最优排列。
- 真实 refresh updates 后 graph/search recall 明显下降，值得另行诊断。

### 不支持的核心 claim

- 不支持 selective recoupling/capsule 超越普通缓存、vector cache 或 static replication。
- 不支持 capsule 在兑现收益前保持有效。
- 不支持 updates 累积由 fresh/compact/adjacency maintenance 恢复的增长型 layout debt。
- 不支持把 recall 下降归因于 physical layout。

### 裁决

**Kill Selective Recoupling；Kill Dynamic Layout Debt；不统一两条路线；不实现完整系统。**

如果 GPT/PZ 选择继续 DGAI，唯一由本轮新暴露、但尚未形成 claim 的现象是 update-induced graph/search-quality degradation。下一轮必须先拆分 delete、reinsert、邻居修复和搜索入口等因素，并定义图质量 oracle；不能把本报告当作该新方向已经成立的证据。

## 10. 复现证据索引

- SIFT C0：`.../runs/sift_strategy23_c0_formal_10000.jsonl`
- GIST C0：`.../runs/gist_strategy23_c0_formal_1000.jsonl`
- SIFT C1/C2：`.../runs/sift_strategy23_c1_c2_r1/c1_c2_summary.csv`
- GIST C1/C2：`.../runs/gist_strategy23_c1_c2_r1/c1_c2_summary.csv`
- Uniform C3 raw：`.../runs/sift_strategy23_c3_uniform_mixed_r1/`
- C3/C4 analysis：`.../runs/sift_strategy23_c3_c4_analysis_r2/`
- Clustered C3 raw/regions：`.../runs/sift_strategy23_c3_clustered_mixed_r1/`
- canonical harness：`codex/share/dgai_opportunity_trace.cpp`、`codex/share/dgai_layout_debt_trace.cpp`
- analysis scripts/tracker：`codex/work/dgai_recoupling_layout_debt/`

上述 `...` 均指 `/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_recoupling_layout_debt`。
