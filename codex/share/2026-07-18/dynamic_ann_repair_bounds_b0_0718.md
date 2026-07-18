# Dynamic ANN Repair Bounds B0：Deletion-Only Local-Certificate Audit

## 0. Executive decision

**B0 formal result：`PASS-B (general bounded-degree directed metric graph model)`。**

对任意固定有限局部半径 `r`，本报告给出一对完整的不可区分实例。两实例具有相同数据集、查询与入口分布、固定 deterministic greedy search、删除点 `v` 的 pre-delete `r`-hop local view，以及相同的删除前成功轨迹；但排除 mandatory incident-edge cleanup 后，把 fixed search success 恢复为 1 所需的最少**新增边** `AddOPT` 分别为 `0` 和 `1`。因此，不存在一个只读取该有限半径邻域、同时对所有实例 sound 且能在每个 `AddOPT>0` 实例上给出正 lower bound 的 certificate；也不存在精确的 pure-local skip/repair oracle。

这个结论直接 Kill 一类候选：

> 仅凭删除点的固定半径 graph neighborhood，在读取远端 search suffix 前，对所有实例精确判定是否必须新增 repair edge，或在每个 positive-`AddOPT` 实例上都给出正的 sound lower bound。

**Strategic decision：`STOP / do not enter B1`。** 该 PASS 是一个一般模型中的负面定理，不是 Vamana 系统候选复活信号。构造没有证明其两个实例都可由 Vamana/DiskANN builder 在常用参数下输出；`0/1` gap 也不产生 mutated-record 或 SSD page-I/O gap。除非后续单独获得 Gpt 授权，把 theorem 收紧到实际 graph family 或形成更强 information lower bound，否则建议关闭本 repair-bound implementation line。

本轮没有运行实验、生成 trace、构建索引、修改代码、实现 prototype 或启动 B1。

## 1. Fixed formal model

### 1.1 Search instance

固定对象为：

```text
metric space (M, d)
finite dataset X subset M
directed graph G=(X,E), maximum out-degree R
deleted vertex v in X
entry distribution D_s
query distribution D_q
deterministic search procedure S
```

主定理使用最简单的 fixed greedy search。对当前 live vertex `u`，`S` 比较 `u` 与它的全部 live outgoing neighbors；若存在到查询 `q` 严格更近的邻居，就移动到距离最小者，否则停止并返回 `u`。tie-breaking 固定，但构造中没有距离 tie。termination rule 也是固定的“无严格改进即停止”。

定义：

```text
Success_S(H,q,s) = 1
```

当且仅当 `S` 在 live graph `H` 中从入口 `s` 出发，最终返回 `q` 在 live dataset 中的真正最近邻。于是：

```text
P_success(H) = Pr_{q~D_q,s~D_s}[Success_S(H,q,s)=1].
```

本报告选择 point-mass `D_q` 与 `D_s`，因此 theorem 约束的是一个完全固定、可复核的 search trace，而不是用 connectivity、degree 或经验 Recall@k 代替 search quality。

### 1.2 Deletion and repair action

`G-v` 表示删除 `v` 以及所有 incident edges 后的 live graph。mandatory incident-edge cleanup 不计入下述额外 repair optimum。repair 只能对 live vertices 选择：

```text
Delta E^- subset E(G-v)
Delta E^+ subset (X\{v})^2
```

结果图仍须满足 maximum **out-degree** `R`。先定义 theorem 使用的 extra-addition optimum：

```text
AddOPT(G,v)
  = min |Delta E^+|
    s.t. P_success((G-v-Delta E^-)+Delta E^+) >= tau,
         maximum out-degree <= R.
```

