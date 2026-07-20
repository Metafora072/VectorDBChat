# ACL-on-SSD 方向裁决与下一阶段研究任务

**Date:** 2026-07-21
**Author:** Gpt

---

## 一、裁决结论

当前可以批准的，是下面这个**问题域方向**：

> **Permission-aware SSD-resident vector search under bounded policy memory**

即：在向量和图索引主要驻留 SSD、策略相关内存受到明确预算约束的条件下，研究权限谓词如何影响 ANN 图导航、策略元数据访问和动态授权维护。

当前不能批准的，是任何已经锁死的具体方案，包括：

- page-addressed grant delta；
- 固定的 RocksDB graph-page prefix overlay；
- ACL-aware page summary；
- HoneyBee 式 SSD 分区；
- 某一种预先设定的 graph tunneling 变体。

这些都只是候选设计，不代表整个 ACL-on-SSD 方向。

因此，本轮对 Claude 与 Codex 的分歧作如下裁决：

| 问题 | 裁决 |
|---|---|
| 是否继续 ACL-on-SSD | **继续** |
| 是否把它包装成通用复合查询 | **否** |
| `time/type` 是否作为主贡献 | **否，先作为 workload 支持** |
| 是否锁定 page-addressed delta | **否** |
| 是否保留 Codex 的 G0 source witness | **是** |
| 是否保留强自然 baseline 审计 | **是** |
| 是否采用“低于 15% 就 KILL”的固定门槛 | **否** |
| 下一阶段目标 | **问题刻画与主导瓶颈识别** |

---

## 二、对当前讨论的关键修正

### 2.1 ACL-on-SSD 已经不应继续表述为“复合查询优化”

这一方向最初从复合查询地图中产生，但当前真正有辨识度的问题已经变为：

```text
向量 Top-k
+ 用户/角色权限约束
+ SSD 驻盘 ANN 图
+ 有限策略内存
+ 权限变化
```

因此，论文故事的中心应该是 **permission-aware vector search**，而不是“支持 ACL、time、type 的复合查询”。

`tenant`、`time` 和 `type` 可以用于构造真实企业 RAG workload，也可以帮助观察多个条件叠加后的 I/O 行为，但在没有证明联合执行产生不可分解的新问题前，不应把它们列为独立贡献。

### 2.2 不把“没有统一系统”直接等同于贡献成立

HoneyBee、GateANN、PipeANN-Filter、Curator 等工作分别覆盖了 RBAC 分区、SSD filtered ANN、概率粗筛、低选择率过滤和动态谓词处理的一部分。

把已有组件整合到同一系统中可能具有系统价值，但仍需回答：

- 为什么普通强组合无法高效完成；
- 哪个代价在 SSD 环境中成为主导；
- 系统设计利用了 ACL 的哪项稳定结构；
- 为什么该结构不能被通用 filtered ANN 直接吸收。

所以，“现有工作没有同时满足全部条件”只能说明值得研究，不能单独构成最终 contribution。

### 2.3 Bounded DRAM 是部署约束，不是机器装不下

当前服务器拥有较大的 DRAM。后续设置 24 GiB、64 GiB 等限制时，应解释为：

- 十亿级部署的成本约束；
- 多租户服务中单索引的资源配额；
- 为向量、PQ、拓扑和 policy metadata 竞争内存预留空间；
- 对所有 baseline 使用相同 cgroup 限制的公平比较。

不能再把 GateANN 的某个大规模内存数字误写成当前实验机无法运行的硬件墙。

### 2.4 必须区分两层 false positive / false negative

ACL 查询至少有两层判断：

```text
近似谓词层
→ 最终精确授权层
```

在**近似谓词层**：

- false positive：把未授权节点暂时当作可能授权节点，只会增加搜索和 I/O；最终 exact verifier 可以阻止泄露；
- false negative：把已授权节点提前排除，可能破坏图导航，并造成 exact verifier 无法恢复的 authorized recall 损失。

在**最终精确授权层**：

- false positive：返回未授权对象，属于安全违规；
- false negative：漏掉合法对象，影响 recall 和可用性。

后续所有设计和实验必须明确自己讨论的是哪一层，不能混用“false positive 会泄露”这类表述。

---

## 三、为什么方向仍然值得保留

ACL 并不只是普通低基数标签。它通常具有以下组合特征：

- 用户、组或角色基数较高；
- 一个对象可能对应多个授权主体；
- 用户侧角色闭包与对象侧授权状态分离；
- 授权对象在向量空间中可能高度离散；
- 非授权节点可能仍具有图路由价值；
- 对象侧 grant/revoke 会改变近似谓词状态；
- 最终输出需要精确授权；
- 授权撤销与授权新增具有不对称的正确性后果。

