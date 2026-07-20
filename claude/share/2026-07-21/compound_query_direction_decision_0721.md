# 方向决策分析：回应 Codex 审查后的修正判断

**Date:** 2026-07-21
**Author:** Claude

---

## 一、承认 Codex 的事实纠正

Codex 的纠错全部成立，我逐条接受：

| # | 我的错误 | 修正 |
|---|---------|------|
| 1 | HoneyBee 写为 SIGMOD 2025 | 实际为 **SIGMOD 2026** |
| 2 | 称"SSD ACL = 零" | GateANN 已在 SSD 上支持 conjunction/range/multi-label；Qdrant 有 on-disk payload index |
| 3 | 称"动态权限更新无人解决" | HoneyBee 支持 role update benchmark；Curator 支持 grant/revoke + Bloom 重算 |
| 4 | 漏检 Curator | Curator (SIGMOD 2026) 直接研究 per-vector ACL / multi-tenant，有 Bloom/shortlist + grant/revoke |
| 5 | ACL 安全语义写反 | false positive = 未授权泄露（严重）；false negative = 漏掉授权项（影响 recall）；Bloom 无 false negative，只能做粗筛 |
| 6 | 称 Veda "完全没有动态处理" | 附录有 insert/delete/grant/revoke/merge 草案 |
| 7 | 称 Policy-aware Vision "无实现" | 已在 pgvector 上实现并比较 enforcement strategy |

**结论：我之前的 novelty 判断过强。"SSD ACL = 零、动态更新 = 零、Bloom+tunneling 是新机制"均不成立。**

---

## 二、但 Codex 的结论过于保守

PZ 说得对："有平行工作不代表我们不能做。"

Codex 的纠错是事实层面的，完全正确。但 Codex 从"先前工作已覆盖某些机制"推导出"不能立项"，这个推理跳跃太大。让我区分两件事：

### 2.1 机制级别的 novelty vs 系统级别的贡献

Codex 证明了以下机制不是新的：
- ACL sketch / Bloom filter → Curator, PipeANN-Filter 已有
- Graph tunneling / 非法节点路由 → GateANN 已有
- Grant/revoke 支持 → HoneyBee, Curator 已有
- Multi-predicate conjunction on SSD → GateANN 已有

但这些机制**从未在同一个 SSD 系统中被整合解决**。现状是：
- **HoneyBee / Curator / Veda**：有 ACL 处理，但**纯内存**
- **GateANN**：有 SSD + multi-predicate，但 **63 GB/100M 内存**，无 ACL 语义
- **PipeANN-Filter**：有 SSD + Bloom，但**无 ACL、无动态更新**

没有任何系统同时满足：SSD-resident + ACL-aware + bounded DRAM + permission churn handling。

这就像问"DGAI 有什么新机制？"——答案是 DGAI 的每个单独组件（Vamana 图、SSD 存储、增量更新）都有先驱，但把它们正确组合成一个高效的 SSD 动态图 ANN 系统，就是贡献。

### 2.2 Codex 识别的三个真正残余空间

Codex 自己也承认了三个 **"待验证假设"**，这正是做研究的起点：

1. **Out-of-core policy metadata under strict DRAM** — 当 ACL 列表+图拓扑+PQ 的总内存需求超过物理 DRAM（十亿级场景），如何处理？GateANN 完全回避了这个问题。

2. **Permission churn → SSD write amplification** — 权限变更（人员调动、项目重组、文档共享变化）触发的 metadata 更新在 SSD 上如何高效执行？没有任何 SSD 系统测量过这个成本。

3. **Freshness / snapshot consistency** — 撤权后的可见性延迟窗口：如果一个用户刚被撤权，但 index/filter state 尚未更新，该用户的查询是否仍能返回已撤权的文档？这是安全语义独有的问题——普通 filter 错误只影响 recall，ACL 错误可能违法。

**这三个问题本身就足以支撑一篇系统论文。**

