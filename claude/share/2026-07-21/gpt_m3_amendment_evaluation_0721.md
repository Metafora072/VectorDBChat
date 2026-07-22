# Gpt M3 Manifest Amendment 评估

**Date:** 2026-07-21 16:30
**Author:** Claude

---

## 技术裁决质量：精确，没有过分

Gpt 指出的六个问题全部数学正确：

| 问题 | 评价 |
|------|------|
| A1 selectivity floor ~3% | ✅ 正确，Bernoulli + 至少一个 role 确实使 s=0.01 不可达 |
| A2 `obj % 10` 不是图/向量 cluster | ✅ 正确，ID 取模不建立语义或拓扑相关性 |
| A3 core 贡献 ~29.8% selectivity floor | ✅ 正确，0.3 × [1-(1-0.8)^3] ≈ 0.298，低选择率不可达 |
| A5 假 page map | ✅ 正确，`obj//64` 不是真实 node→page mapping |
| 路径/hash 不闭合 | ✅ 正确，manifest 确实未与 M0 artifact identity 对齐 |
| GT 无资源 projection | ✅ 正确，1000×1M×128 需要 canary |

这些是我 manifest 的实际缺陷，Codex 先指出了大部分，Gpt 确认并系统化。RETURN-FOR-REVISION 是合理裁决。

修订后的 F0-F3 框架（直接生成 resolved authorization mask，而非经 role 间接生成）是**概念上的改进**——搜索路径看到的就是 Boolean mask，用 mask 直接控制 selectivity 更精确、更可控。

结构描述符要求（Section 5：edge cut、homophily、page entropy 等）是正确的实验设计——必须证明四个 family 确实结构不同，否则实验无意义。

决策逻辑（Section 12）的六种结果清晰可 falsify，KILL 条件合理（adversarial-only、single-strategy-dominates 都是真实的 failure mode）。

**结论：技术层面没有过分或不妥当之处。**

---

## 但问题不在技术层面，而在方向本身

### 过程开销已经失控

回顾整个流程：

```
方向提出 → 12 族分析 → Codex 7 项纠正 → 收敛到 ACL
→ Gpt 方向裁决 + 三轴 + Q/M/U fork
→ Codex G0 witness + M0-M2 执行
→ Claude manifest 交付
→ Codex 6 项 manifest 缺陷
→ Gpt RETURN-FOR-REVISION + 10 项 prelaunch 要求
→ 还没开始跑 M3
```

我们现在处于 **P0 阶段的 M3 prelaunch**，整个方向的第一个真正实验还没执行。而 prelaunch 又需要 10 项联合交付物。这个过程开销对于一个"方向级 falsification"实验来说过重。

### ACL 场景的学术定位问题

PZ 的直觉是对的。ACL/权限感知向量搜索的核心问题：

**1. 场景与企业强绑定，学术 contribution 难提炼**

- ACL 是企业基础设施需求（multi-tenant RAG、RBAC、FGAC）
- 解决 ACL 问题的动机是产品功能，不是系统原理
- HoneyBee (SIGMOD 2026)、Curator (SIGMOD 2026)、Veda 都发在应用导向或工业 track
- FAST/VLDB research track / OSDI 需要的是可泛化的系统洞见

**2. "ACL 不是普通 filtered ANN" 的论点在弱化**

最初的卖点是 ACL 与标签本质不同（高基数、安全语义、碎片化、动态更新）。但：
- 高基数 predicate 已被 GateANN、PipeANN-Filter 处理
- 安全语义（false negative = recall loss, false positive at exact layer = leak）是正确性约束，不是系统设计的 novelty
- 碎片化就是低选择率 + 无结构，这是 filtered ANN 的已知 hard case
- 动态更新在 P0 阶段被排除了（轴 C 先分析）

剩下的核心问题是**轴 A：授权结构影响 SSD 图遍历**。但这本质上是**"predicate structure × graph topology × SSD I/O"**的特例——如果我们证明了 ACL 结构影响 I/O，真正的 insight 是 predicate 空间结构影响 SSD graph search，不需要绑定 ACL。

**3. 1M 规模下核心瓶颈不存在**

轴 B（policy metadata SSD 访问成本）在 1M 规模下被 page cache 完全吸收（~12.5 MB）。这意味着：
- 我们只能测轴 A（碎片化），轴 B 和轴 C 都需要更大规模
- 但 100M+ 规模下又受限于 PZ 硬件的 238 GiB DRAM
- 论文需要说"这个问题在足够大的规模下才出现"，但实验只在 1M 上做——审稿人会质疑

**4. 即使 M3 PASS，后续路径不清晰**

假设 M3 得到 `PASS-Q-PHENOMENON`——证明授权结构确实影响 SSD 图遍历。然后呢？
- 需要设计一个**系统**来解决这个问题
- 系统的 novelty 不能只是"根据 selectivity 选策略"（Phase Transition 论文已经做了）
- 需要 ACL-specific 的系统设计点，但轴 B/C 都没有实验验证
- 从 phenomenon 到 paper 还有很长的路

---

## 建议

### 对当前方向的判断

ACL-on-SSD 作为一个**企业工程问题**是真实的。但作为瞄准 FAST/VLDB/OSDI 的**学术研究方向**，它有三个结构性弱点：

1. contribution 难以与 filtered ANN 划清界限
2. 核心瓶颈在实验可行规模下不显现
3. 从 characterization 到系统设计的路径不清晰

### 是否继续

两个选项：

**选项 A：止损退出**
M0-M2 已经完成了方向级验证的基础工作。G0 witness 证明了 stale grant 的控制流 vulnerability 是真实的。如果要退出，现在是最佳时机——已经投入的工作不多，且已有的 G0 witness 可以作为其他方向的 building block。

**选项 B：快速 falsification 后决定**
如果还不想完全放弃，可以大幅简化 M3：跳过 Gpt 的 10 项 prelaunch 要求，直接做一个最小实验（F0 Random vs F1 Graph-Localized，两个 selectivity，一个 seed），48 小时内看结果。如果 F0 和 F1 没有显著差异 → KILL，不再继续。如果有 → 再决定是否投入完整实验。

**我的倾向是选项 A。** 把精力转向更有学术 leverage 的方向。PZ 的 SSD graph ANN 基础设施（PipeANN、multi-NVMe）是很好的资产，应该用在一个 contribution 边界更清晰的问题上。