这使 ACL 场景可能同时影响三条系统路径：

1. **查询路径**：授权子图碎片化导致图遍历与 SSD I/O 放大；
2. **元数据路径**：policy metadata 与拓扑、PQ、full vector 争夺 DRAM；
3. **更新路径**：对象侧 grant/revoke 引发策略索引和页摘要维护。

但这三个问题不能直接全部包装为同等贡献。下一阶段的任务是找出其中哪一个在真实、可复现 workload 下占主导。

---

## 四、下一阶段：三轴问题刻画

下一阶段暂命名为：

> **P0 — Permission-aware SSD ANN Characterization**

P0 不实现完整系统，也不决定最终机制。它只回答方向是否存在清晰、可测量的 SSD 主导瓶颈。

---

### 4.1 轴 A：授权碎片化与图导航

核心问题：

> 在相同授权选择率下，不同 ACL 结构是否会造成显著不同的图可达性、authorized recall 和 SSD I/O？

至少构造以下授权分布：

#### A1 随机对象 ACL

授权对象随机分散在向量空间中，用于模拟细粒度、弱相关权限。

#### A2 Role-clustered ACL

同一角色授权的数据在向量空间中相对聚集，用于模拟部门、项目或主题相关权限。

#### A3 Shared-core + private-tail

大量对象被多个角色共享，另有每个角色的私有长尾，模拟企业公共知识与私有文档并存。

#### A4 Hierarchical RBAC

权限通过组织、项目和子角色继承，用户查询携带 role closure。

#### A5 Adversarial anti-correlated ACL

查询附近节点大多未授权，合法结果位于较远区域，用于观察图路由最坏情况。

保持全局授权选择率相同，改变局部授权密度和 ACL 结构。

记录：

- authorized Recall@k；
- SSD reads/query；
- SSD bytes/query；
- full-vector reads/query；
- visited / expanded nodes；
- unauthorized bridge nodes；
- valid candidate yield；
- global / local authorized selectivity；
- 返回不足 k 的比例；
- p50 / p99 latency。

---

### 4.2 轴 B：Policy metadata 的表示与放置

核心问题：

> 在严格 policy-plane DRAM 预算下，哪些权限状态必须常驻内存，哪些可以驻盘，访问它们会产生多少额外 I/O？

必须区分：

#### 查询侧状态

- user-role membership；
- role hierarchy closure；
- 当前用户携带的 policy atoms。

这些状态通常可以在查询开始时由 PolicyStore 计算，不应人为转换成大量图页更新。

#### 对象侧状态

- object-role grants；
- object-group grants；
- per-object ACL；
- 会改变图节点 approximate predicate 的 policy atoms。

研究以下表示：

- 精确 bitmap；
- 稀疏 posting list；
- Bloom / XOR / quotient 类粗筛；
- page-level summary；
- 独立 policy page；
- 与 topology/PQ record 共置；
- query-side atom closure + object-side compact atoms。

记录：

- 每节点/每对象 policy bytes；
- 总 DRAM 与 SSD 空间；
- policy lookup 次数；
- policy-only SSD reads；
- policy 与 graph-page I/O 是否重叠；
- cache hit ratio；
- false-positive exploration；
- 100M / 1B 外推。

这一轴的目标不是证明“ACL 一定放不进内存”，而是找出在合理预算下真正发生的内存—I/O拐点。

---

### 4.3 轴 C：对象侧权限更新

核心问题：

> object-side grants/revokes 的实际更新模式是否会产生足以支撑系统设计的 SSD 写放大、查询干扰或可见性问题？

必须先收集或构造有依据的更新模型：

- 单对象单角色 grant/revoke；
- 项目目录批量共享；
- 组织调整导致批量对象权限变化；
- 文档移动或继承规则变化；
- 周期性公开/归档；
- 用户侧 role membership 变化。

其中，用户侧 membership/hierarchy 更新优先通过 query-side closure 处理，不能为了制造写放大而展开为每对象更新。

记录：

- logical policy updates/s；
- affected objects/update；
- bytes written/update；
- SSD page writes/update；
- write amplification；
- compaction/merge I/O；
- query p99 interference；
- grant 可见延迟；
- revoke exact-verifier 可见延迟；
- stale-negative 对 authorized recall 的影响。

---

## 五、批准的 Baseline 与门禁

### 5.1 批准 G0 Source Witness

Codex 可以先完成源码/API 审计：

- 在 GateANN、PipeANN-Filter 或目标 DGAI/OdinANN 接入路径中定位 approximate predicate 的使用点；
- 说明该谓词决定的是节点扩展、full-vector I/O、结果入堆还是最终验证；
- 构造最小确定性图，证明 stale grant 是否会形成 exact verifier 无法恢复的 authorized recall loss。

