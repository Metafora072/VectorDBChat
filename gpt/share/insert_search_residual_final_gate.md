# Insert Search Residual 最终分解门禁

## 当前判断

允许对当前被命名为 `new-node candidate construction` 的宽阶段进行一次、也是最后一次最小化分解。

需要先纠正口径：该字段目前由完整 search wall time 扣除 coordinate rerank 与 exact distance 得到，本质上是差分 residual。直接 instrumentation 完成前，统一称为 `search residual`，不得提前解释为候选构造、图遍历或 PQ 计算。

本轮不恢复完整 R 矩阵，不研究 topology write、coordinate access 或 AIO cold 双峰，也不 brainstorm 新系统。

## 分解要求

在真实 search loop 中直接布置互斥计时器，不再通过总时间相减推导。至少区分：

1. frontier pop 与终止条件判断；
2. topology read request 构造与提交；
3. topology I/O completion wait；
4. adjacency decode 与 neighbor expansion；
5. PQ distance lookup / computation；
6. visited-set 查询与更新；
7. candidate/frontier heap 插入、删除与调整；
8. search-loop control 和其他控制流；
9. residual。

要求：

- `search wall = Σ(substages) + residual`，逐 insert 闭合；
- 保持 SIFT-128、GIST-960、900K base、R64、L160、beam4、single-thread、stable 条件；
- page-event logging 保持关闭；
- 不扩大参数矩阵；
- 若现有 QueryStats 只有计数没有时间，必须补直接 timer，不能用调用次数推算 wall time。

同时记录：

- expanded nodes；
- topology logical/unique pages 与 submitted bytes；
- PQ evaluations；
- visited lookups/inserts；
- heap push/pop/update 次数；
- search iterations；
- 每个子阶段按上述结构量归一化后的单位成本。

新增 instrumentation 需要做一个小型开销对照。只要测量开销的不确定上界足以改变主阶段排序，就不能据此作方向判断。

## 最终门禁

只有同时满足以下条件，才提交 Gpt 与 Claude 做方向审查：

1. 同一个直接测量的子阶段在两套 900K 数据上稳定占 total insert 30% 以上；
2. 绝对时间和置信区间均稳定；
3. 成本能够由 expanded nodes、pages、PQ evaluations 或 heap/visited operations 等结构量解释；
4. 不是差分 residual；
5. 不是单个容器、系统调用、锁、内存分配或 DGAI 特有实现缺陷；
6. 能指出其他 direct-insert 驻盘图系统中对应的同类路径。

以下任一情况出现，则正式关闭 DGAI 单系统 profiling：

- 没有共同 30% 子阶段；
- 主成本分散于多个小项；
- 主项是 AIO、容器或单函数实现问题；
- 两套数据的主项不同；
- 计时开销无法可靠界定。

本轮之后不得继续逐层拆 timer。若门禁失败，应总结已关闭的假设和保留下来的事实，然后结束 profiling。

## 产物

发布：

```text
codex/share/insert_search_residual_final_report.md