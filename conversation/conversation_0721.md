**PZ(00:02:21)**:
Claude 提出的新方向，即复合查询的方向我挺感兴趣的，让 Claude 做了一轮调研，空间还比较充裕，Gpt 你评估下，不要过分严格，只要有实际场景，有自圆其说的故事，有充足动机，有充足设计点，能取得效果就没问题，如果有机会，我们可以一起讨论构思系统设计

**Gpt(00:04:41)**:
这个方向值得继续推进，我会给出 GO。

但立项时不要把题目写成宽泛的“支持复合查询”或“优化 filtered ANN”。这个大方向已经比较热，单纯增加 AND / OR / range 支持，很容易被已有工作覆盖。

更合适的收敛方式是：

面向动态 SSD 驻盘图 ANN 的自适应复合查询执行系统。

核心研究对象不是“能不能执行复合谓词”，而是：

当一个向量查询同时包含多个属性谓词，而且谓词选择率、谓词间相关性、谓词与向量空间的相关性不断变化时，系统如何在查询执行过程中动态选择和切换过滤、图遍历与 SSD 读取策略？

这个版本具有真实应用、清晰矛盾、充足设计空间，也很容易构造出明显效果。我认为它比单独研究抽象的 distribution shift 更容易形成一个完整系统故事；distribution shift 可以作为复合查询系统的重要 workload 维度。

**PZ(00:05:47)**:
我们不能做成通用的，这样就很启发式，我们要锚定一些典型复合查询，做设计优化，接下来我觉得可以先做个整体研究，把现在场景需求中的复合查询都统计一下，看看有哪些复合查询，其典型程度如何，会在哪些实际场景出现，针对这些复合查询，现有 baseline 的效率如何，相关的优化论文/工作对其的提升如何，还存在什么问题，这个表如果列出来了，我们的思路就会更清晰些，也能知道接下来做什么，你觉得呢

**Gpt(00:12:18)**:
我赞成先做一轮开放式复合查询研究，暂不急着收敛到具体查询或系统机制。详细的场景需求地图、基础执行方案、现有论文/系统能力矩阵、候选设计空间和讨论任务已整理到 [`Gpt/share/compound_query_research_map.md`](Gpt/share/compound_query_research_map.md)。

请 Claude 和 Codex 分别从真实场景、典型查询族、现有工作覆盖、SSD 驻盘图瓶颈和可验证设计空间展开，并在给出独立判断后互相评议。当前阶段先扩开思路，不做严格 KILL。

**Claude(00:24:10)**:
完成 Gpt 研究地图中 12 个查询族的独立分析。详细报告：`claude/share/2026-07-21/compound_query_analysis_claude_0721.md`。

**最重要的新发现：ACL/权限感知向量搜索在 2025–2026 突然出现了 3 篇独立工作，但全部是内存方案。**

1. **HoneyBee** (SIGMOD 2025, Georgia Tech)：RBAC 动态分区 + HNSW，13.5× 低于行级安全延迟，纯内存
2. **Veda/EffVeda** (arXiv 2605.01342, 2026)：Access-aware lattice 索引，纯内存
3. **Policy-aware Vector Search** (arXiv 2606.19803, June 2026)：Vision paper，形式化了 FGAC 问题，明确指出 FGAC ≠ 传统 filtered ANN，无系统实现

另外发现 **Phase Transition 论文** (arXiv 2606.16341)：证明 filtered ANN 策略选择存在相变，选择率估计误差 → plan regret 集中在相变边界。为系统设计提供原则性理论基础。

**12 个查询族排序后的判断：**

- **排除 5 个**：3.7 (地理，偏离主线)、3.9 (代码搜索，缺 workload)、3.11 (dense+sparse 融合，过广)、3.12 (relational join，通用 QO)、3.6 (多范围，独立价值低)
- **降级 2 个**：3.1/3.2 (多标签 AND/OR，已充分覆盖)、3.3 (类别+单范围，novelty 不够)
- **保留 3 个主候选**：
  1. ⭐ **3.5 Tenant+ACL+time/type** — 场景 A 级，学术热度上升（SIGMOD 2025 已接受），SSD=零，ACL 独特性质（高基数、安全语义、碎片化、动态）提供充足 novelty
  2. **3.4 多类别+范围** — 场景 A 级，内存方案密集但 SSD 仍有空间
  3. **3.10 日志时序** — 结构清晰（append-only+分段），但可能被认为是工程组合
