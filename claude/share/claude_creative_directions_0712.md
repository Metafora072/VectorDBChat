# 跳出现有框架的方向探索

日期：2026-07-12

## 方法论转变

之前八个方向全部 Kill 的根本原因：我们一直在问"现有驻盘图索引的 insert 路径里，哪个阶段可以优化？"——这是一个错误的问题框架。正确的问题应该是"现有驻盘图索引在什么使用场景或系统环境下存在结构性不适配？"

好的系统论文不是找到一个函数慢了然后加速它，而是指出在某种条件变化下，现有架构的基本假设不再成立，从而需要新的设计。

## 现有工作的共同隐含假设

审视 DGAI、OdinANN、FreshDiskANN、LSM-VEC、IP-DiskANN、NAVIS、VeloANN、GORIO，它们共享以下未被挑战的假设：

1. **存储是本地的、延迟均匀的。** 所有系统假设 SSD 挂在本机 PCIe 上，4KB 随机读延迟约 100μs。没有系统考虑远程存储（NVMe-oF, CXL-attached memory）的延迟特征。
2. **查询和更新使用同一套 I/O 路径。** 没有系统区分查询 I/O 和更新 I/O 的调度优先级或提交方式。
3. **Graph traversal 是同步的、逐跳的。** 除 VeloANN（静态）外，所有动态系统的 beam search 是"读一页→处理→决定下一页→读下一页"的串行路径。
4. **索引结构在构建时确定，更新只做局部修改。** 没有系统根据运行时查询负载特征动态调整索引的物理组织。
5. **单一存储层。** 所有系统假设只有 DRAM + 一块 SSD。没有系统利用多级存储层次（DRAM / CXL / fast-NVMe / capacity-NVMe）。

打破这些假设中的任何一个，都可能产生新的设计空间。

## 方向一：远程/解聚存储上的动态图索引

### 打破的假设
假设 1：存储是本地的。

### 问题背景
云端和数据中心已大规模转向存储解聚（disaggregated storage）：计算节点通过 NVMe-oF (TCP/RDMA) 或 CXL 访问远程 NVMe 池。这改变了根本的成本模型：
- 单次 4KB 随机读延迟从 ~100μs 变为 ~10-50μs (CXL) 或 ~100-500μs (NVMe-oF/RDMA)
- 但可用存储容量从单块 SSD (2-8TB) 变为弹性池 (100TB+)
- 网络带宽可能比单 SSD 高（多路聚合）
- 计算和存储可独立扩展

### 现有工作的空白
- **d-HNSW (2025)**：HNSW 在 RDMA 解聚内存上，但只处理**静态**查询，不支持动态更新。
- **GORIO (2026.07)**：GPU 驱动 NVMe-oF 上的图搜索，但是**只读**的，不处理 insert/delete。
- **所有动态系统**（DGAI, OdinANN, FreshDiskANN 等）：全部假设本地 SSD。

**没有系统在远程/解聚存储上做动态图索引更新。**

### 为什么这不是简单移植
远程存储的延迟结构改变了设计决策：
- OdinANN 式的 direct insert（逐点读写远程页）在高 RTT 下不可接受
- FreshDiskANN 式的 batch merge（大量顺序 I/O 到远程）可能反而有利
- 本地缓存策略需要重新设计（什么缓存在计算节点 DRAM，什么留在远程）
- 更新的可见性协议需要跨节点一致性（本地不存在此问题）
- I/O 请求可以大规模 pipeline（远程高延迟但高带宽，适合预取和批量提交）

### 可能的系统设计
- 计算节点保留：PQ 向量（全量）、routing graph（轻量顶层）、更新 buffer
- 远程存储保留：full vectors、完整图结构、immutable base layers
- 更新路径：本地 buffer → 本地 PQ + routing update → 异步批量 flush 到远程
- 查询路径：本地 routing 定位区域 → 批量预取远程页面 → 本地精确计算
- 一致性：本地缓存 + 版本号 / lease，不需要强一致（ANN 本身是近似的）

### FAST 味道
存储解聚是 FAST 核心话题。CXL、NVMe-oF、RDMA 都是 FAST 社区关注的技术。一个针对远程存储特性设计的动态图索引系统，与 FAST 2026 的 OdinANN、PipeANN 形成对话。

### Kill 条件
- 如果简单把 OdinANN/DGAI 的 I/O 换成远程 I/O + prefetch 就能获得 acceptable 性能（说明不需要新设计）
- 如果远程延迟使图搜索的多跳性质根本不可行（说明应该用 IVF/cluster 而非图）
- 如果 d-HNSW 的方法直接加上动态更新就能 work（说明 novelty 不够）

### PZ 适配度：极高
存储解聚、NVMe-oF、CXL、远程 I/O 调度都是存储/体系结构核心议题。

---

## 方向二：异步执行引擎 + 跨操作 I/O 融合

### 打破的假设
假设 2 + 3：查询/更新使用同一路径 + 同步逐跳搜索。

### 问题背景
VeloANN (PVLDB 2025) 证明：对**静态**图索引，用协程异步执行 + record-level buffer 可以比 DiskANN 提升 5.8x 吞吐。核心原理是利用一个查询等待 I/O 时，切换到另一个查询的计算。

但 VeloANN 完全不处理动态更新。在 mixed workload 下：
- 查询需要读取图页面和向量页面
- 更新需要读取图页面、修改、写回
- 两者可能访问相同或相邻的页面
- 当前所有动态系统（DGAI、OdinANN）中，查询和更新是完全独立的 I/O 路径

