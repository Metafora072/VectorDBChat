# Dynamic Vamana M0–M3 Final Novelty Review

**审议时间：** 2026-07-18（UTC+8）  
**审议范围：** M0–M3 runtime evidence、论文原文与官方代码/项目材料  
**最终建议：** `ABANDON IMPLEMENTATION / CLOSE THIS DIRECTION`  
**机制 novelty 评分：** `2/10`

## 1. 最终裁决

M0–M3 已完整回答当前研究链的证据问题，但没有产出一个同时满足问题真实性、机制新颖性和系统实现门禁的 Dynamic Vamana 写优化机制。

必须采用以下正式结论：

> M0–M3没有产生可继续实现的Dynamic Vamana写优化idea。

因此本轮：

- 不构建 matched-R base；
- 不实现 queue coalescing；
- 不通过修改 page lock、提交顺序或 durability contract 强行制造合并机会；
- 不把 Claude 提出的“部分可见”“分层持久化”直接转为原型；
- 不自动启动多 NVMe 或其他新方向实验。

M0–M3 仍形成了有价值的否定性 characterization：跨系统写差距严重混杂；neighbor-repair 写入可精确分解；现有锁与提交状态机中 same-page pre-submit supersession 机会为零。这些结果可用于关闭错误因果叙述和约束后续选题，但不足以单独构成新的写优化系统。

## 2. M0–M3 最终证据边界

1. M0/M1 将 recurring update-window 的主要跨系统差距定位到 insert-neighbor-repair，并证明 target-only 与 shared-page 合计均为 `4096 bytes/replacement`。
2. M2 将 neighbor-repair page touches 精确分解为 `scheduled repair fanout × page mapping × temporal rewriting`。
3. DGAI 与 OdinANN 的实验配置不是单变量对照：前者为 `R=32`、644 B/record、6 records/page；后者为 `R=96`、900 B/record、4 records/page，且 search、prune、position allocation、cache、I/O engine、publish/save 路径均不同。
4. `R=96/32` 只产生 `3× scheduled repair attempts`，不等于 3× 有效图修改、3× 端到端写入，亦不代表 online visibility 的代价。
5. M3 的 `22,522,471` 个 neighbor-only page-version events 全部满足 lifecycle/physical closure；四点的 pre-enqueue、queued 和 inflight supersession 均精确为零。
6. 所有 same-page repeats 均发生在 prior completion 之后；current background queue 的 page-key coalescing 无法消除这些写入。
7. 实验中的 online visibility、application completion、fresh-process visibility 和 crash durability 是四个不同边界。四个 M3 点没有 `fsync/fdatasync`，不能把 completion 或 fresh-process smoke 升格为 crash durability。

据此正式 Kill：

> 利用现有 background queue 进行 same-page pre-submit supersession/queue coalescing。

## 3. 核心候选主张与 novelty

| Core claim | Novelty | Closest prior/evidence | 裁决 |
|---|---|---|---|
| 解耦 vector 与 topology，避免 topology-only 更新重写 vector | LOW | DGAI 直接以物理解耦消除冗余 vector I/O | 已占据 |
| 只修改 affected vertices/pages，并减少 reverse/replacement edges | LOW | Greator、IP-DiskANN、Wolverine、SVFusion | 已占据 |
| 让 target 先可见、repair/传播/合并稍后完成，形成 freshness-write 中间态 | LOW–MEDIUM（问题）；LOW（当前机制） | FreshDiskANN 的 searchable in-memory delta；SVFusion 的 CPU commit、异步批量 GPU propagation、version fallback | 问题不是空白，当前提案无新不变量 |
| 利用 stage-wide temporal rewrite 做普通 page buffering/coalescing | LOW | OdinANN 已做 page update combining；Greator 有 page-aware reverse-edge cache；M3 又证明当前 queue 的可覆盖机会为零 | 机制被 prior art 与本地反证同时封闭 |
| 放宽 crash durability 换取写合并 | MEDIUM（宽泛设计空间）；LOW（当前候选） | FreshDiskANN/SVFusion 已有分层、版本化和后台合并，但都没有给本候选提供可直接复用的 Vamana crash invariant | 未被 M0–M3 观测为跨系统差距来源，且无状态机，未过门禁 |

这里需要区分 finding novelty 与 mechanism novelty。M2/M3 对广泛 temporal rewriting、page-version lifecycle 和零 supersession 的精确测量具有一定 characterization 新意；但“观察到了重复”不等于“存在可安全删除的写”，更不等于已有新系统机制。

## 4. Prior-work matrix

