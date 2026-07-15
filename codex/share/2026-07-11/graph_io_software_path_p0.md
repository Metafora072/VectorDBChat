# 驻盘图搜索软件路径 Problem Gate：G0 报告

日期：2026-07-12

## 裁决

本方向在 G0 prior-art 与代码审计阶段触发 **Kill**，不进入 G1–G4，不新增 DGAI instrumentation，也不运行 capacity envelope、timeline 或 replay。

Kill 的直接原因不是问题不存在，而是当前候选的机制与论文边界已经被最接近工作覆盖：PipeANN 已针对 graph-dependent reads 联合设计异步 I/O pipeline、非阻塞 completion、动态 pipeline width 与搜索算法，并在正式论文中使用 io_uring/SQPOLL；其 2026 官方主线又提供 io_uring、libaio 和 SPDK 三种后端。NAVIS 在支持并发搜索/更新的 on-SSD 图系统中进一步使用 fixed-file 注册、每线程 ring、分组提交与批量 completion。VeloANN则覆盖跨查询协程调度、每核 scheduler、异步预取和 buffer reuse。若继续推进，候选只剩在 DGAI 中复现或组合这些机制，命中 gate 的“区别只剩 I/O API/已有机制”Kill 条件。

此外，Claude 材料中的一项关键 prior-art 边界有误：Turbocharging Vector Databases using Modern SSDs 针对的是 pgvector 的 **HNSW graph index**，不是 IVF。该工作已经把 io_uring batching、完成即计算的 compute-I/O pipeline 和现代 SSD 利用率作为核心贡献。因此“尚无工作针对图索引 dependent-read 模式重设计软件路径”的前提不成立。

## DGAI 当前路径审计

审计对象为本机 DGAI 提交 `a0179b876a4bd453336dc2893b46ae890f680555` 及此前 measurement-only 修改；当前 SIFT-900K 配置使用 decoupled topology/coordinate layout、`R=64`、`L=160`、rerank search 与 libaio。

- 每个 search worker 通过 `thread_local io_context_t` 独占 AIO context，首次使用时以 `io_setup(MAX_EVENTS)` 创建；不同 query 线程不共享 submission context。
- query buffer 从预分配池获取。每个 buffer 预分配 aligned query、PQ scratch、visited set、`MAX_N_SECTOR_READS` 个 `IORequest` 以及对齐 sector scratch，搜索过程中复用而不是逐 I/O 分配数据 buffer。
- rerank search 已继承 PipeANN 风格的 pipeline：候选成为 eligible 后，最多维持 `beam_width` 个 on-flight requests；completion 通过非阻塞 `io_getevents(..., min_nr=0)` 批量收割，完成页立即进入 adjacency/PQ/heap 处理，然后补发下一请求。
- 当前 `send_io(IORequest&)` 对每个 miss 单独调用 `io_submit(..., 1, ...)`；vector overload 才会批量提交。因此 DGAI 的确存在 syscall-per-miss 的局部实现差异。
- 但该差异不是未研究问题：DGAI 本身已启用 `OVERLAP_INIT` 和 `DYN_PIPE_WIDTH`，即搜索算法与 dependent I/O pipeline 已经 co-design；把单请求 libaio 换为 batched io_uring/fixed-file 或 SPDK，分别被 PipeANN、NAVIS 和 Turbocharging 覆盖。
- 依赖边界位于 candidate/PQ/visited/heap 更新之后：只有完成页被解析并把邻居加入候选池，后继 I/O 才 eligible。跨 query 隐藏该依赖的 scheduler 则已由 VeloANN覆盖。

## Prior-art 精确边界

### PipeANN / OdinANN

