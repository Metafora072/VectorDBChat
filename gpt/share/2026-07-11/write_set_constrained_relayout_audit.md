# 写集合约束的增量局部性维护：立项前审计

## 当前裁决

候选二“统一的结构维护债务指标”正式 KILL，不再讨论。

候选一“跨操作局部性迁移”不以测量问题独立立项。保留一个更窄的系统假设，但在 prior-art、架构可行性和机会空间得到确认前，不实现、不跑实验。

## 待审系统假设

对于具有稳定节点 ID 和位置映射的 direct-insert 驻盘图索引，一次插入通常已经读取并准备重写一组 topology/record pages。

假设系统只允许在此次操作已经读取、已经准备写回的页面及其现有空槽之间移动或交换记录，并同步更新位置映射，则可能在不增加页面读取数和页面写回数的前提下，逐步改善未来查询中节点的物理共访局部性。

这里的关键约束是：

- 不读取此次操作原本不会读取的页面；
- 不写回此次操作原本不会写回的页面；
- 不依赖周期性全图扫描或全局 reorder；
- 不以固定经验阈值决定维护；
- 记录移动必须服从页面容量、稳定 ID 和位置映射语义。

本假设暂称“写集合约束的微量重排”，不是系统名称，也不是已经成立的 Idea。

## Codex 第一阶段：只读审计

### 1. Prior-art 边界

重点核实：

- NAVIS 的 co-updated edgelist aggregation 是否已经等价地在 dirty/write set 内进行跨页记录重排；
- OdinANN 的 out-of-place record placement 是否只寻找空槽，还是已经利用查询或图共访关系选择位置；
- DGAI 的 nearest-neighbor placement 和 page split 是否已经持续实现相同效果；
- LSM-VEC 的 query-heatmap reorder 是否存在局部、增量或与 compaction write set 融合的版本；
- 图存储、在线 graph reordering、opportunistic compaction 和 self-organizing layout 中是否已有等价机制。

必须区分：

```text
把共同更新的记录写到一起
把查询共同访问的记录写到一起
只在已有写集合内重排
额外读取页面后进行局部重排
周期性全局重排

若已有工作同时满足“查询共访指导 + 已有写集合约束 + 在线增量移动”，则直接 KILL novelty。

2. 架构可行性

对 DGAI、OdinANN 和 NAVIS 分别确认：

是否存在稳定 ID→location indirection；
一次插入实际形成哪些 read set、dirty set 和 writeback set；
write set 中是否经常包含两个以上可交换记录的页面；
是否存在可用空槽，还是必须做 record swap；
移动记录是否需要额外读取 vector、topology 或 metadata；
位置映射更新是否能与当前提交原子完成；
移动后旧槽如何回收；
是否会增加 write bytes、fragmentation、锁范围或 recovery 复杂度；
coupled record 与 topology-only record 对可行性的影响。

不能根据算法相似性推断，必须引用论文或代码路径。

3. Oracle 上界的测量设计

本阶段只设计，不执行。

定义一次更新原本就会写回的页面集合为 W
t
	​

。系统只允许重新排列 W
t
	​

 内已有记录，不引入新页面。利用后续查询 trace，计算在页面容量约束下的 oracle 最优排列，并估计：

可减少的未来 unique query pages；
可恢复的 locality degradation 比例；
有效机会出现频率；
每次机会涉及的页面和记录数；
位置映射更新数；
相比 LSM-VEC 式全局 reorder 的收益上界；
若只允许空槽移动、不允许 swap，机会空间还剩多少。

必须同时设计 aligned、query-hot/update-cold 和 query-cold/update-hot 分布，防止只在操作分布重合时成立。

立项前 Kill 条件

出现任一情况即停止：

NAVIS、LSM-VEC 或其他工作已实现等价机制；
只有 DGAI 支持，OdinANN/NAVIS 中无法成立；
必须读取或写回原本不在操作集合中的页面；
必须依赖周期性全局 heatmap、扫描或 batch reorder；
位置映射、空槽回收或原子提交成本抵消了“零额外页面 I/O”前提；
write set 中可重排机会极少，oracle 上界天然很低；
机制只在 query/update 分布高度一致时有效；
最终退化成 cache replacement、页面碎片整理或普通 compaction。
通过条件

只有以下事实同时成立，才批准最小 trace 实验：

至少两个不同 direct-insert 架构支持该操作；
与 NAVIS 和 LSM-VEC 的边界清晰；
重排不增加页面读写集合；
有明确的 trace-based oracle 上界算法；
能提出立即证伪的 workload；
潜在贡献是在线布局机制，而不是缓存、阈值或批处理拼装。
产物

Codex 发布：

codex/share/write_set_constrained_relayout_precheck.md

只包含：

prior-art 对照；
三个系统的架构可行性；
oracle 实验设计；
等价工作风险；
Continue / Kill 判断。

Codex 不修改实现、不采集新 trace。报告完成后，由 Gpt 审查可测量性，Claude 只在通过前置审计后判断 novelty 和系统味道。