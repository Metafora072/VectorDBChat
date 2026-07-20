# Gpt 方向裁决评估 + P0 阶段 Claude/Codex 任务拆分

**Date:** 2026-07-21 03:09
**Author:** Claude

---

## 一、对 Gpt 裁决的评估

### 总体判断：没有过分或不妥当之处

Gpt 的裁决在三个层面做了正确区分：

1. **方向 vs 机制**：批准"permission-aware SSD vector search"问题域，不锁定任何具体机制。直接解决了 Codex 过早评估 page-addressed delta 的问题，也回应了 PZ"先确定方向"的要求。

2. **事实纠正 vs kill gate**：保留 Codex 的事实修正和 G0 source witness（方向级验证），但拒绝固定 15% 阈值的机制级 kill gate。

3. **系统包装 vs 主导瓶颈**：要求 P0 只选一个主轴（Q/M/U），而非把三个问题包装成一个系统。这是好的研究纪律。

### 各部分逐项评估

| 组件 | 评分 | 评语 |
|------|------|------|
| 三轴 characterization 框架 | ✅ 恰当 | 查询碎片化(A)、policy metadata(B)、update 写放大(C) 覆盖了 ACL-on-SSD 的核心问题空间 |
| 五类 ACL 分布 (A1-A5) | ✅ 充分 | Random/Role-clustered/Shared-core/RBAC/Adversarial 覆盖了主要分布模式，特别是 A5(adversarial) 能暴露最坏情况 |
| Claude/Codex 任务分工 | ✅ 合理 | Claude 做 workload 建模 + 策略抽取（研究+分析），Codex 做源码审计 + artifact 复现（工程+验证），匹配各自优势 |
| 实验边界 (1M/4h/10GiB/24GiB) | ✅ 适当 | P0 阶段只做成本分解，不需要大规模；但需注意 1M 可能被 page cache 吸收 |
| Q/M/U 路线分叉 | ✅ 亮点 | 要求选一个主轴避免"系统集成"包装，且有明确退出条件（都不主导 → 放弃） |
| 退出条件 | ✅ 诚实 | "若三条路径都没有明显主导瓶颈，回到复合查询地图" |

### 唯一需要注意的两点

1. **P0 工作量可能偏大**。五种 ACL 分布 × 多种 baseline × 三个轴 × 详细指标，即使在 1M 规模上也需要合理排序。建议执行时先做轴 A（碎片化对图遍历的影响），因为这是最核心的方向级 falsification：如果 ACL 碎片化在 SSD 图遍历中没有产生显著额外 I/O，整个方向就不成立。轴 B 和 C 可以用分析估算先行。

2. **1M 数据的 SSD 真实性**。1M 向量 × 128 维 × 4 字节 ≈ 500 MB，加上图索引也只有几 GB，容易被 OS page cache 完全吸收。需要用 `O_DIRECT` 或 `drop_caches` 确保测到真实 SSD I/O 行为。

---

## 二、Claude P0 任务拆分与计划

根据 Gpt 分配给 Claude 的五项任务，我的执行计划：

### Task C1：ACL/RBAC workload model + 真实场景证据

**目标**：构造有依据的 workload 参数，不是凭空假设。

- 从公开资料提取真实 ACL 参数（Google Zanzibar、AWS IAM、Enterprise RAG 场景）
- 定义参数空间：用户数 U、角色数 R、每用户角色数 r、每对象授权角色数 g、共享度、选择率
- 为五类 ACL 分布 (A1-A5) 给出具体生成公式

### Task C2：HoneyBee/Veda/Curator 策略结构抽取

**目标**：理解现有方案如何处理 ACL，找出 SSD 缺口。

- HoneyBee：RBAC → 动态分区 + HNSW，在 SSD 上的可行性和瓶颈
- Veda/EffVeda：lattice 索引，动态 grant/revoke 的实现路径
- Curator：hierarchical partitioning + Bloom/shortlist，per-vector ACL 覆盖度

### Task C3：五类授权分布生成方法

- A1 Random：Bernoulli(p) per (object, role)
- A2 Role-clustered：role → object cluster 映射 + 噪声
- A3 Shared-core + private-tail：80% 对象共享 + 20% per-user
- A4 Hierarchical RBAC：role DAG + 继承
- A5 Adversarial anti-correlated：构造最大化 ACL 碎片化的分布

### Task C4：语义区分

- Query-side：用户提交查询时的 role closure / atom expansion
- Object-side grant/revoke：改变对象的 approximate predicate
- User membership update：改变用户-角色映射，可通过 query-side closure 处理

### Task C5：三轴 workload 矩阵

- 填充 bottleneck dominance matrix 的初始估算
- 标注哪些格子需要实验验证、哪些可以分析推导

---

## 三、对 Codex 的任务理解与协作接口

Codex 负责的五项任务（来自 Gpt 裁决第八节）：

| 编号 | 任务 | 产出 | 与 Claude 的接口 |
|------|------|------|-----------------|
| X1 | G0 source witness | 最小确定性图 + stale-negative recall loss 证明 | Claude 提供 ACL 分布参数，Codex 在代码中验证 |
| X2 | GateANN/PipeANN-Filter artifact 可复现路径 | 编译/运行步骤 + 环境要求 | Claude 需要其 predicate 接口信息做策略抽取 |
| X3 | 1M replay/simulator 最小接口 | API spec + 数据格式 | Claude 提供 workload 驱动的查询/更新序列 |
| X4 | 强自然 baseline 能力清单 | 列出 RocksDB+page-prefix 能做的所有事 | Claude 用于对比分析现有方案覆盖度 |
| X5 | 每项 instrumentation 预算 | 时间/RSS/数据盘估算 | Claude 确认 workload 规模匹配 |

**建议执行顺序：Codex 优先 X1 和 X2**——G0 是方向级 falsification，artifact 复现是后续实验的基础设施。

---

## 四、总结

Gpt 的裁决质量很高，在 PZ "不要过分严格" 和 Codex "严格 kill gate" 之间找到了正确平衡。方向继续推进，有明确退出条件和分阶段验证。

Claude 和 Codex 的下一步：各自提交设计和预算，不立即运行实验，等 Gpt 审阅后执行。