- **3.8（静态+动态属性）合并进 3.5**：ACL 本身就是"极度动态属性"，3.8 的核心问题自然成为子贡献

**推荐主攻方向：3.5 (Tenant+ACL+time/type)**，收敛后的论文方向为 **SSD-Resident Permission-Aware Vector Search**。理由：
- 故事不需要论证（enterprise RAG + 权限 = 刚需）
- ACL 与普通标签本质不同（高基数、碎片化路由、安全语义、动态更新）→ 不是 filtered ANN 特例
- SSD 上有 4 个特有技术挑战（ACL metadata 无法全部内存化、碎片化图遍历、权限更新写放大、安全-性能张力）
- HoneyBee (SIGMOD 2025) 是天然 baseline → 有 head-to-head 比较对象
- PZ 的 DGAI/OdinANN + multi-NVMe 完美匹配

请 PZ 和 Gpt 评估这个收敛方向。

**Codex(00:39:21)**:
我完成了独立 prior/workload 审查与两路 red-team，详细报告见 `codex/share/2026-07-21/compound_query_independent_audit_0721.md`。结论是保留 ACL 场景，但当前只能 `HOLD-FULL-SYSTEM / GO-BOUNDED-PREFLIGHT-DESIGN`：Claude 将 HoneyBee 误写为 SIGMOD 2025，实际为 SIGMOD 2026；Curator 已覆盖 ACL、Bloom/shortlist 与 grant/revoke，HoneyBee 也已有权限更新；GateANN 已在 SSD 上支持 conjunction/range/multi-label 并实现非匹配节点内存 tunneling；PipeANN-Filter 已覆盖 Bloom 粗筛加精确验证。因此“SSD ACL=零、动态更新=零”及对应机制 novelty 均不能成立。ACL 安全语义也需纠正：最终 authorization 的 false positive 才可能泄露，false negative 损害 recall；Bloom 只能粗筛，返回前必须 exact verify。

残余机会收窄为严格 DRAM 上限下的 out-of-core policy metadata、权限 churn 的 SSD 写放大，以及索引与权限状态的 freshness/snapshot 一致性。`tenant+ACL+time/type` 目前只证明了 policy-aware 场景，尚未证明 time/type 带来不可分解的复合查询问题；必须用 ACL-only 作成对控制。若坚持真正的 compound predicate，KHI 已证明 multi-attribute range 是独立活跃查询族，应升为第一备选，但同样需先找 SSD 页级 I/O residual。

请 Gpt 二选一签发下一轮：A）policy workload + strong-baseline feasibility preflight，只闭合 workload、100M/1B 内存外推、baseline 可复现性与 A0 成本；B）转向 multi-attribute range on SSD 做同级 preflight。当前未修改 DGAI/OdinANN、未下载数据、未启动实验。建议首轮若获批仍限定 1M、4 小时、10 GiB 数据盘新增、24 GiB RSS，全部大工件放 `/dev/nvme8n1`。

**PZ(01:41:02)**:
Codex，你要明白有平行工作不代表我们不能做，如果已有工作还有未解决的问题，或者我们可以做一个更好的设计，达到更好的效果，也是可以做的。Claude，请分析 Codex 此轮的推进结果，看看能不能先确定一个大致的方向。是做 ACL 场景，还是考虑 3.4 多类别或是其它方向。

**Claude(01:51:57)**:
分析了 Codex 的审查结论。Codex 的 7 项事实纠错全部成立，我逐条接受（HoneyBee 是 SIGMOD 2026 非 2025、漏检 Curator、安全语义写反等）。"SSD ACL=零、动态更新=零"的表述确实过强，已修正。

但 Codex 的结论过于保守。关键区分：**机制级别的 novelty vs 系统级别的贡献**。

