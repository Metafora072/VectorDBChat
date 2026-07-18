# Dynamic ANN Architecture Frontier A0

**审计日期：** 2026-07-18（UTC+8）  
**审计类型：** existing-work limitation / primary-source / paper–artifact boundary audit  
**资源边界：** 只读；未运行实验、未构建索引、未编译、未修改系统代码；新增空间远小于 1 GiB  
**最终裁决：** `KILL / SWITCH DIRECTION`  
**保留候选：** `0`

## 1. 结论

A0 确认了一个真实但已被现有架构完整展开的 frontier：动态驻盘图 ANN 要么把新状态保留为额外组件，支付 query fan-out、内存或 compaction/materialization debt；要么立即修改单一 authoritative graph，支付随机 page update、邻接修复、并发控制与写干扰。Localized patch 可以把 direct update 收窄到 affected pages，但 Greator 已经占据这一点；LSM-VEC 又把 out-of-place multilevel graph、edge delta、compaction 与动态 locality maintenance 纳入同一架构。

本轮没有找到一种同时满足以下条件的机制：

1. 不是 `memory delta + localized repair + LSM` 的组合；
2. 有新的 authoritative state、更新状态机及至少三个 ANN-specific invariant；
3. 至少一个现有架构无法通过局部扩展实现；
4. 与 M0–M3 的直接观测相连，但不继承已推翻的 visibility 因果；
5. 能在单机、多 NVMe、无 GPU 条件下，以 matched semantics 和 matched quality 公平验证；
6. 独立反方评分同时达到 significance 7、novelty 6、depth 7、feasibility 7。

因此 A0 不进入 profiling、matched-R、代码准备或系统原型。Dynamic ANN architecture continuation 应关闭；后续只有在出现一个独立 runtime anomaly 和新的问题证据后，才值得重新立项。

## 2. 审计口径与事实边界

### 2.1 不做跨论文伪精确 Pareto 排名

M0–M3 的 `target / neighbor repair / publish` 分解只对本地冻结 DGAI/OdinANN artifact 有机械闭合意义。FreshDiskANN 的 update 先进入 TempIndex，Greator 是 delete/insert/patch 小批流程，LSM-VEC 的物化单位是 LSM edge records，SVFusion 又包含 CPU–GPU–disk 版本传播。A0 只比较状态表示、物化单位和不可避免的税，不用不匹配的论文数字计算“谁严格支配谁”。

### 2.2 DGAI paper 与本地 artifact 分开

