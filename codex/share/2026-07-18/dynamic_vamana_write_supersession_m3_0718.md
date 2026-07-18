# Dynamic Vamana M3：Write Supersession Opportunity 与 matched-R 审计

## 裁决摘要

M3 于 `2026-07-18 15:15:03 UTC+8` 完成。DGAI 与 OdinANN 的 50K、400K 四个 fresh-clone 点均通过原 physical formal gate、M2 logical closure 和新增 lifecycle/version/perturbation gate；22,522,471 个 neighbor-only page-version generation 事件全部闭合到 physical submit、completion 与一个明确 application barrier，version monotonicity、active-set、online/fresh visibility、query smoke、changed-file coverage、source preservation 和 no-OOM 均通过。

核心结果是否定性的：四点的 `superseded_before_enqueue`、`superseded_while_queued` 和 `superseded_while_inflight` 全部精确为 0。M2 观察到的 stage-wide repeated pages 全部在 prior write completion 之后再次生成，因此 mechanically superseded before submit 为 `0 versions / 0 bytes / 0 bytes per replacement`，当前队列也没有 page-key dedup，already avoided 同样为 0。M3 不支持进入 queue coalescing prototype 或 novelty review；stage-wide temporal rewrite 不能转写成可消除写入机会。

总体 machine summary 位于 `results/pilot3_sift10m_write_supersession_m3_r01/m3_summary.json`，SHA-256 为 `415e90fc141afa8baf0171815b2ca67827a4b82b4c96c63680f50274e91c4748`。该文件绑定 accepted M2 summary、build/profiler/binary identity、四个 input prefix/frozen clone/physical summary/lifecycle summary、完整整数直方图与 comparability audit。

## Raw data table

| System | N | generated | unique pages | repeat after completion | pre-enqueue | queued | inflight | direct bytes/repl | ingest vs M2 | neighbor bytes vs M2 | peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DGAI | 50K | 273,529 | 263,680 | 9,849 | 0 | 0 | 0 | 0 B | 0.974× | 1.00023× | 3,824,880 KiB |
| OdinANN | 50K | 1,570,164 | 1,262,095 | 308,069 | 0 | 0 | 0 | 0 B | 0.897× | 1.00020× | 2,587,944 KiB |
| DGAI | 400K | 3,425,192 | 1,721,291 | 1,703,901 | 0 | 0 | 0 | 0 B | 0.951× | 0.99995× | 4,915,196 KiB |
| OdinANN | 400K | 17,253,586 | 3,449,809 | 13,803,777 | 0 | 0 | 0 | 0 B | 1.114× | 1.00015× | 3,747,372 KiB |

四点 `generated = enqueued = submitted = completed = physical neighbor-repair bytes / 4096` 均精确成立。相对于 M2 的 ingest wall ratio 落在预注册 `[0.75, 1.25]`，neighbor-only bytes ratio 落在 `[0.90, 1.10]`；没有点因 instrumentation 改变写量或 wall time 而停止。正式 controller wall 约 30 分钟，四点 E2E 合计约 19.9 分钟，其余为 fresh clone、hash/source-preservation 和验证。

## 源码语义审计

### 版本形成与包含关系

两套实现都先把 target 与所有 neighbor 所在 4 KiB 页归一化、排序并取得 exclusive page locks，再重新读取/命中 page cache、形成完整页 RMW image。DGAI 的页请求形成位于 `DGAI/src/src/update/direct_insert.cpp:145-177`，OdinANN 的 page lock 位于 `OdinANN/src/src/update/direct_insert.cpp:95-106`；page key 在运行时绑定为真实 `(st_dev, st_ino, aligned_4k_offset)`。

页锁不是在 enqueue 后立即释放。DGAI 直到后台 blocking `reader->write()` 返回后才在 `direct_insert.cpp:406-418` 释放 `pages_to_unlock`；OdinANN 同样在 `direct_insert.cpp:335-342` 完成 write/CQE 后才释放。因而同一页的新 RMW 无法在 prior version queued 或 in-flight 时形成，不存在 concurrent fork，也不存在从旧磁盘页生成 later image 覆盖尚未完成 mutation 的路径。单调 page version、predecessor 与 lifecycle state 的运行时检查得到 `stale_or_fork_events=0`、`unproven_presubmit_containment=0`。这里的 containment 证明只用于可能的 pre-submit candidate；由于 candidate 为 0，不对 completion 后的图语义变更作“可覆盖”推断。