Codex 证明了 Bloom 预检、graph tunneling、grant/revoke、multi-predicate conjunction 等单个机制不是新的。但这些机制**从未在同一个 SSD 系统中被整合解决**：
- HoneyBee / Curator / Veda：有 ACL，但**纯内存**
- GateANN：有 SSD + multi-predicate，但 **63 GB/100M 内存**，无 ACL 语义
- PipeANN-Filter：有 SSD + Bloom，但**无 ACL、无动态更新**

没有系统同时满足：SSD-resident + ACL-aware + bounded DRAM + permission churn。

Codex 自己也识别了三个真正的残余空间：(1) 严格 DRAM 上限下的 out-of-core policy metadata；(2) 权限 churn 的 SSD 写放大；(3) 撤权可见性/snapshot 一致性。**这三个问题足以支撑系统论文。**

**方向判断：仍然推荐 ACL 方向**，但修正 framing：
- **旧 framing**（已否定）："SSD ACL = 零，所有机制新"
- **修正 framing**："现有 ACL-aware 系统全是内存，现有 SSD filtered ANN 不考虑 ACL 特殊需求（策略元数据超 DRAM、权限 churn 写放大、撤权可见性延迟）。我们设计首个在严格 DRAM 预算下支持 ACL 感知的 SSD 向量搜索系统"

ACL 优于 3.4（多类别+范围）的原因：
1. 故事冲击力：安全 > 性能优化
2. 差异化清晰度：ACL 与普通 label 有明确性质差异，不会被审稿人说"只是 GateANN 的增量改进"
3. Baseline 更 clean：HoneyBee（内存）vs 我们（SSD），而非 GateANN（SSD 但 63GB）vs 我们（同样 SSD）
4. 3.4 竞争更拥挤：KHI 已做多属性范围 2.46-16.22× 加速

接受 Codex 的质疑：ACL+time/type 的"复合"贡献暂不强调。主贡献锚定 ACL-on-SSD 系统，time/type 作为附带支持。

详细分析：`claude/share/2026-07-21/compound_query_direction_decision_0721.md`。建议 PZ 确认方向后，先做 design-level 可行性分析（GateANN DRAM 外推、HoneyBee SSD 空间/更新放大估算、权限 churn rate 真实数据），再进入 preflight。

**Codex(02:15:29)**:
我接受 Claude 关于“保留 ACL-on-SSD 大方向、先做 design-level feasibility”的主判断，并用 `research-refine` 加三路独立审计把方法推进到可审议门禁；详细结论见 `codex/share/2026-07-21/permission_aware_ssd_design_feasibility_0721.md`，完整评审历史见 `codex/work/2026-07-21/policy_ssd_refine/refine-logs/`。

先纠正一个会改变 framing 的资源事实：GateANN 的 63 GiB 是 **1B/Rmax=16 neighbor store 单项**，不是 100M；其 100M artifact 约 17 GiB。当前机器为 251 GiB DRAM、约 238 GiB available，因此不能以“本机装不下”立题。64 GiB 只能作为明确的 deployment cost cap，用 cgroup 对所有 baseline 公平约束。当前数据盘 `/dev/nvme8n1` 尚有约 759 GiB 可用。

外部方法审查评分为 **6.275/10，RETHINK**。它不否定 ACL 问题：object-side grant 的 stale-negative 可能损害 authorized recall，revoke 的 stale-positive 可由 exact authorization 兜底；它否定的是当前机制已经成立。`PipeANN-Filter + Curator semantics + Zanzibar/RocksDB MVCC + graph-page-prefix delta` 已能自然获得 WAL、page-local lookup、cache、batching 与 compaction。若 page-addressed delta 只把 RocksDB key 从 node 换成 graph page，即使性能更好也很难构成独立机制贡献。

因此我没有启动代码或实验，而将下一步收紧为三道低成本门禁：

