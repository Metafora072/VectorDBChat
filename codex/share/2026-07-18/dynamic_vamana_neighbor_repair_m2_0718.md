# Dynamic Vamana M2：Neighbor-Repair Amplification Decomposition

## 范围与停止边界

M2 只运行 DGAI/OdinANN 的 50K 与 400K 四个 fresh-clone 点，复用 accepted V5 physical profiler，并新增结束时一次性输出的内存聚合逻辑计数。目标是把 neighbor-repair-only 写入拆成 repair fanout、page mapping 与 temporal rewriting；不实现缓存、延迟写回、批处理或其他优化，不运行额外规模。

## 源码与配置审计

启动前静态审计曾将 DGAI driver 中显式构造的 `R=32`、`L=75`、`C=160`、`beam_width=16` 误当作双系统公共配置。50K 运行时审计纠正了这一假设。DGAI 实际为 `R=32`、`L=75`、`C=160`、`beam_width=16`、`alpha=1.2`，记录长度为 644 B，每个 4 KiB 页容纳 6 条记录；OdinANN 从索引 metadata 与 load 路径取得的实际配置为 `R=96`、`L=128`、`C=384`、`beam_width=8`、`alpha=1.2`，记录长度为 900 B，每页容纳 4 条记录。两个系统都保持原始输入 replacement 顺序和每批 128 条的 insertion kernel，但关键图参数与记录布局并不相同。同一 run 内配置变化会触发 gate 失败。

DGAI 经 `do_beam_search()` 与 `prune_neighbors()` 形成 `new_nhood`，再逐邻居追加 target，必要时执行本实现的 PQ 或 delta prune，最终由 `writes_4k` 在单次 replacement 内按页去重，走 libaio 与 wbc-write。OdinANN 经 `do_pipe_search()` 与 `prune_neighbors()` 形成 `new_nhood`，还包含 entry-point removal 与 `R+1 → R` 调整，逐邻居使用其 `delta_prune_neighbors()`，随后由 `writes_4k` 单操作去重并进入 io_uring background writer。两者只有 4 KiB 页大小与 `alpha` 相同，图参数、记录容量、搜索、prune、位置分配和执行引擎均存在差异，所以跨系统结论严格视为组合差异，不能作为任一单因素的因果证据。

Instrumentation 在每个 `insert_in_place` 内只构造局部计数，随后以一次互斥内存聚合更新完整整数直方图与 page-touch frequency；不记录邻居 ID、page ID 明细或逐操作日志。它分别统计 scheduled repair attempt、target 最终保留的 accepted reverse edge、真正 adjacency-mutated record，避免把被 prune 后仍因 relocation 写回的记录混作有效反向边。每次操作的 neighbor-only logical page set 必须与 `writes_4k` 提交页集合完全一致，最终还必须满足 physical neighbor-repair-only bytes = submitted touches × 4096。

## 启动前资源预算

独立 build 位于项目 NVMe 的 `neighbor-repair-m2-v1-r01`。启动前项目 NVMe 可用约 973 GiB、MemAvailable 约 240 GiB；四个 clone、结果与 build 预计新增 64–72 GB，build 预计 5–10 分钟，四点严格串行 controller wall 预计 25–40 分钟。每点使用 40 GiB cgroup memory limit 与 2 小时 hard limit，任一 formal/logical closure gate 失败即停止。

## 结果

M2 于 `2026-07-18 13:51:50 UTC+8` 完成。DGAI 与 OdinANN 的 50K、400K 四点均通过原 physical formal gate 和新增的 11 项 M2 gate。每点都满足 replacement 数量、完整直方图 operation 数量、repair fanout 恒等式、逐操作 logical/submit page set、physical bytes、运行时配置稳定性、active-set、visibility、query smoke、changed-file coverage、ledger closure、source preservation 与 no-OOM 要求。总体 machine summary 为 `results/pilot3_sift10m_neighbor_repair_m2_r01/m2_summary.json`，SHA-256 为 `2bbadbe5...c5b24`。

### 原始结果

