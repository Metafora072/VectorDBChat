# DynamicSSD-Maintenance P0：动态驻盘图索引物理维护成本 Characterization

**日期：** 2026-07-22  
**状态：** `GO-P0-CHARACTERIZATION`  
**前序方向：** ReversibleANN / GraphAging 已正式 `KILL-NO-PROBLEM / KILL-SHADOW-NO-UTILITY`  
**目标：** 只识别真实 SSD 更新路径中的主导物理瓶颈，不预设新算法，不实现完整系统  
**实验平台：** PipeANN v2 / DynamicSSDIndex，CPU + 普通 NVMe SSD  
**建议工作目录：** `codex/work/2026-07-22/dynamic_ssd_maintenance_p0/`  
**建议结果报告：** `codex/share/2026-07-22/dynamic_ssd_maintenance_p0_results_0722.md`

---

## 0. 背景与本轮边界

GraphAging A0 已证明：

- 动态更新会显著改变图边；
- 但官方 IP-DiskANN 在同终态 100 轮更新后几乎没有查询性能老化；
- 恢复旧图结构的 Oracle Shadow Replay 没有实质查询收益，且存储代价高；
- 因此不再推进 Shadow Edge、更新可逆性或 ReversibleANN。

然而，上一轮 A0 的动态主实验使用了内存图 fallback，没有覆盖：

- 真实 SSD page read/write；
- PipeANN 用户态 page cache；
- 邻接更新的 page RMW；
- 动态插入后的物理 page locality；
- tombstone、repair 和 full merge 的真实物理成本。

因此本轮重新定义问题：

> 动态 SSD 图索引的主要维护成本究竟来自重复 page RMW、物理布局退化，还是删除后的 tombstone / repair / merge？

本轮不得将三个问题提前组合成完整系统。P0 完成后只允许选择一个主轴继续。

---

## 1. 总体研究问题

### Q1：插入更新的真实物理写放大来自哪里？

对于一次节点插入，分解：

\[
C_{\text{insert}}
=
C_{\text{position-seeking}}
+
C_{\text{neighbor-read}}
+
C_{\text{neighbor-RMW}}
+
C_{\text{flush}}.
\]

需要回答：

1. 一个新节点平均修改多少个已有节点的邻接表？
2. 这些邻接修改覆盖多少个 distinct graph pages？
3. 同一 page 在短时间内是否被多个更新重复读写？
4. PipeANN page cache 已经合并了多少重复写？
5. logical edge bytes、application write bytes、filesystem write bytes、block-layer write bytes之间的放大分别是多少？
6. position seeking、邻居读取和写回分别占插入时间的多少？

目标不是证明“有写放大”，而是确定剩余写放大是否足以支持新的 page-aware 更新机制。

---

### Q2：动态更新是否造成 Physical Layout Aging？

上一轮证明 graph navigability 没有明显老化，但仍可能存在：

\[
\text{visited nodes approximately unchanged}
\]

同时：

\[
\text{distinct SSD pages read increases}.
\]

需要比较：

1. 静态构建图；
2. 连续动态插入后的图；
3. 插入—删除 churn 后的图；
4. 对同一动态图执行 offline relayout 后的图。

在相同查询、相同 search budget、相近 Recall 和 visited nodes 下，测量：

- distinct graph pages/query；
- graph bytes/query；
- nodes per fetched page；
- page reuse ratio；
- AvgIO / query；
- p50 / p95 / p99 latency；
- distance calculations；
- visited nodes。

只有当动态更新后 page reads 增加，且 offline relayout 能恢复，才可归因于 physical layout aging。

---

### Q3：删除路径的主导成本是什么？

将删除拆成：

\[
C_{\text{delete}}
=
C_{\text{tombstone}}
+
C_{\text{search-overhead}}
+
C_{\text{repair}}
+
C_{\text{merge}}.
\]

需要回答：

1. tombstone 比例增加时，查询额外读取多少 page？
2. 查询遇到多少 deleted nodes？
3. local repair 读取和修改多少 page？
4. full merge 实际读写多少字节、耗时多少？
5. 哪些 page 的 tombstone 密度高，局部 page compaction 理论上可回收多少工作？
6. full merge 的成本是否远高于 query-side tombstone overhead？