其中 minimization 同时选择 `Delta E^-` 与 `Delta E^+`，但 objective 只数新增 replacement edges。主定理取 `tau=1`。有限图上的候选 edge action 集有限，所以 `AddOPT` 是 well-defined combinatorial optimization。也可另定义额外 edge-action optimum `MutOPT=min(|Delta E^-|+|Delta E^+|)`；本构造中 deletion-only action无助于恢复成功，因此 `MutOPT` 同样为 `0/1`。若计算包含删除 `v` 的 total mutations，数值取决于 target-record 与 incident-edge cleanup convention，本报告不使用该口径。

`AddOPT/MutOPT` 不等于最小 distinct adjacency-record 数，更不等于最小 page writes。两种成本在第 7 节单独讨论。

### 1.3 Local view

先在**删除前**把 directed graph 忽略方向得到 symmetrized graph。`View_r(G,v)` 是以 `v` 为 root 的 metric-labeled view，包含：

1. 到 `v` 的 symmetrized graph distance 不超过 `r` 的全部 vertices；
2. 这些 vertices 的 ID 与 metric coordinates；
3. 球内 edges 的方向；
4. 球内 vertex 的完整 outgoing adjacency；若 neighbor 在球外，可将其 ID/coordinate 作为 boundary stub 暴露；
5. 固定的 `X,D_q,D_s,S,R`。

因此 theorem 并未依赖“隐藏数据坐标”或“隐藏本地 adjacency”的弱 local-view 定义。certificate 唯一不能读取的是半径外 edge structure；一旦沿 post-deletion trace 继续读取远端 edges，它就已经不再是 `r`-local certificate。

## 2. Prior-work guarantee matrix