| System | N | R/L/C/beam | record/page | attempts / repl. | accepted / repl. | mutated / repl. | neighbor-only pages / repl. | temporal rewrite | neighbor bytes / repl. |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| DGAI | 50K | 32/75/160/16 | 644 B / 6 | 32.000 | 19.171 | 23.100 | 5.469 | 1.037 | 22,402 B |
| DGAI | 400K | 32/75/160/16 | 644 B / 6 | 32.000 | 18.930 | 21.110 | 8.563 | 1.990 | 35,076 B |
| OdinANN | 50K | 96/128/384/8 | 900 B / 4 | 96.000 | 47.255 | 74.970 | 31.397 | 1.244 | 128,602 B |
| OdinANN | 400K | 96/128/384/8 | 900 B / 4 | 96.000 | 46.612 | 54.308 | 43.128 | 4.999 | 176,651 B |

表中 `attempts` 是 `new_nhood` 中会被调度写回的邻居记录数，`accepted` 表示 prune 后仍包含新 target 的反向边，`mutated` 表示最终邻接数组与写入前不同的记录。`neighbor-only pages` 是排除 target/shared page 后的单操作 distinct logical page 数，也与最终提交的 4 KiB page 数逐操作完全一致。四点的 physical neighbor-repair-only bytes 分别为 `1,120,112,640`、`14,030,266,368`、`6,430,113,792`、`70,660,304,896` bytes，均精确等于 submitted touches 乘以 4096。

完整整数直方图保存在各点 `neighbor_repair_logical.json`。下表按 `mean / median / p95 / p99 / max` 给出门禁要求的摘要。每个点的 `distinct_mutated_neighbor_node_ids` 与 `mutated_neighbor_node_records` 完全相同，说明同一 replacement 内没有重复计入同一 mutated neighbor ID。

| Metric | DGAI 50K | DGAI 400K | OdinANN 50K | OdinANN 400K |
|---|---|---|---|---|
| repair attempts | 32/32/32/32/32 | 32/32/32/32/32 | 96/96/96/96/96 | 96/96/96/96/96 |
| accepted updates | 19.17/19/27/29/32 | 18.93/19/27/29/32 | 47.26/47/74/83/96 | 46.61/46/73/83/96 |
| pruned/rejected | 12.83/13/21/24/30 | 13.07/13/21/24/31 | 48.74/49/73/80/94 | 49.39/50/73/80/95 |
| mutated records/IDs | 23.10/23/29/30/32 | 21.11/21/28/30/32 | 74.97/76/92/95/96 | 54.31/54/82/91/96 |
| distinct neighbor pages | 6.47/6/8/9/11 | 9.52/10/11/11/11 | 31.99/32/40/43/48 | 43.73/46/48/48/48 |
| neighbor-only submitted pages | 5.47/5/7/8/10 | 8.56/9/10/10/10 | 31.40/31/40/42/48 | 43.13/45/48/48/48 |
| target-page shared flag | 0.999/1/1/1/1 | 0.954/1/1/1/1 | 0.588/1/1/1/1 | 0.599/1/1/1/1 |

### 页面覆盖与时间重写

| System | N | logical neighbor events | neighbor-only touches | stage-unique neighbor-only pages | rewritten-page share | touch share from rewritten pages | top 1% touch share | top 10% touch share | hottest-page touches/share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DGAI | 50K | 323,422 | 273,465 | 263,656 | 3.55% | 7.01% | 2.10% | 13.23% | 5 / 0.00183% |
| DGAI | 400K | 3,806,783 | 3,425,358 | 1,721,378 | 61.59% | 80.70% | 2.82% | 20.46% | 23 / 0.000671% |
| OdinANN | 50K | 1,599,269 | 1,569,852 | 1,262,225 | 20.53% | 36.10% | 2.86% | 19.17% | 13 / 0.000828% |
| OdinANN | 400K | 17,490,840 | 17,251,051 | 3,451,116 | 92.71% | 98.54% | 2.73% | 20.35% | 43 / 0.000249% |

400K 的高 rewrite factor 不是由少数极热页面主导。OdinANN 中 92.71% 的 stage-unique neighbor-only pages 被触及至少两次，贡献 98.54% 的 touches；但最热页只占 `0.000249%`，top 1% pages 只占 2.73% touches，top 10% 只占 20.35%。DGAI 也呈相同方向。观察事实支持大量页面普遍重复写，不支持少数热点页解释。

### 精确乘法分解

为避免把 accepted edge 或真正 mutated record 与实际物理写回集合混淆，physical page-touch 的无重叠分解使用 scheduled repair attempt。对每个系统与规模，以下等式逐计数成立：