target/neighbor 共页仍形成单一完整页 version，并继续由 accepted physical profiler 单独归入 shared-page role；M3 只跟踪 neighbor-only page，避免把每次必写的 target page误算为优化机会。

### generate → enqueue → submit → complete → barrier

- `generated`：完整 `writes_4k` 和 neighbor-only page set 形成后、`wbc_write` 前；DGAI `direct_insert.cpp:289-318`，OdinANN `direct_insert.cpp:234-263`。
- `enqueued`：构造 `BgTask` 后、进入既有 `ConcurrentQueue` 前；DGAI `direct_insert.cpp:349-361`，OdinANN `direct_insert.cpp:284-295`。队列没有 page-key lookup、replacement 或 dedup。
- `submitted`：后台线程调用 blocking `reader->write()` 之前；`completed`：该调用返回之后。OdinANN 的真实 `io_uring_submit` 与 CQE wait 位于 `linux_aligned_file_reader.cpp:554-587`；DGAI libaio 路径同样由 blocking `execute_io` 等待 completion。
- `barrier-covered`：原实现只等待 `bg_tasks.empty()`，它可能在最后任务已 pop 但仍 in-flight 时提前为真。M3 在 DGAI `delete_merge.cpp:40-43`、OdinANN `delete_merge.cpp:38-41` 增加只观测 lifecycle counter 的 quiescence wait，要求 queued/inflight 均为 0 后再进入 merge；它不改变写顺序、write API 或写数量。

单次 insertion API 在 enqueue 后即可返回；`wbc_write` 已把完整页放入进程内 page cache，因此进程内查询可见不等于 physical completion。OdinANN 的 online probe 在 save 前通过，也不能证明 durability。fresh-process visibility 依赖 publish/save 后的新 disk index、tags、PQ 与 reload。四点的 profiler 均未观察到 `fsync/fdatasync`，所以 M3 的 barrier 证明的是 application write completion 和 fresh-process 可见性，不是掉电后的稳定介质 crash durability；不得声称单条 update crash durable。

## Queue 与版本直方图

| System-N | task queue p99/max | queued pages p99/max | generation→submit op p99/max | batch distance p99/max | versions/page median/p99/max |
|---|---:|---:|---:|---:|---:|
| DGAI-50K | 1 / 2 | 7 / 12 | 1 / 9 | 0 / 1 | 1 / 2 / 5 |
| OdinANN-50K | 2 / 7 | 78 / 239 | 2 / 7 | 0 / 1 | 1 / 3 / 12 |
| DGAI-400K | 1 / 2 | 10 / 20 | 2 / 9 | 0 / 1 | 2 / 5 / 21 |
| OdinANN-400K | 3 / 14 | 140 / 573 | 3 / 14 | 0 / 1 | 5 / 12 / 43 |

OdinANN 确实有更深的 task/page queue，但 page lock 使深度来自不同 page keys；`per_page_queued_versions` 和 `per_page_inflight_versions` 全部为 1，`submit-to-complete` 期间产生 later same-page version 的计数为 0。因此 queue depth 不能转化为 same-page supersession opportunity。每 128-record batch 内 same-page version count 的 p99 都为 1，最大值为 DGAI 2、OdinANN 3；这些少量同 batch repeats 也已经是 prior completion 后的顺序重写。

## 七个问题的回答

