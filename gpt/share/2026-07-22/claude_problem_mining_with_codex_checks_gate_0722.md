# Claude 主导的新一轮 VectorDB / ANNS Problem Mining

**日期：** 2026-07-22  
**状态：** `GO-PROBLEM-MINING`  
**目标：** 修正 Codex 连续两轮 `0PASS` 的流程性偏差，由 Claude 主导发现研究问题，Codex 子智能体只承担相互隔离的检索、核查和反方评审工作  
**本轮不要求：** 必须产出完整论文级 PASS idea  
**本轮要求：** 产出 3–5 个没有 direct prior、可低成本证伪的 problem seeds，并选出 1–2 个 A0-ready 候选

---

## 0. 为什么需要更换流程

Codex 连续两轮 idea-discovery 得到 `0PASS`，这不能简单解释为 VectorDB / ANNS 已经没有研究空间。

当前流程存在四个系统性问题。

### 0.1 同一角色同时负责生成与否决

Codex 的实际工作模式近似：

```text
生成候选
→ 检索相邻论文
→ 构造拒稿理由
→ 自己裁决
```

对模型而言，找到一个相似工作并写出“可能只是已有工作的变体”很容易；证明一个尚不成熟的候选具有清晰 novelty 更难。

因此该流程天然倾向：

```text
宁可错杀，不可误留
```

---

### 0.2 Discovery 阶段仍使用 Paper Gate

一个早期候选常被同时要求具备：

- 已证实的现实问题；
- 明确 novelty；
- 完整核心机制；
- 多个系统组件；
- concurrency / failure / metadata 设计；
- 强 baseline；
- 可投稿顶会的完整故事。

这相当于要求候选在尚未做 A0 前已经接近投稿状态。

本轮必须分离：

```text
Problem Discovery
→ Direct-Prior Check
→ Falsifiability
→ Mechanism Discovery
→ Paper Gate
```

前三步不得使用最终投稿标准。

---

### 0.3 “至少多个技术组件”与“避免工程拼接”互相冲突

简单而深刻的 idea 容易因组件不足被杀死；加入 cache、scheduler、compaction、predictor 后，又容易因工程组合被杀死。

因此本轮不按组件数判断工作量。首先寻找：

> 一个新的 ANN-specific 研究对象、矛盾、语义或不变量。

系统组件只能在问题成立后自然展开。

---

### 0.4 历史 Kill Map 过早参与生成

过去已 KILL：

- ZNS；
- GraphAging / Shadow Edge；
- ACL 安全；
- generic adaptive beam；
- ordinary page batching；
- 普通 topology–vector decoupling；
- generic repair scheduler；
- 多种 multi-NVMe 投机遍历版本。

这些结论应在后续查重和机制评审中使用，不能在问题生成前就限制 Claude 的发散。

本轮 Claude 在 Phase 1 生成问题时，不得逐条套用历史 KILL 结论。等形成独立问题表述后，再由 Codex 子智能体检查是否真正同构。

---

## 1. 角色分工

### 1.1 Claude：主研究者与最终综合者

Claude 必须亲自完成：

1. 研究问题的发散生成；
2. 问题的合并和分类；
3. 判断哪些是值得核查的 problem seeds；
4. 综合 Codex 子智能体报告；
5. 保留有争议但可证伪的候选；
6. 最终选出 3–5 个 problem seeds 和 1–2 个 A0-ready 候选。

Claude 不得把最终 idea-discovery 整体外包给一个 Codex 任务。

---

### 1.2 Codex 子智能体：隔离式核查

每个子智能体只执行一个明确角色，不能看到其他角色的结论，不能自行做最终裁决。

建议至少使用以下五类子智能体。

#### Agent P：Direct-Prior Checker

输入：

- 一个独立问题陈述；
- 问题的对象、目标和系统边界。

只回答：

1. 是否存在直接提出同一问题的工作；
2. 最接近的 3–5 篇 primary sources；
3. prior 覆盖的是：
   - 相同问题；
   - 相同机制；
   - 相同指标；
   - 相同系统边界；
4. 给出：

```text
DIRECTLY-COVERED
PARTIALLY-STUDIED
NO-DIRECT-PRIOR-FOUND
UNCERTAIN
```

限制：

- 机制关键词相似不能自动判定 direct prior；
- 必须同时比较问题语义、优化目标、核心机制和系统边界；
- `UNCERTAIN` 不能等同于 KILL。

---

#### Agent F：Falsifiability / A0 Checker

输入：

- 问题陈述；
- 可疑现象。

只回答：

1. 能否定义明确的可观测量；
2. 能否设置 static / exact / oracle / isolated baseline；
3. 正结果和负结果分别是什么；
4. 当前单机 CPU + NVMe 环境能否在 2–8 小时内完成最低成本 A0；
5. 输出：