$$
\frac{\text{submitted touches}}{N}
=
\frac{\text{scheduled records}}{N}
\times
\frac{\text{stage-unique pages}}{\text{scheduled records}}
\times
\frac{\text{submitted touches}}{\text{stage-unique pages}}.
$$

三个因子依次表示 repair fanout、跨 stage 的 unique-page mapping 和 temporal rewriting。它们是计数恒等式，不等价于单因素干预的因果贡献。跨系统比值如下。

| N | repair fanout ratio | page-mapping ratio | temporal-rewrite ratio | exact product | observed physical ratio |
|---:|---:|---:|---:|---:|---:|
| 50K | 3.000 | 1.596 | 1.199 | 5.741 | 5.741 |
| 400K | 3.000 | 0.668 | 2.512 | 5.036 | 5.036 |

50K 的 unique-page 差距首先包含 3× scheduled fanout，随后由 OdinANN 更低的页面记录容量及组合 page mapping 再放大 1.596×，temporal rewriting 追加 1.199×。400K 时 fanout 仍为 3×，但 stage unique pages 已发生覆盖饱和，page-mapping ratio 降至 0.668×；更高的 2.512× temporal rewriting 使最终差距仍为 5.036×。accepted-repair ratio 在两个规模分别为 2.465× 与 2.462×，mutated-record ratio 则从 3.245× 降至 2.573×，所以不能把 3× scheduled fanout 直接写成 3× 有效图修改。

## 问题回答与结论边界

OdinANN 的 neighbor-repair-only bytes 更高，首先来自更大的 scheduled repair set，而不是相同记录集合映射到更多页。它每次固定调度 96 条邻居记录，DGAI 为 32 条；50K 时实际 mutated records 仍高 3.245×。记录布局也不相同，OdinANN 的 900 B 记录使每页只能容纳 4 条，DGAI 的 644 B 记录每页容纳 6 条，因此 fanout 与 page mapping 同时存在，无法把跨系统差距归为单一算法或布局因果。

50K 的 unique-page 差距主要由 repair fanout 发起，并被 page mapping 进一步放大。400K 的高 rewrite factor 来自广泛页面重复触及，而非少数热点。同一系统从 50K 到 400K 时 scheduled fanout 不变，accepted 与 mutated fanout 反而略降；增长来自每 replacement 涉及更多 distinct pages，以及 stage 范围扩大后的 temporal overlap。

在固定 replacement trace 下，物理差距可以用上表的三个乘法因子无重叠、逐计数闭合，但这些因子描述的是当前两个完整实现的组合。M2 不支持 online visibility 导致放大、缓存或延迟写回必然有效、OdinANN 算法存在缺陷、已形成新系统贡献或结论可跨实现普遍化。由于 `R/L/C/beam`、记录布局、搜索、prune、位置分配和 I/O(Input/Output，输入输出) 引擎同时不同，任何单因素因果判断都需要额外的 matched-parameter 或 matched-layout 实验并由后续 gate 单独授权。

Instrumentation 保持 update thread 数量、输入 trace、flush API 与 physical I/O 路径不变，但每个 replacement 在 I/O 数据准备后增加一次受互斥保护的内存聚合。该测量会引入运行时开销并可能轻微扰动线程调度，因此 wall time 只作描述性证据，不用于系统性能结论。四点 physical neighbor bytes 与 M1 同规模结果保持接近并全部独立闭合，但这不能消除所有调度扰动风险。

## 时间、空间与停止状态

| System | N | ingest | publish | E2E | peak RSS |
|---|---:|---:|---:|---:|---:|
| DGAI | 50K | 50.82 s | 19.41 s | 70.24 s | 3,803,020 KiB |
| DGAI | 400K | 432.98 s | 77.55 s | 510.53 s | 4,752,760 KiB |
| OdinANN | 50K | 37.78 s | 76.53 s | 114.31 s | 2,421,528 KiB |
| OdinANN | 400K | 281.46 s | 213.90 s | 495.36 s | 3,449,384 KiB |

controller wall 约 30 分钟。正式 clone apparent size 为 `62,182,783,385 bytes`，result apparent size 为 `57,315,169 bytes`，运行期间项目 NVMe free-space delta 为 `62,239,965,184 bytes`，另有约 690 MiB 独立 build。全部 artifact 位于 `/dev/nvme8n1`。结束后无 active tmux、systemd unit 或实验进程，`experiments_started_beyond_gate=false`；没有启动额外规模、缓存、延迟写回或其他优化原型。
