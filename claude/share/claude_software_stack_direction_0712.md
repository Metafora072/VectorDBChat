# 软件栈瓶颈方向评估

日期：2026-07-12

## PZ 的核心洞察

现代高带宽 SSD（PCIe 5.0，14 GB/s 读、7+ GB/s 写）的设备吞吐已接近内存带宽一个数量级以内。但现有驻盘图索引远未饱和设备带宽，瓶颈已从设备转移到软件栈。WSBuffer (FAST 2026) 在通用 buffered I/O 上验证了这一论断并获得 3.91x 提升。问题是：这个思路是否适用于驻盘图索引？

## 支撑证据

### 直接证据

**IISWC 2025 (VU Amsterdam / Intel / IBM)**: 对 Milvus + DiskANN 的系统性 benchmark 发现，向量搜索的最大读带宽仅 1,720 MiB/s (1.7 GiB/s)，而 Samsung 990 Pro 裸设备可达 7.2 GiB/s。**SSD 带宽利用率不足 24%。** 增大 `search_list` 从 10 到 100 后带宽增加 3.3x 但仍未饱和，且吞吐下降 60.9%——说明软件栈扩展性而非设备是限制。

**我们自己的 P0 数据**: DGAI 在 8 query workers + 高负载下达到 ~590K read IOPS，queue depth ~47。Samsung 990 Pro 可达 ~1.3M 4KB random read IOPS。**DGAI 使用了设备约 45% 的 IOPS 能力。**

### 间接证据

**软件栈单次 I/O 开销**: Linux 内核 I/O 栈（syscall → VFS → 文件系统 → block layer → NVMe driver）每次 I/O 约 4-8μs。现代 NVMe 4KB 随机读设备延迟约 10μs。**软件开销占总延迟的 40-80%。**

**WSBuffer (FAST 2026)**: 重新设计 write buffer 路径后，对 EXT4/F2FS/BTRFS/XFS 提升高达 3.91x 吞吐、82.80x 延迟。证明软件栈重设计可以释放巨大带宽。

## 现有相关工作的精确边界

| 工作 | 做了什么 | 没做什么 |
|---|---|---|
| **VeloANN** (PVLDB 2025) | 协程异步执行，重叠多个查询的 I/O 等待与计算；record-level buffer；affinity co-placement。5.8x vs DiskANN | 不处理动态更新；不减少 per-I/O 软件栈开销本身；用 libaio 不用 io_uring |
| **LIOS** (2025) | 利用搜索 I/O stall 期间的 CPU 空闲时间调度更新任务；resumable pruning。1.48-2.68x 更新加速 | CPU 侧优化，不减少 I/O 栈开销；不改变 I/O 提交方式；不重设计布局 |
| **Turbocharging** (VLDB 2025, SNU) | io_uring 用于 pgvector；spatially-aware insertion reordering；locality colocation | 针对 pgvector 的 IVF 索引，不是图索引的 dependent-read 模式；不处理动态更新 |
| **WSBuffer** (FAST 2026) | 重设计 buffered write path；scrap buffer + direct-to-SSD aligned writes | 通用 I/O，不了解图索引的访问模式；只做写路径 |
| **GORIO** (2026.07) | GPU 驱动 NVMe-oF 图搜索 | GPU 专用；只读；远程存储 |

**关键空白：没有工作针对驻盘图索引的特定 I/O 模式重设计软件栈来最大化 SSD 带宽利用。**

## 图索引 I/O 模式的特殊性

图索引的 I/O 模式与通用 buffered I/O（WSBuffer 目标）和 IVF 索引（Turbocharging 目标）都不同：

1. **依赖读 (dependent reads)**：beam search 的每一跳依赖上一跳的结果。不能简单把所有读请求一次性提交。
2. **跳内并行 (intra-hop parallelism)**：同一跳内可以并行读取 beam_width 个节点的邻接页面。
3. **小 I/O 密集**：每次读 4KB（一个节点的邻接表+坐标），产生大量小随机读。
4. **更新与查询 I/O 混合**：动态系统中更新的 RMW 与查询的读共享设备。
5. **PQ 过滤**：大部分距离计算用内存中的 PQ 向量，只有最终 rerank 读全精度坐标。

这些特性意味着：
- WSBuffer 的 write path 优化不直接适用（图搜索主要是读）
- Turbocharging 的 io_uring 方案不直接适用（IVF 是大块顺序扫描，图索引是小随机读的依赖链）
- 但图索引有自己的优化空间：**跳内批量提交 + 跨查询 I/O 重叠 + 预取下一跳候选**