1. `G0 Source witness`：在真实 ANN 代码中定位 approximate predicate 的剪枝点，并用最小确定性图证明 stale object-side grant 会造成 exact recheck 无法恢复的 recall loss；失败则 `KILL-NO-ANN-WITNESS`。
2. `G1 Strong natural baseline`：允许 RocksDB 使用同样的 graph-page prefix、cache、WAL、batching、durability 与 compaction，禁止 node-keyed 弱基线。
3. `G2 Unique property`：只寻找一个强自然组合无法获得的、可形式化的物理性质，例如把 policy overlay lookup 与已有 graph-page I/O 合并并给出额外 I/O 上界；若只是 schema/cache，或决定性指标差异均小于 15%，则 `KILL-RENAME-MVCC-LSM`。

同时把 scope 收紧为改变对象侧 approximate predicate 的 grants/revokes；user-role/hierarchy 更新走 query-side closure。MVCC、WAL、lazy revoke、snapshot token、exact verifier 都是复用 plumbing，不再列贡献；`time/type` 只作 workload 支持。

请 Gpt 审阅并决定：是否批准我只准备 G0/G1 的源码/API 审计方案与逐项时间、空间预算。获批前不修改 DGAI/OdinANN、不下载数据、不运行实验；后续 preflight 上限仍为 4 小时、10 GiB 数据盘新增、24 GiB RSS，禁止系统盘大写入。

**Claude(02:18:36)**:
分析 Codex 的处理。先说结论：**Codex 的事实纠错继续扎实，但战略层面偏离了 PZ 的问题**。PZ 问的是"能不能先确定一个大致的方向"，Codex 的回答是对一个具体机制（page-addressed grant delta）的 kill-or-go 审查。这两个问题不在同一层级。

**Codex 做得好的：**

1. **GateANN 内存纠正**：63 GiB 是 1B/Rmax=16 neighbor store，不是 100M。100M 约 17 GiB。这确实改变了"内存放不下"的论证基础——我之前用了错误数字。

2. **外部审查（6.275/10 RETHINK）**：审查质量非常高，P0 修改项（强基线等价性、真实剪枝点 witness、线性化协议）都是系统论文真正需要回答的问题。

3. **Scope 收紧**：把贡献限定为"object-side permission grants that change approximate predicates on SSD graph records"，排除 MVCC/WAL/lazy revoke 等 plumbing，这是正确的纪律。

**我认为有问题的：**

1. **过早锁定机制再 kill**：Codex 拿到我"ACL-on-SSD"的方向建议后，立即构造了一个具体的机制（page-addressed grant delta），然后证明这个机制可能不够新，然后设计 kill gate。但我们还没选定具体机制！"page-addressed grant delta"只是一种可能的实现方案。外部审查给出 Contribution Quality 4.0/10，但这针对的是这个特定方案，不是整个方向。Problem Fidelity 8.5/10 说明问题本身被认可。

2. **"自然组合"baseline 是理论构造**：Codex 指出"PipeANN-Filter + Curator semantics + Zanzibar/RocksDB MVCC + graph-page-prefix delta"可以自然组合。这在逻辑上成立，但现实中没人做过这个组合。之所以没人做，本身可能说明整合这些组件需要解决非平凡的工程和系统问题——这也是研究贡献的来源。系统论文的价值经常在于"正确地组合已有技术解决一个实际问题"，不一定需要发明新数据结构。

3. **KILL 门槛过低**：G2 要求"决定性指标差异均 ≥15%"，否则 KILL。但 15% 是人为阈值，在方向探索阶段设定这样的 kill 条件限制了设计空间探索。应该先理解问题的 SSD I/O 特征，再决定什么样的优化是合理的。

**我的综合判断：**

| 层面 | 状态 |
|------|------|
| **方向（ACL-on-SSD）** | ✅ 两方都认可问题真实（Problem Fidelity 8.5/10），继续 |
| **具体机制** | ⚠️ 不应锁定为"page-addressed grant delta"，需要更多设计探索 |
| **下一步** | 应该做 design-level 的问题理解（ACL 碎片化如何影响 SSD 图遍历、权限更新的真实 I/O pattern），而不是直接 kill-or-go 一个具体方案 |

**建议的推进方式：**

回到 PZ 的原始问题——先确定方向。我建议：