### 核心 Insight
在 mixed workload 下，如果使用 io_uring 统一管理所有 I/O 请求（无论来自查询还是更新），可以：
1. **Cross-operation batching**：多个查询 + 多个更新的 I/O 请求合并到一个 io_uring SQE 批次提交，减少 syscall 次数
2. **Page sharing**：如果查询 A 和更新 B 都需要同一页，只读一次
3. **Priority scheduling**：查询请求高优先级 (IOPRIO)，更新请求低优先级
4. **Compute overlap**：查询等 I/O 时执行更新的 PQ 计算或 prune；更新等写回时处理查询的候选排序

### 与 P0 实验的关系
P0 显示 DGAI 没有 query-update 干扰，因为 update 的 I/O 量相对 query 是噪声级。但这恰恰是因为 DGAI 的 update rate 很低（单线程 ~20/s）。如果设计一个高吞吐的异步引擎，可能把 update rate 提高一个数量级，此时干扰问题会重新出现，而异步引擎就是解法本身。

### Novelty 边界
- VeloANN：静态查询，无更新，无 io_uring
- Turbocharging (VLDB 2025, SNU)：io_uring 用于 pgvector 查询，不处理动态图更新
- OdinANN：同步 I/O，无跨操作融合
- NAVIS：复用 insert 搜索路径给 query，但不是 I/O level 的融合

### Kill 条件
- 如果 io_uring batch submission 的延迟已经很低（<5μs），跨操作 coalesce 的相对收益太小
- 如果 mixed workload 下页面共享率太低（类似 oracle 发现），batching 只省 syscall 不省 I/O
- 如果简单的线程级隔离（query threads + update threads + 共享 page cache）就够了

### PZ 适配度：高
io_uring、NVMe I/O 调度、优先级、设备队列深度都是存储/体系结构议题。

---

## 方向三：查询负载自适应的物理重组（Graph Cracking）

### 打破的假设
假设 4：索引结构在构建时确定。

### 问题背景
CrackIVF (VLDB 2025, ETH Zurich) 将 database cracking 引入 IVF 向量索引：查询到达时，按查询向量对 partition 进行细分，使后续同区域查询更快。但 CrackIVF 是 IVF-based（非图），且不处理动态更新。

对于**驻盘图索引**，类似的 insight 是：
- 构建时的物理布局基于数据分布，但查询分布可能与数据分布不同
- 高频查询区域的图节点应该物理上更紧凑（减少 I/O）
- 低频区域可以容忍更分散的布局

### 核心 Insight
在每次查询执行过程中，系统已经知道了：
- 本次搜索路径上的所有节点（traversed set）
- 哪些节点被多次查询命中（热节点）
- 哪些页面包含相互不相关的节点（可以 crack）

利用这些运行时信息，可以在不额外 I/O 预算的情况下：
- 记录 page access 热度
- 当一个热页被读入时，判断其中哪些节点是真正热的
- 在后台（或 idle I/O slot 中）将热节点搬迁到相邻位置

这不同于 LSM-VEC 的周期性全局重排（太重）和 DGAI 的 SADL（只看 insert locality）。它是基于实际查询负载的增量式物理重组。

### 与 Oracle Kill 的区别
Oracle 实验 kill 的是"利用 INSERT 的 write set 做 relayout"。这个方向是"利用 QUERY 的 read set 做后台 relayout"——read set 远大于 write set，且与未来查询的相关性更强。

### Novelty 边界
- CrackIVF：IVF-based，非图，非驻盘（内存为主）
- LSM-VEC：周期性全局重排，非增量
- Porder (NeurIPS 2022)：离线全图重排
- DGAI SADL：基于 insert locality，非 query locality
- VeloANN affinity：构建时静态决定

### Kill 条件
- 如果查询分布高度均匀（所有节点等频访问），没有热区可以优化
- 如果重组的 write I/O 成本（搬迁节点）超过后续查询节省的 read I/O
- 如果简单 LRU page cache 已经覆盖了热节点（不需要物理重组）
- 如果与 CrackIVF 的 novelty 区分不够清晰

### PZ 适配度：中-高
涉及 page-level I/O、物理布局、后台重组调度。但算法成分也较重。

---

## 优先级排序

| 方向 | Novelty | FAST 味道 | PZ 适配 | 实现难度 | 推荐 |
|---|---|---|---|---|---|
| 1. 解聚存储动态图索引 | 极高（无等价工作） | 极强 | 极高 | 中（需 RDMA/NVMe-oF 环境） | **首选** |
| 2. 异步引擎 + I/O 融合 | 高（VeloANN 只做静态） | 强 | 高 | 低（io_uring + coroutine） | 次选 |
| 3. Graph Cracking | 中-高（CrackIVF 类比） | 中 | 中-高 | 低-中 | 后备 |

## 建议

方向一（解聚存储）的 novelty 最强且 PZ 适配最好，但需要确认实验环境（是否有 RDMA NIC 或可模拟远程延迟的测试平台）。如果硬件不可得，方向二可以完全在现有单机 NVMe 环境完成且实现路径清晰。

下一步建议：PZ 判断硬件可得性和个人兴趣后，选择一个方向。选定后，Gpt 可以设计最小证伪实验（problem gate），Codex 执行。我在系统假设成型后做最终 novelty 审查。