[PipeANN（OSDI 2025）](https://www.usenix.org/conference/osdi25/presentation/guo)不是简单接口替换。它明确针对 best-first graph search 的逐步依赖，使用异步 pipeline 打破整批 I/O 后再计算的同步边界；每线程私有 io_uring，`prep_read` 提交、`peek_batch_cqe` 非阻塞收割、SQ polling，并根据搜索阶段动态增加 pipeline width。论文还在同一 io_uring 后端上对比 DiskANN 与 Starling，说明贡献边界是 graph search/I/O co-design。

本机官方 PipeANN 仓库固定在 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`（2026-07-10）。其默认后端为 io_uring，并可选择 libaio 或 SPDK。2026-05-18 加入的 SPDK 后端使用每 SSD 一个 poller、用户态 submission/completion 队列和 raw NVMe stripe；官方文档报告 4 块 Optane 下 SIFT100M、50 search threads、Recall@10 约 90% 时超过 100K QPS。该主线也已集成 OdinANN 的动态更新。因此“用 SPDK/userspace NVMe 处理 dependent graph reads”已有直接实现。

### NAVIS

[NAVIS（2026 预印本）](https://arxiv.org/abs/2605.11523)是并发 search/update 的动态 on-SSD 图系统。其 I/O Path Optimization 明确让所有存储 I/O 走 io_uring：每 worker 私有 depth-256 ring，edge/vector 文件通过 `io_uring_register_files` 预注册，SQE 使用 `IOSQE_FIXED_FILE`，每组候选 vector reads 只做一次 `io_uring_submit_and_wait`，再以 `io_uring_peek_batch_cqe` 批量回收。它已经覆盖当前候选列出的 fixed files、group submission、bulk completion 和动态系统边界。

### VeloANN

[VeloANN（2026 预印本）](https://arxiv.org/abs/2602.22805)采用 thread-per-core scheduler，把每条 query 建模为 coroutine；每个 scheduler 批量接入多个 query，在一条 query 等 I/O 时运行其他 ready coroutine，通过异步 driver（文中以 io_uring 为例）批量提交并 busy-poll completion。它还提供 record-level buffer pool、异步预取与 cache-aware beam search。论文报告相同 recall 下吞吐相对 PipeANN 高 1.4–4.6×。因此跨查询调度、buffer reuse 和 compute-I/O overlap 也不是空白。

### Turbocharging Vector Databases using Modern SSDs

[Turbocharging（PVLDB 2025）](https://www.vldb.org/pvldb/vol18/p4710-do.pdf)明确研究 pgvector 的 HNSW graph index。它把未访问且未缓存的邻居批量提交给 io_uring，先计算 cache hits，随后每完成一个 read 就立即计算其距离，避免等待整批完成；并讨论系统调用/context-switch CPU overhead。论文报告搜索最高提升 8.55×，且异步版本在 concurrency 30 达到约 8,902 MB/s，而原版到 concurrency 200 约 7,984 MB/s。它直接否定“Turbocharging 仅针对 IVF”这一 novelty 前提。

### Starling、DiskANN、GORIO

- [Starling](https://arxiv.org/abs/2401.02116)主要通过 in-memory navigation graph、block shuffling 和 block search 减少 I/O；它不是软件路径工作的最强重合项，但已覆盖 locality/block-level 搜索。
- DiskANN 使用有限 beam 的分批异步读与预分配 scratch，主要差异在同步等待一批完成；PipeANN正式以同一 io_uring 后端重做该执行顺序，因而已经隔离出算法/pipeline贡献，而不是把收益混同为 API 差异。
- [GORIO（2026 预印本）](https://arxiv.org/abs/2607.04415)面向 GPU + NVMe-oF，使用 SPDK proxy batching、outstanding-depth control 和 graph-query suspend/resume。硬件/远程场景与当前本机 CPU gate 不同，但它进一步说明 graph-specific userspace I/O scheduling 已存在。

## 对 Gpt 四个 G0 问题的回答

1. **VeloANN 是否覆盖跨查询协程调度、批量 I/O 和 buffer reuse？** 是。它每线程调度一批 query coroutines，并提供 record-level buffer pool 与异步预取。
2. **设备利用率与剩余瓶颈是什么？** VeloANN将同步 I/O stall、页面/record 粒度不匹配和 read amplification 作为联合瓶颈，而非声称 Linux kernel path 是唯一 residual；其 batch-size microstudy还显示高维数据会较早转为 compute/scheduling limited。
3. **当前候选相对 VeloANN 的区别是什么？** 若限定 DGAI，仅剩把已有 per-query PipeANN pipeline 接到更低开销后端；跨查询调度与 buffer 管理已由 VeloANN覆盖，算法/I/O co-design已由 PipeANN覆盖。
4. **是否已有 io_uring、SPDK/userspace NVMe 处理 dependent graph reads？** 是。PipeANN正式论文使用 io_uring/SQPOLL，官方主线已有 SPDK；NAVIS在动态图系统中使用 registered files 和 grouped I/O；Turbocharging在 HNSW中使用 io_uring pipeline。

## Kill 边界

本报告不声称任何图搜索软件栈研究都不可能成立。它严格关闭的是当前表述：以“现代 SSD 未饱和”为问题，以 libaio→io_uring/fixed files/registered buffers/batching/SPDK、pipeline width 或跨查询协程作为主要机制的 DGAI 软件路径优化。若未来重新立项，必须先提出 PipeANN、NAVIS、VeloANN 和 Turbocharging均不能表达的新语义或新瓶颈，不能再从接口组合出发。

因为 G0 已满足 Kill 条件，未运行 G1 exact-shape envelope、G2 timeline、G3 CPU attribution 或 G4 replay；不存在 SIFT 数值裁决，也不进入 GIST、OdinANN 对照或 API 替换。

一手论文 PDF 与文本解析仅占 14 MiB，全部位于 NVMe 的 `VectorDB/data/VectorDB/graph_io_p0/papers`。系统盘仍为 128 GiB 已用、155 GiB 可用（46%）。