1. **方向确定为 ACL/权限感知 SSD 向量搜索**。这一点两方共识。
2. **不立即设计具体机制**。先做问题理解：
   - ACL 碎片化对 SSD 图遍历的真实影响（用小规模模拟）
   - 现有 SSD filtered ANN（GateANN/PipeANN-Filter）在 ACL 场景下的实际表现和瓶颈
   - 权限更新在 SSD 上的真实 I/O pattern
3. **理解问题后，再设计机制**。可能的贡献不一定是"page-addressed delta"——也可能是 ACL-aware 图布局、基于权限结构的分区策略（类似 HoneyBee 但在 SSD 上）、或者全新的路由策略。
4. **Codex 的 G0（source witness）可以先做**——确认 stale-negative 在真实 ANN 代码中确实导致不可恢复的 recall loss。这是方向级别的 falsification，不是机制级别的。

**Gpt(03:00:57)**:
我同意 Claude 对层级的区分，也保留 Codex 的事实纠错与 G0/强基线审计。当前批准的是 **ACL/权限感知 SSD 向量搜索的问题域**，不是 page-addressed grant delta；`time/type` 暂只作为 workload，不再强调通用复合查询。

下一轮先做三轴 characterization：授权碎片化对图导航的影响、policy metadata 在有限内存下的访问成本、object-side grant/revoke 的真实写放大。完成后只选择一个主轴继续，避免把查询、元数据和更新三个问题一起包装成工程集成。详细裁决与任务见 [`Gpt/share/2026-07-21/permission_aware_ssd_direction_decision_0721.md`](../Gpt/share/2026-07-21/permission_aware_ssd_direction_decision_0721.md)。

批准 Codex 准备 G0 source witness、强自然 baseline 审计及逐项预算；暂不采用固定 15% KILL 阈值，也不启动完整系统实现或大规模实验。

**Claude(03:09:37)**:
评估 Gpt 裁决：没有过分或不妥当之处。三轴 characterization（查询碎片化/policy metadata/update 写放大）覆盖了核心问题空间，Q/M/U 路线分叉要求只选一个主轴避免系统集成包装，退出条件明确。两点注意：(1) P0 工作量偏大，建议先做轴 A（碎片化对图遍历的影响）作为方向级 falsification；(2) 1M 数据可能被 page cache 吸收，需 direct I/O 或 drop caches 确保 SSD 真实性。

Claude P0 任务已拆分（C1-C5），Codex 建议优先 X1（G0 source witness）和 X2（artifact 复现）。详细评估与任务计划见 [`claude/share/2026-07-21/gpt_ruling_evaluation_0721.md`](../claude/share/2026-07-21/gpt_ruling_evaluation_0721.md)。

Codex，请开始你的 P0 任务。建议优先级：X1（G0 source witness）> X2（artifact 复现路径）> X4（强自然 baseline 清单）> X3/X5。产出为设计和预算文档，不直接运行实验。具体要求：

1. **X1 G0 Source Witness**：在 GateANN 或 PipeANN-Filter 源码中定位 approximate predicate 的剪枝点，构造最小确定性图证明 stale object-side grant 导致不可恢复的 authorized recall loss。这是方向级 falsification。
2. **X2 Artifact 复现**：GateANN (`github.com/GyuyeongKim/GateANN-public`) 和 PipeANN (`github.com/thustorage/PipeANN`) 的编译/运行步骤、环境要求、1M 规模下的时间和空间估算。
3. **X4 强自然 Baseline**：列出 RocksDB + graph-page-prefix key 能做的所有事（WAL/cache/Bloom/batching/compaction/snapshot），这是后续任何机制必须击败的对照。
4. **X3/X5**：1M simulator 接口 spec + 每项 instrumentation 预算。

边界：<=4h 运行、<=10 GiB 数据盘新增、<=24 GiB RSS，禁止系统盘大写入，不修改 DGAI/OdinANN 主路径。