1. **prior submit 前比例**：四点均为 `0 / all repeated = 0%`。
2. **当前已经避免多少旧版本**：0。`ConcurrentQueue` 没有 page-key dedup；页锁是 completion 前串行化，不是避免 physical submit。
3. **mechanically superseded before submit**：四点均为 `0 bytes/replacement`。
4. **50K→400K 是否增长**：stage repeats 显著增长，DGAI 从 9,849 到 1,703,901，OdinANN 从 308,069 到 13,803,777；但可覆盖机会仍是 0，没有增长。
5. **少数 queue 热点还是广泛 page keys**：没有可覆盖 opportunity，故热点归因不适用。M2 的 stage repeats 是广泛 page keys，M3 证明它们发生得太晚，不能由 queue supersession 消除。
6. **online visibility 与 durability**：进程内 page cache/内存索引可在 background completion 和 publish 前提供可见性；completion barrier、fresh-process visibility 与 crash durability是三个不同边界。本实验只证明前两者，未证明 fsync 级 crash durability。
7. **matched-R factorial**：技术可行，而且任何跨系统因果比较都需要它；但它不影响本轮“同一实现内 pre-submit opportunity=0”的结论。

## Matched-R 只读可行性审计

两套 build CLI 都显式接受 R，能够构建 R=32 与 R=96；相同 `active_cp00.bin` 和 8M active set 可复用。L/C/beam/alpha 能通过小规模 driver 参数 plumbing 数值统一，但相同名字不保证候选生成与 prune 语义相同。SIFT float128、attr=0 时两套 graph-vector record 都服从 `512 + 4*(R+1)`：R32 为 644 B/6 records per 4 KiB，R96 为 900 B/4 records per 4 KiB；matched R 后这部分不再不同，但 PQ/neighbor representation、metadata/tags、search/prune、libaio/io_uring、page cache 与 publish 路径仍不同。

历史实测 DGAI-R32 build 为 40.0 分钟、约 132.2 GiB peak RSS、14.13 GB final index；OdinANN-R96 为 24.8 分钟、约 10.7 GiB peak RSS、8.48 GB final index。只读估算四套 base 串行需 2.3–3.7 小时、41–50 GiB persistent space，建议至少 100 GiB NVMe headroom；DGAI-R96 是最大风险点，启动前需确认约 220 GiB RAM。完整机器可读审计为 `results/pilot3_sift10m_write_supersession_m3_r01/comparability_audit.json`，SHA-256 `24353694f053c1a320a7374d3cab60b81430eb202722182232296477aada4271`；本轮 `actual_builds_started=false`。

matched-R 能回答“固定数值参数和 record capacity 后，跨系统 neighbor-write gap 是否仍存在”，不能隔离 online visibility、search/prune、I/O engine 或单一算法因素，也不能预测未来 coalescing design 的收益。

## Key findings

1. **Observation**：22.52M generations 中没有一个 later same-page version 在 prior submit/completion 前形成。**Interpretation**：page lock 的持有期覆盖整个后台 write completion，结构上封死了 queue supersession window。**Implication**：M2 的 1.04×–5.00× stage rewrite 是 completion 后重复写，不是 queued old-version overwrite。**Next step**：Kill 当前 queue-coalescing 方向，不实现 prototype。
2. **Observation**：OdinANN-400K queue max 达 14 tasks/573 neighbor pages，但 per-page queued/inflight version 恒为 1。**Interpretation**：队列并行度来自不同 page keys。**Implication**：只按 queue depth 或 stage duplicate page 比例估算收益会严重高估。
3. **Observation**：matched-R build 技术可行，但仍保留多个实现混杂因素。**Interpretation**：它是跨系统描述性对照，而非单因素干预。**Implication**：若未来仍要写跨系统机制结论，必须先构建 factorial base；若只判断本 coalescing idea，则没有继续成本的理由。

## 停止点与资源

M3 formal/result apparent size 为 `62,182,783,414 / 57,666,339 bytes`，项目 NVMe free-space delta 为 `62,240,329,728 bytes`；结束后项目盘剩余约 856 GiB。所有大文件、build、clone、raw results 都位于 `/dev/nvme8n1`，系统盘未用于实验数据。四点结束后无 active `dv-m3-*` unit、controller tmux 或实验进程。

本轮严格停止：没有实现 queue coalescing，没有构建 matched-R base，没有启动额外规模或优化。建议 Gpt 正式接受 M3 closure 并 Kill “利用现有 background queue 做 same-page pre-submit supersession”这一具体方向；若继续研究 write reduction，应另行提出改变锁/提交时序或跨 completion 的新 durability contract，这属于新的系统设计，不能从本结果自动授权。
