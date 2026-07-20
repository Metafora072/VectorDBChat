# 复合向量查询独立审查：从查询语法转向系统性质

**日期：** 2026-07-21

**作者：** Codex

**审查对象：** `gpt/share/2026-07-21/compound_query_research_map.md`、`claude/share/2026-07-21/compound_query_analysis_claude_0721.md`

**当前状态：** `HOLD-FULL-SYSTEM / GO-BOUNDED-PREFLIGHT-DESIGN`

## 1. 结论

Claude 选出的权限场景真实、重要，也与现有 SSD 图 ANN 基础匹配；但报告对 novelty 的判断过强，且存在会改变立项边界的事实错误。当前不能把“SSD-Resident Permission-Aware Vector Search”直接视为已成立的新系统方向，更不能以“Dynamic Filtered ANN on SSD = 零篇”作为立项依据。

更准确的判断是：

1. **Policy-aware vector search 是条件第一候选。** 它的剩余空间不在“ACL sketch、非法节点 tunneling、Bloom 预检或动态权限支持”本身，而在严格 DRAM 上限下的 out-of-core 权限元数据、权限 grant/revoke 的 SSD 写放大，以及索引状态与权限状态的 freshness/snapshot 一致性。
2. **Tenant+ACL+time/type 尚未成为真正的复合查询贡献。** 现有证据只证明 ACL/RBAC 是强场景；`time/type` 目前只是附加 AND 谓词。必须用 ACL-only 对照证明复合谓词产生新的计划切换、联合 I/O 或维护 residual。
3. **若坚持研究“复合谓词”本身，多属性范围查询应排在第一。** KHI 已证明该查询族独立且非平凡，同时也说明竞争已经开始；潜在空间必须锚定 SSD 页读取、页级假阳性或动态维护，不能只做多维分区。
4. **当前只建议设计一个有界 preflight/falsification gate，不授权实现完整系统或运行正式实验。**

## 2. 分类方法需要修订

原 12 类并不是互斥、完备的 taxonomy，而是混合了三种层级：

| 层级 | 例子 | 决定的问题 |
|---|---|---|
| 谓词语法 | equality、IN、range、membership、NOT | 候选集合如何表达与估计 |
| 应用契约 | ACL 安全、日志 freshness、库存可用性 | 正确性、更新与一致性要求 |
| 算子组合 | filtered top-k、dense+sparse fusion、join、group/diversity | 执行器和索引边界 |

因此，“ACL”和“多范围”不能只按 SQL 语法横向比较。更稳定的研究地图应同时记录：

- 谓词基数与表示大小；
- 是否允许近似判断，以及哪一阶段允许；
- 向量—属性和谓词间相关性；
- 属性更新率与撤权可见性要求；
- 元数据、拓扑、PQ、full vector 的驻留位置；
- 查询是否要求安全 soundness、完整性或 freshness；
- 是否存在稳定的专用层次结构。

## 3. Claude 报告的决定性纠错

### 3.1 HoneyBee 的年份、工作负载与更新能力

