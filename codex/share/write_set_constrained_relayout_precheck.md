# 写集合约束微量重排立项前审计

## 审计结论

本轮结论为 **Continue-to-oracle-review**，而不是批准立项或实现。现有一手材料中未发现同时满足查询共访指导、严格限制在单次 direct insert 的既有页面 I/O(Input/Output，输入输出)集合内、在线增量移动记录三项条件的等价工作。该 novelty 边界暂时存活。本文所称 ANN(Approximate Nearest Neighbor，近似最近邻)均指驻盘图索引场景。

架构上，OdinANN 与 NAVIS 都具有稳定节点 ID、内存位置间接层以及现成的 out-of-place record relocation，可在不增加基线页面 I/O 集合的条件下改变本次被搬移记录在既有目标页间的分组。DGAI 也具备 topology-only 位置映射、页内空槽复用和记录搬移，但其当前实现已经用近邻关系做 placement/page split，且映射更新、磁盘写入与恢复的原子语义没有被论文或代码完整证明，因此只能作为第三个、风险更高的载体。

最大的未决项不是静态可实现性，而是机会空间。NAVIS 已经把 co-updated edgelist 聚合到最少的新页，OdinANN 也优先把更新记录合并写入空页或 insert path 上的半空页。若本次 write set 通常只有一个目标页，或者多个目标页之间没有可被 query co-visit 信号改善的分组自由度，则 oracle 上界会天然接近零并立即 Kill。故下一步只应审查 oracle 定义；在 Gpt 批准前不采集 trace、不修改实现。

## 判定标准

本报告将一次原始插入在完全不启用待审机制时形成的页面读集合记为 `R_t`，页面写回集合记为 `W_t`。为防止通过重新定义基线偷增 I/O，`W_t` 必须在布局决策前冻结，并同时记录 page ID、写回字节数和新分配页。候选机制不得增加 `R_t` 或 `W_t` 中的 page ID，不得扩大任一页的写回长度，也不得把原本异步延后的维护提前计入本次插入。

允许重排的记录只包括两类。第一类是基线本来就会 out-of-place 写入 `W_t` 的新记录或更新记录。第二类是驻留在 `R_t∩W_t` 页中、其完整字节已经随基线页读进入内存且所在页本来就会整页写回的记录。禁止为了获得更多候选记录读取仅在 `W_t`、不在 `R_t` 的旧内容，也禁止从 `R_t\W_t` 搬出普通记录后额外写回其源页。

> **等价覆盖条件**
> 只有已有工作同时利用真实或采样 query co-visit 信号、只在当前操作冻结后的 `R_t/W_t` 内移动记录、并以在线增量方式更新持久布局，才判定 novelty 被覆盖。只满足其中一项或两项属于相邻设计。

## Prior-art 对照

