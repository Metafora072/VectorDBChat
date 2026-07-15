# 动态驻盘图索引：跨系统问题发现计划

## 当前状态

DGAI 单系统 profiling 正式关闭。现有证据已经否定：

- topology random write 是主要瓶颈；
- append-only adjacency version；
- deferred topology write；
- exact-vector access；
- coordinate acquisition；
- PQ、heap、visited 或单个 search 子阶段可独立形成主方向。

这些阴性结果应保留为边界证据，但不再从 DGAI trace 中继续挖 Idea。

## 新阶段目标

从不同动态驻盘图索引架构之间的共同矛盾出发，寻找跨系统、可测量、未被现有工作解决的问题。

本阶段先建立事实地图，不写系统设计，不跑新实验。

## Codex：事实与代码边界

请审阅至少以下代表性系统及其论文/公开代码：

- DGAI
- OdinANN
- FreshDiskANN
- LSM-VEC
- IP-DiskANN
- NAVIS

只记录能够由论文或代码直接支持的事实。对每个系统整理：

1. 更新模型：direct insert、buffer、merge、rebuild 或其他；
2. topology 与 vector 的物理布局；
3. 新节点如何发现邻居；
4. reverse edge 如何建立、剪枝和修复；
5. 单次更新修改哪些持久化对象；
6. 查询与更新是否复用读取、缓存和计算；
7. 写入单位、回收单位和维护周期；
8. 长期更新后如何控制 recall、空间和局部性退化；
9. 论文声称的主要瓶颈及其证据；
10. 尚未解决的 tradeoff，而不是单个函数缺陷。

重点形成三类架构张力：

```text
query locality ↔ update locality
immediate visibility ↔ amortized maintenance
graph quality ↔ update I/O / memory / rebuild cost

不要把普通 batching、cache、阈值调参、并发优化或硬件替换包装成开放问题。

输出要求

发布：

codex/share/cross_system_dynamic_ann_problem_map.md

报告包含：

系统事实矩阵；
三类架构张力；
已被 prior work 占据的设计空间；
最多三个仍可能开放的“问题”，只写问题，不写完整方案；
每个问题对应的最小验证实验和立即 Kill 条件；
哪些系统可以实际运行，哪些只能做论文/代码审计。
后续协作

Codex 发布事实地图后：

Claude 从论文 novelty 和系统味道角度，独立判断最多三个候选问题，也可以明确回答“当前没有合格方向”；
Gpt 从可测量性、因果闭环和实验门禁角度独立审查；
PZ 根据研究目标、机器资源和时间决定是否选择一个候选进入 profiling。

只有同时满足以下条件，候选才允许进入实验：

至少存在于两个不同架构的系统；
不是 DGAI 特有实现缺陷；
有明确成本、退化或不可兼得关系；
可以通过一个低成本实验快速证伪；
novelty 不依赖“首次使用某通用技术”；
预期贡献不是多个小优化的拼装。

在事实地图完成前，不修改任何系统，也不启动新的大规模实验。