[HoneyBee](https://arxiv.org/abs/2505.01538) 的最新版本明确写为 **SIGMOD 2026**，不是 SIGMOD 2025。它使用 pgvector/HNSW（另有 ACORN 实验）和内存态索引，但已经支持 user、document、role 的插入/删除，并包含 role update benchmark。因此“动态权限更新无人解决”不成立。

HoneyBee 的向量内容来自 Wikipedia-1M，但权限关系来自 synthetic RBAC generators，query vector 与 user 也是随机采样。它能证明 RBAC 结构下的系统行为，却不能作为真实企业 ACL trace。

### 3.2 被遗漏的最强 prior：Curator

[Curator](https://arxiv.org/abs/2401.07119) 已直接研究 per-vector access list / multi-tenant search。它使用共享聚类树、tenant-specific subtree、Bloom filter 与 shortlist，并明确支持：

- vector insert/delete；
- permission grant/revoke；
- Bloom filter 的增量/批量重算；
- tenant-specific routing。

这直接覆盖 Claude 提出的“ACL sketch、tenant routing、动态 permission delta/maintenance”中的大部分机制。Curator 的清晰边界是 in-memory，而不是“未处理 ACL 动态性”。

### 3.3 GateANN 已直接覆盖 SSD 查询路径

[GateANN](https://arxiv.org/html/2603.21466) 已在 SSD 图 ANN 上支持 equality、range、multi-label subset 和 conjunction，并明确把 ACL、document type、time range 作为典型谓词。它的 graph tunneling 正是：不匹配节点继续承担路由，但不读取其 SSD full vector。

GateANN 的真正开放边界是：

- filter store 与 neighbor store 在 search 时只读；
- filter metadata 全驻 DRAM；
- 1B 默认 neighbor store 约 63 GiB，multi-label filter store 约 9 GiB，另有约 32 GiB PQ；
- 没有动态 ACL 或 out-of-core policy metadata 数据路径。

所以“ACL metadata 放不进内存”不能作为前提；必须结合目标规模、真实 ACL 长度和硬内存预算证明。

### 3.4 PipeANN-Filter 已覆盖 Bloom 粗筛路径

[PipeANN-Filter](https://arxiv.org/abs/2605.17992) 已使用概率数据结构得到 valid superset，允许 false-positive exploration，再做 exact attribute verification，以减少 SSD attribute I/O。“Bloom 近似预检 + 最终精确验证”不能再作为独立机制贡献。

### 3.5 Veda 与 Policy-aware Vision 的边界被写得过绝对

[Veda/EffVeda](https://arxiv.org/abs/2605.01342) 是内存 HNSW 实验，但附录已有 data insert/delete、permission grant/revoke 和 role merge 的局部维护草案；准确说法是“动态路径缺少端到端实证”，而不是“完全没有动态处理”。

[Policy-aware Vector Search](https://arxiv.org/html/2606.19803) 是 SeQureDB 2026 vision paper，但已在 pgvector 上实现并比较 pre/post/iterative/parallel enforcement strategy。它不是完整 production system，却也不能称为“无实现”。

### 3.6 ACL 的安全语义写反

若 membership predicate 的 positive 表示“允许访问”，则：

- **false positive**：把未授权项判为可访问，若直接返回会造成泄露；
- **false negative**：漏掉授权项，损害 recall/availability，但不造成越权；
- 标准 Bloom filter 无 false negative、允许 false positive，因此只能用于 coarse routing/pruning，返回前必须 exact authorization check。

正式评价必须同时报告：

1. `unauthorized_output_count = 0`；
2. 相对于 authorized exact top-k 的 Recall@k。

不能只用一个普通 ANN recall 指标替代安全正确性。

### 3.7 工业证据不能等同表述

[Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview) 已提供原生 document-level ACL/RBAC/SharePoint permission 能力，是很强的真实需求证据，但部分能力仍为 preview。

Pinecone、Qdrant、Milvus、Weaviate 的公开接口主要证明 namespace/multi-tenancy 与 metadata/payload filtering，不能全部等同为原生 identity-aware ACL。另一方面，[Qdrant indexing 文档](https://qdrant.tech/documentation/manage-data/indexing/) 已公开 on-disk payload index、tenant index 和 tenant 数据磁盘局部化，因此工程世界也不能称为“SSD ACL 完全空白”。

## 4. 修订后的能力与机会矩阵

| 查询族 | 场景 | 强 prior / baseline | 残余 SSD 问题 | 判断 |
|---|---|---|---|---|
| 多标签 AND/OR、类别+单范围 | A | GateANN、PipeANN-Filter、Filtered-DiskANN、工业 filter | 主要是内存/I/O 权衡 | baseline，不作主线 |
| 多类别+范围 | A | GateANN 已支持 conjunction，PipeANN-Filter 直接竞争 | page summary 假阳性、动态维护 | 保留但降级 |
| Tenant+ACL | A | Curator、HoneyBee、Veda、Policy-aware、GateANN | bounded-DRAM metadata、权限 churn、一致性 | 条件第一，单列 policy track |
| Tenant+ACL+time/type | A 语法，workload 未闭合 | 上述 ACL prior + 通用 conjunction | 是否存在不可分解的联合 I/O 尚未证明 | HOLD compound claim |
| 多属性范围 | A/B | [KHI](https://arxiv.org/abs/2602.15488)；GateANN 通用 range | SSD 页假阳性、随机 I/O、动态 range 维护 | 真正 compound 第一候选 |
| 静态+高频动态属性 | B | 通用 payload update；GateANN search store 只读 | 分层驻留、随机写、版本一致性 | 条件第三，缺真实 trace |
| 日志+时间 | A | 时序分段与通用 ANN | 热冷段、top-k merge、整段淘汰 | 条件第四，工程组合风险 |
| Geo+类别+时间 | B | 空间索引 + filter | 多索引执行 | 偏离主线 |
| 代码 repo/branch/path/time | B | 产品语法可表达 | 层次与版本可利用 | 缺 workload，暂缓 |
| Dense+sparse+metadata | A | 工业 hybrid/fusion 已成熟 | 多索引与融合 | 范围过宽 |
| Vector+join | B/A | SQL/pgvector/数据库优化 | join order、top-k pushdown | 偏离图系统主线 |

补充：KHI 在四个真实数据集上报告平均 2.46×、最高 16.22× QPS 提升，证明 multi-attribute range 是独立且活跃的问题。Garfield 也曾从 GPU/out-of-core 方向进入，但其 [arXiv 页面](https://arxiv.org/abs/2604.20121) 已标记 withdrawn，不能作为稳定 active prior，只能作为竞争信号。

## 5. 候选方向排序

### 5.1 条件第一：bounded-memory SSD policy-aware vector search

建议题目暂写为：

> Permission-aware SSD vector search under bounded DRAM and policy churn

它比“Tenant+ACL+time/type”更诚实。可能成立的三个系统矛盾是：

1. GateANN 风格的全内存 filter/neighbor state 超出目标 DRAM；
2. grant/revoke 使 on-disk policy metadata、summary 或 partition 产生写放大；
3. 查询必须在明确 snapshot 上同时满足索引 freshness 与权限 soundness，尤其撤权不能延迟泄露。

这三个矛盾仍然只是待验证假设。ACL 数学上编译成 `authorized(user, vector)` 后仍是 query-dependent Boolean predicate；其系统独特性来自安全契约、policy complexity 与 churn，而不是一种天然新的 ANN primitive。

### 5.2 真正复合查询第一：multi-attribute range on SSD

该查询族结构固定、公开真实多属性数据更充足，且 KHI 已证明单范围方法不能自然扩展。候选问题不是再做一个多维树，而是：

- 多属性范围在 SSD 页级 summary 上是否造成高 false-positive page rate；
- 属性相关性与查询框形状是否使同一 global selectivity 对应完全不同的随机 I/O；
- 如何在不复制大量图/向量的情况下组织跨 cell routing；
- 动态数值属性更新是否破坏页摘要与局部布局。

风险也很明确：KHI、GateANN 和 GPU/out-of-core 方案已经压缩 novelty，必须先证明 SSD-Vamana 数据路径上存在它们不能吸收的 residual。

### 5.3 条件第三：稳定属性 + 高频动态属性

该方向最贴合现有动态 SSD 图经验，但目前缺真实属性更新 trace。若只在随机标签上注入 update，它只能证明机制性能，不能证明问题典型。可作为 policy 或商品场景的子问题，不宜先独立立项。

### 5.4 条件第四：日志语义检索 + 时间分段

时间局部性、append-only、热冷段和整段淘汰都很适合 SSD；但其核心机制容易被解释为“时序分段 + ANN”。除非 profiling 发现跨段 top-k 或 segment/index 生命周期出现新的主瓶颈，否则不优先。

## 6. 建议的下一步：只设计有界 preflight，不立即实验

### 6.1 Gate 要回答的唯一问题

> 在固定 authorized Recall@k 与零未授权输出下，严格 DRAM 上限和权限 churn 是否让现有通用 SSD filtering 出现可复现、主导性的 metadata I/O、写放大或 freshness residual；ACL+time/type 是否比 ACL-only 多出不可分解的执行问题？

### 6.2 Preflight 必须冻结

- 至少两类权限模型：RBAC hierarchy 与 per-object ACL/ABAC；
- 每文档 ACL 长度、每用户 entitlement 数、role sharing degree、权限—向量相关性；
- grant、revoke、user-role change、document insert/delete 的独立比例；
- ACL-only 与 ACL+time/type 成对查询；
- authorized exact top-k oracle；
- GateANN、PipeANN-Filter、Filtered-DiskANN/Qdrant on-disk filter 的可实现边界；
- Curator/HoneyBee/Veda 作为机制与内存上界，而不是随意省略的 related work；
- 100M/1B 的 filter store、neighbor store、routing table、exact verifier RSS 外推；
- source/config/workload/result hash 与固定数据盘路径。

当前公开权限 workload 主要仍是 generator，不足以支持“真实企业 ACL 分布”主张。可用 synthetic permission models 做 falsification，但任何 positive 结果最多进入 workload/novelty review，不能直接立项。

### 6.3 必测指标

| 类别 | 指标 |
|---|---|
| 安全与质量 | unauthorized outputs、authorized Recall@k、insufficient-k rate |
| 查询 | p50/p95/p99、QPS、CPU/query |
| SSD | graph/vector/metadata reads/query、bytes/query、request size、IOPS |
| DRAM | filter store、neighbor store、PQ、routing/exact verifier RSS |
| 更新 | logical permission bytes、physical SSD bytes、write amplification、compaction |
| 一致性 | grant/revoke visibility lag、stale-allow window、snapshot violations |
| 复合性 | ACL-only 与 ACL+time/type 的 plan、I/O、latency residual 差值 |

### 6.4 建议资源硬门禁

首轮只允许 1M sanity/preflight，目标上限：

- wall time：4 小时；
- 数据盘新增空间：10 GiB；
- peak RSS：24 GiB；
- 所有 workload、build cache、index、result 与 temp 均放 `/dev/nvme8n1`；
- 禁止在系统盘下载或生成大数据；
- 未完成 measured projection 前不得扩到 10M/100M。

这些是建议门禁，不是运行授权。正式数值需由 GPT/PZ 在 prelaunch 中冻结。

### 6.5 决策标签建议

- `GO-POLICY-SSD-A0`：bounded DRAM 或 churn 使至少一个现有强 baseline 出现主导 residual，且安全/质量口径闭合；
- `HOLD-SYNTHETIC-POLICY-WORKLOAD`：仅 synthetic permission 分布 positive，尚无真实 workload 支撑；
- `REFRAME-MULTI-RANGE-SSD`：ACL residual 被强 baseline 吸收，但 multi-attribute range 的 SSD residual 成立；
- `KILL-COMPOUND-ACL-CLAIM`：ACL+time/type 相对 ACL-only 没有新的执行或维护问题；
- `KILL-POLICY-SSD-GAP`：GateANN/PipeANN-Filter/on-disk filter 在目标内存与 churn 下已覆盖主要成本。

## 7. 给 GPT/PZ 的建议

保留 ACL 场景，但撤回“SSD=零、动态=零、Bloom+tunneling 是新机制”的表述。下一轮请 GPT 二选一：

1. 先签发 **policy workload + strong-baseline feasibility preflight**，只闭合 workload、内存外推、baseline 可复现性和 A0 成本；或
2. 将主讨论切到 **multi-attribute range on SSD**，要求同样的 prior/workload/preflight 审查。

在这两个 preflight 之一通过前，不建议修改 DGAI/OdinANN，也不建议启动 SSD 正式 profiling。