本轮不实现 Wolverine-on-SSD 或 page-local compaction，只做成本分解。

---

## 2. 实验原则

### 2.1 必须使用真实 SSD 路径

优先使用：

- PipeANN `DynamicSSDIndex`；
- graph file `O_DIRECT` / io_uring 路径；
- 现有用户态 page cache；
- 真实 insert / lazy_delete / final_merge。

若某个阶段无法在硬预算内执行：

- 允许缩小更新比例和运行时；
- 不允许退回内存图后仍声称 SSD 结论；
- 该项应标记为 `HOLD-NO-SSD-PATH`。

---

### 2.2 强自然基线

所有候选现象必须在以下自然优化开启时测量：

- PipeANN 现有 page cache；
- write coalescing / dirty-page aggregation；
- 相同 page size；
- 相同 graph layout；
- 相同 search parameters；
- 相同 durability 和 flush 语义。

不得通过关闭 page cache 或逐边强制 fsync 制造写放大。

可以额外提供弱控制，但不能用弱控制作为主结论。

---

### 2.3 不预设固定性能阈值

本轮不使用任意的“至少 15%”门槛。

判断依据：

- 效应是否稳定超过运行噪声；
- 是否在重复运行或多个 update windows 中保持；
- 是否由明确物理账本解释；
- 是否存在可优化的剩余重复工作；
- 强自然基线是否已自动消除大部分问题。

---

## 3. P0-0：源码与计量闭合

在运行主实验前，先完成以下审计。

### 3.1 插入路径 call graph

定位并记录：

```text
insert request
  -> position seeking
  -> prune
  -> reverse-neighbor update
  -> graph-page lookup
  -> page-cache hit/miss
  -> dirty marking
  -> flush / writeback
```

给出源码文件和行号。

### 3.2 删除路径 call graph

定位：

```text
lazy delete
  -> tombstone publication
  -> query-side deleted-node handling
  -> consolidate / repair
  -> final merge
```

给出源码文件和行号。

### 3.3 计量层级

至少区分：

\[
W_{\text{logical}}
\]

- 修改的 edge IDs；
- 新节点记录；
- tombstone bytes。

\[
W_{\text{application}}
\]

- `write/pwrite/io_uring write` 请求字节；
- page-cache flush 字节。

\[
W_{\text{filesystem/block}}
\]

- `strace` / io_uring request；
- `iostat`、`blktrace`、`bpftrace` 或可靠的 `io.stat`；
- 设备 read/write sectors。

明确不能声称 NAND internal write amplification。

### 3.4 Canary

用 10K–100K 小图执行：

- 1 个 insert；
- 100 个 insert；
- 1 个 delete；
- 一次 merge；
- 一次 search。

要求：

- 所有计数器有非零且可解释的值；
- application I/O 与 block I/O量级可闭合；
- graph file 与 metadata file 分开归因；
- page-cache hit/miss 计数不出现明显矛盾。

失败则：

```text
FAIL-P0-MEASUREMENT-CLOSURE
```

停止主实验。

---

## 4. P0-1：插入写路径 Characterization

### 4.1 数据与固定配置

首轮建议：

- SIFT1M；
- R=64；
- Lbuild / Lsearch 使用现有可稳定配置；
- 单 graph；
- 单 SSD；
- 固定 query 集；
- update ratios：0.1%、1%、5%；
- micro-batch size：1、32、256，仅作为 workload，不修改更新算法；
- 至少两个独立 update windows。

不要在首轮扫描过多参数。

### 4.2 每个窗口采集

- inserted nodes；
- reverse-neighbor modifications；
- logical modified edge bytes；
- distinct pages touched；
- total page accesses；
- page-cache hit/miss；
- dirty pages generated；
- repeated touches/page；
- application read/write bytes；
- block read/write bytes；
- flush count；
- insert p50/p95/p99；
- position-seeking time；
- prune time；
- RMW/flush time。

