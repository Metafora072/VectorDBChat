# Page-Cost-Aware Navigability C0：Joint Graph–Packing 理论门禁报告

## 结论

**裁决：KILL，不进入 C1。**

Page-aware graph search 是真实且重要的问题，且现有工作中没有发现与本门禁完全等价的 joint graph–packing theorem：PageANN 没有正式 navigability/page-I/O 保证，OctopusANN 也明确固定 Vamana logical graph。但在本轮固定的资源内，无法同时满足门禁要求的 separation 或 hardness + constructive approximation。

最强的字面 separation 候选来自一维 path 加 shortcut：它能以常数 edge/degree slack 把 worst-case 路由 hop 从线性降到 polylog，从而产生非恒定 page-read 比值。然而这个收益在 `B=1` 时仍完整存在，不需要 packing，也不需要 page-aware construction；它只是经典的 sparsity–hop-diameter trade-off。把搜索语义收紧到真实 closest-first/page search，并要求两侧 matched vertex expansions、gap 在 `B=1` 消失后，本轮没有得到 separation。

自然的 approximation 方向也不够：固定 packing、固定 source 时，选择能覆盖 navigability constraints 的 pages 直接成为 Set Cover；它最多给出 `O(log n)` page-cover approximation，却可能需要 `O(B log n)` edges，既不是 joint `(G, pi)` 算法，也不满足常数 edge slack。只证明 `B=1` hardness、fixed-layout hardness或 weighted Set Cover 同样达不到门禁。

独立反方评分为：problem significance `8/10`、formal novelty `4/10`、system relevance `4/10`、implementation feasibility `3/10`，未达到 `7/6/7/7` 的同时通过线。

## 1. 范围与资源合规

本轮只进行了论文原文核验、公式建模、分离构造尝试和对抗证明审计：

- 未运行数据集实验；
- 未构建或修改任何 ANN index；
- 未修改 Vamana/PageANN；
- 未生成 trace；
- 临时论文材料位于 `/tmp`，新增仓库空间远低于 `1 GiB`；
- 本报告完成后停止，不自动进入 C1。

Claude 在同一轮对话中提出的 learned-repair 和 self-improving graph 两项 quick check 是“若 PZ 或 Gpt 另行批准”的条件请求。GPT 当前 gate 明确要求本轮只判断 joint graph–packing C0，因此本轮未把这两项扩展进来。

## 2. Primary-work 事实纠正

### 2.1 PageANN 不是普通 post-hoc layout

