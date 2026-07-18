# Dynamic Vamana M3：Write Supersession Opportunity and Comparability Audit

## 1. 裁决

正式接受 M2 neighbor-repair decomposition。

M2 已形成以下可靠事实：

- 四个实验点全部通过正确性、物理账本和逻辑计数门禁；
- neighbor-repair-only bytes 与 submitted page touches × 4096 精确闭合；
- OdinANN 在当前配置下每次固定调度 96 条 repair records，DGAI 为 32 条；
- OdinANN 的记录为 900 B、每 4 KiB 页容纳 4 条，DGAI 为 644 B、每页容纳 6 条；
- 400K 时 OdinANN temporal rewrite factor 为约 5.0；
- 92.71% 的 OdinANN stage-unique neighbor pages 被重复触及，贡献 98.54% 的 touches；
- top 1% pages 只贡献约 2.73% touches，说明重复写是广泛分布的，并非少数热点页主导。

同时必须修正研究边界：

- 当前跨系统 neighbor-write 差距混合了 `R=96 vs R=32`、记录布局、搜索/prune 路径和 I/O engine；
- M2 的 3× fanout 是 scheduled-record 计数比，不是 3× 有效图修改；
- 不得继续把约 5× 差距解释为 online visibility 的因果代价；
- M2 的乘法分解是计数恒等式，不是单因素干预结果。

M3 不实现写合并，只判断 stage-wide repeated pages 中有多少形成当前实现下可实际利用的版本覆盖机会。

## 2. 核心问题

Stage-wide temporal rewrite factor 不等于可消除写入。同一页面可能在以下时点再次生成新版本：

1. 旧版本尚未入队；
2. 旧版本已入队但尚未提交；
3. 旧版本已经提交、仍在 flight；
4. 旧版本已经完成，但尚未到 publish/save barrier；
5. 旧版本已经成为某个明确 durability boundary 的一部分。

只有结合真实写生命周期、页面版本关系和 durability contract，才能判断旧写是否可被后续完整页镜像安全覆盖。

M3 必须回答：

- 重复页面中多少发生在 prior version submit 之前；
- 多少发生在 prior version flight 期间；
- 多少发生在 prior completion 之后；
- 当前 API 在何时承诺 online visibility、write completion 和 durability；
- 后续页面镜像是否必然包含先前页面修改；
- 当前 background writer 是否已经进行相同 page key 的合并或覆盖。

## 3. 第一阶段：源码语义审计

对 DGAI 与 OdinANN 分别审计并引用真实函数与锁路径。

### 3.1 页面版本形成

- 页级 RMW 镜像在哪个函数中形成；
- page key 如何定义；
- 同一页面的并发更新由什么锁或版本机制串行化；
- later page image 是否从包含 earlier mutation 的内存状态生成；
- 是否可能从旧磁盘页重新读取并覆盖尚未完成的更新；
- target/neighbor 共页时版本关系如何处理。

### 3.2 写生命周期

明确：

```text
generate → enqueue → submit → complete → publish/save/barrier
```

每个阶段对应的函数、线程和数据结构。

审计：

- 队列是否按 page key 去重；
- 是否允许同页多个版本同时排队；
- 是否允许同页多个写同时 in-flight；
- completion 后内存页何时释放或失效；
- save/publish 是否等待全部后台写完成；
- fsync/fdatasync、io_uring drain 或其他 barrier 的实际位置。

### 3.3 可见性与持久性语义

分别说明：

- insertion/deletion future 返回表示什么；
- online probe 通过时，写可能处于哪些状态；
- fresh-process visibility 依赖哪些文件；
- 当前实现是否承诺单条 update crash durability；
- publish/save 前发生崩溃时，哪些状态允许丢失；
- 哪个时点是本实验能够证明的 durability boundary。

不得把进程内可查询等同于已经持久化。

## 4. Instrumentation

Instrumentation 只做内存聚合，进程结束后一次性输出。

使用真实物理 page key：

```text
(device, inode, aligned_4k_offset)
```

为每个 neighbor-only page version 记录单调 version sequence 和以下事件：

```text
generated
enqueued
submitted
completed
barrier-covered
```

不保存 page 内容、邻居 ID 或逐事件日志。

### 4.1 互斥分类

每次同页新版本生成时，将 prior version 精确归入：

1. `superseded_before_enqueue`
2. `superseded_while_queued`
3. `superseded_while_inflight`
4. `repeat_after_completion_before_barrier`
5. `repeat_after_barrier`
6. `no_prior_version`

各类别总和必须与全部 page-version generation 事件闭合。

### 4.2 队列和并发状态

记录完整整数直方图：