```text
A0-READY
A0-POSSIBLE-BUT-NEEDS-INSTRUMENTATION
NOT-FALSIFIABLE
ENVIRONMENT-BLOCKED
```

不得评价 novelty 或投稿潜力。

---

#### Agent S：System-Specificity Checker

只判断：

1. 问题是否真正依赖 ANN / vector DB 特性；
2. 是否可以被通用 cache、LSM、WAL、batching 或 scheduler 完整概括；
3. 是否存在新的系统状态、算法对象或不变量；
4. 输出：

```text
ANN-SPECIFIC
ANN-DEPENDENT-BUT-GENERIC-MECHANISM
GENERIC-STORAGE
UNCERTAIN
```

不得因机制尚未完整而 KILL 问题。

---

#### Agent E：Environment / Implementation Checker

只检查：

- 是否存在可用 baseline；
- 是否需要 GPU、分布式、特殊设备；
- 数据集和索引规模；
- 是否可在现有 12 块 PCIe 4.0 NVMe、CPU、Ubuntu 环境验证；
- 最小原型需要修改哪些系统。

输出：

```text
FEASIBLE-NOW
FEASIBLE-WITH-MODERATE-ENGINEERING
INFRASTRUCTURE-BLOCKED
```

---

#### Agent R：Adversarial Reviewer

只针对已经通过前四类核查的候选进行攻击：

- 最强反方解释；
- 最可能的 hidden baseline；
- 最容易使现象消失的控制变量；
- 最可能的 novelty collapse；
- A0 中必须加入的 KILL test。

该角色不能独立否决候选，只提交攻击清单。

---

## 2. Phase 1：Claude 只做问题挖掘

Claude 先生成至少 25 个问题陈述。

### 2.1 此阶段禁止提出完整机制

禁止直接写：

- 新 cache；
- 新 scheduler；
- 新 delta log；
- 新 compaction；
- 新 threshold；
- 新 predictor；
- 新 page grouping；
- 多组件系统架构。

每个候选只写：

```text
Problem ID
现象或矛盾
现有索引的隐含假设
为什么该假设可能失效
可观察后果
```

### 2.2 问题来源至少覆盖六类视角

#### A. 抽象假设挑战

挑战现有 ANNS 的基本假设，例如：

- 查询是独立的一次性 top-k；
- 距离函数固定；
- 查询向量单一；
- 索引状态在查询期间固定；
- 一个节点同时代表数据与导航；
- approximate result 只需要集合质量；
- recall 是唯一主要质量维度；
- 图节点的物理访问代价同质。

#### B. 查询执行矛盾

寻找：

- 算法认为等价，但 SSD 执行代价不等价的状态；
- recall 相同，但 I/O 风险或 tail 不同；
- candidate quality 与 candidate fetch cost 冲突；
- 搜索宽度增加后更多 I/O 却没有更多信息。

#### C. 动态状态矛盾

不局限普通插入删除，考虑：

- 向量版本变化；
- embedding model 更新；
- metadata 与 vector 不同步；
- partial materialization；
- query distribution drift；
- index state 与 data state 的时间错位；
- mixed old/new embedding space。

#### D. 多对象和复合查询语义

考虑真实场景中的：

- 多向量对象；
- query-by-example + filter；
- reranking budget；
- 多阶段检索；
- negative example；
- freshness / diversity / group constraints；
- 连续或关联查询。

不能笼统声称“优化所有复合查询”，必须锚定具体语义。

#### E. SSD / 多 NVMe 接口产生的新算法对象

不再只考虑页面调度，考虑：

- async completion order；
- outstanding I/O uncertainty；
- multi-device skew；
- partial candidate arrival；
- read cancellation；
- wasted in-flight I/O；
- device-level parallelism 与 graph dependency；
- computation and I/O overlap 改变搜索正确性或停止条件。

#### F. 生产系统与论文叙事不一致

从开源代码、issue、benchmark 或论文实现中寻找：

- 论文假设在真实代码中被弱化；
- 正确性或性能依赖未公开 fallback；
- metadata/filter/update 路径与主 search path 分离；
- benchmark 隐藏 warm cache、batch 或 static layout；
- 动态路径缺乏与静态路径同等的物理优化。

---

## 3. Phase 2：Claude 初筛 Problem Seeds

Claude 根据以下四个条件，从 25+ 问题中保留 8–12 个：

1. 能描述一个明确受影响的系统状态；
2. 有可观测后果；
3. 不是单纯“某操作比较慢”；
4. 至少存在一种低成本反事实或 oracle。

此阶段只允许以下标签：

```text
KEEP-FOR-CHECK
MERGE-WITH-OTHER
DROP-VAGUE
DROP-NO-OBSERVABLE
```

不得使用顶会潜力或机制组件数进行淘汰。

---

## 4. Phase 3：Codex 子智能体独立核查

对每个保留候选：

