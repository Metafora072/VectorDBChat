# Decoupled ANN Architecture Characterization — 第一轮范围

**日期**：2026-07-13
**目的**：量化解耦 vs 耦合架构在现代 NVMe 上的实际 I/O 行为差异，确认"解耦架构的 I/O 放大"是否是真实且主导的性能问题。

## 1. 方法论：问题驱动，非 prior-art 驱动

按 PZ 的指导和重新校准的标准，本轮**不做 exhaustive prior-art Kill**。先回答经验性问题：

1. 解耦架构（DGAI）的 beam search 中，坐标读（reranking I/O）占端到端时间多少？
2. 与耦合架构（OdinANN）相比，总 I/O 次数和字节量差异多大？
3. per-I/O 软件栈开销（提交/完成路径 CPU 消耗）是否已成为可回收的瓶颈？
4. SSD 设备利用率在两种架构下分别是多少？

数据回答这些问题后，再判断是否存在论文级别的系统设计机会。

## 2. 实验系统

利用已有基础设施，不需要新构建：

| 系统 | 架构类型 | 已有状态 |
|------|---------|---------|
| DGAI | 解耦（拓扑/PQ 与坐标分离） | 已有 SIFT-900K 索引，P0 harness 可用 |
| OdinANN | 耦合（record = neighbors + coordinates） | 已有 SIFT-900K 索引 |

## 3. 测量项

### 3.1 I/O 分解（应用层）

对固定 recall 目标（如 recall@10 ≥ 0.95），beam search 的每次查询记录：

- **拓扑 I/O 次数和字节**：读邻接表/PQ 码的 page reads
- **坐标 I/O 次数和字节**：reranking 阶段读精确坐标的 page reads
- **有效字节比**：实际使用的字节 / 读取的总字节（4KB 对齐可能浪费）
- **I/O 串行深度**：beam search 的跳间依赖产生的最长 I/O 依赖链
- **可并行 I/O 数**：同一跳内可同时发出的 I/O 请求数

### 3.2 设备层指标

- `iostat`：`r/s`、`rkB/s`、`r_await`、`%util`、`avgqu-sz`
- `blktrace`/`bpftrace`：per-I/O issue→complete 延迟分布
- 峰值 IOPS / 实测 IOPS 比（SSD 利用率）
- 峰值带宽 / 实测带宽比

### 3.3 CPU 分解

- `perf stat`：总 cycles、instructions、cache misses
- `perf record`：热点函数（PQ 距离计算 vs 精确距离计算 vs beam 管理 vs I/O 提交/完成）
- 应用层计时：每个阶段（topology read → PQ compute → coordinate read → exact compute → beam update）的墙钟时间

### 3.4 缓存行为

- 拓扑页的跨查询复用率（热页比例）
- 坐标页的复用率（预期很低——每个候选在坐标存储中位置不同）
- page cache hit/miss（如果使用 buffered I/O）

## 4. 实验设计

### 4.1 基础对比

| 配置 | 说明 |
|------|------|
| DGAI query-only | 解耦架构，beam search，固定 recall |
| OdinANN query-only | 耦合架构，beam search，同一数据同一 recall |
| DGAI sweep beam width | beam = {4, 8, 16, 32, 64}，观察 I/O 随 beam 的增长模式 |
| OdinANN sweep beam width | 同上 |

### 4.2 控制变量

- 同一数据集（SIFT-900K）
- 同一查询集（标准 10K queries 取子集）
- 匹配的 recall 水平（通过调 beam width）
- 冷缓存（每次查询前 drop caches）
- 同一 NVMe 设备

### 4.3 可选扩展（第一轮不强制）

- GIST-960（更高维度，可能改变 PQ/精确计算比例）
- warm cache（观察缓存如何影响两种架构）
- 并发查询（1/8/32 threads）

## 5. 预期发现与决策逻辑

### 5.1 如果坐标 I/O 占端到端时间 >30%

解耦架构的 reranking I/O 放大是真实且显著的问题。可以构建论文故事：
- characterization 作为贡献一
- 优化方案（预取、co-location、batch I/O）作为贡献二
- 在耦合和解耦之间寻找更优设计点

### 5.2 如果 per-I/O 软件开销占 I/O 时间 >30%

PZ 的软件栈假设成立。可以合并为一个更大的故事：
- "解耦架构的额外 I/O 次数 × 高 per-I/O 软件开销 = 复合瓶颈"
- 系统设计减少 I/O 次数 + 优化 I/O 路径

### 5.3 如果 CPU 计算（PQ/精确距离）主导

I/O 不是瓶颈，改 I/O 路径或架构没有意义。需要换方向（计算优化或其他问题）。

### 5.4 如果两种架构性能差异 <20%

解耦 vs 耦合的 trade-off 不显著，单独做论文不够。可能需要更大的数据规模（百万/亿级）才能放大差异。

## 6. 不做什么

- 不做 exhaustive prior-art Kill
- 不预设系统设计方案
- 不比较三套 I/O API（pread vs io_uring vs SPDK）
- 不在第一轮做多 NVMe 或分布式实验
- 不把 PageMaxSim 的负结果改名或复活

## 7. 交付物

```
codex/share/decoupled_ann_architecture_characterization_r1_0713.md
```

包含：
1. I/O 分解数据（表 + 图）
2. 设备利用率数据
3. CPU 分解数据
4. 缓存行为数据
5. DGAI vs OdinANN 对比分析
6. 明确结论：坐标 I/O 是否主导、per-I/O 开销是否显著、设计机会在哪里