| Work | Update semantics | Storage layout | Repair scope | Write-reduction mechanism | Visibility/durability | Remaining boundary |
|---|---|---|---|---|---|---|
| [FreshDiskANN](https://arxiv.org/pdf/2105.09613) | Inserts/deletes/searches concurrent；近期更新进入内存 FreshVamana，周期性 StreamingMerge | 长期 SSD index + 短期内存 index | delete consolidation 与 insert merge，计算/空间随 change set | 两遍 StreamingMerge、批量磁盘写、内存 delta 摊薄 SSD 更新 | 论文要求 quiescent consistency，查询覆盖 latest content；未给出本实验口径的 crash-durability contract | merge 干扰、稳态速率受 merge 限制；但已直接占据“即时可查 delta + 延迟 SSD 合并” |
| [DGAI v5](https://arxiv.org/pdf/2510.25401) | 论文描述 direct in-place insertion/update；本地冻结 artifact 则需 publish/reload 才通过 fresh visibility | topology 与 raw vector 分离；内存 PQ；similarity-aware dynamic page layout | insertion search、new-node link 与 reverse-edge maintenance | topology-only 修改不重写 raw vectors；nearest-neighbor page placement、page split | 论文未给出精确 crash contract；论文语义与本地 artifact 的 visibility 行为不一致，不能混用 | query read amplification、paper/artifact 版本差异；但 decoupling 与 page-aware layout 已占据 |
| [OdinANN](https://www.usenix.org/system/files/fast26-guo.pdf) | Direct insert；buffered delete + periodic merge | coupled fixed-size records；页内预留 free slots；DRAM ID→location/PQ | target 与 tens/hundreds neighbor records；delete 后台 merge | GC-free out-of-place record update、同页 update combining、on-path cached page reuse | per-record snapshot/approximate concurrency，而非整操作原子性；论文未证明 crash durability | 默认约 2× 空间，delete 仍 merge；M3 表明当前实现无 pre-submit same-page supersession |
| [IP-DiskANN](https://arxiv.org/pdf/2502.13826) | 单次 insertion/deletion in-place，避免批量 consolidation | singly-linked proximity graph；论文重点是算法而非 SSD physical layout | 搜索近似 in-neighbors；每个受影响方向至多复制少量 replacement edges；仍周期清理 dangling edges | 将 repair 从全批 consolidation 收窄为近似 in-neighbor search 和 `O(cR)` edge additions | 未定义 SSD page、online/fresh/crash 的端到端系统 contract | 物理写放大与多 NVMe 未闭合；但“避免 global consolidation”和“少 replacement edges”已占据 |
| [Greator / Topology-Aware Localized Update](https://www.vldb.org/pvldb/vol19/p495-yu.pdf) | 小批 delete→insert→patch | lightweight topology + query index；page-level localized I/O；libaio | 只识别 affected vertices/pages；reverse edges 按 page-aware `ΔG` 延后 patch | 不扫完整 vector index；只写 affected pages；similar-neighbor replacement；relaxed degree 减少 prune | 以 batch 更新磁盘 index；没有给出与本轮一致的 online/fresh/crash contract | 主要针对小批 delete/patch，但直接占据 affected-only、localized write、少 repair edges 和 page-aware buffering |
| [Wolverine](https://www.vldb.org/pvldb/vol18/p2268-zheng.pdf) | Dynamic deletion repair | 主要是内存图算法评测，不是完整 SSD layout | 修复被删除点打断的 monotonic paths；2-hop candidate restriction 与候选筛选 | 只恢复必要路径、缩小 repair search/edge set | 未提供 SSD durability contract | SSD physical write未闭合；但“减少 repair 边/限定 repair scope”不再是空白 |
| [SVFusion](https://www.vldb.org/pvldb/vol19/p1074-yang.pdf) | Streaming insert；lazy delete；localized repair；异步 global consolidation | GPU–CPU–disk hierarchy；CPU 完整 graph、多版本；GPU hot subgraph/cache | insert reverse edges；严重受损 vertex 的 localized repair；threshold 后 snapshot consolidation | rank-based neighbor selection、thread-local buffer、batch async propagation、增量 subgraph append、reverse-edge log merge | CPU 先 commit version，GPU 分批异步传播；version conflict 查询回退 CPU；多版本 snapshot；未明确 SSD crash durability | 依赖 GPU、含阈值策略，但已直接占据分层可见、异步传播、版本回退与 repair/consolidation 中间态 |
| [Slipstream](https://arxiv.org/abs/2606.02992) | Streaming insert | Faiss/HNSW in-memory implementations | 复用前一次 insertion 的 promising candidates，优化 position seeking | 减少重复 candidate search，而非 page writes | 未讨论 SSD durability | 不解决本轮 physical write；说明 2026 最新工作还在占据 update search 复用空间 |
| [Disk-Resident Graph ANN Search: Experimental Evaluation](https://arxiv.org/abs/2603.01779) | 统一比较 in-place/out-of-place update | 跨 storage/layout/cache/execution/update taxonomy | 非新 repair 算法 | 实证 page size、layout utilization 和 update strategy trade-off | 非事务/持久化机制 | 属于 characterization；进一步压缩“普通 page/block tuning”作为系统贡献的空间 |

## 5. 九类候选空间门禁

| Candidate space | M0–M3 direct observation | Prior occupancy | Gate result |
|---|---|---|---|
| 1. vector/topology decoupling | 4 KiB RMW 与 record payload 已量化 | DGAI | FAIL：机制直接重复 |
| 2. affected-vertex-only update | neighbor repair 是主要 recurring component | Greator、IP-DiskANN、SVFusion | FAIL：affected set/localized page repair 已直接实现 |
| 3. fewer reverse/replacement edges | scheduled/accepted/mutated counts已观测 | Greator、IP-DiskANN、Wolverine、SVFusion | FAIL：简单降 R 是参数调优；少边 repair 已有直接先例；无新图不变量 |
| 4. avoid global consolidation | 两系统固定 publish/save bytes 已观测 | IP-DiskANN direct in-place；OdinANN/DGAI direct insert；FreshDiskANN/SVFusion incremental merge | FAIL：当前只描述成本，没有新状态机 |
| 5. direct in-place insertion | target 与 neighbor write path 已完整归因 | OdinANN、DGAI、IP-DiskANN | FAIL：直接重复 |
| 6. batch/lazy update | publish 固定成本与 batch 摊销已观测 | FreshDiskANN、OdinANN buffered delete、SVFusion | FAIL：直接重复 |
| 7. page/block-aware layout | record/page capacity 与 mapping factor 已观测 | OdinANN、DGAI、Greator；最新 DSE 亦已系统比较 | FAIL：普通 packing/page-size/layout tuning 不足以形成新机制 |
| 8. background buffering/page coalescing | M3 直接测量 | OdinANN/Greator已有 combining/buffer；本地机会精确为0 | FAIL：本实现中机械收益上界为0 |
| 9. relax durability for merging | M3 仅证明无 `fsync/fdatasync`，没有证明 durability 导致写差距 | FreshDiskANN/SVFusion 已有内存 delta、异步版本传播；一般存储缓冲更是成熟机制 | FAIL：缺直接问题证据、状态机、恢复不变量与语义保持证明 |

九类空间中没有一项通过全部门禁。

## 6. 对 Claude P4/P10 的正式修正

### P4：广泛 temporal rewrite

P4 的测量事实成立：OdinANN neighbor-only bytes/replacement 从 50K 的约 128.6 KB 增至 400K 的约 176.7 KB，400K temporal rewrite factor 约 5.0，重复广泛分布而非少数热点主导。

但以下外推不成立：

- 不能仅由 rewrite factor 上升断言端到端写入“超线性增长”；四点没有建立该复杂度模型；
- 不能把 stage-wide repeated page 计为可合并版本；M3 的可覆盖计数为零；
- 不能由当前结果授权跨 completion 延迟写回，因为那会改变锁、可见性和恢复语义；
- 不能把 temporal rewrite 归因为 online visibility，跨系统仍有参数、布局、算法和执行引擎混杂。

因此 P4 是 `MEDIUM novelty characterization / LOW novelty mechanism`，不足以进入实现。

### P10：visibility-write 中间态

“现有系统没有探索中间态”是错误判断：

- FreshDiskANN 已让近期更新驻留于 searchable in-memory index，同时后台合并到长期 SSD index；
- SVFusion 已让 topology 先提交 CPU version，再批量异步传播到 GPU，传播期间由 version conflict 触发 CPU fallback；后台 consolidation 又使用 snapshot、多版本、增量 append 和 reverse-edge integration；
- OdinANN 已采用 per-record consistency，而非整次 insert 的强隔离。

“只有 target 立即可查、reverse edges 延迟”仍可能被写成一个不同的具体状态机，但当前没有给出：旧图到新点/新点到旧图的可达性不变量、查询 fallback、repair debt 上界、fresh-process 恢复规则、crash replay、何时提交 durability，以及不依赖模糊阈值的转换条件。M0–M3 也没有证明该状态机能消除已观测物理写。因此它目前只是未具体化的设计口号，未通过门禁 1、4、5、6、9。

## 7. 历史叙述纠正

以下历史文件已在开头标为中间分析：

- `codex/share/2026-07-17/dynamic_vamana_w1_final_five_point_review_0717.md`；
- `claude/share/2026-07-18/dynamic_vamana_write_attribution_m0_m3_analysis_0718.md`；
- `claude/share/2026-07-18/dynamic_vamana_dgai_odinann_problem_diagnosis_0718.md`。

后续不得引用下列表述作为最终结论：

- online visibility 导致约 4–5× 写放大；
- OdinANN 写放大主要来自其在线可见性机制；
- 3× scheduled fanout 说明至少 3× 总写入来自 R；
- stage-wide rewrite 可由 queue coalescing 消除；
- queue 更深意味着更多 same-page 合并机会。

正确表述是：`3×` 仅为 scheduled repair attempts 的计数比；跨系统物理写差距是参数、布局、算法与执行路径的组合结果；当前 page-lock-to-completion 状态机下 pre-submit same-page supersession 为零。

## 8. Matched-R 与下一研究线

### Matched-R

不构建 matched-R。它只能回答统一数值配置后组合差距是否仍存在，不能隔离 visibility、repair algorithm、layout、cache、I/O engine 或 publish/save 中任何单一机制。本轮没有候选机制依赖 matched-R residual，因此不满足重新授权条件。

### 多 NVMe / query path

不能把“方向关闭”直接解释为应恢复旧的多 NVMe graph-aware placement。该候选此前已因普通 page striping/hash baseline 和 PipeANN 的 SPDK multi-SSD 路径而被 Kill；PipeANN 官方项目目前也明确报告 4 SSD SPDK 扩展。因此原样返回会重复 prior work。

query-path I/O parallelism、dependent-read scheduling 或 early exact-distance speculation 具有独立于本轮错误写因果的动机，但该空间同样拥挤：[PipeANN](https://github.com/thustorage/PipeANN) 已处理 pipelined/SPDK graph I/O，[NAVIS](https://arxiv.org/abs/2605.11523) 已处理 position seeking/selective vector read/cache，近期 [I/O DSE](https://arxiv.org/abs/2602.21514) 又系统比较 layout/search 组合。本地最小 next-page prefetch B3 也几乎没有 useful prefetch，并使 speculative reads 近乎翻倍。

若未来重新进入 query path，必须从新的 runtime observation 开始，并提出不同于普通 prefetch、SPDK striping、dynamic beam 或 cache tuning 的明确 dependency/state machine；在新的 novelty gate 前不启动实验。当前只保留以下排序：

1. `Dynamic Vamana write optimization`：关闭；
2. `原多-NVMe graph-aware placement`：维持既有 Kill；
3. `独立 query-path problem discovery`：可由 Gpt/PZ 另行立项，但不是本轮自动 continuation；
4. `decoupled-query locality repair`：DGAI/NAVIS 已占据主要机制，只有新的直接残余证据才可重开。

## 9. Sources and audit boundary

本报告仅使用论文原文、正式会议/期刊页面、官方代码仓库和 M0–M3 machine evidence。核心原始来源为：

- FreshDiskANN: <https://arxiv.org/pdf/2105.09613>
- DGAI: <https://arxiv.org/pdf/2510.25401>
- OdinANN: <https://www.usenix.org/system/files/fast26-guo.pdf>
- IP-DiskANN: <https://arxiv.org/pdf/2502.13826>
- Greator: <https://www.vldb.org/pvldb/vol19/p495-yu.pdf>
- Wolverine: <https://www.vldb.org/pvldb/vol18/p2268-zheng.pdf>
- SVFusion: <https://www.vldb.org/pvldb/vol19/p1074-yang.pdf>
- Slipstream: <https://arxiv.org/abs/2606.02992>
- Disk-resident ANN experimental evaluation: <https://arxiv.org/abs/2603.01779>
- PipeANN official repository: <https://github.com/thustorage/PipeANN>
- NAVIS: <https://arxiv.org/abs/2605.11523>
- I/O DSE / OctopusANN: <https://arxiv.org/abs/2602.21514>

M0–M3 local evidence anchors：

- `codex/share/2026-07-17/dynamic_vamana_write_attribution_m0_0717.md`；
- `codex/share/2026-07-18/dynamic_vamana_write_attribution_m1_scale_0718.md`；
- `codex/share/2026-07-18/dynamic_vamana_neighbor_repair_m2_0718.md`；
- `codex/share/2026-07-18/dynamic_vamana_write_supersession_m3_0718.md`；
- M3 summary SHA-256：`415e90fc141afa8baf0171815b2ca67827a4b82b4c96c63680f50274e91c4748`。

独立审稿式 novelty audit 对上述证据进行二次核验，给出相同的 `2/10` 机制 novelty、无候选通过九项门禁、关闭当前实现线的结论。

报告到此停止，不启动任何新实验。