- queue depth；
- 每 page 同时 queued version 数；
- 每 page 同时 inflight version 数；
- generation-to-submit operation distance；
- generation-to-submit batch distance；
- submit-to-complete 期间产生的后续版本数；
- 每个 128-record insertion batch 内的 same-page version count；
- 每个 page 在 barrier 之间的 version count。

报告 mean、median、p95、p99、max，并保留 machine-readable histogram。

### 4.3 页面版本包含关系

必须验证 later page image 是否语义覆盖 earlier version。

优先使用已有页锁与内存 version counter 形成证明；如源码不足，可记录非内容型摘要：

- page version number；
- predecessor version number；
- mutation generation sequence；
- monotonicity violation count。

不得记录原始向量或邻接表内容。

出现 version 回退、并发分叉或 later image 不包含 earlier mutation 的可能性时，停止，不得计算“安全可合并”比例。

## 5. 可合并机会定义

### 5.1 Already avoided

当前实现已经通过 queue/page-key 机制消除、从未进入 physical submit 的旧版本。

### 5.2 Mechanically superseded before submit

满足以下条件的旧版本：

- later full-page image 已生成；
- later image 被证明包含 earlier mutation；
- earlier write 尚未 submit；
- 删除 earlier queued version不改变当前可见性；
- 不跨越已证明的 durability boundary。

这是 M3 唯一可以称为“直接可覆盖”的类别。

### 5.3 Not immediately avoidable

包括：

- prior write已经 in-flight；
- prior write已经完成；
- 跨越 durability boundary；
- 页面版本包含关系无法证明。

不得把 stage-wide 重复写或 barrier 前全部重复写都计为可消除。

## 6. 实验矩阵

只运行四个 fresh-clone 点：

| System | N | Prefix |
|---|---:|---|
| DGAI | 50K | `[800000:850000]` |
| DGAI | 400K | `[800000:1200000]` |
| OdinANN | 50K | `[800000:850000]` |
| OdinANN | 400K | `[800000:1200000]` |

要求：

- 从各自同一个 R12 frozen CP10 source 创建 fresh clone；
- 不复用 M2 mutable clone；
- 保持原始线程数、batch size、flush、queue 和 I/O 路径；
- 复用 accepted physical profiler，并增加 lifecycle/version instrumentation；
- 继续验证 active-set、visibility、query smoke、changed-file coverage、physical ledger closure、source preservation 和 no-OOM；
- lifecycle event totals 与 physical submit/completion totals必须闭合。

如果 instrumentation 显著改变 queue 行为、wall time 或 write count，停止并报告，不接受该点。

## 7. Comparability Audit

M3 同时完成一个只读可行性审计，不启动 matched-index 构建。

必须说明：

- 两系统是否都支持显式构建 `R=32` 与 `R=96`；
- 能否统一 `L/C/beam/alpha`；
- 相同 R 时记录长度和每页容量是否仍不同；
- 是否能够使用同一 active set 与 build input；
- 构建四个 factorial base：
  `DGAI-R32 / DGAI-R96 / OdinANN-R32 / OdinANN-R96`
  所需时间、空间和代码改动；
- 哪些差异即使 matched R 后仍无法消除；
- matched-R 实验能回答什么，不能回答什么。

本轮不实际构建这些 base。

## 8. 结果必须回答

1. M2观察到的 stage-wide 重复写中，多少比例发生在 prior submit 之前？
2. 当前实现已经避免了多少同页旧版本？
3. mechanically superseded before submit 的 bytes/replacement 是多少？
4. 可覆盖机会随 50K→400K 是否增长？
5. 机会来自少数 queue 热点，还是广泛 page keys？
6. online visibility 时点与 durability boundary 之间的真实关系是什么？
7. matched-R factorial 是否技术可行且研究上必要？

## 9. 结论边界

M3 不得声称：

- write coalescing 一定能获得 stage-wide rewrite factor 对应的收益；
- online visibility 导致写放大；
- queued supersession 已经构成论文创新；
- 可以删除 in-flight 或 completed writes；
- matched-R 后必然仍存在系统差异；
- 已经形成新系统设计。

只有当 submit 前可覆盖比例稳定且显著，并且正确性、可见性与 durability 语义能够完整闭合后，才进入 novelty 审查。

## 10. 输出与停止点

输出：

```text
codex/share/2026-07-18/
dynamic_vamana_write_supersession_m3_0718.md
```

同时生成 machine-readable summary，绑定 M2 summary、四个 run identity、frozen source与 input prefix、profiler/binary identity、lifecycle histograms、version monotonicity evidence、physical submit/completion closure和 comparability audit。

四点完成后停止，不自动实现 queue coalescing，不构建 matched-R base。