| Work | 固定 search / formal object | deletion repair guarantee | 是否给出 local necessary witness / min-repair approximation | B0 boundary |
|---|---|---|---|---|
| [Greator](https://www.vldb.org/pvldb/vol19/p495-yu.pdf) | lightweight topology 定位 affected vertices/pages，随后 localized replacement 与 page-aware `Delta G` | matched-quality 主要为实验结果；affected-set 与 localized patch 是算法范围，不是必要性证明 | `NO`；没有证明每个 affected page/edge 对固定 search success 必须，也没有对 minimum repair 的 approximation | 强 practical baseline；不能用 affected-set 重命名 theorem |
| [IP-DiskANN](https://arxiv.org/pdf/2502.13826) | deletion 后以 graph search 近似寻找 in-neighbors，并复制常数个 replacement directions | replacement 数量约 `O(cR)`，stable recall 为 empirical；仍需要后续 dangling cleanup | `NO`；search-derived candidates 是 constructive heuristic，不是必要 lower bound | 已占“少量 localized replacement edges”，未占 local impossibility |
| [Wolverine](https://www.vldb.org/pvldb/vol18/p2268-zheng.pdf) | formal monotonic-search-path (MSP) 对象 | 对已知 affected path，合适 shortcut 可恢复该 path；理想修复需识别全局 affected queries/paths，2-hop 与 candidate filtering 是 practical restriction | 提供重要的**充分** path repair；未给一般 r-local necessity 或 minimum-repair approximation | monotonic path 不能未经 query/path coverage 证明替代 `P_success` |
| [Dynamic Exploration Graph](https://arxiv.org/abs/2307.10479) | even-regular undirected structure、connectivity 与 continuous refinement | deletion 后维持/恢复 graph connectivity；实现可自适应扩大 inspected region | `NO`；connectivity 不推出本报告 fixed greedy success | 不能把 connected graph 当 ANN-success invariant |
| [CleANN](https://arxiv.org/abs/2507.19802) | fixed GreedyBeamSearch 配合 query/insert traversals、guided bridges 与 semi-lazy cleaning | workload-aware linking 和 query-adaptive consolidation 主要由实验验证 | `NO`；query-adaptive edge value 没有形成 necessary certificate | 说明有用状态可 query-conditioned，但未解决 min repair |
| [SPatch / Graph-Based NNS with Dynamic Updates via Random Walk](https://openreview.net/pdf?id=l97Kacqdfk) | fixed-query greedy equivalence与 random-walk transition/hitting-time proxy | clique replacement 可给固定 query 的 greedy-equivalent充分修复；star-mesh 对 random walk transition 有 exact/approx results | `NO` for minimum greedy repair；作者明确区分 hitting time 与 softmax/greedy 找到正确目标 | strongest formal adjacent work；充分 upper bound / random-walk proxy 不等于必要 lower bound |
| [Graph-based NNS: From Practice to Theory](https://proceedings.mlr.press/v119/prokhorenkova20a.html) | 在随机球面数据、特定 proximity graph 与维数/规模条件下分析 greedy/beam | static query guarantee | `NO` dynamic deletion optimum；保证依赖全局随机生成假设 | 可用于 restricted family，不支持一般 local deletion claim |
| [Dynamically Detect and Fix Hardness](https://arxiv.org/abs/2510.22316) | fixed GreedySearch；query top-`S` induced subgraph 上的 Escape Hardness | `L` 足够大时给 visit guarantee；实际 repair 依赖 exact/approx query hardness state | 形式上更接近 search success，但 state 是 query-conditioned/global，不是 deletion-centered r-local necessity | 反向支持本报告边界：有意义 witness 需要超出删除点 local view |
| [When to Repair, v2](https://arxiv.org/abs/2607.00728) | matched-budget repair scheduling negative result | current v2 不再主张 signal 带来正收益；讨论何时 repair | `NO`；scheduler signal 不选择“必须修哪些边” | “何时修”与“哪些边必要”必须分开 |

矩阵结论是：已有工作给出了 affected-only implementation、search-derived candidate、monotonic-path sufficient repair、connectivity invariant、workload-aware heuristic，以及 random-walk/greedy-equivalent sufficient upper bound；没有发现对**一般 fixed greedy/beam、单点删除、有限 deletion-local view**给出 complete positive necessary bound、exact skip oracle 或 minimum edge-repair approximation 的 primary result。这不否认某些特定 local views 可以支持 sound positive witness。

## 3. Main claim and status

### 3.1 Claim

**Theorem 1（finite-radius local repair certificate impossibility）。** 对任意有限整数 `r>=0`，存在一维 Euclidean dataset、maximum out-degree `R=2` 的两张 directed metric search graphs `G_A,G_B`、同一个 deleted vertex `v`、相同 point-mass entry/query distributions，以及相同 fixed deterministic greedy search `S`，满足：

1. `View_r(G_A,v)=View_r(G_B,v)`；
2. 删除前两图均有 `P_success=1`，且实际 search trace 相同；
3. 删除 `v` 后，`AddOPT(G_A,v)=0`；
4. 删除 `v` 后，`AddOPT(G_B,v)=1`。

因此，任何以 `View_r(G,v)` 为唯一 graph input 的 certificate `C_r`：

- 若它对全部此类实例给出 sound nonnegative necessary lower bound `C_r<=AddOPT`，则在**这个 local view**上只能输出 `C_r=0`，无法为 `G_B` 证明任何正 repair necessity；
- 若它精确判断 `AddOPT=0` 还是 `AddOPT>0`，则至少在一个实例上错误；
- 若它是 one-sided conservative skip/repair filter，则必须在 `G_A` 上也选择 repair，因而不能相对 zero-optimum instance 给出有限 multiplicative instance-optimality。

定理不声称所有其他 local view 上的 sound witness 都必须为0，也不排除只给 sufficient condition 的 one-sided certificate。

### 3.2 Status

`PROVABLE AS STATED`，适用于一般 bounded-degree directed metric graphs。它不声称两图满足 Vamana/alpha-RNG/MSNET 的 builder-output invariant，也不声称对 beam search 的所有实现自动成立。由于 fixed greedy 是 gate 允许的 search procedure，定理足以反驳“对一般 fixed graph search 存在普遍 finite-radius deletion-local necessary certificate”的主张。

## 4. Complete indistinguishable-instance construction

### 4.1 Vertices and coordinates

固定任意 `r>=0`，令：

```text
L = r + 2.
```

metric space 是实数轴，距离为绝对值。query `q=-1`。数据点为：

```text
X = {t,z,p,v,d_1,...,d_L,a_1,...,a_L}.
```

坐标定义为：

```text
x_t     = 0
x_z     = 1
x_d_i   = L + 2 - i       (thus x_d_L = 2)
x_v     = L + 2
x_a_i   = 2L + 3 - i      (thus x_a_L = L + 3)
x_p     = 2L + 3.
```

所以 `t` 是 `q` 的唯一真正最近邻。取 `D_s=delta_p`，`D_q=delta_q`。

### 4.2 Common and differing edges

两图共同包含：

```text
(p,v), (p,a_1), (v,d_1),
(d_i,d_{i+1}) for 1<=i<L,
(d_L,t),
(a_i,a_{i+1}) for 1<=i<L.
```

`G_A` 额外包含：

```text
(a_L,t).
```

`G_B` 额外包含：

```text
(a_L,z).
```

`t,z` 没有 outgoing edges。所有 vertex 的 out-degree 至多 2。

### 4.3 Search behavior before deletion

从 `p` 看，`v` 比 `a_1` 更接近 `q`，因此两图都选择 `v`。沿 `d_1,...,d_L,t`，每一步坐标严格减小，因而到 `q` 的距离严格减小。删除前两图的唯一实际 trace 都是：

```text
p -> v -> d_1 -> ... -> d_L -> t.
```

返回唯一真正最近邻 `t`，所以两者 `P_success=1`。

### 4.4 Search behavior after deleting v

删除 `v` 及其 incident edges 后，`p` 唯一 live outgoing neighbor 是 `a_1`。`a` chain 上的坐标也严格减小，所以两图均走：

```text
p -> a_1 -> ... -> a_L.
```

在 `G_A-v` 中，下一步是 `t`，search 成功；不需要任何额外 repair，所以：

```text
AddOPT(G_A,v)=0.
```

在 `G_B-v` 中，下一步是 `z`，随后停止。`z` 不是真正最近邻 `t`，所以 zero-repair 不可行。只做 edge deletion也不能创造一条到 `t` 的 greedy path；因此至少需要一个 edge addition。加入 `(p,t)` 即可恢复成功，且删除后 `p` 的 out-degree 从 1 增至 2，仍满足 `R=2`。故：

```text
AddOPT(G_B,v)=1.
```

### 4.5 Equality of r-local views

在两图共同部分中：

```text
dist_sym(v,p)   = 1
dist_sym(v,d_i) = i
dist_sym(v,a_i) = i+1.
```

差异 edge 的 source `a_L` 到 `v` 的距离是：

```text
L+1 = r+3 > r.
```

`t` 也在距离 `L+1=r+3` 之外；`z` 只在 `G_B` 中经 `a_L` 连接，仍在球外。`G_A` 的 `(a_L,t)` 不产生进入 radius-`r` 球的 shortcut：从 `v` 经 `d` chain 到 `t` 已需 `L+1` hops，再到 `a_L` 还需一步。故两图 radius-`r` 球的 vertex set、directed internal edges、local full adjacencies与 boundary stubs 均完全相同。

由于 `X,D_q,D_s,S,R` 本来就相同，得到：

```text
View_r(G_A,v)=View_r(G_B,v).
```

### 4.6 Indistinguishability consequence

deterministic local certificate 对相同 input 必须输出相同值。若输出正 lower bound，它在 `G_A` 上不 sound；若输出 0，它不能证出 `G_B` 的正 necessity。exact classifier 同理不能同时正确。

对 randomized exact classifier，把两个实例等概率混合；由于 observation distribution 完全相同，而 truth label 不同，其错误率至少 `1/2`。这不是“recall 是全局的”口头判断，而是固定数据、固定 search、固定 query/entry 与显式 optimum 的 observation-equivalence proof。

## 5. What additional state is necessary

Theorem 1 并不证明必须保存某一种唯一数据结构，但证明任何能对该实例对作出 exact skip/repair 判断的状态，都必须在 `G_A,G_B` 间取不同值。最小语义上，它至少需要暴露以下等价信息之一：

- post-deletion greedy trace 在 local frontier 之外最终到达 `t` 还是 `z`；
- 从 local boundary state 到目标集合的 query-conditioned transfer summary；
- 一个覆盖远端 suffix 的 search-path/cut witness；
- 实际重放该 query/entry 的远端 path。

这些都是 query/search-conditioned global state，而不是 deletion-centered fixed-radius neighborhood。直观上可以复制互不干扰的 gadgets，并独立选择每个远端 terminal edge，得到增长的远端状态空间；但本报告没有给出该 multi-gadget direct-sum theorem，因此不把它用于 PASS-B，也不主张任意非局部 probe 数或逐 query bit 数的正式下界。

well-defined optimum 可以通过全图 exhaustive enumeration 计算，但这不使它 local：可行性检查本身需要知道 repair 后 fixed search 对 `D_q,D_s` 的全局 path/output。对一般分布，精确计算还需聚合其支持集或一个足以证明概率下界的 global proxy。

## 6. Relation to monotonic paths, hitting time and ANN success

### 6.1 Monotonic path

若对给定 `(q,s,target)` 保留了一条每步严格接近 `q`、且 fixed greedy 不会被其他 outgoing neighbor 引走的 path，则可以推出该次 greedy search 成功。这是 query/target-conditioned 的**充分**条件。Wolverine 的 formal contribution位于这一侧：已知被破坏 path 后构造 shortcut。

反方向一般不成立：search 可以通过另一条 path 成功；某条 monotonic path 被破坏不代表 repair 必要。要把“哪些 path 必须保留”变成 workload-level lower bound，需要全局 query/path coverage，与 Theorem 1 暴露的远端状态问题一致。

### 6.2 Random-walk hitting time

SPatch 对 random-walk transition、Laplacian/hitting-time preservation提供 formal relation，并给特定 fixed-query greedy-equivalent clique repair。这些是强 constructive upper-bound/proxy 结果。但 hitting time 是随机过程统计量；若没有额外定理，不能推出 deterministic greedy/beam 一定找到真正最近邻。SPatch 也明确区分 hitting-time guarantee 与 softmax walk/greedy 到达正确 destination。

因此本报告没有把 hitting time 当 `P_success`。主定理直接计算 fixed greedy 的返回点。

### 6.3 Static graph-ANN theory

静态 theory 可在 iid/random geometric graph、特定维数增长与 edge construction 下证明 greedy/beam search 成功概率或复杂度。这类 theorem 可能支持未来 Route II restricted result，但不能直接给任意实际 Vamana graph 在单点删除后的 local repair lower bound；删除后的图分布和 repair action必须重新证明仍满足原假设。

## 7. Edge, adjacency-record and SSD-page boundary

Theorem 1 的 `0/1` separation首先是**额外 edge additions**，并在本特定构造中同时成立于 baseline deletion 之后的额外 edge-action count；它不是 total deletion cost、record cost或page cost。

删除 `v` 时，`p` 的 adjacency record 已因移除 `(p,v)` 被修改。在 `G_B` 中把 `(p,t)` 加入同一 record，可能不增加 distinct mutated adjacency-record count；两次逻辑 edge mutation也可能在一次 record rewrite 中完成。相反，若实现使用 tombstone、append-only delta、reverse-edge log 或不同 ownership，record cost会不同。因此：

```text
edge lower bound != distinct adjacency-record lower bound.
```

同理，一个 4 KiB page 可以同时承载多个 records/versions；也可以因 copy-on-write、WAL、alignment、compression 或 replication 把一次 record mutation放大为多次 I/O。Theorem 1 不提供 placement/layout，所以：

```text
edge lower bound != 4 KiB page-write lower bound.
```

更强地说，本构造在 eager incident deletion 下可能出现“edge optimum 不同、distinct record/page optimum 相同”。所以不能声称 pre-I/O local certificate failure 必然带来可测 SSD bytes gap。要进入系统映射，至少还需固定 record ownership、packing、deletion semantics、delta/WAL 与 durability contract，并给出可证伪的 edge-to-page prediction；B0 没有获得该授权。

## 8. Answers to the eight gate questions

1. **最小 repair 是否是 well-defined combinatorial optimization？** 是。固定有限图、search、distributions、degree、threshold 与允许的 edge actions 后，`AddOPT`（以及另行定义的 `MutOPT`）在有限 action space 上有明确定义。
2. **给定 `D_q` 后 optimum 是否仍需 global information？** 一般是。Theorem 1 在 `D_q,D_s` 都为已知 point mass 时仍需读取 local frontier 外的 search suffix，已经排除“只因 distribution 未知”的解释。
3. **local neighborhood 能否在所有 positive-optimum 实例上给非零 necessary lower bound？** 不能。对任意固定有限 `r`，Theorem 1 的 `0/1` pair迫使任何 sound nonnegative lower bound在这个不可区分 view 上退化为0；这不排除其他 local views 上存在正 witness。
4. **monotonic path、hitting time与 ANN success有什么 formal relation？** 前者可对特定 query/path提供 greedy success充分条件；后者对 random-walk transition/hitting statistics有 formal preservation。二者均不能未经额外 theorem 变成一般 deterministic ANN minimum-repair necessity。
5. **是否存在 local-view identical、global-necessity different 反例？** 是，第 4 节给出完整一维、maximum out-degree 2、fixed greedy构造。
6. **强假设 witness 是否覆盖实际 Vamana/DiskANN？** 本轮没有建立这样的 constructive witness；反例也未证明属于 Vamana builder-output family。这是 strategic STOP 的主要原因。
7. **edge bound 能否映射成 SSD I/O收益？** 当前不能；page granularity甚至可完全吞掉本构造的 edge gap。
8. **strongest prior 是否已有相同或更强 guarantee？** 没有发现相同的 general finite-radius local necessity impossibility。SPatch/Wolverine给更丰富的 sufficient repair guarantee；Escape Hardness给更接近 success 的 global/query-conditioned witness，但不替代本 local indistinguishability boundary。

## 9. Adversarial audit and limitations

### 9.1 Quantifier and proof risks checked

- **All finite radii：** `L=r+2` 对每个 finite `r` 单独构造实例，不声称一个固定有限图同时骗过所有半径。
- **No distance ties：** 每个实际 step 的候选距离严格不同。
- **Degree feasibility：** common graph maximum out-degree为2；`G_B-v` 加 `(p,t)` 后仍为2。
- **Zero-vs-one optimality：** `G_A` zero repair 已成功；`G_B` zero repair失败，deletion-only action不能创造到 `t` 的 path，而单次 addition可行。
- **Local-ball shortcut：** 差异 terminal edge 的所有 endpoints 与 source 都在 `r` 球外，新增 undirected route不会把它们拉进球内。
- **Same pre-deletion trace：** terminal差异不影响从 `p` 对 `q` 的选择，因为两图先严格选择 `v`。

### 9.2 Deliberate limitations

1. point-mass query/entry与允许任意 replacement edge使失败实例总可通过直连 `p->t` 在一次 addition内修复，所以 `0/1` 是此模型下有意选择的最小 separation，不是大 repair-cost lower bound。
2. graph 是一般 directed metric search graph；没有证明来自 Vamana/HNSW/alpha-RNG builder，也未保持其可能的 global monotonicity invariant。
3. theorem只关闭宣称 always-safe 且 complete/exact/instance-optimal 的 pure fixed-radius deletion-local pre-I/O oracle；它不关闭 conservative over-repair、one-sided sufficient certificate、Wolverine/SPatch式修复、query trace cache、global hardness state、learning heuristic或受限随机图 family上的 certificate。
4. theorem不提供 approximation algorithm、constructive witness、record lower bound或 I/O lower bound。
5. novelty结论只限本次 primary-work audit；若存在未收录的同构 distributed-locality lower bound，paper novelty仍需另做 formal novelty review。

### 9.3 Independent reviewer score

独立反方智能体按 theorem statement、construction、quantifiers、OPT、local-view与 systems overclaim 六项逐项核验，裁决为：

```text
PROVABLE AFTER WEAKENING / EXTRA DEFINITIONS
PASS-B at B0 gate only; KILL as standalone publishable idea; NO automatic B1.
```

它复算了全部坐标、strict-decrease trace、`0/1 AddOPT`、maximum out-degree与local-ball shortcut，未发现 construction 破绽；同时要求把结论严格限定为 pre-delete metric-labeled symmetrized bounded-radius view、mandatory cleanup之外的 extra additions，并删除对 record/page/Vamana 的外推。本报告已落实这些修正。

独立评分（10分制）：

| Dimension | Score | Reviewer rationale |
|---|---:|---|
| significance | 5 | 能关闭 pure bounded-radius exact/complete local oracle，但不关闭现有保守 repair |
| novelty | 4 | formal pair是新的明确边界，但Wolverine已预示全 affected-path识别的非局部性 |
| depth | 5 | 完整 indistinguishability proof，但gap仅为toy `0/1` |
| rigor | 9 after fixes | quantifier、view、AddOPT、degree与shortcut均闭合 |
| feasibility | 9 | 纯纸面构造可直接复核 |

reviewer特别指出：Wolverine与SPatch都可以在本 pair 上保守添加 repair edge，只是在 `G_A` 多修，因此 theorem 不与其 guarantee 冲突；Escape Hardness/NGFix使用 query-driven global defect state，也不属于被Kill的 pure deletion-local oracle。

## 10. Final gate decision

| Gate | Result | Reason |
|---|---|---|
| 完整不可区分实例 | `PASS` | 一维坐标、两图边集、query/entry、search与删除动作全部显式 |
| bounded-radius exact/complete local certificate不可行 | `PASS` | sound complete positive lower bound在这个 `0/1` view上被迫为0 |
| 明确额外 global state | `PASS` | 必须区分远端 search suffix/transfer state；可做多-gadget counting |
| Kill pre-I/O algorithm class | `PASS` | Kill宣称always-safe且optimal/complete的pure fixed-radius deletion-local skip oracle |
| 非 trivial verbal claim | `PASS` | fixed greedy output与 exact optimum均直接证明 |
| 实际 Vamana family覆盖 | `FAIL / OPEN` | 构造未证明为 builder output |
| record/page可证收益 | `FAIL` | edge gap可被同一 record/page吞没 |
| B1/system continuation | `NO` | gate只授权B0；理论负结果不足以形成实现候选 |

最终表述必须保持两层：

```text
B0 theorem gate: PASS-B in the stated general graph model.
Dynamic ANN repair implementation line: STOP; no B1 recommendation.
```

## 11. Resource and stop record

- 执行日期：`2026-07-18`（UTC+8）；
- wall-clock：小于1天，低于1–2天上限；
- 新增持久空间：仅本 Markdown 报告与 gate/conversation文本，远小于1 GiB；
- experiments/builds/traces/instrumentation/prototype：`0`；
- active experiment process/tmux：本轮未创建；
- ContractANN、A0候选、Write Reducibility、Semantic Repair Efficiency、matched-R、multi-NVMe与RAG：均未恢复。

B0 到此停止，等待 Gpt 对 `PASS-B(general) / no-B1` 边界进行审议。