## 可能的系统设计

### 核心思路
**co-design I/O 栈与搜索算法**，使图索引能够饱和现代 SSD 的 IOPS 和带宽：

1. **I/O 栈重设计**：
   - 使用 io_uring 的 registered files + registered buffers + fixed-file 模式，消除 per-I/O 的 fd lookup 和 buffer mapping
   - 每次 beam search 迭代内，将所有候选节点的页面请求合并到一个 SQE batch 提交
   - 对比 libaio/io_submit（DGAI 当前使用）的开销

2. **带宽感知搜索算法**：
   - 动态调整 beam width：当 SSD 带宽有余量时增大 beam（探索更多候选），当 CPU 成为瓶颈时缩小 beam
   - 利用 PQ 距离预测下一跳最可能的节点，提前预取其页面（prefetch pipeline）
   - 多查询协程调度（类似 VeloANN 但加上带宽感知）

3. **布局 co-design**：
   - 将图邻居按 beam search 访问概率排列，使同一迭代的读更可能是顺序/相邻的
   - 使用大 I/O（读取包含多个节点的连续块）替代多次小 I/O
   - 动态更新时保持布局质量

4. **更新路径优化**：
   - 更新的 RMW 使用异步写回（不阻塞查询路径）
   - 更新的 topology 读可以与查询读合并提交（跨操作 I/O 融合）

### 贡献叙事
"现有驻盘图索引使用通用 I/O 栈处理图特有的 dependent-read 模式，仅利用了现代 SSD 不到 25% 的带宽。我们设计了 [SystemName]，一个图感知的 I/O 引擎，通过 [具体机制] 将图搜索的 SSD 带宽利用率从 X% 提升到 Y%，在保持相同 recall 的条件下实现 Z 倍吞吐提升。"

## Novelty 评估

**强项**：
- 问题真实且可量化（IISWC 已测得 <24% 带宽利用率）
- 通用 I/O 栈的瓶颈已被 WSBuffer (FAST 2026) 确认
- 图索引的 I/O 模式（dependent reads）与通用 I/O 和 IVF 都不同，需要专门设计
- 现有工作（VeloANN/LIOS）优化 CPU 利用率而非 I/O 栈，是互补而非竞争
- 与 PZ 的存储/体系结构背景完美匹配

**风险**：
- 如果带宽利用率低主要是因为 beam search 的 **算法依赖性**（每跳必须等上一跳结果），而非 I/O 栈开销 → 降低 per-I/O 开销也无法显著提升吞吐
- 如果 VeloANN 的协程方案已经通过重叠多查询达到了接近设备饱和 → I/O 栈优化的增量收益不够
- 如果图索引的 I/O 模式天然无法产生足够的 outstanding requests 来饱和 NVMe 队列 → 问题不在栈而在并行度

## Kill 条件

1. **分解测试**：在 DGAI 和 OdinANN 上测量 beam search 的 per-hop 时间中，软件栈开销（syscall + kernel）、设备等待、CPU 计算各占多少。如果设备等待 >70%（而非软件栈），方向不成立。
2. **io_uring 简单替换测试**：将 DGAI 的 libaio 替换为 io_uring（不改架构），如果已获得 >50% 的 IISWC gap 恢复，说明简单 I/O 接口替换就够，不需要系统级重设计。
3. **并行度上界测试**：增大 beam width 和并发查询数，测量 IOPS 和带宽。如果在 CPU 饱和前带宽已饱和设备，说明瓶颈确实是软件栈；如果 CPU 先饱和，说明瓶颈是计算。

## 建议的第一步

不写系统、不做实现。先做一个 **瓶颈定位实验（Problem Gate P0）**：

在 DGAI（已有本机环境）上：
1. 使用 `perf` 和 `bpftrace` 分解 beam search 的 per-I/O 时间：用户态准备 → syscall 进入 → kernel 处理 → 设备完成 → syscall 返回 → 用户态处理
2. 测量不同 beam width 和并发查询数下的实际 SSD 带宽利用率
3. 对比 io_uring vs libaio vs 同步 pread 的 per-I/O 开销
4. 产出：一张"时间去哪了"的分解图，明确区分软件栈 / 设备 / CPU 计算

如果 P0 确认软件栈开销是主要瓶颈（占 beam search 总时间 30%+），方向成立，进入系统设计；否则 Kill。