**Codex(03:28:32)**:
已按裁决完成 X1-X5 的只读设计与预算，并用 `experiment-plan` 将其收敛为 claim-driven P0；未下载、编译、运行实验，也未修改 DGAI/OdinANN/PipeANN 源码。总览见 `codex/share/2026-07-21/permission_aware_ssd_p0_codex_plan_0721.md`；G0 与 artifact/baseline/budget 分别见同目录的 `permission_aware_ssd_g0_source_witness_0721.md`、`permission_aware_ssd_artifact_baseline_budget_0721.md`。

**X1 结论：`PASS-G0-CONTROL-FLOW-WITNESS / HOLD-END-TO-END-DYNAMIC-ACL-REPRODUCTION`。** 本机 PipeANN commit `9e7a193...` 的 `IN_FILTER` 在 node page read 前用 approximate predicate 将邻居分入主 pool 或有限 connectivity pool；false 节点只有通过 density + distance-band 门禁才会作为 bridge 提升。已构造与真实控制流一致的三节点 fixture：newly authorized true top-1 因 stale approximate false 未获 bridge promotion、从未读页，decoy exact-pass 后查询终止，因此最终 exact verifier 无法恢复。`PRE_FILTER` 也有候选遗漏路径；`POST_FILTER` 不受该 approximate stale 影响，必须作 negative control。

这不是 PipeANN 已有动态 ACL bug：其接口本来要求 approximate predicate 无 false negative，且公开 API 尚未证明支持对既有对象做 snapshot-aware grant/revoke。G0 证明的是未来 ACL 系统必须维护 grant publication invariant，而不是批准任何具体维护机制。

**X2 结论：复现路径可设计，但当前 artifact 身份不闭合。** 本机没有 GateANN；PipeANN 多个副本均为同一官方 commit 的 dirty worktree，已有 filtered binary 也不能作为 clean baseline。SIFT1M 数据、query 和普通 GT 已在 `/dev/nvme8n1`，但 ACL `.spmat`、query binding 和 authorized GT 不存在。1M 只可称 artifact-path/mechanism preflight，不能宣称复现 GateANN/PipeANN-Filter 论文结果。

另有关键 I/O 边界：PipeANN graph file 使用 `O_DIRECT + io_uring`；但 attribute index 当前是 buffered fd，1M policy metadata 会被本机大页缓存吸收。因此轴 A 的 graph-I/O 可做真实 SSD 证据，轴 B 暂只能报告 analytical/cold-warm boundary；全局 `drop_caches` 和 attribute read-only direct-I/O patch 都需二次审议。

**X3/X4：** 已冻结独立 simulator/replay 接口，并严格区分逻辑 I/O 与设备 replay；强自然 baseline 包含 RocksDB WAL/WriteBatch/snapshot、page-prefix key/Bloom、cache、MultiGet、compaction、direct I/O 与相同 exact verifier/refill。当前未确认本机有可用 RocksDB runtime，所以这里只是能力/公平性审计，不写成实测结果。

**建议下一审批包只做 PipeANN G0 + 轴 A/Q：** identity/hash preflight、A1/A5 smoke、A1-A5 matched-selectivity characterization、代表 cell 的 direct graph-I/O replay 和总结。预算为 200 分钟 + 40 分钟 guard，操作 soft line 为 3h45、20 GiB RSS、8.5 GiB 数据盘；hard line 仍为 4h、24 GiB、10 GiB。GateANN、`R_dense=512/1500`、RocksDB U 轴实测与全局 `drop_caches` 均不在首包。

请 Gpt 审阅是否批准该首包。若批准，我再准备独立工作目录、输入 manifest、命令级 preflight 和 stop hooks；在下一次明确执行授权前仍不运行。

**Gpt(04:10:18)**:
审阅通过。Codex 的 G0 已证明 stale object-side grant 在 PipeANN `IN_FILTER/PRE_FILTER` 的真实控制流中可能造成 exact verifier 无法恢复的 authorized recall loss；但该 publication invariant 只视为正确性前提，不作为当前贡献。

批准首包按 `M0 clean identity → M1 G0 fixture → M2 1M smoke → M3 Axis A/Q` 串行执行，详细裁决见 [`Gpt/share/2026-07-21/permission_aware_ssd_p0_execution_ruling_0721.md`](../Gpt/share/2026-07-21/permission_aware_ssd_p0_execution_ruling_0721.md)。M3 必须等待 Claude 冻结 workload manifest；A5 仅作压力测试，若差异只出现在 A5，不能确认 Q 路线成立。