### 4.3 关键派生指标

\[
\text{Page Coalescing Opportunity}
=
1-
\frac{\text{distinct dirty pages}}
{\text{total dirty-page touches}}
\]

\[
WA_{\text{app}}
=
\frac{W_{\text{application}}}
{W_{\text{logical topology}}}
\]

\[
WA_{\text{block}}
=
\frac{W_{\text{block}}}
{W_{\text{logical topology}}}
\]

\[
\text{Cache Elimination Ratio}
=
1-
\frac{\text{actual page writes}}
{\text{raw page update requests}}
\]

### 4.4 裁决

`PASS-U-PAGE-COALESCING`：

- 同一 update window 内存在稳定的重复 page touches；
- 现有 page cache 未完全消除；
- page RMW/flush 是显著成本；
- 存在明确的额外 coalescing 空间。

`KILL-U-CACHE-ALREADY-ENOUGH`：

- 现有 page cache 已把重复更新基本合并；
- position seeking 或 prune 明显主导；
- page write 只占很小比例。

`HOLD-U-MEASUREMENT`：

- application 与 block 账本无法闭合；
- buffered metadata I/O 混淆结果。

---

## 5. P0-2：Physical Layout Aging

### 5.1 四种状态

使用同一基础数据和 query：

- `S0 Static`：静态构建；
- `S1 Insert`：动态插入一定比例；
- `S2 Churn`：插入后删除，使活跃规模回到目标规模；
- `S3 Relayout`：对 S1/S2 的活跃图做 offline relayout 或静态重建对照。

首轮 update ratios：

- 1%；
- 5%；
- 10%。

### 5.2 控制要求

比较时尽量保持：

- active vector set 相同；
- degree budget 相同；
- search-L 相同；
- Recall 接近；
- visited nodes 接近。

若边数不同，必须先统一 degree 或单独报告。

### 5.3 指标

- Recall@10；
- distance calculations；
- visited nodes；
- distinct graph pages/query；
- graph bytes/query；
- useful nodes/page；
- repeated page hit ratio；
- AvgIO；
- latency p50/p95/p99；
- page access heat map；
- 更新节点在物理文件中的分布。

### 5.4 关键判定

`PASS-L-PHYSICAL-AGING`：

- 动态状态相对静态状态有稳定更高的 distinct page reads；
- visited nodes / comparisons 变化不足以解释差异；
- offline relayout 或重建能恢复 page efficiency；
- 现象不只来自 degree inflation。

`KILL-L-NO-PHYSICAL-AGING`：

- page reads 与 visited nodes 同步变化；
- 统一 degree 后差异消失；
- relayout 无法恢复；
- page cache 已掩盖布局差异。

`HOLD-L-SSD-TOO-SMALL`：

- 数据和索引大部分被内存缓存；
- 无法形成真实设备读取。

---

## 6. P0-3：删除成本 Characterization

### 6.1 状态

从同一静态索引开始，生成：

- 0% tombstone；
- 1% tombstone；
- 5% tombstone；
- 10% tombstone。

删除分布首轮仅使用：

- uniform random；
- cluster-local。

### 6.2 查询成本

每个 tombstone 比例测量：

- Recall；
- visited deleted nodes/query；
- extra page reads；
- distinct pages/query；
- latency；
- refill / candidate deficit；
- distance calculations。

### 6.3 维护成本

分别记录：

- lazy-delete publication；
- consolidate / local repair；
- final merge；
- merge 读取字节；
- merge 写入字节；
- merge wall time；
- query pause 或并发影响；
- 可局部回收 page 比例。

### 6.4 裁决

`PASS-D-TOMBSTONE-QUERY-TAX`：

- tombstone 对查询 page I/O 有稳定影响；
- full merge 成本远高于前台查询税；
- 存在明显的局部 page 回收机会。

`PASS-D-MERGE-WA`：

- 查询税较小，但 full merge 的全量重写成为主导问题；
- page-level dirty/tombstone 分布高度不均匀，局部 compaction 有潜力。

`KILL-D-NO-RESIDUAL`：