[DGAI 论文](https://arxiv.org/pdf/2510.25401)描述的是 direct insertion：topology 与 raw vector 物理解耦，PQ 常驻内存；新点放入最相似邻居所在 page，有空槽则增量写入，满页时进行 similarity-aware split。论文因此已经给出 incremental page layout，不能把本地冻结 artifact 的固定 save/publish/reload 路径写成 DGAI 架构必然要求全局 publish。

本地 artifact（基线 commit `a0179b876a4bd453336dc2893b46ae890f680555`，其上有 M0–M3 measurement-only patch）只支持以下 machine-specific 事实：本轮执行路径在 stage 结束后才通过固定 publish/reload 通过 fresh-process visibility；该事实可以用于解释本地结果，不能反推论文算法。两者在本报告中始终分列。

### 2.3 FreshDiskANN merge 不是 rebuild

[FreshDiskANN](https://arxiv.org/pdf/2105.09613)的 StreamingMerge 不是重建完整图算法。它的计算和 `Δ` 空间主要与 change set 有关；但 Delete/Patch 两阶段确实对长期 SSD index 做 exactly two sequential passes，并生成 intermediate/final LTI。准确边界是“两次全 LTI 顺序 pass”，不是“full rebuild”，也不是“所有工作都只与 `Δ` 成比例”。

### 2.4 LSM-VEC paper 与当前 AsterVec main 分开

[LSM-VEC](https://arxiv.org/pdf/2505.17152)论文把 HNSW bottom layer 放入 Aster graph-oriented LSM，双向 edge 以 source-ID/neighbor-ID KV 先进入内存 buffer，再通过 compaction 下沉；论文删除算法执行 local relink。论文给出的仓库入口现在重定向到 [AsterVec](https://github.com/NTU-Siqiang-Group/AsterVec)，而 current main 的 `deleteNode` 使用 tombstone 并保留 graph/vector routing state。current main 证明 lazy delete 是另一可行设计，但不是论文实验 artifact 的同语义局部优化，后续不得混作同一版本。

## 3. Primary-source matrix

| System/source | Freshness path | Materialization unit / repair | Query tax | Resource / stability tax | 本轮边界 |
|---|---|---|---|---|---|
| [FreshDiskANN](https://arxiv.org/pdf/2105.09613) | 查询同时搜索 LTI、RW-TempIndex、所有 RO-TempIndex，并过滤 DeleteList；merge 后才进入新 LTI | memory graph + DeleteList；StreamingMerge 的 Delete/Insert/Patch，两个全 LTI 顺序 pass | 多 index fan-out；merge 的随机/顺序 I/O 与 query 竞争 | TempIndex/`Δ`/PQ 占 DRAM；持续 update rate 由 merge 控制；merge 产生 latency spikes | Family A 代表；已占 searchable delta + periodic merge |
| [DGAI paper](https://arxiv.org/pdf/2510.25401) | direct insertion 更新 topology pages；论文不要求本地固定 publish | decoupled topology page；nearest-neighbor page placement，满页 split，reverse-edge maintenance | decoupling 产生 sparse topology page 和 vector/topology double-read 风险；HPQ/rerank 用内存与近似误差换 raw-vector I/O | page split、PQ memory、query rerank；paper 未给本地 crash contract | Family B；已占 decoupling、direct page update、incremental similarity-aware layout |
| DGAI frozen local artifact | 当前实验 workflow 在 stage 末尾 save/publish/reload 后才通过 fresh-process check | 本地固定输出文件与 reload workflow | online cache visibility 与 fresh-process visibility 不同 | 固定 publish 只属于该 artifact/workflow | 不能提升为 DGAI paper 的结构性成本 |
| [OdinANN](https://www.usenix.org/system/files/fast26-guo.pdf) | direct insert；delete buffer 后 merge | fixed-size record 的 GC-free out-of-place update；page free-slot combining；on-path cached page reuse | direct update 与 query 竞争 page I/O；approximate concurrency 暴露中间 record state | 约 2× overprovision、DRAM ID-location/PQ、delete merge、锁/队列干扰 | Family B；direct insert、page combining、free-slot/COW record 已占据 |
| [IP-DiskANN](https://arxiv.org/pdf/2502.13826) | insertion/deletion 逐操作进入当前图；仍有 dangling-edge cleanup | search-derived approximate in-neighbors；每个方向复制至多常数条 replacement edges，而非 `O(R²)` 全连 | 每次 delete 需要 graph search；不维护 reverse graph 以避免空间/锁复杂度 | dangling edges 与 light consolidation；算法论文未闭合 SSD page bytes | Family B；“避免 periodic batch consolidation + localized in-place delete”已占据 |
| [Greator](https://www.vldb.org/pvldb/vol19/p495-yu.pdf) | 小批 delete→insert→patch 后更新 query index | lightweight topology 定位 affected vertices/pages；只读写 affected pages；page-aware `ΔG` 合并 reverse edges；similarity-aware localized connection | 额外 topology state；更新仍要加载所有真正 affected pages | 主要面向 small-batch；topology/cache 占资源；无法无损跳过必要 repair | Family C；affected-only、effect-proportional page patch 已直接占据 |
| [LSM-VEC](https://arxiv.org/pdf/2505.17152) + [Aster](https://arxiv.org/pdf/2501.06570) | HNSW upper layers 在内存，bottom layer 从 LSM 获取 adjacency；edge KV 先 buffer 后 compaction | per-edge delta/pivot KV；insert 双向 edge；论文 delete local relink；SST compaction；可选 global reordering | 每访问节点需付 LSM adjacency lookup；delta/pivot 跨层聚合；sampling 以 recall/hash memory 换 vector I/O | compaction/read/write/space amplification；上层 HNSW、hash codes、buffer 占 DRAM；global reorder 未量化 | Family D；SSD delta、out-of-place multilevel graph、incremental materialization 已占据 |
| [SVFusion](https://www.vldb.org/pvldb/vol19/p1074-yang.pdf) | CPU version 先提交，GPU 分批异步传播；version conflict 时 fallback CPU | CPU full graph、多版本、GPU hot subgraph/cache；localized repair + snapshot consolidation | fallback、版本检查、异构候选/数据移动 | GPU memory、CPU graph、版本与传播 backlog | 异构边界；GPU 依赖不能让纯 SSD 复刻天然新颖 |
| [Disk-Resident Graph ANN Experimental Evaluation](https://arxiv.org/pdf/2603.01779) | taxonomy/evaluation，不是新 update protocol | 对比 in-place 与 out-of-place | in-place 避免 multi-component state，但随机 I/O/写干扰；out-of-place 相反 | 实证 workload-dependent trade-off | 直接反证“存在一个普通配置即可普遍消除 trade-off” |

## 4. 四类 architecture family

### 4.1 Family A：Memory delta + periodic global merge

**代表：** FreshDiskANN。

- **Immediate benefit：** 新点/删除先进入 DRAM overlay，低延迟可查；SSD LTI 在 merge 间保持只读，更新可批量顺序化。
- **Structural cost：** 查询必须覆盖 LTI 与全部 TempIndex；TempIndex、DeleteList、`Δ` 与 PQ 占 DRAM；稳定 update throughput 受 merge drain rate 限制；StreamingMerge 对整个 LTI 做两次顺序 pass并与查询争用设备。
- **Cost source：** searchable overlay 是 authoritative recent state；要在 merge 前得到最新结果就必须查询它。线性只读 LTI 的新版本生成又要求全索引 traversal/materialization。
- **Local patch：** 更频繁 merge 减少 query fan-out，却增加 merge 干扰；更少 merge 降低后台频率，却增加 DRAM/query fan-out；dirty-block tracking 在当前线性版本协议下不能自动消除未改 block 的扫描/复制和 atomic switch。
- **Patch introduced cost：** page COW/redirect table 会新增版本 lookup、space reclamation 和 page-level authority，实质转入 direct update 或 LSM family。

### 4.2 Family B：Direct in-place / out-of-place page update

**代表：** DGAI、OdinANN、IP-DiskANN。

- **Immediate benefit：** 当前 graph 是单一 authoritative state；无需查询多 delta/levels；单更新可立即整合进图，避免全 LTI merge。
- **Structural cost：** 插入/删除改变的不止 target，还要建立/修复 incoming connectivity；这些邻接记录分散在磁盘 pages，产生随机 read/write、page RMW/COW、锁和前台 query interference。DGAI decoupling 又明确把低 update I/O 换成 topology/vector 分离带来的 query tax。
- **Cost source：** directed proximity graph 的 navigability 依赖已有节点指向新点或绕过删点；单一 authoritative adjacency 只能在对应 records/pages 处物化这些变化。
- **Local patch：** free slots、page combining、on-path reuse、search-derived in-neighbors、similarity-aware placement 已分别被 OdinANN/IP-DiskANN/DGAI 使用；继续改 `R`、page size 或 batch 只是参数和常数。
- **Patch introduced cost：** 延迟这些变化需要额外 searchable state、repair debt/fallback 与 reclaim protocol，随即转入 Family A/D 或 SVFusion 已占据的 versioned propagation。

### 4.3 Family C：Localized small-batch patch

**代表：** Greator。

- **Immediate benefit：** lightweight topology 先定位 affected vertices/pages，避免全 index/vector scan；page-aware `ΔG` 把同页 reverse-edge update 合并，similarity-aware connection 减少 pruning。
- **Structural cost：** 必须维护足以定位 affected set 的辅助 topology；所有真正受影响且需要保持质量的 pages 仍需读取、修改和写回；其主要 workload boundary 是小批更新。
- **Cost source：** “affected-only”减少的是无关工作，不提供证明某个 affected mutation 对 matched-quality 不必要的 oracle。
- **Local patch：** 改为 continuous streaming、扩大 cache 或提前筛 repair 都是工作流/模块扩展，不能自动跳过必要 affected pages。
- **Patch introduced cost：** 把 affected changes 改成 append-only delta 会增加 query merge/compaction；把它们留内存会增加 overlay/DRAM；因此回到 Family A/D trade-off。

### 4.4 Family D：Out-of-place multi-level / LSM graph

**代表：** LSM-VEC/Aster。

- **Immediate benefit：** edge changes 先以 delta KV 顺序吸收，无需对完整 graph 做 global reconstruction；bottom-layer graph 可超出 DRAM；compaction 时还能做 connectivity-aware layout maintenance。
- **Structural cost：** 一个 vertex 的最新 adjacency 可能由 MemTable/多层 delta/pivot 共同组成，lookup 要跨层聚合；compaction 读取重叠 SSTables并写出新状态，产生 write/space amplification和 backlog；insert/delete 仍需 proximity search 与 connectivity maintenance。
- **Cost source：** out-of-place update 允许多个物理版本共存；在 compaction 前恢复逻辑最新值必然查找/合并这些版本，compaction 后则必须支付 materialization/reclamation。
- **Local patch：** Bloom filter、cache、tiering、sampling ratio 和 compaction tuning只降低常数。维护一个独立“单一最新 adjacency”会恢复 random RMW 或复制第二个 authoritative index。
- **Patch introduced cost：** 更激进 compaction降低 query read amplification但增加写/干扰；更慢 compaction反之。关闭 global reordering可省写，却放弃其长期 locality机制。

### 4.5 SVFusion boundary

SVFusion 已经表明 versioned/asynchronous propagation 并非空白：CPU version 是最新完整状态，GPU 层可以滞后，查询在冲突时 fallback，后台再 consolidation。纯 SSD 系统仍需不同实现，但仅把 GPU 换成 SSD level 不是新的状态机；必须产生超出“authoritative tier + stale replicas + fallback”的新不变量，本轮没有找到。

## 5. 结构性 frontier 的证明与反证

### 5.1 单一状态与多组件状态的成本守恒

若查询只读一个 authoritative adjacency image，则每次需要立即生效的 neighbor mutation 最终必须落到其 record/page；随机性、page granularity 和并发控制是 direct family 的成本。若更新先写别处，则最新 adjacency 分裂为 base + delta/levels/version；查询要合并，或后台先合并再查询。前者是 query tax，后者是 materialization/compaction tax。

这是状态表示的结构性选择，不证明任何具体实现达到最优；它只说明“同时取消 direct random updates、query merge 和 background materialization”需要第三种 authoritative representation。A0 的候选搜索没有找到一种不等价于 page-COW/redirect、searchable delta 或 LSM delta/pivot 的第三种表示。

### 5.2 Localized repair 不能提供 repair necessity oracle

Greator 已经做到 affected-only；IP-DiskANN 与其他 graph repair work 已经缩小 in-neighbor/replacement scope。M2 的 `scheduled → accepted/mutated` 差额只描述 prune 的执行结果，不说明哪些最终 mutation 对 matched recall/latency 是不必要的。要在读 page 前跳过 repair，必须有一个可维护的 graph-quality/navigability certificate；degree、2-hop 或 local monotonic-path witness 不能界定 ANN recall，而能界定 global navigability 的 state 又可能需要广泛更新。

### 5.3 M3 不支持跨 completion write absorption

M3 对 `22,522,471` 个 neighbor-only page versions 的 lifecycle closure 显示，pre-enqueue、queued 和 inflight same-page supersession 全部为零；所有 repeat 都发生在 prior completion 后。要吸收它们必须改变 page ownership、visibility、locking 与 recovery，而不是给现有 queue 加 dedup。重复又是广泛分布，bounded hot-page cache 没有可靠命中保证；不设界则退化为大 memory delta，SSD journal 则退化为 LSM。

## 6. 候选机制审计

A0 最终保留候选为 `0`。以下三项只是被反方用于寻找反例的 pre-candidate sketches，不进入 profiling。

| Pre-candidate sketch | 最接近工作 | 失败原因 | Significance / Novelty / Depth / Feasibility |
|---|---|---|---:|
| Source-keyed reverse-edge mailbox / adjacency fragment | Greator `ΔG`；LSM-VEC/Aster delta+pivot；FreshDiskANN delta | 查询合并 mailbox 时支付 per-node/per-level read amplification；预合并则恢复 RMW/compaction。实质是三类已有技术组合，给 LSM-VEC 加 source-keyed delta 属局部扩展 | `7 / 3 / 6 / 8` |
| Navigability certificate / repair-debt witness | Wolverine monotonic-path repair；DEG connectivity/refinement；CleANN guided bridges；random-walk/hitting-time deletion | 唯一接近非组合式候选，但 local witness 不能约束 recall，global certificate 又无法低成本维护；M2 没有必要 repair oracle，公平实现前就无法给出可证伪预测 | `8 / 5 / 8 / 4` |
| Epoch page ownership / post-completion absorption | OdinANN page combining；普通 dirty-page cache；FreshDiskANN delta；LSM | M3 的机械 supersession 为零；跨 completion 才有收益，必须改变语义。设 cache bound 是普通 write-back cache，不设 bound 是 memory delta，写 SSD log 是 LSM，缺 ANN-specific invariant | `6 / 2 / 5 / 6` |

独立反方门槛为 `7 / 6 / 7 / 7`，任一项不达标即 KILL。三项全部失败；最强的 certificate sketch 也只达到 novelty 5、feasibility 4。

## 7. M0–M3 的正确研究价值

M0–M3 与 A0 的直接联系只限于以下 observations：

- recurring bytes 的主要本地组件是 neighbor-page writes；
- DGAI/OdinANN 当前配置分别为 `R=32/96`，不能据此归因 visibility；
- scheduled attempts 与 actual mutations 不相等，但不构成 repair necessity oracle；
- 400K repeat 广泛分布；
- current queue 中 pre-submit same-page supersession 为零。

这些 findings 有 characterization 价值，能 Kill queue coalescing、hot-page absorption 和“prune 掉一半所以可省一半 page I/O”等错误推断。它们不证明 direct update 的 repair 都是冗余，也不证明一个新状态机可以安全消除物理写。

## 8. A0 pass-gate closure

| Pass condition | Result | Evidence |
|---|---|---|
| 未被直接覆盖的结构性 trade-off | `NO` | 结构性 trade-off 真实，但其四类 design points 已由 FreshDiskANN、direct family、Greator、LSM-VEC 展开 |
| 与 M0–M3 直接观测相连且不继承错误因果 | `PARTIAL` | repair/write findings相连，但没有必要性 oracle |
| 非组合式核心机制 | `NO` | mailbox/epoch 分别退化为 combination/cache；certificate 未形成可维护 state machine |
| 现有架构不能局部扩展实现 | `NO` | mailbox 可由 LSM-VEC/Greator 局部扩展；其余没有可实现机制 |
| matched semantics/quality 的公平 baseline | `PARTIAL` | DGAI/OdinANN 可运行；Greator/LSM-VEC paper-current-artifact 版本边界和 certificate quality 使 strongest comparison 未闭合 |
| 独立评分同时过线 | `NO` | 三项均至少两项不过线 |

任一 `NO` 即不能通过；本轮有四项 `NO`。

## 9. 最终决策与停止边界

正式决策：

> `Dynamic ANN Architecture Frontier A0 = KILL; no surviving candidate; switch direction.`

因此：

- 不申请最小 profiling；
- 不构建 matched-R base；
- 不实现 mailbox、certificate、page epoch、dirty-page 或 LSM prototype；
- 不复活 Write Reducibility、Semantic Repair Efficiency、ContractANN、multi-NVMe 或 RAG；
- 不把 paper 缺失指标、current artifact drift 或本地固定 publish 当成新系统机会。

下一步应由 PZ/Gpt 选择一条有独立问题证据的新方向。A0 本身不自动选择 pivot，也不运行任何后续工作。

## 10. Sources

核心 primary sources：

- FreshDiskANN: <https://arxiv.org/pdf/2105.09613>
- DGAI: <https://arxiv.org/pdf/2510.25401>
- OdinANN: <https://www.usenix.org/system/files/fast26-guo.pdf>
- IP-DiskANN: <https://arxiv.org/pdf/2502.13826>
- Greator: <https://www.vldb.org/pvldb/vol19/p495-yu.pdf>
- LSM-VEC: <https://arxiv.org/pdf/2505.17152>
- Aster / Poly-LSM: <https://arxiv.org/pdf/2501.06570>
- AsterVec current repository: <https://github.com/NTU-Siqiang-Group/AsterVec>
- SVFusion: <https://www.vldb.org/pvldb/vol19/p1074-yang.pdf>
- Disk-Resident Graph ANN Experimental Evaluation: <https://arxiv.org/pdf/2603.01779>

Candidate-boundary sources：

- Wolverine: <https://www.vldb.org/pvldb/vol18/p2268-zheng.pdf>
- Dynamic Exploration Graph (DEG): <https://arxiv.org/abs/2307.10479>
- CleANN: <https://arxiv.org/abs/2507.19802>
- Graph-Based Nearest Neighbors with Dynamic Updates via Random Walk (SPatch): <https://openreview.net/pdf?id=l97Kacqdfk>

Local evidence anchors：

- `codex/share/2026-07-18/dynamic_vamana_neighbor_repair_m2_0718.md`
- `codex/share/2026-07-18/dynamic_vamana_write_supersession_m3_0718.md`
- `codex/share/2026-07-18/dynamic_vamana_m0_m3_final_novelty_review_0718.md`
- `codex/share/2026-07-18/dynamic_ann_bounded_idea_brainstorm_0718.md`

本报告到此停止，没有任何实验或实现 continuation。
