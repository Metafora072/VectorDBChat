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