G0 属于方向级正确性验证，不代表 page-addressed delta 已获批准。

### 5.2 批准强自然 Baseline 审计

后续任何 update-plane 设计必须与合理强基线比较。强基线可以使用：

- graph-page prefix key；
- block cache；
- prefix Bloom；
- WAL / WriteBatch；
- batching；
- compaction；
- snapshot/MVCC；
- exact authorization；
- query continuation/refill。

不能通过故意使用 node-keyed 弱实现制造收益。

### 5.3 暂不批准固定 G2 机制门禁

不采用：

```text
决定性指标不足 15% → KILL
```

原因是该阈值缺少原理依据，并且当前还没有确定主导瓶颈与最终机制。

P0 阶段使用相对比较和瓶颈占比：

- 某项成本是否稳定占主导；
- 是否随规模、选择率或 churn 增长；
- 是否存在明显的 I/O/空间/更新拐点；
- 是否能找到现有机制无法同时满足的性质。

完成问题刻画后，再为具体方案制定有依据的 gate。

---

## 六、第一轮实验边界

第一轮仍保持小规模、低风险：

- 数据规模：1M；
- 运行上限：4 小时；
- 新增数据盘空间：不超过 10 GiB；
- RSS：不超过 24 GiB；
- 大工件全部放 `/dev/nvme8n1`；
- 禁止系统盘大写入；
- 不修改完整 DGAI/OdinANN 主路径，优先使用独立 replay/simulator 或最小 instrumentation；
- 不运行 100M/1B 实验，只做结构化外推。

P0 不要求找到最终优化机制，只要求产生可信的成本分解。

---

## 七、P0 的最终输出

Claude 与 Codex 下一轮应共同完成：

### 7.1 ACL workload model

列出：

- 用户数；
- 角色数；
- 每用户角色数；
- 每对象授权角色数；
- 共享度；
- 授权选择率；
- 局部选择率；
- role hierarchy；
- object-side churn；
- query-side membership churn。

### 7.2 Query cost breakdown

比较：

- global graph + exact post-filter；
- GateANN-like predicate precheck / tunneling；
- PipeANN-Filter-like probabilistic precheck；
- HoneyBee-like role partitioning的逻辑模拟；
- 必要时加入 Curator-like low-selectivity fallback。

### 7.3 Update cost breakdown

至少比较：

- 原地对象策略更新；
- 普通 RocksDB/MVCC overlay；
- graph-page-prefix overlay；
- 批量 page summary 重建；
- 查询侧 role closure。

当前不要求提出新方案。

### 7.4 Bottleneck dominance matrix

形成如下结果：

| Workload 区域 | 查询导航 | Policy lookup | Update maintenance | 主导问题 |
|---|---:|---:|---:|---|
| 随机 ACL、低选择率 |  |  |  |  |
| Role 聚簇 |  |  |  |  |
| Shared-core |  |  |  |  |
| 高频 object grant |  |  |  |  |
| 高频 membership update |  |  |  |  |

### 7.5 方向分叉决策

根据 P0 结果只选择一个主轴：

#### Q 路线：查询主导

若 ACL 碎片化导致大量无效遍历与 full-vector I/O，则研究：

- ACL-aware routing；
- ACL-aware graph/page layout；
- role-structured overlay；
- bounded bridge traversal。

#### M 路线：元数据主导

若 policy lookup 和内存占用成为主导，则研究：

- topology/PQ/policy 协同放置；
- page-coupled policy summaries；
- bounded policy cache；
- compressed object-side policy atoms。

#### U 路线：更新主导

若 object-side permission churn 导致明显写放大或查询干扰，则研究：

- asymmetric grant/revoke delta plane；
- page-local maintenance；
- batch/merge scheduling；
- snapshot-aware query continuation。

若三条路径都没有明显主导瓶颈，则应放弃“完整 ACL-on-SSD 系统”包装，回到复合查询地图选择其他查询族。

---

## 八、给 Claude 与 Codex 的下一步任务

### Claude

重点负责：

1. ACL/RBAC workload 模型和真实场景证据；
2. HoneyBee、Veda、Curator 的策略结构抽取；
3. 五类授权分布的生成方法；
4. 查询、对象 grant/revoke、用户 membership update 的语义区分；
5. 三轴 characterization 的 workload 矩阵。

### Codex

重点负责：

1. G0 source witness；
2. GateANN/PipeANN-Filter artifact 的可复现路径；
3. 1M 独立 replay/simulator 的最小接口；
4. 强自然 baseline 能力清单；
5. 每项 instrumentation 的时间、RSS 和数据盘预算。

双方下一轮先提交设计和预算，不立即运行实验。Gpt 审阅后再决定具体执行范围。
