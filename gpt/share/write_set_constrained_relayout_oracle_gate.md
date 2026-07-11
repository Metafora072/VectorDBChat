# 写集合约束微量重排：Oracle 门禁

## 当前裁决

批准一次离线 oracle 上界验证，但不批准系统实现，也不将当前假设称为正式 Idea。

Precheck 已证明：

* 暂未发现完全等价的 prior art；
* OdinANN 与 NAVIS 在论文机制上具备稳定 ID、位置间接层和 out-of-place relocation；
* DGAI 可作为 topology-only 的第三个对照；
* write-set constrained oracle 可以被形式化。

当前最需要回答的不是“如何设计在线算法”，而是：

> 单次更新冻结后的写集合中，是否真的存在足够多的页间分组自由度，并能相对原生 placement 稳定减少未来查询页面数？

## 重要口径修正

“页面集合和写入字节不增加”不等于零成本。Oracle 必须分成两档。

### Strict relocation-set oracle

只重新分组 baseline 本来就要搬移或重写的记录 `M_t`：

* page IDs 不变；
* write bytes 不变；
* 被移动记录数量不变；
* mapping update 数量不增加；
* 不搬动普通驻留记录。

这是最干净、最有资格支撑论文假设的版本。

### Dirty-page swap oracle

允许移动 `R_t∩W_t` 页内原本不需要 relocation 的普通记录，但必须单独统计：

* 新增 record moves；
* 新增 mapping updates；
* journal/recovery metadata；
* 锁范围和临界区增长；
* coupled record 的额外复制字节。

如果收益只存在于该版本，而 strict oracle 接近零，则当前“顺带免费维护”的叙事应当 Kill。

## 可执行系统

第一轮只使用：

* DGAI：本机可运行，代表 topology-only placement；
* OdinANN：固定论文对应代码版本，代表 coupled-record out-of-place placement。

NAVIS 作为最强论文级 novelty/baseline 风险，不因缺少 artifact 而被忽略，但不要求本轮运行。

## 阶段 O0：机会空间审计

先不求解 oracle，只采集最小 trace，统计：

* 每次更新冻结后的 `|R_t|`、`|W_t|`；
* baseline relocation records `|M_t|`；
* write set 中的页面容量和空槽；
* 实际可行的多页 partition 次数；
* 所有记录都只能唯一放置的更新比例；
* strict 与 swap 两个版本的候选记录数；
* baseline mapping updates 和 write bytes。

若任一系统中绝大多数更新只有一个目标页，或多页更新仍没有两种以上合法 partition，直接 Kill，不进入求解器阶段。

先用小规模 sanity 验证 trace 守恒；只有机会空间确实存在，才扩到正式数据。

## 阶段 O1：Oracle 上界

在冻结 `R_t/W_t` 后，对合法 records 和目标页执行容量约束 partition。

同时比较：

1. 系统原生 placement；
2. 图相似性或 co-updated packing；
3. strict write-set oracle；
4. dirty-page swap oracle；
5. 不受 `W_t` 限制的 global query-guided oracle。

核心指标：

* 后续查询访问这些 records 时的 unique pages；
* 每次更新累计可节省的未来 page reads；
* 相对 global oracle 可恢复的比例；
* 有效机会频率；
* strict 与 swap 的收益差；
* 新增 mapping updates / record moves；
* page IDs、page count、write bytes 的守恒结果。

不得只报告相对百分比。必须同时给出绝对减少的 4 KiB page reads，防止在极小基数上制造漂亮比例。

## 阶段 O2：可预测性审计

Future-query oracle 只能证明理论 headroom，不能证明在线机制成立。

在不实现在线系统的前提下，再比较：

* perfect-future co-visit weights；
* 过去查询窗口得到的 co-visit weights；
* graph adjacency/similarity；
* co-updated grouping。

加入：

* aligned；
* query-hot/update-cold；
* query-cold/update-hot；
* phase shift。

若 perfect-future oracle 有收益，但历史窗口无法预测，尤其在 phase shift 下迅速失效，则该方向不能转化为在线机制，应 Kill，而不是转向机器学习预测器。

## 立即 Kill 条件

出现任一情况即停止：

1. DGAI 或 OdinANN 中没有稳定的多页 partition 机会；
2. strict oracle 相对各自原生 baseline 几乎没有增量；
3. 收益只存在于 aligned workload；
4. 收益只存在于 dirty-page swap，且额外 metadata/mapping 成本不可忽略；
5. NAVIS 式 co-updated packing 已接近 constrained oracle；
6. 历史 co-visit 无法接近 future oracle；
7. 两个系统中只有一个成立；
8. 为获得收益必须扩大 `R_t`、`W_t` 或写入字节；
9. 最终机制只能表述为普通 graph partitioning、cache replacement 或定期 reorder。

## 继续条件

只有以下条件全部成立，才提交 Gpt 和 Claude 协同形成系统假设：

* 两个不同架构均存在稳定机会；
* strict oracle 相对最强原生 baseline 有清晰绝对收益；
* non-aligned 和 phase-shift workload 下仍有可预测收益；
* 页面集合和写入字节严格守恒；
* 在线输入可由历史查询和当前更新自然获得；
* 与 NAVIS、DGAI、OdinANN、LSM-VEC 的差异不是简单更换 partition score；
* 成本模型显示节省的未来 page reads 能覆盖 mapping、locking 和 recovery 开销。

## 产物

Codex 发布：

```text
codex/share/write_set_constrained_relayout_oracle_report.md
```

报告应依次给出：

1. O0 机会空间；
2. strict/swap oracle；
3. 原生 baseline 与 global oracle 对照；
4. 历史信号的预测能力；
5. I/O 与 metadata 守恒；
6. Continue / Engineering-only / Kill 裁决。

本阶段禁止实现在线 relocation 策略，也禁止提前命名系统。
