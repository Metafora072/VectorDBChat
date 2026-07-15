# VAQ 语义约束物理设计：G0 Finding Gate

## 当前裁决

原始“VAQ physical-design advisor”正式关闭，不直接实现 advisor。

批准一个更窄的 G0 finding gate，验证以下结构性命题：

> ANN 的局部 Recall@k 不是 vector-augmented analytical query 的充分质量指标。不同物理设计可能产生相同数量、但分布不同的 ANN false negatives；这些错误经过 join multiplicity、group distribution 和 aggregate 后，会形成不同的端到端 answer error，使 relational design 与 vector design 无法彼此独立优化。

当前不声称该命题成立，也不批准新的索引、advisor 或 cost model。

---

## 与现有工作的边界

必须正面对比：

- Exqutor：VAQ cardinality、join order 和执行计划；
- MINT：storage/recall 约束下的 multi-vector index tuning；
- BoomHQ：vector–scalar correlation 与运行时策略；
- PostgreSQL-V：integrated 与 decoupled vector storage；
- 传统 AutoAdmin / CoPhy：关系型物理设计搜索。

本候选唯一允许保留的差异是：

```text
局部 ANN 质量
        ↓
false-negative 的数据分布
        ↓
join / group / aggregate 误差传播
        ↓
端到端 quality-constrained physical design

若最终只是在传统 advisor 中增加 recall 字段，直接 Kill。

G0-0：范围冻结

本轮禁止：

开发 advisor；
设计新的 ANN index；
修改 HNSW、IVF 或 DiskANN 算法；
加入 materialized view、buffer manager、tiering 等额外旋钮；
一开始枚举大规模物理设计空间；
用 synthetic correlation 作为唯一证据。

先只研究两个耦合维度：

global vector index 与 attribute-partitioned local indexes；
scalar access structure 与 vector access structure 的组合。

运行时使用 Exqutor 或等价的强 query optimizer，避免把普通 join-order 错误误判为物理设计问题。

G0-1：数据与查询

至少使用两类数据。

数据集 A：标准 VAQ workload

复用 Exqutor 的 TPC-H/TPC-DS vector-augmented workload，不自行构造更弱 benchmark。

数据集 B：真实相关数据

选择一个公开数据集，同时具有：

文本或图像 embeddings；
categorical/numerical scalar attributes；
自然形成的 vector–scalar correlation；
可定义 join、group 和 aggregate。

不得只通过人工打乱或复制标签制造相关性。

查询族

至少覆盖：

scalar filter → ANN → join；
ANN range/threshold → join → group-by；
ANN top-k → fact-table join → COUNT/SUM/AVG；
ANN 结果按 category/tenant/time 分组并选择 top groups。

每类查询必须有 exact-vector 或高质量 exhaustive reference answer。

G0-2：受控物理设计空间

第一轮只枚举少量真实可运行设计：

D0: global ANN index + post-filter
D1: global ANN index + scalar pre-filter
D2: attribute-partitioned local ANN indexes
D3: scalar structure + global ANN 的联合执行

ANN 只选择当前环境中可公平运行的两类，例如 HNSW 与 IVF。

每个设计记录：

index bytes；
build time；
update cost；
query latency；
local Recall@k；
candidate count；
join input cardinality；
downstream answer quality。

比较设计时必须控制：

相同 storage budget；
相同 update/build budget；
相同端到端 quality SLO，或报告完整 Pareto frontier。

不得只把更大的 index 与更小的 index直接比较。

G0-3：错误传播事实

对每条 query 记录 ANN false negatives 的分布，而不只记录数量：

所属 join key；
group/category；
join multiplicity；
measure value；
是否集中在高权重或稀有 group；
是否改变 top-group 排名。

报告：

local Recall@k；
join tuple recall；
group coverage；
COUNT/SUM/AVG relative error；
top-group rank agreement；
false-negative concentration；
query-level paired confidence interval。

核心测试是：

是否存在两个真实物理设计，其 local Recall@k 在统计上相当，但下游 answer quality 明显不同？

若不存在，普通 recall 已足够，直接 Kill。

G0-4：不可分离性 Oracle

不实现 MINT、CoPhy 或新 advisor。利用小设计空间直接枚举，构造五个 oracle baseline。

Vector-local oracle

只根据 vector latency、storage 和 local recall 选择设计。

Relational-local oracle

假设 vector access 语义固定，只根据 exact relational cost 选择 scalar design。

Sequential V→R

先确定 vector design，再选择 relational design。

Sequential R→V

先确定 relational design，再选择 vector design。

Joint semantic oracle

直接以以下约束选择联合设计：

latency / throughput
storage
build/update cost
end-to-end answer-quality SLO

重点不只是比较平均延迟，而是检查：

最优设计排序是否随端到端 quality metric 改变；
V→R 与 R→V 是否选择不同设计；
sequential baselines 是否遗漏 joint oracle 的 Pareto 点；
是否存在一个简单的 recall/selectivity/correlation 规则即可复现 joint oracle。
Continue 条件

只有以下结构性现象同时成立，才进入 advisor 架构讨论：

在两套数据上，相近 local recall 的真实物理设计产生统计显著不同的 downstream answer quality；
差异出现在至少两类 join/aggregate query，而非单个特制模板；
物理设计改变了 false-negative 在 join key 或 group 上的分布，而不仅是改变错误总数；
vector-local 与 relational-local objective 出现可解释的设计排序反转；
joint semantic oracle 存在 sequential baselines 无法达到的 Pareto 点；
该 Pareto 差距明显大于运行噪声，并且不能由 Exqutor plan fix、BoomHQ parameter tuning 或单独 MINT tuning消除；
简单规则在 held-out queries 或第二数据集上无法接近 joint oracle；
结果指向一个新的 semantic what-if abstraction，而不是更多 index knobs。

通过后仍只进入 architecture review，不自动批准完整系统。

Kill 条件

出现任一情况即停止：

local Recall@k 足以稳定预测 join/aggregate answer quality；
不同设计的 answer error 差异落在统计噪声内；
最优设计始终是同一个固定组合；
任一 sequential baseline 已落在 joint oracle 的同一 Pareto frontier；
差异主要来自 Exqutor 已处理的 cardinality 或 join-plan 错误；
差异主要来自 HNSW/IVF 参数，属于 MINT/BoomHQ 空间；
只在 synthetic correlation 中成立；
只对一个 query family 成立；
exhaustive enumeration 需要构建大量不可复用索引，成本已接近未来 advisor 的全部工作；
最终贡献只能写成“将 end-to-end quality 加入 cost function”。
执行顺序
workload/data preflight
        ↓
小设计空间正确性 sanity
        ↓
相同 local recall 下的 error-propagation 检验
        ↓
若失败：KILL
        ↓
sequential vs joint oracle
        ↓
若无 Pareto gap：KILL
        ↓
第二数据集与 held-out queries
        ↓
Gpt + Claude architecture review

前一阶段失败时不得继续扩大设计空间。

Codex 产物

发布：

codex/share/vaq_semantic_physical_design_g0_report.md

内容依次包括：

workload 与真实数据集；
实际运行的物理设计及预算守恒；
local recall 与 downstream quality 的对应关系；
false-negative 分布；
design ranking reversal；
sequential 与 joint oracle Pareto frontier；
简单规则 baseline；
Continue-to-architecture-review 或 Kill。

本轮不实现 advisor，不把 exhaustive oracle 包装成系统。