---

## 三、方向决策

### 我的判断：仍然推荐 ACL 方向，但修正 framing。

**旧 framing（过强，已被 Codex 否定）：**
> "SSD ACL = 零，所有机制都是新的"

**修正后的 framing（更诚实，仍然有力）：**
> 现有 ACL-aware 向量搜索系统（HoneyBee、Curator、Veda）全部假设数据和元数据常驻内存。现有 SSD filtered ANN（GateANN、PipeANN-Filter）处理通用谓词但不考虑 ACL 的特殊需求：策略元数据可能超过 DRAM、权限变更产生 SSD 写放大、撤权的可见性延迟有安全后果。我们设计首个在严格 DRAM 预算下支持 ACL 感知的 SSD 向量搜索系统。

### 与 3.4（多类别+范围）的比较

| 维度 | 3.5 ACL | 3.4 多类别+范围 |
|------|---------|---------------|
| 故事冲击力 | 强（安全 = 天然 motivation） | 中（性能优化，审稿人可能认为是 GateANN 的增量改进） |
| 问题独特性 | 高（安全语义、高基数、碎片化、churn 是通用 filter 没有的维度） | 中（多谓词联合是通用 filter 的自然扩展） |
| 内存竞争 | HoneyBee/Curator/Veda — 都是 SIGMOD 级别，但都不在 SSD 上 | EMA/JAG/SIEVE/Curator — 更拥挤 |
| SSD 竞争 | GateANN 处理通用谓词但不考虑 ACL 特殊性 | GateANN + PipeANN-Filter 直接覆盖 |
| 差异化清晰度 | 清晰："ACL 不是普通 label" 有明确的性质差异表格 | 模糊：需要证明"多谓词 > 单谓词 + 单谓词" |
| Baseline 对比 | HoneyBee (内存) vs 我们 (SSD)，clean setup | GateANN (SSD 但 63GB) vs 我们 (SSD bounded DRAM)，更像增量改进 |

**ACL 方向仍然更优**，原因是差异化更清晰、故事更有冲击力、baseline 比较更自然。

### 关于 Codex 提出的 "multi-attribute range" 作为备选

Codex 建议如果 ACL 不成立，转向 multi-attribute range on SSD。我同意这是合理的 Plan B，但有两个担忧：
1. KHI (arXiv 2602.15488) 已经在多属性范围 ANN 上取得 2.46–16.22× QPS 提升，虽然是内存方案，但 novelty 空间被压缩
2. GateANN 已经在 SSD 上支持 range conjunction，差异化只剩"page-level summary 优化"和"动态维护"

### 关于 Codex 质疑 "ACL+time/type 是否是真正的复合查询"

Codex 的这个质疑我认为是对的。当前没有证据表明 ACL+time/type 的联合执行比 ACL-only + time-filter 的独立执行有本质区别。

**修正方案：** 主贡献锚定在 ACL-on-SSD（系统层面），time/type 作为"实际场景中 ACL 常伴随的附加谓词"来处理，但不强调"复合查询"作为独立贡献维度。如果实验中发现 ACL+time 的联合执行确实产生了新的 I/O pattern（比如 ACL 碎片化 + time range 范围限制 → 极度稀疏的可达子图），那么可以作为额外发现。

---

## 四、建议的下一步

1. **方向锁定**：Permission-aware SSD vector search under bounded DRAM and permission churn
2. **不急于实验**：先完成一个 design-level 的可行性分析，回答：
   - GateANN 在目标规模（100M/1B）下的 DRAM 需求外推
   - HoneyBee 的分区策略在 SSD 上的空间/更新放大估算
   - 权限更新频率的真实数据（企业 IAM 系统的 churn rate）
   - 可用的 workload generator（HoneyBee 的 RBAC generator 是否公开）
3. **然后做 preflight**：在 1M scale 上验证 ACL 碎片化是否真的导致 SSD ANN 的显著性能退化
