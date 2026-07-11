# 动态驻盘 ANN 跨系统问题地图

## 审计边界与证据口径

本文只建立现有系统的事实地图并提炼尚未闭合的研究问题，不提出完整系统方案，也不把 DGAI 的单系统性能现象外推为行业共性。审计对象为 DGAI、OdinANN、FreshDiskANN、LSM-VEC、IP-DiskANN 和 NAVIS。事实优先来自原论文与作者官方仓库；无法由论文或代码确认的字段统一标记为未说明，而不是根据相似系统补全。

证据分为三个等级。本机已验证表示本地代码可编译、运行且已有实验记录；官方代码可审计表示作者公开了实现，但本轮未在本机复现；仅论文可审计表示未找到与论文对应的官方实现。论文机制与当前仓库可能存在版本差异，尤其是 Microsoft DiskANN 当前主线已重写为 provider 驱动的 Rust 实现，不能将其持久化语义直接倒推到 2021 年 FreshDiskANN 或 2025 年 IP-DiskANN 论文。

主要一手来源包括 [FreshDiskANN 论文](https://arxiv.org/abs/2105.09613)、[IP-DiskANN 论文](https://arxiv.org/abs/2502.13826)、[Microsoft DiskANN 官方仓库](https://github.com/microsoft/DiskANN)、[OdinANN 论文](https://www.usenix.org/conference/fast26/presentation/guo)、[OdinANN/PipeANN 官方仓库](https://github.com/thustorage/PipeANN)、[LSM-VEC 论文](https://arxiv.org/abs/2505.17152)、[DGAI 论文](https://arxiv.org/abs/2510.25401)、[DGAI 官方仓库](https://github.com/iDC-NEU/DGAI) 与 [NAVIS 论文](https://arxiv.org/abs/2605.11523)。

## 系统事实矩阵

### 更新、布局与建边路径

| 系统 | 更新模型 | topology/vector 物理布局 | 新节点邻居发现 | 反向边、裁剪与删除修复 | 每次更新直接修改的持久对象 |
|---|---|---|---|---|---|
| FreshDiskANN | 新增点先进入内存 RW-TempIndex；删除进入 DeleteList；内存达到阈值后用后台 StreamingMerge 合并到 SSD 上的长期索引 LTI。逻辑更新可立即被查询看见，物理主图延迟更新。 | LTI 为 SSD 驻留的 Vamana 图，内存保留全量 PQ 压缩向量；近期图在内存。论文的 LTI 记录沿用 DiskANN 的图记录布局，批处理按块读写。 | 内存阶段用 FreshVamana 的 GreedySearch 与 RobustPrune；合并阶段对每个新点搜索 SSD LTI，得到 visited set 后裁剪出邻居。 | 插入的 backward edges 先写入内存 `Δ`，随后 Patch 阶段按块写回。删除阶段把被删节点的未删除邻居并入受影响节点候选集再裁剪，依赖全索引扫描找到入边。 | 前台主要修改内存 TempIndex、DeleteList 及其快照；合并生成新的中间/最终 LTI，并分阶段顺序读取、重写图块。 |
| IP-DiskANN | 每次插入和删除都原地处理，避免 FreshDiskANN 的重型批量 consolidation；但删除后仍周期性扫描清除未找到的 dangling edges。 | 论文定义的是 DiskANN 单向有界度图算法，没有固定持久化布局。当前官方 DiskANN3 将向量、邻接表等对象的存取委托给 DataProvider，因此写粒度取决于后端，不能从论文确定。 | 插入沿用 DiskANN GreedySearch，visited set 经 RobustPrune 形成新节点出边，再向邻居添加反向边并按需裁剪。 | 删除时再次以被删向量为查询做 GreedySearch，以 visited set 中仍指向被删点的节点近似其入邻居；对每个近似入邻居和原出邻居只增加至多 `cR` 量级替代边，超度后 RobustPrune。遗漏入边由轻量全图扫描清除。 | 论文层面修改被删点、新点、近似入邻居、原出邻居的邻接表；具体持久对象和写放大未规定。 |
| LSM-VEC | 图边以 key-value 形式进入内存缓冲，再随 LSM compaction 逐层下沉；插入和删除均采用 HNSW 风格分层图更新。 | 少量 HNSW 上层驻内存；大规模底层图由 graph-oriented LSM-tree/AsterDB 持久化；原始向量单独存为按 ID 排列的连续磁盘数组。 | 自顶向下搜索；内存层寻找近邻，底层在 LSM 驻盘图中搜索并连接 top-M 邻居。 | 插入建立双向边。删除枚举被删点邻居，删除双向边，汇总邻居的邻居作为候选并为每个受影响邻居重新连接 top-M，随后删除节点和向量。 | 写入或删除 LSM 中的边 KV，更新内存上层图，并写入或删除向量数组对象；后台 compaction 重写 SST/层级文件。 |
| OdinANN | 插入逐点直接写入 on-disk graph；删除 ID 先进入内存集合，达到删除比例或 search-I/O amplification 阈值后两遍合并。 | 每个定长记录把原始向量与出邻居 ID 耦合存储；一页含多个记录并预留空槽。内存保存 PQ 向量和 ID-to-location 等映射。 | 对新向量执行图搜索；候选邻居来自搜索路径，随后建立双向边并裁剪。 | 新节点和邻居记录采用近似快照、按记录锁与 delta pruning。删除合并第一遍收集被删节点邻居，第二遍以这些邻居替换被删 ID、裁剪并写回。 | 插入将新记录和多个更新后的邻居记录 out-of-place 写到预留页，更新内存位置表并立即回收旧槽；删除合并顺序重写受影响记录。 |
| DGAI | 插入原地更新；删除标记原始向量并使用既有图删除方法修改 topology。DGAI 的主要目标是让 topology-only 更新不再读写原始向量。 | topology 与 raw vector 分别存于两个磁盘文件；内存保存 PQ 表。topology 页包含多个节点邻接表，raw vector 通过独立映射访问。 | 插入先以新向量执行 greedy search；搜索结果既用于建边，也用于选择与最近邻同页的 topology 位置。 | 新节点出边来自搜索与裁剪，再更新邻居的 reverse edges；页满时按相似关系 split。论文对删除修复直接复用既有方法，未声明新的反向索引。 | 写一个 raw-vector 空槽，修改新节点及 reverse-edge 节点所在 topology 页；必要时分裂 topology 页并更新位置映射。删除标记向量、修改 topology。 |
| NAVIS | 聚焦并发直接插入，结构更新沿用 OdinANN 式原地更新；删除不是核心贡献，论文建议沿用 OdinANN 的 buffered delete。 | edgelist 与 full vector 完全分文件，内存 indirection table 分别记录两类位置；多条 edgelist 同页，向量独立存放；另有小型内存 entrance graph。 | 先从 entrance graph 选入口，再做 on-disk position seeking；PQ 距离排序后，CASR 只加载足以稳定 top-K 的部分 full vectors，其余边槽使用 PQ 结果。 | 新点与邻居建立 reciprocal links 并裁剪；修改的 edgelist 被聚合后 out-of-place 写页。entrance graph 也为被提升的新点加双向边并按需裁剪。删除修复细节未展开。 | 写新 full vector，聚合写若干修改后的 edgelist 页，更新 indirection table；旧 edgelist 位置失效，优先复用整页失效空间；部分插入还修改内存 entrance graph。 |

### 复用、维护与长期控制

| 系统 | query/update 读、缓存或计算复用 | 写入/回收单位与维护周期 | recall、空间与局部性长期控制 | 论文声明的瓶颈与证据 | 尚未解决的 tradeoff |
|---|---|---|---|---|---|
| FreshDiskANN | 查询并行搜索 LTI、RW-TempIndex 和所有 RO-TempIndex 后合并结果；StreamingMerge 复用内存 PQ 向量做近似距离，但前台查询路径与后台合并搜索主要共享 SSD。 | 前台为内存图更新；后台以图块为单位执行 Delete、Insert、Patch。内存阈值触发合并，持续更新率受 merge 完成速度约束。 | FreshVamana 的 `α-RNG` 裁剪维持长更新流 recall；合并后清空短期索引控制内存。论文 week-long 实验显示 recall 稳定，但 merge 的随机读及大块顺序 I/O 会抬高或尖峰化查询延迟。 | 逐点写主图会产生每次插入最多 `R` 个随机写，逐点删除会产生大量入边写；StreamingMerge 将计算与空间降到 change-set 比例。实测 merge 阶段对搜索有明显干扰。 | 立即可见依赖多索引查询，长期有界依赖集中合并；平滑前台更新与周期性资源峰值不能同时免费获得。 |
| IP-DiskANN | 删除搜索产生的 visited set 同时近似入邻居并提供替代边候选，属于一次遍历多用；未规定存储缓存复用。 | 每次更新修改局部邻接表；删除累计到阈值后全图扫描，仅清 dangling edges、不做距离计算。持久写单位由实现后端决定。 | 以 `c` 控制修复边数，以 `α>1` RobustPrune 保持导航性；论文在长 runbook 上报告稳定 recall。遗漏入边并非立即清除，仍存在轻量延迟维护。 | 单向图无法廉价枚举入邻居；维护完整反向边会接近翻倍图空间并增加锁复杂度。论文用 recall、distance computations、QPS 和 update speed 对比 FreshDiskANN/HNSW。 | 局部近似修复降低每次删除成本，但修复覆盖率、残留 dangling edge 与后续扫描周期之间仍是显式取舍。 |
| LSM-VEC | 查询采样生成 edge heatmap，后续全局 reordering 使用该热度；LSM 缓冲吸收更新。论文没有说明插入搜索中间态被查询缓存直接复用。 | 边更新先写内存、再由 compaction 顺序写 SST；向量独立写。系统周期性对底层图做 query-heatmap 驱动的全局 reordering，并与 compaction 对齐。 | HNSW 分层与双向局部重连维持图质量；compaction 控制版本和空间；全局 reorder 控制查询局部性。三类控制分别存在，论文未给出联合触发器。 | 论文将静态 DiskANN 的离线构建和 SPFresh 的低 recall/原地更新视为不足；报告 billion-scale 下更低查询/更新延迟与至少 66.2% 内存下降。 | 写优化依赖 out-of-place 层级化，而查询优化依赖跨层查找、采样和周期性重排；更新局部性与查询物理局部性由不同机制维护。 |
| OdinANN | 插入搜索读到的页面保留在缓存，后续 neighbor update 直接使用，避免额外 RMW read；同一批修改记录被合并到少数页。 | 定长记录 out-of-place 移动，旧槽立即成为空槽，无显式 insert GC；默认约 2 倍空间换约 2 倍写放大。删除达到约 10% 或 search I/O 上升约 1.1 倍时，两遍全图合并回收。 | 动态 candidate pool 抵消 deleted IDs 对结果数的污染；删除 merge 根据数据量和服务 I/O 两类指标触发；插入的近似并发控制允许非全图快照。 | 论文指出 buffered insert 的内存 merge 仍逐点执行并产生数百读，batching 收益有限；direct insert 的主要挑战是随机写和并发锁。实验报告稳定搜索性能，但代价是约 2 倍磁盘空间和约 11.1 ms 插入延迟。 | 空间预留换平滑写入，近似隔离换并发，删除仍靠周期扫描；服务稳定性、空间效率与强操作级一致性不可同时最大化。 |
| DGAI | 插入 neighbor search 结果同时驱动 SADL placement；同页 topology 被后续 search 和 reverse-edge update 复用。query-level buffer 复用已读 topology 页，但 raw vectors 仍在 rerank 时独立读取。 | topology 以 4 KiB 页读写，页满时 split；raw vector 写独立空槽。论文强调 incremental maintenance，未声明全局 rebuild/GC 周期。 | SADL 在插入时把新点放到最近邻页并相似性 split，以持续维护 topology locality；HPQ 与两阶段查询抵消解耦布局的查询代价。删除和长期碎片控制未形成新的统一机制。 | 论文测得耦合布局在 topology 修改时产生冗余 raw-vector I/O，解耦后更新 I/O 大降；同时承认解耦使 vector retrieval 成为独立查询 I/O。报告更新 I/O 相对基线下降 69.4%–96.2%。 | 解耦提高更新局部性、降低写放大，却破坏查询中 topology/vector 的天然共取；SADL 只能维护 topology 页局部性，不能消除跨文件取数。 |
| NAVIS | 同一次 insertion position seeking 的入口图 explored set 与磁盘 explored set被复用于 entrance-graph 增量更新；新鲜入口图形成的近入口高复用 edgelist 被专用 cache 保留。结构更新聚合搜索中共同更新的邻接表。 | full vector 单独写；多条修改 edgelist 聚合为页级 out-of-place 写，整页失效后优先复用。entrance graph 覆盖率低于主图约 1% 时，部分新点被增量提升。 | 动态入口图防止入口随新增区域漂移；90% mostly-frozen cache 与 10% admission window保护热路径；out-of-place 聚合写保持共更新邻接表的物理共置。论文未处理长期删除债务。 | 在 OdinANN 上测得并发更新使搜索吞吐平均下降 27.89%，position seeking 最多占更新时间 85%；NAVIS 报告插入吞吐最高提升 2.74 倍、并发查询吞吐最高提升 1.37 倍。 | 用更新遍历维护查询入口与缓存的收益建立在二者访问分布相关上；当更新分布与查询分布错位时，更新产生的局部性可能不是查询真正需要的局部性。 |

## 跨架构核心张力

### 查询局部性与更新局部性

耦合记录使一次查询页读同时取得向量和邻接表，但每条 reverse-edge 更新也会重写大向量。DGAI 与 NAVIS 通过解耦消除这类写放大，却必须另外设计 PQ 过滤、选择性向量读、缓存或 topology 重排来补回查询损失。LSM-VEC 进一步把更新局部性定义为顺序 compaction，把查询局部性定义为 heatmap 驱动的物理重排；二者甚至不由同一时间尺度控制。现有系统证明了张力真实存在，但没有证明某一种静态布局或固定复用规则能在更新分布、查询分布和向量维度变化时始终成立。

### 立即可见与摊销维护

FreshDiskANN 让新点在内存图中立即可见、随后批量合并；LSM-VEC 让更新进入 memtable、随后 compaction；OdinANN 直接插入但延迟删除清理；IP-DiskANN 立即做近似局部修复、随后扫描 dangling edges；NAVIS 立即更新主图，但只按比例提升入口图。六个系统都把逻辑可见性与物理结构完全整理分开，只是债务载体分别变成内存图、LSM 层、删除集合、dangling edges、空洞页或 stale entrance graph。问题不再是是否需要后台维护，而是服务系统何时已积累到必须维护、哪一种服务退化信号能够提前说明这一点。

### 图质量与 update I/O、内存及 rebuild 成本

FreshVamana 与 IP-DiskANN 用更保守的 `α-RNG` 和局部修复保 recall；OdinANN 用空间预留和删除扫描换稳定前台；LSM-VEC 维护多层双向图并周期重排；DGAI、NAVIS 把图结构写与向量写拆开。更完整的入边信息、更广的修复范围和更频繁的整理通常提高 navigability，却分别增加内存、随机写、锁竞争或扫描成本。现有设计覆盖了两端的大量点，但缺少跨系统可比较的 maintenance debt 定义，论文通常各自报告 recall 稳定或平均吞吐，难以判断同一资源预算下谁只是把成本推迟到了另一阶段。

## 已占据的设计空间

当前不应再把以下内容单独包装为新 idea。第一，内存 delta 加周期性 merge 已由 FreshDiskANN 充分占据；第二，单向图删除的局部近似入邻居发现与轻量残边扫描已由 IP-DiskANN 占据；第三，直接插入、页内预留、out-of-place 记录合并与近似并发控制已由 OdinANN 占据；第四，LSM 化边存储、后台 compaction 和查询热度驱动重排已由 LSM-VEC 占据；第五，topology/vector 解耦、插入驱动的相似页布局与 PQ 两阶段查询已由 DGAI 占据；第六，选择性向量读、position-seeking 结果复用、动态入口图和入口感知缓存已由 NAVIS 占据。

因此，单独提出 co-locate/decouple、自适应 merge 阈值、缓存更新路径、保存 reverse index、用 LSM 吸收写、增量入口图或按相似度放页，都缺乏独立 novelty。合格问题必须位于这些机制之上的共同控制缺口，而不是更换数据结构名称。

## 可能的开放问题

### 候选一：跨操作局部性何时可迁移

问题不是如何缓存，而是插入 position seeking、reverse-edge maintenance 和查询 traversal 所观察到的热点是否属于同一个分布。OdinANN 用插入路径页避免 RMW read，DGAI 用插入近邻决定 topology placement，NAVIS 用插入 explored set 更新查询入口图与缓存，LSM-VEC 则用查询 heatmap 决定物理重排。这些机制分别默认某一种操作能预测另一种操作的未来局部性，但没有给出分布错位时的适用边界。该问题跨越至少四种架构，且直接对应查询局部性与更新局部性的真实取舍。

最小证伪实验只需要操作级 page/vertex trace，不改索引。对同一数据集构造 aligned、query-hot/update-cold、query-cold/update-hot 三种查询/更新分布，按时间窗计算更新访问集合对后续查询访问的 precision、recall、Jaccard，以及用更新热度替代查询热度时的可实现 cache-hit 上界。若在所有工作负载中二者都高度重合，或重合度变化不能预测查询 I/O/延迟变化，则立即 Kill；若只在 DGAI 成立而 OdinANN/NAVIS 不成立，也 Kill 跨系统叙事。

可运行性方面，DGAI 本机已有 trace 能力，OdinANN/PipeANN 有官方代码可补同口径 trace；NAVIS 与 LSM-VEC 当前仅能先做论文/代码可得性审计。这个候选在获得第二种可运行架构前只能标记为 Continue-to-audit，不能立项。

### 候选二：逻辑新鲜之后的结构维护债务如何被服务侧观测

各系统都能让更新很快对查询可见，但物理结构达到稳态的时间不同。FreshDiskANN 等待 merge，LSM-VEC 等待 compaction/reorder，OdinANN 等待 delete merge，IP-DiskANN 等待 dangling-edge scan，NAVIS 只选择性更新 entrance graph。现有触发器分别依赖内存量、删除比例、search I/O amplification、LSM 策略或入口图覆盖率，观测量彼此不兼容。开放问题是能否用一个与前台服务直接相关、且不依赖具体存储结构的债务量，提前区分无害延迟整理与即将导致 recall、tail latency 或空间恶化的延迟整理。这里的贡献目标是问题和测量定义，不是先指定一个控制器。

最小证伪实验不需要开发维护算法。选 FreshDiskANN/IP-DiskANN 官方实现与 DGAI/OdinANN 中至少一种，运行短周期更新并在每个维护边界采集四条时间序列：更新已可见比例、固定 recall 下 search I/O、p99 latency、无效或待整理结构占比。用 leave-one-workload-out 检验任一服务侧指标能否提前预测维护后收益。若各系统的收益只能由各自私有计数解释，公共指标没有跨系统排序能力；或维护前后前台性能差异小于噪声，则立即 Kill。若最终只是把删除比例、memtable 大小等阈值线性组合，也 Kill，因为这只是已有触发器的打包。

可运行性方面，FreshDiskANN/IP-DiskANN 可从 Microsoft DiskANN 官方代码审计并选择兼容版本，DGAI 已在本机运行，OdinANN/PipeANN 有官方实现；LSM-VEC 与 NAVIS 暂无已确认官方 artifact。候选至少需要两个不同维护模型复现同一债务—服务退化关系后，才进入 Claude 的 novelty 审查。

## 可运行系统与论文/代码审计系统

| 系统 | 本轮状态 | 下一步允许的动作 | 当前禁止的外推 |
|---|---|---|---|
| DGAI | 本机已编译、运行并完成既有 profiling；官方仓库与论文均可审计 | 只允许复用现有 trace 或做极小 trace 补齐，且必须等候高层审查 | 不得把此前任何 DGAI 子阶段占比当作跨系统瓶颈 |
| OdinANN | 官方论文；官方 PipeANN 仓库声明已集成 OdinANN 更新 | 先做版本映射与只读代码审计，再判断能否低成本复现 | 不得把 PipeANN 当前主线性能等同 FAST 2026 论文版本 |
| FreshDiskANN | 官方论文；Microsoft DiskANN 提供相关算法代码，但仓库已迭代 | 先固定与论文匹配的 legacy 分支/commit | 不得用当前 Rust provider 的持久化行为倒推原论文 |
| IP-DiskANN | 官方论文；当前 DiskANN3 声明采用其更新逻辑 | 可做算法和 provider 接口审计，实验前必须固定实现语义 | 论文未规定 SSD 写粒度，不能制造相关数字 |
| LSM-VEC | 本轮只确认论文，未确认官方 artifact | 仅论文审计与作者 artifact 搜索 | 不得声称可复现，也不得补写 compaction 参数 |
| NAVIS | 本轮只确认论文，未确认官方 artifact | 仅论文审计与作者 artifact 搜索 | 不得将其插入结果外推到删除维护 |

## 当前裁决

事实地图保留两个候选问题，不选择具体方案，也不启动实验。候选一的证伪成本最低，但必须先证明至少两种架构上确有 query/update locality mismatch；候选二覆盖面更广，但最容易退化成已有阈值机制的拼装，故门槛更高。下一步应由 Claude 独立审查 novelty 与系统味道，由 Gpt 审查可测量性和因果闭环，再由 PZ 决定是否给任何候选最小实验授权。在此之前，Codex 不修改系统实现，不继续 DGAI profiling。
