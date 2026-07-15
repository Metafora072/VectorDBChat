# 驻盘图搜索软件路径：Problem Gate

## 当前判断

PZ 提出的方向具有研究价值，但目前只确认了一个现象：

> 驻盘图搜索没有达到 SSD 的标称或微基准能力。

该现象不能直接推出：

* Linux I/O 软件栈是主要瓶颈；
* `libaio` 是核心问题；
* `io_uring` 能显著改善性能；
* 图索引需要一个新的 I/O engine；
* 设备带宽而不是 IOPS、依赖链或 CPU 是正确容量指标。

本阶段只回答“性能损失究竟发生在哪里”，不设计系统。

---

## 必须纠正的三个论证口径

### 1. 不使用顺序带宽作为主要基线

图搜索以小块随机读和依赖读为主，因此主要比较对象应是：

* 相同 4 KiB/8 KiB request size；
* 相同 `O_DIRECT`、alignment 与文件系统；
* 相同随机地址分布；
* 相同 CPU/NUMA；
* 相同 queue depth；
* 相同 NVMe 设备。

报告 exact-shape random-read IOPS、latency 和 CPU cost。顺序 GB/s 只作设备背景，不能用于计算“SSD 利用率”。

### 2. 不做可重叠阶段的简单时间相加

异步搜索中的用户计算、syscall、内核排队和设备服务可能同时发生。不得把每个请求的局部耗时相加后声称其占端到端时间多少。

需要使用：

* 全局事件时间线；
* 每条 query 的依赖 DAG；
* event-interval union；
* critical-path accounting。

### 3. 不把接口替换当作系统贡献

`io_uring` fixed files、registered buffers 或 SQE batching 本身不是论文级贡献。只有先证明通用接口无法表达或利用图搜索特有的 dependent-read parallelism，才允许进入 graph-aware I/O/search co-design。

---

# G0：代码与 Prior-art 审计

Codex 先确认 DGAI 当前路径：

* 每个 search iteration 产生多少个 eligible requests；
* 一次 `io_submit()` 提交多少个 IOCB；
* buffer 是否预分配、复用和对齐；
* completion 如何轮询或等待；
* 是否跨 query 共享 AIO context；
* 是否存在 syscall-per-request；
* 实际 queue depth 由什么限制；
* candidate compute 与下一批 I/O 的依赖边界在哪里。

同时精确审计：

* VeloANN；
* DiskANN/PipeANN/OdinANN；
* Starling；
* NAVIS；
* Turbocharging；
* GORIO；
* 其他 graph-specific asynchronous I/O 工作。

重点回答：

1. VeloANN 是否已经进行跨查询协程调度、批量 I/O 和 buffer reuse；
2. 其设备利用率和剩余瓶颈是什么；
3. 当前候选相比 VeloANN 的差异究竟是 kernel API、调度范围还是算法/I/O co-design；
4. 是否已有工作使用 io_uring、SPDK 或 userspace NVMe 处理 dependent graph reads。

若区别最终只剩“把 libaio 换成 io_uring”，立即 Kill。

---

# G1：Exact-shape Capacity Envelope

## 设备基线

在同一数据文件和 NVMe 上构造与 DGAI 查询读相同的 raw-I/O benchmark：

* 相同 request size；
* 相同 alignment；
* 相同读地址分布；
* 相同 direct-I/O 语义；
* queue depth 从低到高扫描；
* CPU 和内存固定在同一 NUMA node；
* 分别报告单核和多核 submission。

记录：

* IOPS；
* p50/p99 device latency；
* CPU cores consumed；
* system/user CPU；
* queue depth；
* request issue/completion rate。

这形成设备在**该请求形状下**的容量上界 `C_device`。

## 图搜索基线

DGAI query-only，先使用：

* SIFT-128；
* 900K base；
* R=64；
* 固定 recall 目标；
* 固定索引和数据。

扫描：

* query workers；
* beam width；
* offered query load。

beam 改变时必须保持同一 recall 区间，不能用降低质量换吞吐。

记录图搜索峰值：

```text
C_search
```

以及：

```text
C_search / C_device
```

但该比例只表示 headroom，不解释原因。

---

# G2：Overlap-aware Timeline

在每个请求和 search iteration 上记录：

1. candidate/page request 成为 eligible；
2. 用户态 enqueue；
3. `io_submit` 进入与返回；
4. block-layer issue；
5. block-layer complete；
6. completion 被用户态取走；
7. adjacency/PQ 处理开始与结束；
8. 下一跳 request 成为 eligible。