PageANN 从高质量 vector graph（实现中为 Vamana）出发，在原图的 `h`-hop 候选内把相近 vectors 聚成 page nodes；随后聚合 constituent vectors 的跨页 edges、删除页内 edges 并合并重复 page connections。每个 logical page node 一一映射到 physical SSD page，页面包含 full vectors、page-neighbor IDs 和 compressed neighbor vectors。查询先经内存 routing，再执行 page-to-page traversal；读页后计算页内全部 full-vector distances，并用压缩邻页向量选择下一跳。[PageANN §4.1–§4.4](https://arxiv.org/abs/2509.25487)

因此不得再声称 PageANN 只是“标准 Vamana 后做 shuffle”。它已经覆盖：

- logical granularity 从 vector node 改为 page node；
- topology aggregation；
- logical/physical page alignment；
- full-page evaluation 和 page-level traversal。

PageANN 全文未发现 theorem/lemma、`alpha`-navigability、sorted reachability或 worst-case distinct-page guarantee。真正剩余的空白只能是：以 page reads 为目标，同时选择 topology 与 packing，并保留正式 navigability/space/degree guarantee。

### 2.2 OctopusANN 已有 page-level cost model

OctopusANN 定义局部 overlap

$$
OR(u)=\frac{|B(u)\cap N(u)|}{n_p-1},
$$

并以顶点平均得到 `OR(G)`。对 disk-resident best-first search，其解释模型为

$$
\operatorname{PageReads}
=O\!\left(\frac{\bar R H}{OR(G)n_p}\right),
$$

使用内存 PQ 过滤后写为

$$
O\!\left(\frac{H}{OR(G)n_p}\right),
$$

其中 `H` 是 expected hop count、`R-bar` 是 average out-degree、`n_p=floor(PageBytes/RecordBytes)`。[OctopusANN §3.1](https://arxiv.org/abs/2602.21514)、[PVLDB DOI](https://doi.org/10.14778/3801059.3801064)

它还系统组合 PQ、MemGraph、PageShuffle、PageSearch 与 DynamicWidth。因此“edge/node cost 与 page cost 不一致”“提高 overlap 可减少 I/O”都不是 novelty。尚未被它覆盖的一点是：论文明确固定 DiskANN/Vamana logical graph，只优化 memory layout、physical layout和 search scheduling；它没有选择 logical topology，也没有逐查询 distinct-page theorem。

## 3. 固定 formal page model

### 3.1 数据、记录与 packing

给定 finite metric space `(P,d)`、`|P|=n`、`alpha>=1`。图 `G=(P,E)` 为 directed graph，受 maximum out-degree `R_*` 和 total edge budget `M` 约束。

为避免 topology 改变后偷偷改变每页记录数，本报告不把 `B` 与 degree 独立指定。固定 physical page bytes `C_page` 和统一的 padded record：

$$
S_{rec}(R_*)=S_{vec}+S_{meta}+S_{deg}+R_*S_{id}.
$$

每条 record 包含 full/compressed vector、metadata、neighbor count 和 `R_*` 个 padded neighbor-ID slots；因此

$$
B=\left\lfloor\frac{C_{page}}{S_{rec}(R_*)}\right\rfloor.
$$

两侧比较使用同一个 `R_*` 和同一个 padded record bytes。否则 joint graph 增加 degree 时会让真实 `B` 下降，门禁中的同容量比较无效。packing

$$
\pi:P\rightarrow\{1,\ldots,m\}
$$

满足每页至多 `B` 条完整 records，不分离 adjacency 与 vector。

### 3.2 固定查询与 page-aware search

为让 `alpha`-navigability 的量词与查询一致，主对象限定为 exact-target queries：`q=t in P`，source `s in P`。固定 deterministic greedy `S_page`：

1. 读取当前 vertex `v` 所在页面；若该页已缓存则不重复计费。
2. 根据 `v` record 中的 neighbor IDs 读取尚未缓存的 out-neighbor pages，以取得候选的 vector records并计算 exact distance。一次读取带回的整页 records 可用于结果计算和后续缓存命中，但**未经显式 edge 到达的共页 vertex 不得进入 navigation frontier**。这避免 packing 隐式添加 `B-1` 条未计入 `E` 的零成本边。
3. 在 `v` 的 out-neighbors 中选择距离 `t` 最近且严格改善的 vertex，ID 作为固定 tie-break；无改善则终止。
4. 到达 `t` 时终止。每次 expansion 最多新触发 `R_*` 个 candidate pages；若理论改为全局内存 PQ，必须另建 memory/search model，不能隐含免费取得 neighbor distances。

对 `alpha`-navigable graph，数据点目标至少存在一条满足

$$
d(u,t)<d(v,t)/\alpha
$$

的出边，所以 greedy 可继续。注意：这个对象只对应 exact-target greedy，不自动推出 arbitrary external query 或 fixed-width beam 的 page cost。若要覆盖真实 beam，需要采用并重新证明 sorted `alpha`-reachability一类更强性质。

查询成本为

$$
C(G,\pi;s,t)
=\left|\{Q:Q\text{ 被 }S_{page}\text{ 为当前点或候选邻居读取}\}\right|,
$$

主目标固定为 worst case：

$$
C_{wc}(G,\pi)=\max_{s\ne t\in P}C(G,\pi;s,t).
$$

本报告不混用 expected workload objective。

### 3.3 模型仍有的系统边界

“读页后 free-evaluate 所有共页 records”不能同时解释为这些 records 免费可导航。若允许后者，packing 等价于加入未计费 implicit edges，edge/degree budget失真；若直接把一页变成 logical node，则模型已切换为 PageANN page-node graph，而不是同一个 vector-node `G`。本轮采用“免费计算、不可隐式转移”的保守语义，但它与 PageANN/OctopusANN 的 full page-search 仍不完全等价，这是 system relevance 降分的原因之一。

## 4. 三个优化对象与 strongest baseline

令

$$
OPT_{edge}=\min_G |E(G)|
\quad\text{s.t. }G\text{ is }\alpha\text{-navigable},\ 
\Delta^+(G)\le R_*.
$$

### 4.1 Fixed-graph best layout

对明确给定的 `G_0`：

$$
PostLayout(G_0)=\min_{\pi}C_{wc}(G_0,\pi).
$$

这个 baseline 是不可实现也允许使用的最强 packing oracle；它支配普通 ID reorder、graph partitioner、PageShuffle 和 same-page tie-break 后的 layout。DiskANN++、Starling等具体系统只用于证明 oracle 覆盖范围，不能代替 oracle。

### 4.2 Edge-sparsity-optimal family

$$
SparsePageOPT=
\min_{G,\pi}C_{wc}(G,\pi)
$$

subject to `G` is `alpha`-navigable、`|E|=OPT_edge`、`Delta+(G)<=R_*`。这排除了挑一个刻意差的 sparse graph 制造 gap。

### 4.3 Joint page-cost optimum

$$
PageOPT_c=
\min_{G,\pi}C_{wc}(G,\pi)
$$

subject to `G` is `alpha`-navigable、`|E|<=c OPT_edge`、`Delta+(G)<=R_*`，并使用相同 padded record和由它推导的 `B`。

可接受的 Separation A 必须来自 `SparsePageOPT/PageOPT_c`，而不仅是某个 `PostLayout(G_A)`；还应补充 gate 原文没有写出的 page-specificity 条件：`B=1` 时 gap 消失或为常数，且两侧 matched vertex-expansion/hop bound。否则任何 ordinary hopset 都能冒充 page-native result。

## 5. Separation 推导与反证审计

### 5.1 字面门禁下的一维候选

取 `P={0,...,N}`、`d(i,j)=|i-j|`、`alpha=1`。对相邻目标 `(i,i+1)`，1-navigability 要求存在 `u` 使

$$
|u-(i+1)|<1,
$$

所以唯一可能是 `u=i+1`；反向同理。于是全部 `2N` 条相邻 directed edges 被强制，bidirected path 已经充分，故 `OPT_edge=2N` 且 edge-optimal graph 唯一。

从 `0` 到 `N` 的 greedy path 访问所有 `N+1` 个 vertices，并在逐步比较相邻候选时取得这些 records。无论 oracle 如何 packing，它都会读取全部非空 pages，因此

$$
SparsePageOPT=PostLayout(G_0)=\left\lceil\frac{N+1}{B}\right\rceil.
$$

令 `N=2^k`。在 path 上为 `i>0` 增加

$$
i\rightarrow i-\operatorname{lowbit}(i),
$$

并为 `i<N` 增加其关于 `N` 的对称 shortcut

$$
i\rightarrow i+\operatorname{lowbit}(N-i).
$$

去重后总边不超过 `3N <= 2 OPT_edge`，maximum out-degree不超过 4；因保留全部 path edges，它仍是同一 `alpha=1`-navigable graph。固定一个不越过目标、优先取得最大测地进展的 deterministic router。令 `T(k)` 为区间 `[0,2^k]` 上单向路由的最坏步数；按中点递归，一侧先清除 offset 的最低 1-bit，再进入低一层区间，得到

$$
T(k)\le T(k-1)+k+1=O(k^2).
$$

即使每次 expansion 为比较候选而读取至多 4 个 neighbor pages，也有 `PageCost<=1+4T(k)=O(log^2 n)`。若只按 gate 的字面条件计数，就会得到

$$
\frac{SparsePageOPT}{PageOPT_2}
=\Omega\!\left(\frac{n}{B\log^2 n}\right)
$$

的非恒定比值。

### 5.2 Proof status

**Status: NOT CURRENTLY JUSTIFIED as a page-native separation.**

该候选不能作为 PASS theorem，原因不是最优 packing 消掉了 path lower bound，而是结论的机制错误：

1. `B=1` 时比值仍为非恒定；packing 完全没有参与 upper bound。
2. joint graph 的优势全部来自 shortcut 降低 `H`，换成 node-expansion objective仍然成立。OctopusANN 已把 `H` 单独列入 cost model。
3. 候选依赖 `alpha=1` 的仅严格下降；没有证明实用 `alpha>1` 或 sorted reachability。
4. 最容易证明 polylog bound 的 geometric router会拒绝某些 overshooting shortcuts，不等价于普通 closest-neighbor best-first。
5. 若改成 PageANN/OctopusANN 式 page-induced transitions，原 path lower bound需要重证；oracle 可把一页中的非连续 vertices 当 landmarks。
6. 即使把上下图都 padding 到同一 maximum-degree record以维持 `B`，结果依然只是 edge–hop trade-off。

因此，这个构造只证明当前 gate 若不加入 page-specificity 和 matched-expansion 条件会出现 formal loophole；它没有证明 joint graph–packing 的研究主张。

### 5.3 收紧条件后的结论

本轮没有找到同时满足以下条件的 metric family：

- strongest post-layout oracle 仍有非恒定 lower bound；
- `B=1` 时 gap 消失；
- 两侧使用同一 closest-first或 fixed-beam search；
- 两侧 matched vertex expansions/hop bound；
- constant edge和 degree slack；
- 相同 padded record bytes；
- 同一 `alpha`/sorted reachability；
- gain 来自跨查询路径的 packability，而不是更短路径。

故 Separation A 不成立；Separation B 单独证明某一 construction 较差也不足以救回该方向。

## 6. Hardness / approximation 边界

Sparse Navigable Graphs 对每个 source `s` 定义

$$
Z_\alpha(s,u)=\{t\in P:d(u,t)<d(s,t)/\alpha\}.
$$

选择 `s` 的 out-neighbors 使全部目标 constraints 被覆盖，等价于一个 Set Cover；已有 `O(log n)` approximation和匹配的对数 hardness。[Sparse Navigable Graphs §4](https://arxiv.org/abs/2507.14060)

对固定 packing `pi`，自然的 page set 为

$$
C_s(Q)=\bigcup_{u:\pi(u)=Q} Z_\alpha(s,u).
$$

选择最少 pages 使 `C_s(Q)` 覆盖 `P\{s}` 仍是 Set Cover。greedy 至多得到 `O(log n)` page-cover factor，但要真正使用同页中不同 `u` 的 coverage，`s` 仍必须拥有指向这些 `u` 的显式 edges；最坏每个选中页需要 `B` 条边，因此只能得到约 `O(B log n)` edge bicriteria，而非门禁要求的常数 `c`。

结论如下：

- 给每条 edge 一个固定 page weight：weighted Set Cover 重述，KILL；
- `B=1`：继承 sparse navigability hardness，但没有 page novelty，KILL；
- 固定 `G` 优化 layout：Starling 已证明 fixed-graph block shuffling 困难，hardness-only 不新；
- 多跳 distinct-page union：跨 hop 复用使成本非加性，已有 Set Cover approximation不能直接传递；本轮没有新的 reduction或 constructive joint approximation；
- joint `(G,pi)`：本轮没有 bounded approximation或 constant-edge bicriteria算法。

所以 Separation C 也未达到 PASS。

## 7. Prior-work matrix

| 工作 | 已覆盖对象 / 保证 | 对候选的边界 |
|---|---|---|
| [PageANN](https://arxiv.org/abs/2509.25487) | Vamana-derived page nodes、跨页边聚合、页内边删除、logical/physical page alignment、full-page evaluation | 已占据 page-native graph系统构造；仅缺 formal navigability/page-I/O theorem |
| [OctopusANN](https://arxiv.org/abs/2602.21514) | `R-bar/H/OR(G)/n_p` page-I/O模型；PQ、MemGraph、PageShuffle、PageSearch、DynamicWidth | 固定 Vamana topology，joint logical construction仍为空；但 hop/overlap故事已占据 |
| [DiskANN++](https://arxiv.org/abs/2310.00402) | query-sensitive entry、isomorphic layout mapping、async PageSearch | strongest baseline不能弱化为普通 ID layout/beam |
| [Starling](https://doi.org/10.1145/3639269) | sampled memory navigation graph、fixed-topology block shuffle、block search、layout hardness | fixed-layout NP-hard 不是新结果；其 padded record也说明 `B` 必须由 bytes/degree推导 |
| [Sparse Navigable Graphs](https://arxiv.org/abs/2507.14060) | `alpha`-navigability、edge/max-degree objective、Set Cover equivalence、approximation/hardness | edge weight或固定 packing的自然 formulation容易退化为 Set Cover |
| [Efficiently Constructing Sparse Navigable Graphs](https://epubs.siam.org/doi/10.1137/1.9781611978971.59) | 相关 Set Cover 实例的近二次构造、`O(log n)` approximation、hardness；扩展 shortcut reachability/monotonicity | 仅复用 sparse construction或对数 approximation门槛不足 |
| [Sort Before You Prune](https://proceedings.mlr.press/v267/gollapudi25a.html) | sorted `alpha`-reachability和 greedy/beam guarantee | 真正 page-aware prune 必须保留排序 witness；只有同距离 tie-break安全时又落入 gate KILL |
| [Disk-resident graph ANN experimental evaluation](https://arxiv.org/abs/2603.01779) | page size、record capacity、dimension与 I/O utilization 的系统证据 | 支持问题重要性；同时预测 `B=1` 时 locality gain应消失，不提供 formal novelty |

## 8. PASS/KILL 核对

| 条件 | 结果 | 说明 |
|---|---|---|
| 严谨 joint formal object | 部分 | exact-target greedy可固定，但真实 beam/page-induced transition仍未覆盖 |
| PageANN/OctopusANN无等价 theorem | 通过 | 未发现等价 formal theorem；系统机制和 cost维度已高度覆盖 |
| 非恒定 separation 或 hardness + constructive approximation | **失败** | 字面 gap 是 hopset loophole；无 joint approximation |
| strongest post-layout oracle | 通过 | path lower bound对任意 packing成立，但不是 page-specific gain |
| graph/packing/search/record完全固定 | 部分 | padded record可修复 bytes问题；page frontier语义仍与真实系统有差距 |
| matched navigability、edge/degree | 部分 | 字面构造可控制；没有 matched hop/expansion，无法隔离 page贡献 |
| 可证伪系统预测 | **失败** | 当前可预测的是 shortcut减少 hop；不能预测 layout-only oracle与 joint design 的 page-specific差异 |
| 独立评分达到 `7/6/7/7` | **失败** | `8/4/4/3` |

任一失败即 KILL；本轮有三项决定性失败。

## 9. 最终裁决与非声明

**KILL 当前 Page-Cost-Aware Navigability 路线；不准备 C1，不运行 PoC。**

本报告不声称“joint graph–packing 数学问题不存在”。准确结论是：在 PageANN、OctopusANN、Starling和 sparse-navigability/Set-Cover 理论已经覆盖的边界下，本轮没有找到一个同时具备 formal novelty、page-specific nonconstant gap、真实搜索对应和可构造保证的对象。继续投入很可能只得到以下之一：

- PageANN 构造的理论化复述；
- OctopusANN `H` 或 `OR(G)` 的另一种优化；
- ordinary hopset/shortcut trade-off；
- fixed/weighted Set Cover；
- same-page tie-breaking heuristic。

若未来重开，必须先把“`B=1` gap消失、matched expansions、fixed bytes、无 implicit page edges、strongest layout oracle、constant edge/degree bicriteria”写成硬条件；在此之前不应进入系统实现。