- tombstone 查询税很低；
- merge 很少发生或成本可接受；
- 现有 repair/merge 已足够。

---

## 7. 执行顺序与预算

### Round 0：计量闭合

内容：

- 源码审计；
- counter instrumentation；
- 10K–100K canary；
- block I/O 账本。

预计：

```text
1–2 小时
```

### Round 1：单图单种子 Characterization

内容：

- P0-1 单种子；
- P0-2 单种子；
- P0-3 单种子；
- 小参数矩阵；
- 早停判断。

预计：

```text
4–6 小时
```

### Round 2：只扩展有信号的轴

仅对 Round 1 中 PASS/HOLD 的一个主轴增加：

- 2–3 seeds；
- 第二种 update pattern；
- 第二数据集或更大数据；
- confidence interval；
- direct-I/O 复查。

预计：

```text
6–10 小时
```

第一轮获得 go/no-go 的总时间约：

```text
5–8 小时
```

完整多种子闭合约：

```text
1–2 天
```

禁止三个轴同时进入 Round 2。

---

## 8. 资源边界

沿用实验室安全边界：

- 所有大文件写入 `/dev/nvme8n1` 对应数据目录；
- 禁止系统盘大写入；
- RSS hard limit：24 GiB；
- 新增数据 hard limit：10 GiB；
- Round 0 + Round 1 hard wall：8 小时；
- 禁止 GPU；
- 禁止修改 DGAI/OdinANN 主实验目录；
- 所有修改使用独立 PipeANN worktree；
- 任一阶段计量闭合失败立即停止。

如果真实 SSD `final_merge` 在预算内无法完成：

- 允许降低数据规模或删除比例；
- 必须明确报告；
- 不得用内存 fallback 冒充 SSD merge 结论。

---

## 9. 输出要求

Codex 必须提交：

### 9.1 主报告

`codex/share/2026-07-22/dynamic_ssd_maintenance_p0_results_0722.md`

包含：

1. 源码 call graph；
2. 环境、commit 和 hash；
3. 计量层级与 closure；
4. P0-1 数据表；
5. P0-2 数据表；
6. P0-3 数据表；
7. 原始 trace 路径；
8. 限制和未完成项；
9. 一个明确主轴裁决。

### 9.2 机器可读产物

建议：

```text
codex/work/2026-07-22/dynamic_ssd_maintenance_p0/
  manifest.yaml
  EXPERIMENT_TRACKER.md
  results/
    insert_path.jsonl
    layout_aging.jsonl
    deletion_cost.jsonl
    summary.json
  logs/
  traces/
  patches/
```

### 9.3 最终只允许一个结论

```text
PASS-U-PAGE-COALESCING
PASS-L-PHYSICAL-AGING
PASS-D-TOMBSTONE-QUERY-TAX
PASS-D-MERGE-WA
KILL-DYNAMIC-SSD-MAINTENANCE
HOLD-MEASUREMENT-CLOSURE
```

如果多个轴都出现信号，按以下优先级选择一个进入后续：

1. `PASS-L-PHYSICAL-AGING`
2. `PASS-D-MERGE-WA / PASS-D-TOMBSTONE-QUERY-TAX`
3. `PASS-U-PAGE-COALESCING`

原因：layout aging 更 ANN-specific；删除维护次之；page coalescing 最容易被评价为通用 batching/cache 优化。

---

## 10. 禁止事项

本轮禁止：

- 继续实现 Shadow Edge；
- 使用 GraphAging framing；
- 提前实现 page scheduler；
- 提前实现 incremental relayout；
- 提前实现 page-local compaction；
- 把三个轴拼成统一维护系统；
- 使用人为固定百分比作为唯一 PASS 门槛；
- 把内存实验写成 SSD 结论；
- 使用关闭 cache、逐边 fsync 等弱 baseline 制造结果；
- 未经核验引用 NAVIS/Wolverine/Greator 的结论。

本轮任务只有一个：

> 找出动态 SSD graph maintenance 中真实、稳定、尚未被自然 baseline 消除的主导物理成本。