同时记录：

* eligible request count；
* userspace pending count；
* kernel submitted count；
* block outstanding count；
* per-hop fan-out；
* search iterations；
* PQ evaluations；
* expanded nodes。

基于事件区间，将设备未充分工作的原因划分为：

### Dependency-starved

```text
eligible == 0
outstanding == 0
```

说明算法还没有产生下一批可发请求。

### Userspace-starved

```text
eligible > 0
尚未进入 io_submit
```

说明请求已经可发，但用户态调度、数据结构或 batching 未及时提交。

### Kernel-path delay

请求已提交给 AIO，但尚未到达 block issue。

### Device-active

存在已 issue、未 complete 的请求。

### Post-completion compute

请求完成，但下一跳仍在 decode、PQ、heap 或 visited 处理中。

采用区间并集和 query critical path 统计，不将并行请求耗时重复计算。

---

# G3：CPU 与并行度归因

使用 `perf`、线程 CPU accounting 和内核符号，将 CPU cycles 至少分为：

* search/PQ/heap/visited；
* request preparation；
* libaio submit/completion；
* VFS/filesystem/block/NVMe path；
* allocator/copy；
* scheduler/context-switch。

同时做 core-scaling：

```text
1 / 2 / 4 / 8 / 16 query workers
```

判断：

* CPU 是否先于设备容量饱和；
* 增加 worker 后 outstanding I/O 是否继续增加；
* system CPU 是否随 IOPS 线性增长；
* 每完成一次 I/O 消耗多少 user/kernel cycles；
* 高并发下吞吐受 CPU 还是 eligible parallelism 限制。

---

# G4：Trace-driven Counterfactual

不更换 I/O API，使用现有 libaio 做两种诊断 replay。

## Arrival-preserving replay

保持真实请求地址、大小和 ready timestamp，只去除图数据结构操作。

用于确认现有 I/O engine 在相同到达模式下的 submission 成本。

## Dependency-preserving replay

保留每跳的依赖关系：上一跳 completion 后才释放下一跳请求，但去除 PQ、heap、visited 等用户计算。

用于估计 dependent-read 本身允许的最大 IOPS。

两种 replay 都只是因果上界，不是系统实现。

---

# Problem Gate 通过条件

以下条件必须同时成立：

1. exact-shape `C_device` 明显高于 `C_search`；
2. CPU 在设备达到 exact-shape capacity 前已经成为限制；
3. userspace-starved 或 kernel-path delay 在 critical path 中形成稳定、可回收的显著区间；
4. I/O submission/completion 软件路径消耗构成主要 CPU 成本，而不是 PQ/heap/visited；
5. dependency-preserving replay 明显高于原 search throughput；
6. 现象在 SIFT 后能于 GIST-960 复现；
7. 最小化 OdinANN/VeloANN-style 对照后仍存在；
8. Amdahl 上界支持至少约 1.3× 的端到端吞吐潜力。

第 8 条是论文意义门槛，不是系统运行时阈值。

---

# Kill 条件

任一条件成立即停止：

* exact-shape raw-I/O 能力只比搜索高很少；
* 设备空闲主要因为没有 eligible request；
* PQ、heap、visited 或 adjacency compute 先饱和 CPU；
* 增加 query concurrency 后已达到 exact-shape 设备能力；
* kernel/software path 只占少量 CPU；
* replay 证明主要限制是 hop dependency；
* 现象只在一个数据集或一个 beam 设置存在；
* VeloANN 已经覆盖同一问题与机制；
* 一个简单的 batched `io_submit` 修复即可恢复主要性能；
* novelty 只剩 io_uring registered buffer/fixed file 的组合。

---

# 本阶段禁止事项

在 Gate 通过前禁止：

* 替换成 io_uring；
* 设计 bandwidth-aware beam；
* 做 adaptive beam policy；
* 添加 prefetch；
* 修改物理布局；
* 加入 update I/O 融合；
* 命名系统；
* 宣称“软件栈占 30%”；
* 使用顺序带宽差距作为预期加速比。

---

# Codex 产物

发布：

```text
codex/share/graph_io_software_path_p0.md
```

内容仅包括：

1. G0 代码与 prior-art 边界；
2. exact-shape device/search capacity envelope；
3. overlap-aware timeline；
4. CPU cycles 与 core scaling；
5. trace replay 上界；
6. SIFT 裁决；
7. Continue-to-GIST 或 Kill。

第一轮只运行 DGAI + SIFT。SIFT 未通过时，不进入 GIST、OdinANN 或 API 替换。
