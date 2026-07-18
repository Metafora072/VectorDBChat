# Dynamic Vamana M2：Neighbor-Repair Amplification Decomposition

## 1. 裁决

正式接受 M1 matched-size 结果。

M1 已证明：

- DGAI 与 OdinANN 的 publish-save 在 50K、100K、200K、400K 四点均为固定写入量；
- OdinANN 的 load/shadow-copy 同样为固定写入量；
- recurring update-window 差距主要来自 insert-neighbor-repair；
- 两系统 target-only 与 target+neighbor-shared-page 合计均精确为 4096 bytes/replacement；
- insert 差距全部来自 neighbor-repair-only；
- 50K 时差距主要表现为 OdinANN 触及更多 unique pages；
- 400K 时 unique-page 差距缩小，而 page rewrite factor 差距扩大；
- 简单 affine 模型不能解释整个 50K–400K 区间。

M2 只分解 neighbor-repair amplification chain，不设计优化机制，不开始 novelty 宣称。

## 2. 核心问题

M2 必须区分以下三类来源：

1. **Repair fanout**
   - 每次 replacement 实际修改多少个邻居节点；
   - 两个系统是否生成不同数量的反向边修复或剪枝结果。

2. **Page mapping**
   - 被修改的邻居节点映射到多少个不同 4 KiB 页面；
   - 页面差异是否来自记录布局、节点位置分布或同页聚合。

3. **Temporal rewriting**
   - 同一页面是否在不同 replacement 之间被重复提交；
   - 物理 page touches 的增长究竟来自新的页面，还是旧页面反复重写。

不得在这三层尚未闭合前直接提出“缓存”“延迟修复”“批量合并”或“去重写回”方案。

## 3. 第一阶段：源码与配置归一化审计

先形成 DGAI/OdinANN 对照表，引用真实源码位置与运行 manifest，至少包括：

- `R`、搜索宽度、prune alpha、候选上限及其他图构建/更新参数；
- 节点记录字节数；
- 每个 4 KiB 页面可容纳的节点记录数；
- vector、邻接表与 metadata 的共置方式；
- reverse-edge insertion 和 prune 调用链；
- 一次 insert 中邻居修复集合形成的位置；
- 页级 `writes_4k` 去重发生的位置；
- 后台队列、flush 和提交时机；
- 是否存在跨 replacement 的 dirty-page 合并或去重；
- DGAI 与 OdinANN 的差异来自算法、布局、参数还是执行引擎。

若任一关键参数或记录布局不同，必须明确标注。跨系统差异只能继续作为组合差异，不能写成单因素因果关系。

## 4. Instrumentation 层级

Instrumentation 必须使用内存聚合，结束时一次性输出，不逐操作写日志。

### 4.1 每次 replacement 的逻辑计数

记录 exact histogram：

- reverse-edge repair attempts；
- accepted reverse-edge updates；
- pruned/rejected updates；
- mutated neighbor node records；
- distinct mutated neighbor node IDs；
- distinct neighbor page IDs before page-write submission；
- target page是否与neighbor page共页；
- 最终提交的neighbor-only 4 KiB page writes。

每项以：

```text
value -> operation_count
```

形式保存完整整数直方图，并报告 mean、median、p95、p99、max。

### 4.2 Stage 级页面计数

记录：

- neighbor logical page events；
- neighbor submitted page touches；
- stage-unique neighbor pages；
- 每个page被触及次数的完整频率表：
  `touch_count -> page_count`；
- 最热页面的touch count与其占总touches比例；
- logical page event到physical submit的exact closure。

不记录向量内容、邻居ID明细或逐操作日志。

### 4.3 数学分解

对每个系统和规模计算：

```text
repair_nodes_per_replacement
logical_neighbor_pages_per_replacement
submitted_neighbor_pages_per_replacement
nodes_per_logical_page
temporal_rewrite_factor
neighbor_write_bytes_per_replacement
```

其中：

```text
temporal_rewrite_factor
= submitted neighbor page touches / stage-unique neighbor pages
```

并验证：

```text
neighbor-repair-only bytes
= submitted neighbor page touches × 4096
```

若该等式不成立，停止并修复计数定义。

进一步将差异分解为：

```text
repair fanout
× page mapping
× temporal rewriting
```

该分解必须由真实计数构造，不允许加入经验阈值或不可观测项。

## 5. 实验点

只运行四个新点：

| System | N | Prefix |
|---|---:|---|
| DGAI | 50K | `[800000:850000]` |
| DGAI | 400K | `[800000:1200000]` |
| OdinANN | 50K | `[800000:850000]` |
| OdinANN | 400K | `[800000:1200000]` |

每个点必须：

- 从各自同一个 R12 frozen CP10 source 创建独立 fresh clone；
- 不复用 M1 mutable clone；
- 使用 accepted V5 physical profiler，加上新的逻辑计数；
- 保持原始更新顺序、并发、flush 和 I/O 路径不变；
- 通过 active-set、visibility、query smoke、changed-file coverage、ledger closure、source preservation 和 no-OOM 门禁。

M1 的 100K/200K 数据继续作为已接受的物理写轨迹，不因 M2 重跑。

## 6. 必须回答的问题

最终报告必须回答：

1. OdinANN 的 neighbor-repair-only bytes 更高，首先来自更多 mutated neighbor records，还是相同记录映射到更多页面？
2. 50K 的 unique-page 差距是否由每次 operation 的 repair fanout造成？
3. 400K 的高 rewrite factor 是少数热点页主导，还是大量页面普遍重复写？
4. 同一系统从50K到400K，repair fanout是否变化，还是仅 temporal overlap累积？
5. 两系统的页记录布局和每页节点容量是否相同？
6. 在固定replacement trace下，物理写入差异能有多少由：
   - repair fanout；
   - page mapping；
   - temporal rewriting
   分别解释？

如果无法形成无重叠的精确分解，报告冲突与缺失项，不强行给百分比。

## 7. 结论边界

本轮不得声称：

- online visibility导致neighbor repair放大；
- 缓存或延迟写回一定能够消除差距；
- OdinANN算法存在缺陷；
- 已经形成新系统贡献；
- M2结果具有跨实现的普遍性。

只有当某一层在两个规模均稳定占主导，并且存在可修改且不破坏正确性/可见性的机制空间后，才进入 novelty 审查。

## 8. 输出与停止点

输出：

```text
codex/share/2026-07-18/
dynamic_vamana_neighbor_repair_m2_0718.md
```

同时生成 machine-readable summary，绑定：

- M1 scale summary；
- 4 个新 run identity；
- frozen source identities；
- input prefix；
- profiler/instrumented binary identity；
- 完整直方图与分解等式。

四点完成后停止，不自动实现优化原型，不运行更多规模。