1. 单独调用 Agent P；
2. 单独调用 Agent F；
3. 单独调用 Agent S；
4. 单独调用 Agent E；
5. 子智能体之间不得共享输出；
6. Claude 最后汇总。

### 4.1 Discovery Gate

候选进入下一阶段只需满足：

- Agent P 不是 `DIRECTLY-COVERED`；
- Agent F 不是 `NOT-FALSIFIABLE`；
- Agent S 不是确定的 `GENERIC-STORAGE`；
- Agent E 不是确定的 `INFRASTRUCTURE-BLOCKED`。

存在 `UNCERTAIN` 时应进入 HOLD，不得自动 KILL。

### 4.2 合法标签

```text
PASS-PROBLEM-SEED
PASS-A0-READY
HOLD-NEEDS-EVIDENCE
HOLD-NEEDS-MECHANISM
HOLD-PRIOR-UNCERTAIN
KILL-DIRECT-PRIOR
KILL-NOT-FALSIFIABLE
KILL-GENERIC-NON-ANN
KILL-ENVIRONMENT
```

本阶段禁止：

```text
KILL-NOT-TOP-CONFERENCE
KILL-NO-THREE-COMPONENTS
KILL-NO-CRASH-SEMANTICS
KILL-NOT-COMPLETE-SYSTEM
KILL-MECHANISM-IMMATURE
```

---

## 5. Phase 4：Claude 主导机制发现

只针对 3–5 个 `PASS-PROBLEM-SEED`：

1. Claude 为每个问题提出至少两种机制族；
2. 两种机制必须基于不同核心对象，不能只是参数变化；
3. 可再调用两个相互隔离的 Codex Builder：
   - Builder A：algorithm-first；
   - Builder B：system-state-first；
4. Builder 不得读取 prior checker 和 reviewer 的负面结论；
5. Claude 比较：
   - 两个 Builder 是否都收敛到通用 cache/batch；
   - 是否出现不同机制；
   - 是否存在真正 ANN-specific 的设计对象。

如果所有 Builder 只能产生通用存储机制，候选转为：

```text
HOLD-NEEDS-MECHANISM
```

而不是伪装成复杂系统。

---

## 6. Phase 5：反方攻击与 A0 选择

Agent R 只对最终 3–5 个候选做攻击。

Claude 最终选择 1–2 个 A0-ready idea，每个必须给出：

### 6.1 最小问题陈述

一句话说明：

- 什么状态；
- 什么失败；
- 什么可观测后果。

### 6.2 核心区分

明确区别于最近工作的：

- 问题语义；
- 优化目标；
- 核心对象；
- 系统边界。

### 6.3 A0

包含：

- baseline；
- oracle；
- variable；
- metric；
- PASS；
- HOLD；
- KILL；
- 时间和资源预算。

### 6.4 不要求完整系统

A0 阶段不得提前要求：

- recovery protocol；
- production concurrency；
- 三项以上机制；
- 端到端完整系统。

这些只在现象 PASS 后设计。

---

## 7. 输出要求

Claude 输出：

`claude/share/2026-07-22/claude_problem_mining_with_codex_checks_0722.md`

报告必须包含：

1. 25+ 原始问题；
2. 8–12 个初筛问题；
3. 每个 Codex 子智能体的独立结论；
4. 3–5 个 problem seeds；
5. 1–2 个 A0-ready 候选；
6. 仍为 HOLD 的候选；
7. 被 KILL 的候选及唯一明确理由；
8. 对 Codex 连续 0PASS 的流程性复盘。

同时在对话中给出简洁摘要。

---

## 8. 成功标准

本轮不以“必须找到一篇完整论文 idea”为成功标准。

成功结果可以是：

```text
3–5 PASS-PROBLEM-SEED
1–2 PASS-A0-READY
其余 HOLD / KILL
```

也可以是：

```text
0 PASS-A0-READY
但有 3 个 HOLD-NEEDS-EVIDENCE
并明确指出缺少什么证据
```

以下结果视为流程失败：

```text
所有候选再次因为“不够完整系统”或“可能不够顶会”而 KILL
```

如果最终仍为 0 problem seeds，Claude 必须说明：

- 是 direct prior 真正全覆盖；
- 还是不可证伪；
- 还是环境不可行；
- 还是问题生成空间仍被历史锚定。

不能只给出“方向饱和”这一笼统结论。

---

## 9. 本轮研究边界

继续遵守：

- 研究 VectorDB / ANNS；
- 不考虑安全主线；
- 不依赖 GPU；
- 不要求分布式集群；
- 单机多 NVMe 可用；
- 可以研究查询、更新、布局、执行、语义和系统接口；
- 避免 arbitrary threshold 作为核心；
- 避免多个普通模块的工程拼接；
- 允许早期 idea 不成熟；
- A0 后继续使用严格 KILL gate。

核心纪律：

> 放宽的是进入 A0 前的问题保留规则，不是 A0 之后的证据标准。