保持 4h/24 GiB/10 GiB hard limit，不运行 GateANN、RocksDB U 轴、`R_dense=512/1500` 或全局 `drop_caches`。Codex 在执行前补充最终命令、写入路径与 stop hooks 后即可开始。

**Codex(04:25:10)**:
已完成 M0–M2 的命令级 preflight、data-disk 写路径与双层 stop hooks，详见 `codex/share/2026-07-21/permission_aware_ssd_p0_execution_manifest_0721.md`；执行夹具位于 `codex/work/2026-07-21/permission_p0_execution/`。所有大工件唯一写入 `/home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01`，每阶段由 systemd `MemoryMax=24G/MemorySwapMax=0/ProtectSystem=strict` 与进程树 watcher 共同约束，共享 soft/hard line 仍为 `3h45/4h、20/24 GiB、8.5/10 GiB`。

红队核验后，M0–M2 可闭合，但我将 artifact 差异明确降格：clean official commit 需要冻结的 `cblas.h` ABI header、regular-uring capability probe + `PIPEANN_FORCE_URING` 小补丁，以及 `USE_TCMALLOC=OFF`；这些都是本机 build adapter/allocator deviation，M2 只做 SIFT1M build 与 16-query all-authorized path smoke，不称论文性能复现。M1 是四节点、六格 `PRE/IN/POST × fresh/stale` correctness fixture，不称物理 SSD 实验。

M3 继续 `HOLD`，除 Claude manifest 未到外还有两个需提前裁决的控制变量冲突：`IN_FILTER` 需要冻结有界非零 `R_dense`；且四种 ACL 分布必须保持相同 adjacency/page map，不能把各自重建图的差异归因于 policy structure。请 Claude 提交 machine-readable manifest；请 Gpt 在其到位后裁决是否批准 `R_dense=128` 单-index受限 smoke，以及“固定图、仅替换 policy payload”的 adapter。M0–M2 将按已批准顺序启动，任一 gate 失败立即停，不会自动越过到 M3。

**Codex(04:48:28)**:
M0–M2 已执行完成并全部 PASS，完整身份、结果和限制见 `codex/share/2026-07-21/permission_aware_ssd_p0_m0_m2_results_0721.md`。共享 guard 从首次启动至 direct-I/O trace 完成累计 18.06 分钟；所有尝试最高 RSS 4.18 GiB，run-root 峰值 1.146 GiB，远低于 24 GiB/10 GiB，所有大工件均在 `/dev/nvme8n1`。

M0 冻结了 official `9e7a193...`、输入/adapter/CMake/binary hashes，并闭合 host liburing/BLAS；`USE_TCMALLOC=OFF` 与 host-compatible liburing 2.5 include 均记录为 artifact deviation，不称论文复现。M1 的 `PRE/IN/POST × fresh/stale` 六格和 5 项 assertion 全通过。M2 完成 SIFT1M filtered build 与 16-query all-authorized smoke：planner 全部选择 POST，Recall@10 在 L=10/20/40 分别为 67.5%/89.4%/99.4%；由于只有 16 query，这些 QPS/latency 不作为性能结论。短 trace 已确认 graph fd 为 `O_DIRECT`、实际发生 `io_uring_setup/enter`，graph I/O size 为 4096 bytes；attribute I/O 仍是 buffered。

有一项必须透明保留：systemd 汇总的 `IOReadBytes/IOWriteBytes` 为 0，无法与应用逻辑 `AvgIO` 闭合，所以本轮不报告物理 bytes/query 或 SSD 吞吐，只能确认 direct graph path。M3 继续 HOLD：请 Gpt 审阅 M0–M2 是否通过进入下一 gate，并裁决 `R_dense=128` 与固定图/仅替换 policy payload 两项；请 Claude 提交冻结 workload manifest。Codex 会在 M3 前先修正 cgroup/block-layer physical I/O 计量，不会直接开跑。
