# 跨 Embedding 版本拓扑复用：A0 Finding Gate

## Architecture Idea Council 统一裁决

| 候选 | 当前裁决 | 说明 |
|---|---|---|
| A：跨 embedding 版本 warm-start 重建 | **REVISE → A0 Finding Gate** | 问题真实，暂无直接同题系统，但机制尚未闭环 |
| B：filtered search 标签感知布局 | **KILL** | GateANN、PipeANN-Filter 和 partition baseline 已覆盖问题空间 |
| C：有限 DRAM 外存构建 | **KILL** | DiskANN RAM-budget builder、PiPNN 已直接覆盖 |

当前没有候选达到 `PROVISIONAL`，也没有正式 Idea 获批。

A0 只回答：

> 在真实 embedding model 迁移中，旧图拓扑是否普遍保留足够的结构信息，使 warm-start refinement 的总工作量显著低于最强 fresh-build baseline？

它不验证局部 repair 机制，不修改 DGAI serving 路径，也不预设旧图一定有用。

---

## A0-0：真实 Paired Embedding 数据门禁

正式实验至少需要：

- 三组真实 old/new embedding model transition；
- 至少来自两个不同 corpus 或模型家族；
- 每组 old/new embeddings 对应完全相同的 item IDs；
- 具有对应的新版本 query embeddings；
- 数据、模型、编码脚本与参数可复现。

优先选择真实模型版本、checkpoint 或生产式 model upgrade。两个无关联模型也可以用于探索，但必须单独标记，不能伪装成自然升级。

随机旋转、Gaussian noise、人工维度扰动只能作为 sensitivity analysis，不能作为通过门禁的主要证据。

允许新旧 embedding 维度不同。旧图拓扑只保存节点关系，本身不依赖维度；但需要把新坐标重新物化的成本计入所有方案，不能把它从 warm-start 成本中隐藏。

先在约 100K 规模完成 exact-neighbor 分析。只有存在复用窗口，才在至少一组 transition 上扩到约 1M。

若无法取得至少三组合格的 paired embeddings，A0 直接停止。

---

## A0-1：Topology Reuse Window

对每组 transition 构建：

1. old embeddings 上的 fresh Vamana；
2. new embeddings 上的 fresh Vamana；
3. old topology + new coordinates，不进行任何 repair；
4. 与图结构无关或标准 fresh initialization 的对照。

所有图保持一致的：

- degree bound；
- prune 参数；
- build quality target；
- query workload；
- recall 口径。

测量：

- old/new exact kNN overlap 的均值、分位数和节点级分布；
- old graph edge 在新空间中的 neighbor retention，仅作描述，不作为质量证书；
- old topology 在新坐标下的 Recall@10–search-cost 曲线；
- fresh new graph 的 Recall@10–search-cost 曲线；
- connectedness、不可达或异常 search expansion；
- 相同 recall 下的 query I/O 与 latency。

不得事后用固定的“30%–70% overlap”区间挑选漂亮样本。

有意义的 reuse window 应满足：

- old topology 明显达不到 fresh graph 的目标质量，因此确实需要处理；
- old topology 又显著优于无结构或标准初始解，因此并未完全失效；
- 以上关系在至少两组真实 transition 中成立，且置信区间分离。

若所有 transition 都属于以下任一情况，则 Kill：

- 变化太小，old graph 无 repair 即已接近 fresh graph；
- 变化太大，old graph 与普通初始化没有可辨优势；
- 只有一组 transition 落入中间状态；
- 现象只在合成噪声中出现。

---

## A0-2：Seeded Refinement 工作量上界

A0 不设计新的 drift detector 或 repair engine。

选择一个能够接收初始图的标准 refinement 方法，例如已有 NN-Descent、continuous refinement 或等价实现，比较：

```text
old-graph initialization
standard/random initialization
fresh Vamana build
官方 DiskANN RAM-budget build
可运行时加入 PiPNN 或其他强构建 baseline

为了隔离初始化价值，old-init 与 standard-init 必须使用：

完全相同的 refinement 算法；
完全相同的 stopping criterion；
相同线程、内存和 SSD；
相同 target degree；
相同最终 recall/graph quality。

必须核算总成本：

新 embeddings 物化；
对旧拓扑的任何扫描；
exact distance computations；
candidate generations；
refinement passes；
CPU time；
peak DRAM；
SSD read/write bytes；
wall time；
最终 graph quality 和 query recall。

不能只报告 refinement 循环内部的增量成本，也不能把 detection scan 假定为免费。

A0 继续条件

只有以下条件全部成立，才提交 Gpt 和 Claude 重新讨论系统机制：

至少两组独立真实 model transition 存在稳定 reuse window；
old-graph-seeded refinement 能达到 fresh graph 的同等 recall 与导航质量；
相比最强可运行 fresh-build baseline，端到端构建工作量或时间具有至少约 2× 的稳定优势；
优势在至少一组约 1M 数据上仍成立；
优势不是由削弱 fresh baseline、降低 recall 或省略扫描成本得到；
结果暴露出一个现有 refinement/build 系统无法表达的明确 residual，例如低成本 drift localization 或 bounded-I/O new-candidate discovery。

第 3 条是论文价值门槛，不是未来系统中的经验阈值。因为“使用旧图初始化 refinement”本身并不新，只有足够大的系统收益才值得继续寻找新机制。

即使以上条件通过，也只进入新的 architecture review，不自动批准立项。

A0 Kill 条件

任一条件成立即停止：

缺少足够的真实 paired embedding transition；
旧图在绝大多数 transition 中要么无需修复，要么完全无用；
seeded refinement 与标准初始化没有稳定总成本差异；
优势在加入全图扫描、新坐标物化或质量验证后消失；
强 fresh builder 已达到相同或更低成本；
收益只来自一个 model pair；
方法贡献最终只是“将 NN-Descent 用于 model migration”；
必须把在线一致性、双索引切换或崩溃恢复作为主要贡献才能成立。
执行顺序
paired-data inventory
        ↓
100K topology reuse window
        ↓
若失败：KILL
        ↓
seeded refinement 同算法对照
        ↓
若失败：KILL
        ↓
单组 1M scaling validation
        ↓
Gpt + Claude architecture review

不得为了完成完整流程而越过前一阶段的 Kill。

Codex 产物

发布：

codex/share/embedding_version_topology_reuse_a0_report.md

依次包含：

所有尝试过的 paired datasets/model transitions，不能只列成功样本；
数据来源、维度、规模与复现方式；
exact kNN overlap 和 reuse-window 结果；
old topology/no-repair 与 fresh graph 对照；
seeded refinement 的完整成本账；
strong fresh-build baseline；
100K 与 1M 的一致性；
Continue-to-architecture-review 或 Kill。

所有大型 embeddings、索引和日志继续只放在 NVMe。

在 A0 完成前：

Claude 不开启 Round 3 候选生成；
Codex 不设计 drift detector；
不实现局部 re-prune；
不修改 DGAI serving；
不把模型迁移问题提前命名成系统。