| 工作 | 布局信号 | 重排范围与时机 | 是否受当前 `W_t` 约束 | 与待审假设的关系 |
|---|---|---|---|---|
| NAVIS，2026 preprint | 用 co-updated、图相邻推断未来 co-traversal，不使用实际 query co-visit heatmap | 每次插入把修改的 edgelist out-of-place 聚合到新页，失效旧槽并更新 indirection | 是局部在线写，但论文没有把选择空间形式化为冻结 `W_t`，也没有按查询共访重新分组 | 最强相邻工作。已经覆盖记录搬移、已有更新工作复用和局部性目标；尚未覆盖 query-guided partition。若 constrained oracle 不能稳定优于 NAVIS 的 co-update packing，则 Kill。来源为 [NAVIS 论文](https://arxiv.org/abs/2605.11523)。 |
| DGAI SADL，2025 preprint | 新向量与候选邻居的向量/拓扑相似性 | 优先把新 topology 放入候选邻居页空槽；无空槽时拆分最近邻页并按页内图关系重新分组 | 空槽路径可不扩大写集合；split 明确新增一页和额外 4 KiB 写，不满足严格零增量版本 | 已覆盖 insertion-driven similarity placement 和局部 page split，但未用查询共访，也没有在任意多个既有 dirty pages 间做受约束优化。来源为 [DGAI 论文](https://arxiv.org/abs/2510.25401) 与 [官方代码 commit `a0179b8`](https://github.com/iDC-NEU/DGAI/tree/a0179b876a4bd453336dc2893b46ae890f680555)。 |
| OdinANN，FAST 2026 | 空槽数量与 insert search path；不使用 query co-visit | 每次插入把新记录和更新邻居记录 out-of-place 放入空页、on-path 半空页或新页 | 设计目标就是复用已读 search-path 页并减少写页数，但页内/页间分组目标是 update combining | 覆盖稳定 ID、位置间接层、记录搬移与 write-set reuse，没有覆盖查询指导的分组。来源为 [OdinANN 论文](https://www.usenix.org/conference/fast26/presentation/guo)。 |
| LSM-VEC，2025 preprint | sampled query traversal heatmap 与图结构评分 | 周期性对底层驻盘图做 global reordering，并与 compaction 对齐 | 否；依赖全局排列和 LSM compaction，未限制在单次 direct insert 的 `W_t` | 已覆盖 query-guided disk relayout 的目标函数，是 oracle 的全局上界基线；未覆盖在线微量、零 write-set expansion。来源为 [LSM-VEC 论文](https://arxiv.org/abs/2505.17152)。 |
| Porder，NeurIPS 2022 | 实测 edge-traversal frequency | 建图后对整个 HNSW(Hierarchical Navigable Small World，分层可导航小世界图)做 profile-guided weighted graph reordering | 否；离线全图重排，且目标是 DRAM(Dynamic Random-Access Memory，动态随机存取存储器)cache locality | 覆盖 query co-access 指导的 weighted layout objective，不覆盖动态驻盘更新。来源为 [Graph Reordering for Cache-Efficient Near Neighbor Search](https://papers.neurips.cc/paper_files/paper/2022/file/fb44a668c2d4bc984e9d6ca261262cbb-Paper-Conference.pdf)。 |
| Greator，PVLDB 2025 | 被删除节点的轻量 topology 与受影响页 | small-batch deletion/patch 只读写 affected pages，reverse edges 按页聚合 | 限制更新 I/O 到 affected pages，但不移动记录以优化查询物理共访 | 覆盖 localized update 和 page-aware delta，目标是减少扫描与 prune，不是 physical relayout。来源为 [Greator 论文](https://www.vldb.org/pvldb/vol19/p495-yu.pdf)。 |
| Database Cracking，CIDR 2007；Stochastic Cracking，PVLDB 2012 | 查询谓词与当前访问范围 | 查询执行时持续、增量地物理重组列数据 | 只处理查询触及区域，但不是 update write set，数据模型和目标也不同 | 证明 piggyback query-driven reorganization 是已知范式，因此不能声称首次利用自然操作做布局维护；没有覆盖 ANN record co-visit 和冻结 `W_t`。来源为 [Database Cracking](https://stratos.seas.harvard.edu/publications/database-cracking) 与 [Stochastic Database Cracking](https://www.vldb.org/pvldb/vol5/p502_felixhalim_vldb2012.pdf)。 |
| OREO，2024 preprint | 未知未来 query stream 上的 layout cost | 在线决定何时切换完整布局，实际重排由后台副本完成 | 否；显式计入 reorganization cost，但不是页级 write-set constraint | 覆盖在线布局决策与查询收益/重排成本平衡，不覆盖本次操作内的零新增页面 I/O。来源为 [Dynamic Data Layout Optimization with Worst-case Guarantees](https://arxiv.org/abs/2405.04984)。 |
| Self-Organizing Data Containers，CIDR 2022 | client access history | client 在访问时增量创建或修改磁盘/云对象布局 | 否；可创建新 block/index/replica | 是自组织持久布局的相邻愿景，反而强调增量重排、协调和回收仍是开放问题；不构成 ANN 写集合等价实现。来源为 [SDC 论文](https://www.vldb.org/cidrdb/papers/2022/p44-madden.pdf)。 |
| Azure SQL Automatic Index Compaction，2026 preview | 最近修改页与 page density，不使用 query co-visit | 后台只在少量 recently modified pages 间搬行并释放空页 | 范围接近 dirty-page constrained，但不是前台操作冻结 `W_t`，目标是密度而非共访 | 这是工程上最接近的非 ANN 类比，说明最近修改页内微量搬移本身不新；查询共访目标和严格零扩张约束仍不同。来源为 [Microsoft 官方介绍](https://techcommunity.microsoft.com/blog/azuresqlblog/stop-defragmenting-and-start-living-introducing-auto-index-compaction/4500089)。 |

审计未找到等价机制，但 novelty 空间已被两侧夹住。NAVIS 占据 update-set packing，LSM-VEC/Porder 占据 query-guided relayout，Database Cracking/SDC 占据访问驱动的增量重组。未来贡献必须证明三者的交集产生了单独、可观的机会，而不是把已有机制并列拼装。

## 三个目标系统的架构可行性

### DGAI

DGAI 为 topology 和 coordinate 分别维护 `id2loc_topo_`、`id2loc_coord_` 以及反向的 page-layout 表，节点 ID 与物理槽位解耦。官方代码在 insert search 后收集 reverse-edge 邻居页并加页锁；若邻居页有空槽，新节点 topology 直接放入其中。若没有空槽，则读取最近邻页内容、创建新页、在两页间搬移 topology record，并批量更新 `id2loc_topo_`。旧槽通过 `empty_locs_topo`、整空页通过 `empty_pages_topo` 回收。这些路径说明 topology-only record swap 在数据结构层可行。

严格约束下，DGAI 只有两种合法机会。第一种是在本来就要写回的两个以上 reverse-edge topology 页之间重新分配其完整页缓冲中的记录；第二种是在 baseline 本来就触发 split 时，只改变同一旧页与同一新页间的 partition，不再新增第三页。不得把未触发 split 的操作强行改成 split，因为现有 instrumentation 已将其记为额外 4 KiB 写，这会直接违反 `W_t` 约束。

风险在一致性和恢复。代码对 split 页持有节点锁与页锁，并同步修改 page-layout 和 `id2loc_topo_`，但官方基线在持久写前已更新部分内存映射；论文没有说明 WAL(Write-Ahead Logging，预写日志)、journal 或崩溃恢复协议。因此，不能声称映射更新能与多页写原子提交。任何 oracle 只能先计算逻辑收益，不能把实现可提交性视为已证明事实。另一个风险是 DGAI 的 SADL 已按近邻关系分组，constrained oracle 必须对其而非顺序 placement 基线报告增量收益。

### OdinANN

OdinANN 的定长耦合 record 同时包含 raw vector 与出邻居，内存维护 ID-to-location 与 location-to-ID 映射。插入将新节点及 reverse-edge 邻居的更新 record 写到新位置，随后切换映射并把旧槽立即标为可复用。分配规则优先整空页，其次选择 insertion search path 上已经读入缓存且占用低于 `m` 的半空页，最后才新增 overprovisioned page。默认分析中空间与写放大均约为 2 倍。

这一路径原生满足两项关键条件。需要搬移的 coupled record 本来就会被完整重写，raw vector 已包含在缓存 record 中，不必额外读取 coordinate；多个目标页的分配本来就由本次 update combining 决定，因此只改变这些 destination pages 间的 record partition 不必增加页面数或写字节。旧槽回收、位置映射切换和 per-record/per-page locking 也已有机制。论文还用 snapshot、journal 和 record 内 transaction metadata 处理恢复，语义比 DGAI 完整。

限制同样明确。若所有更新 record 能装入单页，则不存在 partition 选择；若需要多个页，OdinANN 的空槽规则首先优化写合并，查询指导的分组不能降低本次写页数，只可能影响未来查询。若 query-guided 分组破坏 `n-m` 条 record 合并能力、扩大临界区或使 journal/mapping 更新增多，则应按 Kill 条件停止。耦合 record 较大，页容量小于 topology-only 设计，机会频率可能偏低。

### NAVIS

NAVIS 把 full vector 与 edgelist 分文件存放，内存 indirection table 为每个 vertex 保存两组 page-number/offset。插入只写新向量，并把所有修改 edgelist out-of-place 聚合到新 edge page；旧 edgelist slot 失效，映射指向新位置，整页失效后才回收。RMW cache 独占 dirty page，结构更新在写盘并刷新 clean cache 后释放页锁，读者每次先通过 indirection 解析当前位置。

因此 NAVIS 也是可行载体，但同时是最强 novelty 风险。其 baseline 已经把 co-updated records 聚在一起，并明确以图相邻和未来 co-traversal 解释局部性收益。严格 constrained relayout 只能在基线本来需要两个以上 edge destination pages 时，用 query co-visit 权重改变这些 record 的分组；不得多搬未修改 edgelist，除非其源页和目标页都已属于冻结后的 `R_t∩W_t` 且不会增加 mapping changes。若 NAVIS 的最小页 packing 已让所有候选落入一页，或 query-guided partition 相对 co-update grouping 没有收益，候选应直接 Kill，而不是换弱基线制造空间。

NAVIS 的映射新鲜度、旧页失效和整页回收已有清晰协议，但论文没有公开 artifact，本轮只能确认论文级可行性，不能确认内部 allocator 是否暴露跨目标页 partition hook。故通过条件应写为 OdinANN 代码/论文级可行、NAVIS 论文级可行，而不是两个系统均已可运行。

## Oracle 上界设计

### 输入与基线冻结

每次更新 `t` 先用原系统执行只记录不改布局的 baseline replay，得到 `R_t`、`W_t`、每页容量、页内 record 列表、基线将被重写或搬移的 record 集合 `M_t` 以及映射更新集合。future query window `Q_{t+1:t+H}` 仅供 oracle 估计上界，不能用于在线实现主张。查询 trace 必须记录逻辑 vertex/edgelist 访问序列，再通过当时的 ID-to-location 快照转换成 physical pages，避免用重排后的地址反向污染权重。

合法候选集合为基线已搬移的 `M_t`，加上 `R_t∩W_t` 页内已完整读入且本来就会随整页写回的 record。合法目标页只能来自冻结的 `W_t`。对 NAVIS/OdinANN baseline 本来分配的新目标页，应把相同 page IDs 与相同总容量固定下来；oracle 不能申请额外空页。

### 优化模型

对单次机会建立小规模整数规划。令 `x_{v,p}` 表示 record `v` 是否放入合法目标页 `p`，`y_{q,p}` 表示未来查询 `q` 是否需要页 `p`。约束每个 record 恰好放入一页、每页总 record bytes 不超过冻结容量、非候选 record 保持原位、page ID 与写回字节集合不变。目标是最小化：

$$
\sum_{q\in Q_{t+1:t+H}} w_q\sum_{p\in W_t} y_{q,p}.
$$

其中 `w_q` 为查询权重。若查询 `q` 访问被分配到页 `p` 的任一 record，则 `y_{q,p}=1`。该目标直接最小化未来查询在这组受影响记录上的 unique pages，而不是用边距离或缓存命中率替代物理 I/O。由于单次 `W_t` 通常较小，整数规划只用于 oracle；若规模过大，可用 weighted co-visit graph partitioning 求可验证上界和贪心下界。

### 对照组与指标

必须同时报告原系统 baseline、静态 topology/similarity 分组、co-updated packing、write-set constrained oracle 以及不受 `W_t` 限制的 global Porder/LSM-VEC-style oracle。核心指标为未来 unique query pages 减少比例、相对 global oracle 可恢复的 locality degradation 比例、有效机会频率、每次机会的页数/record 数、额外 mapping updates、页容量利用率以及 write-set/bytes 守恒。

空槽版本与 swap 版本必须分开。empty-only oracle 只能把候选 record 移入操作开始时已有的空槽或因同次合法搬移新产生的空槽，不能形成需要临时第三槽的循环置换；swap oracle 允许在两个冻结 dirty pages 间交换等长 record。两者差值刻画 indirection 和原子提交复杂度带来的真实机会损失。

### 工作负载与立即证伪

aligned workload 让查询热点和更新区域一致；query-hot/update-cold 让查询集中在很少被更新的区域；query-cold/update-hot 让更新集中于查询不关心的区域。还应加入 workload phase shift，使 oracle 的 future window 分别使用短期同分布和突变分布。若候选只在 aligned workload 有效，立即 Kill。

不应先固定一个漂亮的收益门槛再寻找数据。最小审查门禁建议为：至少 OdinANN 与 NAVIS 两类布局都出现非零且稳定的多页 partition 机会；constrained oracle 在两种非 aligned workload 中仍能减少未来 unique pages；相对各自最强 baseline 而非顺序布局存在可见增量；page ID、page count、write bytes 和 mapping update 账全部闭合。任何系统需要新增页读/写、机会频率接近零、或 NAVIS baseline 已达到 oracle，即立即 Kill。

## 等价工作风险与实施风险

第一，NAVIS 可能通过 co-updated packing 实质上已经获取大部分可得收益。此时 query heatmap 只是更换 partition score，贡献不足。第二，Azure SQL recently-modified-page compaction 与 Database Cracking 已使 piggyback、局部增量搬移不再新，论文不能以这些抽象表述作为贡献。第三，LSM-VEC 与 Porder 已占据 query-guided objective，必须证明 `W_t` constraint 不是单纯把全局算法裁剪到小集合，而是带来不同的在线机制和成本边界。

第四，稳定 ID 不等于免费 indirection。每搬一个 record 都会增加映射写、锁范围和 recovery 元数据；对 coupled record 还会复制完整向量。第五，重排可能提高未来查询局部性却破坏本次 update combining、空槽聚合和 page reclamation。第六，使用 future trace 的 oracle 只能证明 headroom，不能证明在线策略能预测正确；后续若只得到 ML cache/replacement policy，则按既定条件 Kill。

## 最终裁决

本 precheck 不触发 prior-art Kill，也不触发架构不可行 Kill。OdinANN 与 NAVIS 至少在论文机制层都允许对本次本来就要 out-of-place 写出的多个 records 做不同的页间 partition，同时保持页面 I/O 集合不变；DGAI 提供第三种 topology-only 载体。与 NAVIS、DGAI、LSM-VEC、Porder、Greator 和自组织存储的边界能够明确写出，oracle 也可被形式化并设置非 aligned workload 的即时反例。

因此结论为 **Continue-to-oracle-review**。这只表示 Gpt 可以审查 oracle 是否值得执行，不表示 idea 已立项。下一步若获批，也只允许先用已有或最小新增 trace 计算上界；不得实现在线策略。若 Gpt 认为 NAVIS 的 co-update packing 已使可区分贡献过薄，或认为两个架构的 allocator 无法在冻结 `W_t` 下暴露足够 partition 自由度，应在实验前直接 Kill。
